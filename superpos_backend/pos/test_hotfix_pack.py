"""Sprint 3 Hotfix Pack — regression tests for the five verified issues
found during the pre-Batch-6 architecture/adversarial review, on top of
the already-shipped Sprint 3 Batches 1-5:

    HOTFIX 1 — Product edit regression (frontend + backend contract).
               Backend contract coverage lives here; the frontend fix
               itself is `ProductFormModal.tsx`'s `buildPayload()` (no
               frontend test runner exists in this repo — see
               IMPLEMENTATION_PROGRESS.md's hotfix entry for how it was
               verified with a real end-to-end browser click-through).
    HOTFIX 2 — stock_adjustment lost-update race condition.
    HOTFIX 3 — ADJUSTMENT movement-type direction ambiguity.
    HOTFIX 4 — purchase discount AVCO valuation.
               (Its regression test lives in
               `pos.tests.PurchaseInvoicePostingTests
               .test_purchase_discount_nets_out_of_moving_average_cost` —
               co-located with that class's existing discount/tax fixture
               rather than duplicated here.)
    HOTFIX 5 — mandatory Idempotency-Key on purchase invoice posting.

Out of scope by explicit instruction (do not implement, do not test):
inventory revaluation, negative-inventory settlement, FIFO, GL COGS
postings, purchase/sales return costing, Recipe/BOM, manufacturing,
multi-location costing.
"""

import threading
from decimal import Decimal

from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import (
    Branch, FinancialAccount, PaymentMethod, Supplier, Tenant, User,
)
from pos.models import (
    Category, InventoryCost, Product, StockMovement, Warehouse,
)
from pos.services import stock_movements as stock_movements_svc


# ── HOTFIX 1: PATCH /products/{id}/ contract — the exact fields the ────────
# review named (name, barcode, selling price, category, units) succeed on
# an existing product without touching cost. `ProductCostLockdownApiTests`
# in test_costing.py already covers name; this fills in the rest.

class ProductEditFieldCoverageApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Hotfix1 Tenant')
        cls.manager = User.objects.create_user(
            username='hf1mgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.category_a = Category.objects.create(tenant=cls.tenant, name='Category A')
        cls.category_b = Category.objects.create(tenant=cls.tenant, name='Category B')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category_a,
            name='Widget', barcode='HF1-1', sku='SKU-HF1-1',
            price=Decimal('20.00'), cost=Decimal('10.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('5'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _patch(self, **fields):
        return self.client.patch(
            reverse('product-detail', args=[self.product.pk]), fields, format='json',
        )

    def test_edit_barcode_succeeds_without_touching_cost(self):
        resp = self._patch(barcode='HF1-1-NEW')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, 'HF1-1-NEW')
        self.assertEqual(self.product.cost, Decimal('10.00'))

    def test_edit_selling_price_succeeds_without_touching_cost(self):
        resp = self._patch(price='25.00')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal('25.00'))
        self.assertEqual(self.product.cost, Decimal('10.00'))

    def test_edit_category_succeeds_without_touching_cost(self):
        resp = self._patch(category=self.category_b.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.category_id, self.category_b.pk)
        self.assertEqual(self.product.cost, Decimal('10.00'))

    def test_edit_multiple_fields_together_succeeds_without_touching_cost(self):
        """Mirrors the exact real-world shape of the regression: a client
        editing several unrelated fields in one save must not be blocked
        by cost, since cost is never in the payload for an edit."""
        resp = self._patch(name='Widget Deluxe', barcode='HF1-2', price='30.00')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Widget Deluxe')
        self.assertEqual(self.product.barcode, 'HF1-2')
        self.assertEqual(self.product.price, Decimal('30.00'))
        self.assertEqual(self.product.cost, Decimal('10.00'))

    def test_units_endpoint_is_a_separate_write_surface_unaffected_by_cost_lockdown(self):
        """`ProductUnit` mappings are created via their own nested endpoint,
        entirely independent of ProductSerializer's cost lockdown — confirms
        the 'units' field named in the review is a non-issue by construction,
        not something that happens to also work."""
        from pos.models import Unit, UnitGroup
        group = UnitGroup.objects.create(tenant=self.tenant, name='Count')
        unit = Unit.objects.create(
            tenant=self.tenant, unit_group=group, name='Piece', factor_to_base=Decimal('1'),
        )
        resp = self.client.post(
            reverse('product-unit-list', args=[self.product.pk]),
            {'unit': unit.pk, 'conversion_to_base': '1', 'is_base': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.cost, Decimal('10.00'), 'unrelated write path, cost untouched')


# ── HOTFIX 3: explicit ADJUSTMENT_IN/ADJUSTMENT_OUT direction ──────────────

class StockAdjustmentDirectionApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Hotfix3 Tenant')
        cls.manager = User.objects.create_user(
            username='hf3mgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Direction Widget', barcode='HF3-1', sku='SKU-HF3-1',
            price=Decimal('40.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('10'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_positive_adjustment_stores_adjustment_in_and_counts_as_inflow(self):
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.product.pk, 'actual_qty': '15', 'reason': 'Found extra stock',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        mv = StockMovement.objects.get(product=self.product)
        self.assertEqual(mv.movement_type, StockMovement.MovementType.ADJUSTMENT_IN)
        self.assertEqual(mv.qty, Decimal('5'))
        self.assertEqual(mv.quantity_before, Decimal('10'))
        self.assertEqual(mv.quantity_after, Decimal('15'))

        # Read-side: the API's quantity_in/quantity_out must agree with the
        # write-side classification — this is exactly what was broken
        # before the hotfix (every ADJUSTMENT row, regardless of sign, was
        # reported as an OUTFLOW).
        list_resp = self.client.get(reverse('stock-movement-list'))
        row = next(r for r in list_resp.json()['results'] if r['id'] == mv.id)
        self.assertEqual(row['quantity_in'], '5.000')
        self.assertEqual(row['quantity_out'], '0.000')

        # Statement-derived closing balance must match Product.stock — the
        # concrete "reports/statements/balances must all agree" guarantee
        # the review asked for (closing_quantity anchors its opening value
        # off Product.stock when there's no earlier ledger row, exactly
        # this fixture's situation, so this is the correct reconciliation
        # check — a raw get_product_stock_balance() would only sum this
        # one movement and can't see the fixture's un-ledgered opening 10).
        self.product.refresh_from_db()
        summary = stock_movements_svc.get_product_stock_statement_summary(self.product)
        self.assertEqual(summary['closing_quantity'], self.product.stock)

    def test_negative_adjustment_stores_adjustment_out_and_counts_as_outflow(self):
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.product.pk, 'actual_qty': '4', 'reason': 'Shrinkage',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        mv = StockMovement.objects.get(product=self.product)
        self.assertEqual(mv.movement_type, StockMovement.MovementType.ADJUSTMENT_OUT)
        self.assertEqual(mv.qty, Decimal('-6'))
        self.assertEqual(mv.quantity_before, Decimal('10'))
        self.assertEqual(mv.quantity_after, Decimal('4'))

        list_resp = self.client.get(reverse('stock-movement-list'))
        row = next(r for r in list_resp.json()['results'] if r['id'] == mv.id)
        self.assertEqual(row['quantity_in'], '0.000')
        self.assertEqual(row['quantity_out'], '6.000')

        self.product.refresh_from_db()
        summary = stock_movements_svc.get_product_stock_statement_summary(self.product)
        self.assertEqual(summary['closing_quantity'], self.product.stock)

    def test_statement_summary_net_change_correct_across_both_directions(self):
        """A positive count, then a shrinkage — the derived ledger balance
        (opening + net_change) must land on the true final stock, which
        the pre-hotfix bug would have gotten wrong (it treated the +5 as
        an additional outflow instead of an inflow)."""
        self.client.post(reverse('inventory-adjust'), {
            'product': self.product.pk, 'actual_qty': '15', 'reason': 'Found extra',
        }, format='json')
        self.client.post(reverse('inventory-adjust'), {
            'product': self.product.pk, 'actual_qty': '9', 'reason': 'Shrinkage',
        }, format='json')

        summary = stock_movements_svc.get_product_stock_statement_summary(self.product)
        # opening 10 -> +5 -> -6 -> 9. net_change over the whole window = -1.
        self.assertEqual(summary['net_change'], Decimal('-1'))
        self.assertEqual(summary['closing_quantity'], Decimal('9'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('9'))


# ── HOTFIX 2: lost-update race condition ────────────────────────────────────

class StockAdjustmentConcurrencyTests(TransactionTestCase):
    """Uses TransactionTestCase (not TestCase) + real threads so the two
    requests genuinely run in separate DB transactions against Postgres —
    a plain TestCase wraps everything in one rolled-back transaction and
    can't exercise real row-level locking."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Race Tenant')
        self.manager = User.objects.create_user(
            username='race_mgr', password='pw', role=User.Role.MANAGER, tenant=self.tenant,
        )
        self.category = Category.objects.create(tenant=self.tenant, name='Grocery')
        self.product = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Race Widget', barcode='RACE-1', sku='SKU-RACE-1',
            price=Decimal('50.00'), cost=Decimal('10.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('10'),
        )

    def test_concurrent_adjustments_produce_a_consistent_quantity_chain(self):
        from django.db import connections

        results = {}

        def do_adjust(key, actual_qty):
            try:
                client = APIClient()
                client.force_authenticate(user=self.manager)
                results[key] = client.post(reverse('inventory-adjust'), {
                    'product': self.product.pk, 'actual_qty': actual_qty,
                    'reason': f'concurrent adjustment {key}',
                }, format='json')
            finally:
                # Each thread gets its own DB connection (Django connections
                # are thread-local) — close it explicitly or it dangles past
                # the thread's lifetime and blocks TransactionTestCase's
                # test-database teardown with "being accessed by other users".
                connections.close_all()

        t1 = threading.Thread(target=do_adjust, args=('a', '15'))
        t2 = threading.Thread(target=do_adjust, args=('b', '8'))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results['a'].status_code, status.HTTP_200_OK, results['a'].content)
        self.assertEqual(results['b'].status_code, status.HTTP_200_OK, results['b'].content)

        movements = list(
            StockMovement.objects.filter(product=self.product).order_by('id'),
        )
        self.assertEqual(len(movements), 2)
        # Whichever thread actually landed first (nondeterministic — that's
        # fine, this endpoint's semantics don't promise an ordering), the
        # ledger must be an unbroken chain: the second row's quantity_before
        # must equal the first row's quantity_after. Before the fix, both
        # requests could read the same stale Product.stock and each write a
        # movement claiming quantity_before=10 — a lost update visible right
        # here as a broken chain, even though the final Product.stock value
        # might have accidentally looked plausible.
        self.assertEqual(
            movements[1].quantity_before, movements[0].quantity_after,
            'lost-update race: both adjustments read the same stale previous_stock',
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, movements[1].quantity_after)
        # Statement-derived closing balance must still agree with the
        # cached counter after a concurrent write pair — the same
        # reconciliation invariant the direction fix's tests check under
        # sequential conditions (see the note there on why this uses the
        # statement summary rather than the raw ledger-only balance sum).
        summary = stock_movements_svc.get_product_stock_statement_summary(self.product)
        self.assertEqual(summary['closing_quantity'], self.product.stock)


# ── HOTFIX 5: mandatory Idempotency-Key on purchase invoice posting ────────

class PurchaseInvoiceIdempotencyRequiredApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Hotfix5 Tenant')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Main')
        cls.manager = User.objects.create_user(
            username='hf5mgr', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Idempotency Widget', barcode='HF5-1', sku='SKU-HF5-1',
            price=Decimal('30.00'), cost=Decimal('10.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.supplier = Supplier.objects.create(tenant=cls.tenant, name='Hotfix5 Supply')
        cls.warehouse = Warehouse.objects.create(tenant=cls.tenant, code='HF5-WH', name='HF5 Store')

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _body(self, **over):
        body = {
            'branch': self.branch.id, 'supplier': self.supplier.id,
            'lines': [{
                'product': self.product.id, 'warehouse': self.warehouse.id,
                'qty': '10.000', 'unit_cost': '10.00',
            }],
        }
        body.update(over)
        return body

    def test_missing_idempotency_key_is_rejected(self):
        resp = self.client.post(
            reverse('purchase-invoice-list'), self._body(), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertEqual(resp.json()['error']['code'], 'IDEMPOTENCY_KEY_REQUIRED')
        self.assertEqual(
            StockMovement.objects.filter(product=self.product).count(), 0,
            'a rejected request must not touch stock at all',
        )

    def test_blank_idempotency_key_is_rejected(self):
        resp = self.client.post(
            reverse('purchase-invoice-list'), self._body(), format='json',
            HTTP_IDEMPOTENCY_KEY='   ',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertEqual(resp.json()['error']['code'], 'IDEMPOTENCY_KEY_REQUIRED')

    def test_retry_with_same_key_does_not_duplicate_any_side_effect(self):
        body = self._body()
        r1 = self.client.post(
            reverse('purchase-invoice-list'), body, format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-retry-1',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)

        r2 = self.client.post(
            reverse('purchase-invoice-list'), body, format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-retry-1',
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)
        self.assertEqual(r1.json()['id'], r2.json()['id'], 'retry must replay, not create a new invoice')

        from pos.models import InventoryCostMovement, PurchaseInvoice
        self.assertEqual(PurchaseInvoice.objects.filter(supplier=self.supplier).count(), 1)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 1)
        self.assertEqual(InventoryCostMovement.objects.filter(product=self.product).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('10.000'), 'stock must not double-count on replay')

        from accounts.services import supplier_ap as supplier_ap_service
        self.assertEqual(
            supplier_ap_service.get_supplier_balance(self.supplier), Decimal('100.00'),
            'AP must not double-count on replay',
        )

    def test_different_key_same_payload_creates_a_second_invoice(self):
        """Confirms the mandatory-key check didn't accidentally make ALL
        retries idempotent regardless of key — a genuinely new key is a
        genuinely new (if suspicious) request, same as before this hotfix."""
        body = self._body()
        r1 = self.client.post(
            reverse('purchase-invoice-list'), body, format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-key-a',
        )
        r2 = self.client.post(
            reverse('purchase-invoice-list'), body, format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-key-b',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])

    def test_same_key_different_payload_is_a_conflict(self):
        r1 = self.client.post(
            reverse('purchase-invoice-list'), self._body(), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-conflict',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)

        r2 = self.client.post(
            reverse('purchase-invoice-list'), self._body(paid_amount='50.00'), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-conflict',
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT, r2.content)
        self.assertEqual(r2.json()['error']['code'], 'IDEMPOTENCY_CONFLICT')

    def test_duplicate_supplier_reference_rejected_even_with_a_fresh_key(self):
        """Business-uniqueness safety net: a client bug that mints a new
        Idempotency-Key on every retry (defeating the key-based replay
        protection) is still caught when the supplier's own invoice number
        repeats for the same supplier — without this, two different keys
        would silently create two invoices for what's clearly the same
        real-world document."""
        r1 = self.client.post(
            reverse('purchase-invoice-list'),
            self._body(reference='SUPPLIER-INV-001'), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-ref-key-1',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)

        r2 = self.client.post(
            reverse('purchase-invoice-list'),
            self._body(reference='SUPPLIER-INV-001'), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-ref-key-2',
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT, r2.content)
        self.assertEqual(r2.json()['error']['code'], 'SUPPLIER_REFERENCE_DUPLICATE')

        from pos.models import PurchaseInvoice
        self.assertEqual(
            PurchaseInvoice.objects.filter(supplier=self.supplier, reference='SUPPLIER-INV-001').count(),
            1,
        )

    def test_blank_supplier_reference_never_triggers_the_uniqueness_guard(self):
        """The overwhelming majority of existing invoices have no supplier
        reference at all — the guard must only ever fire when one is
        actually provided, never for blank/omitted values."""
        r1 = self.client.post(
            reverse('purchase-invoice-list'), self._body(), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-blank-ref-1',
        )
        r2 = self.client.post(
            reverse('purchase-invoice-list'), self._body(), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-blank-ref-2',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])

    def test_same_reference_different_supplier_is_allowed(self):
        other_supplier = Supplier.objects.create(tenant=self.tenant, name='Other Supplier')
        r1 = self.client.post(
            reverse('purchase-invoice-list'),
            self._body(reference='SHARED-REF'), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-diffsup-1',
        )
        r2 = self.client.post(
            reverse('purchase-invoice-list'),
            self._body(reference='SHARED-REF', supplier=other_supplier.id), format='json',
            HTTP_IDEMPOTENCY_KEY='hf5-diffsup-2',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)
