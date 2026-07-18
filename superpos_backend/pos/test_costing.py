"""Sprint 3 Batch 1/2/3 — InventoryCost / InventoryCostMovement / costing.py.

Batch 1 shipped the data model dark (model tests + seed command tests
below). Batch 2 extracts the AVCO math into `pos/services/costing.py` and
wires it into purchase posting — tests for the service itself live here;
the end-to-end purchase-posting integration test lives in
`pos/tests.py::PurchaseInvoicePostingTests` (reuses that class's existing
fixtures instead of duplicating them). Batch 3 closes the two remaining
uncoordinated cost-write paths (`ProductSerializer` direct writes, CSV
import) and wires `update_cost_from_adjustment` into `stock_adjustment` —
API-level tests for all three live in `ProductCostLockdownApiTests`,
`StockAdjustmentCostApiTests`, and `CsvImportCostRoutingApiTests` below.
"""

from decimal import Decimal
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import Category, InventoryCost, InventoryCostMovement, Product
from pos.services import costing as costing_svc


class InventoryCostModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Costing Tenant A')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='COST-1', sku='SKU-COST-1',
            price=Decimal('600.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

    def test_create_inventory_cost(self):
        row = InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee,
            avg_unit_cost=Decimal('500.0000'),
        )
        self.assertEqual(row.avg_unit_cost, Decimal('500.0000'))

    def test_product_uniqueness_enforced(self):
        """OneToOneField(Product) — a second row for the same product must
        fail at the DB level (D-35: one average per product)."""
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, avg_unit_cost=Decimal('500'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryCost.objects.create(
                    tenant=self.tenant, product=self.coffee, avg_unit_cost=Decimal('600'),
                )

    def test_avg_unit_cost_stores_4dp(self):
        row = InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee,
            avg_unit_cost=Decimal('550.1234'),
        )
        row.refresh_from_db()
        self.assertEqual(row.avg_unit_cost, Decimal('550.1234'))


class InventoryCostMovementModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Costing Tenant B')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='COST-2', sku='SKU-COST-2',
            price=Decimal('600.00'), cost=Decimal('0.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.inv_cost = InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.coffee, avg_unit_cost=Decimal('0'),
        )

    def test_movement_ordering_newest_first(self):
        first = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=self.inv_cost,
            avg_cost_before=Decimal('0'), avg_cost_after=Decimal('500'),
            quantity_received=Decimal('10'), unit_cost_received=Decimal('500'),
            source_document_type='purchase_invoice', source_document_id=1,
        )
        second = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=self.inv_cost,
            avg_cost_before=Decimal('500'), avg_cost_after=Decimal('550'),
            quantity_received=Decimal('10'), unit_cost_received=Decimal('600'),
            source_document_type='purchase_invoice', source_document_id=2,
        )
        rows = list(InventoryCostMovement.objects.filter(product=self.coffee))
        self.assertEqual(rows, [second, first])

    def test_movement_optional_fields_nullable(self):
        """A manual adjustment (Batch 3) won't have qty/unit_cost_received —
        confirm those columns tolerate NULL without a quantity/unit context."""
        row = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=self.inv_cost,
            avg_cost_before=Decimal('550'), avg_cost_after=Decimal('600'),
            source_document_type='manual_cost_adjustment', note='Owner correction',
        )
        self.assertIsNone(row.quantity_received)
        self.assertIsNone(row.unit_cost_received)


class SeedInventoryCostsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Seed Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='SEED-1', sku='SKU-SEED-1',
            price=Decimal('600.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

    def test_dry_run_does_not_write(self):
        call_command('seed_inventory_costs')
        self.assertFalse(InventoryCost.objects.filter(product=self.coffee).exists())

    def test_apply_creates_from_product_cost(self):
        call_command('seed_inventory_costs', apply=True)
        row = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(row.avg_unit_cost, Decimal('500.00'))
        self.assertEqual(
            InventoryCostMovement.objects.filter(product=self.coffee).count(), 0,
            'opening-value seed must not write an audit movement row',
        )

    def test_apply_is_idempotent(self):
        call_command('seed_inventory_costs', apply=True)
        call_command('seed_inventory_costs', apply=True)
        self.assertEqual(InventoryCost.objects.filter(product=self.coffee).count(), 1)

    def test_apply_never_overwrites_existing_row(self):
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, avg_unit_cost=Decimal('999.0000'),
        )
        call_command('seed_inventory_costs', apply=True)
        row = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(row.avg_unit_cost, Decimal('999.0000'))

    def test_tenant_scoping(self):
        other_tenant = Tenant.objects.create(name='Other Seed Tenant')
        other_category = Category.objects.create(tenant=other_tenant, name='Grocery')
        Product.objects.create(
            tenant=other_tenant, category=other_category,
            name='Tea', barcode='SEED-2', sku='SKU-SEED-2',
            price=Decimal('100.00'), cost=Decimal('50.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        call_command('seed_inventory_costs', apply=True, tenant=self.tenant.id)
        self.assertTrue(InventoryCost.objects.filter(product=self.coffee).exists())
        self.assertEqual(InventoryCost.objects.filter(tenant=other_tenant).count(), 0)


# ── Batch 2: pure moving_average_cost() math ────────────────────────────────

class MovingAverageCostFunctionTests(TestCase):
    """Pure-function tests — no DB objects needed beyond what Decimal math
    requires. `moving_average_cost` is deliberately side-effect-free."""

    def test_owner_worked_example(self):
        """The exact numbers from the Business Owner's Sprint 3 request:
        buy 10kg @ 500/kg, then a week later buy 10kg @ 600/kg -> 550/kg."""
        after_first = costing_svc.moving_average_cost(
            Decimal('0'), Decimal('0'), Decimal('10'), Decimal('500'),
        )
        self.assertEqual(after_first, Decimal('500.0000'))

        after_second = costing_svc.moving_average_cost(
            Decimal('10'), after_first, Decimal('10'), Decimal('600'),
        )
        self.assertEqual(after_second, Decimal('550.0000'))

    def test_single_purchase_matches_legacy_assertion(self):
        """Ported from the pre-extraction test — same formula, now 4dp."""
        result = costing_svc.moving_average_cost(
            Decimal('100'), Decimal('6'), Decimal('50'), Decimal('9'),
        )
        self.assertEqual(result, Decimal('7.0000'))

    def test_sequential_compounding_three_purchases(self):
        """Real coverage gap closed: a third purchase must blend correctly
        into an average that already reflects two prior purchases."""
        avg = costing_svc.moving_average_cost(
            Decimal('0'), Decimal('0'), Decimal('5'), Decimal('100'),
        )
        self.assertEqual(avg, Decimal('100.0000'))  # 5 @ 100 -> 100

        avg = costing_svc.moving_average_cost(
            Decimal('5'), avg, Decimal('5'), Decimal('200'),
        )
        self.assertEqual(avg, Decimal('150.0000'))  # +5 @ 200 -> (500+1000)/10=150

        avg = costing_svc.moving_average_cost(
            Decimal('10'), avg, Decimal('20'), Decimal('300'),
        )
        # (10*150 + 20*300) / 30 = (1500 + 6000) / 30 = 250
        self.assertEqual(avg, Decimal('250.0000'))

    def test_negative_stock_fallback_returns_unit_cost(self):
        """Regression: an oversold product (negative stock) must not divide
        by a non-positive denominator — falls back to unit_cost as-is."""
        result = costing_svc.moving_average_cost(
            Decimal('-5'), Decimal('100'), Decimal('3'), Decimal('80'),
        )
        self.assertEqual(result, Decimal('80.0000'))

    def test_zero_denominator_fallback(self):
        result = costing_svc.moving_average_cost(
            Decimal('-10'), Decimal('50'), Decimal('10'), Decimal('42'),
        )
        self.assertEqual(result, Decimal('42.0000'))

    def test_small_quantity_high_precision_matters(self):
        """D-13's stated rationale: 4dp avoids drift on gram-level
        ingredients that a 2dp average would round away."""
        # 3 grams of saffron @ 1500/gram blended into an existing 1g @ 1000.
        result = costing_svc.moving_average_cost(
            Decimal('1'), Decimal('1000'), Decimal('3'), Decimal('1500'),
        )
        # (1*1000 + 3*1500) / 4 = 5500/4 = 1375.0000 exactly — but assert the
        # 4dp quantize doesn't silently truncate a non-terminating case too:
        result2 = costing_svc.moving_average_cost(
            Decimal('1'), Decimal('1000'), Decimal('1'), Decimal('1001'),
        )
        self.assertEqual(result, Decimal('1375.0000'))
        self.assertEqual(result2, Decimal('1000.5000'))  # exact at 4dp


# ── Batch 2: apply_purchase_receipt / update_cost_from_adjustment / reads ──

class CostingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Costing Service Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='CSVC-1', sku='SKU-CSVC-1',
            price=Decimal('700.00'), cost=Decimal('0.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

    def test_apply_purchase_receipt_updates_inventory_cost_and_mirror(self):
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('500'),
            source_document_type='purchase_invoice', source_document_id=1,
        )
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('500.0000'))
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.cost, Decimal('500.00'))  # 2dp mirror synced

        mv = InventoryCostMovement.objects.get(product=self.coffee)
        self.assertEqual(mv.avg_cost_before, Decimal('0.0000'))
        self.assertEqual(mv.avg_cost_after, Decimal('500.0000'))
        self.assertEqual(mv.quantity_received, Decimal('10'))
        self.assertEqual(mv.source_document_type, 'purchase_invoice')
        self.assertEqual(mv.source_document_id, 1)

    def test_apply_purchase_receipt_does_not_apply_stock_itself(self):
        """apply_purchase_receipt only touches InventoryCost/Product.cost —
        the caller (purchase_invoices.post_purchase_invoice) is responsible
        for the actual Product.stock increase via stock_movements."""
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('500'),
            source_document_type='purchase_invoice',
        )
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.stock, Decimal('0'), 'costing.py must not touch Product.stock')

    def test_update_cost_from_adjustment_blends_like_a_purchase(self):
        """Per the Business Owner's confirmed AVCO rule set (matching SAP/
        Oracle/Odoo): a POSITIVE inventory count blends into the average
        exactly like a purchase receipt, just via a different entry point/
        source_document_type. Not wired to any endpoint yet (Batch 3)."""
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('500'),
            source_document_type='purchase_invoice',
        )
        # Simulate the stock effect apply_purchase_receipt intentionally
        # doesn't apply itself (see test above) — this test's blend math
        # needs Product.stock to already reflect the 10 units received.
        self.coffee.stock = Decimal('10')
        self.coffee.save(update_fields=['stock'])

        costing_svc.update_cost_from_adjustment(
            product=self.coffee, qty=Decimal('5'), adjustment_cost=Decimal('800'),
            source_document_type='stock_adjustment', source_document_id=42,
            note='Found 5 extra units during a physical count',
        )
        inv = InventoryCost.objects.get(product=self.coffee)
        # (10*500 + 5*800) / 15 = (5000 + 4000) / 15 = 600.0000
        self.assertEqual(inv.avg_unit_cost, Decimal('600.0000'))

        mv = InventoryCostMovement.objects.get(source_document_type='stock_adjustment')
        self.assertEqual(mv.source_document_id, 42)
        self.assertEqual(mv.note, 'Found 5 extra units during a physical count')

    def test_update_cost_from_adjustment_rejects_non_positive_qty(self):
        """A negative/shrinkage adjustment has no cost to blend in — it must
        consume the current average via get_cost_for_sale, never call this
        function."""
        with self.assertRaises(costing_svc.CostingError):
            costing_svc.update_cost_from_adjustment(
                product=self.coffee, qty=Decimal('-3'), adjustment_cost=Decimal('500'),
            )
        with self.assertRaises(costing_svc.CostingError):
            costing_svc.update_cost_from_adjustment(
                product=self.coffee, qty=Decimal('0'), adjustment_cost=Decimal('500'),
            )

    def test_get_cost_for_sale_never_writes(self):
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('500'),
            source_document_type='purchase_invoice',
        )
        movements_before = InventoryCostMovement.objects.count()
        cost = costing_svc.get_cost_for_sale(self.coffee)
        self.assertEqual(cost, Decimal('500.0000'))
        self.assertEqual(
            InventoryCostMovement.objects.count(), movements_before,
            'get_cost_for_sale must be read-only — it wrote a movement row',
        )

    def test_get_cost_for_return_never_writes(self):
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('500'),
            source_document_type='purchase_invoice',
        )
        movements_before = InventoryCostMovement.objects.count()
        cost = costing_svc.get_cost_for_return(self.coffee)
        self.assertEqual(cost, Decimal('500.0000'))
        self.assertEqual(InventoryCostMovement.objects.count(), movements_before)

    def test_get_cost_for_sale_on_product_with_no_inventory_cost_row_yet(self):
        """Defensive lazy-fetch path: a product that predates Batch 1's seed
        command (or a tenant that skipped it) still gets a correct read,
        opened from its Product.cost mirror."""
        bare_product = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Legacy Product', barcode='CSVC-2', sku='SKU-CSVC-2',
            price=Decimal('50.00'), cost=Decimal('30.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        self.assertFalse(InventoryCost.objects.filter(product=bare_product).exists())
        cost = costing_svc.get_cost_for_sale(bare_product)
        self.assertEqual(cost, Decimal('30.0000'))


# ── Batch 3: close the uncoordinated cost-write paths (API level) ──────────

class _CostingApiTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Batch3 Tenant')
        cls.manager = User.objects.create_user(
            username='b3mgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='b3cash', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='B3-1', sku='SKU-B3-1',
            price=Decimal('700.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('10'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.coffee, avg_unit_cost=Decimal('500.0000'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)


class ProductCostLockdownApiTests(_CostingApiTestBase):
    """`cost` is derived once a product exists — only create() may set it
    freely (opening value); update() must reject it."""

    def test_patch_cost_on_existing_product_rejected(self):
        resp = self.client.patch(
            reverse('product-detail', args=[self.coffee.pk]),
            {'cost': '999.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('cost', resp.json())
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.cost, Decimal('500.00'), 'cost must be unchanged')

    def test_patch_other_fields_still_succeeds(self):
        resp = self.client.patch(
            reverse('product-detail', args=[self.coffee.pk]),
            {'name': 'Coffee Deluxe'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.name, 'Coffee Deluxe')

    def test_create_product_with_cost_initializes_inventory_cost(self):
        resp = self.client.post(reverse('product-list'), {
            'name': 'Tea', 'barcode': 'B3-NEW-1', 'sku': 'SKU-B3-NEW-1',
            'price': '80.00', 'cost': '45.00', 'tax_rate': '0.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        product_id = resp.json()['id']
        inv = InventoryCost.objects.get(product_id=product_id)
        self.assertEqual(inv.avg_unit_cost, Decimal('45.0000'))
        self.assertEqual(
            InventoryCostMovement.objects.filter(product_id=product_id).count(), 0,
            'opening value at create time is not a movement',
        )


class StockAdjustmentCostApiTests(_CostingApiTestBase):
    """POST /inventory/adjust/ — the second AVCO-updating event (a positive
    count with a known cost)."""

    def test_positive_count_with_unit_cost_blends_average(self):
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.coffee.pk, 'actual_qty': '15', 'reason': 'Found extra stock',
            'unit_cost': '800',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        # (10*500 + 5*800) / 15 = 600.0000
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('600.0000'))
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.stock, Decimal('15'))
        self.assertEqual(self.coffee.cost, Decimal('600.00'))

        mv = InventoryCostMovement.objects.get(source_document_type='stock_adjustment')
        self.assertEqual(mv.note, 'Found extra stock')

    def test_positive_count_without_unit_cost_leaves_average_untouched(self):
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.coffee.pk, 'actual_qty': '15', 'reason': 'Found extra, cost unknown',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('500.0000'), 'no unit_cost given — average unchanged')
        self.assertEqual(
            InventoryCostMovement.objects.filter(source_document_type='stock_adjustment').count(), 0,
        )

    def test_shrinkage_ignores_unit_cost_even_if_given(self):
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.coffee.pk, 'actual_qty': '4', 'reason': 'Shrinkage',
            'unit_cost': '800',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('500.0000'), 'shrinkage must never change the average')
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.stock, Decimal('4'))

    def test_cashier_forbidden(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(reverse('inventory-adjust'), {
            'product': self.coffee.pk, 'actual_qty': '15', 'reason': 'x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CsvImportCostRoutingApiTests(_CostingApiTestBase):
    """POST /products/import/ — the third uncoordinated write path,
    now routed through the same audited mechanism as a physical count."""

    CSV_HEADER = 'name,barcode,sku,price,cost,stock,reorder,category_name\n'

    def _import(self, csv_body):
        upload = SimpleUploadedFile(
            'products.csv', (self.CSV_HEADER + csv_body).encode('utf-8'),
            content_type='text/csv',
        )
        return self.client.post(reverse('product-import'), {'file': upload}, format='multipart')

    def test_update_row_raising_stock_blends_cost(self):
        # existing: stock=10 @ avg 500. Row raises stock to 15 @ cost 800.
        resp = self._import(f'Coffee,{self.coffee.barcode},SKU-B3-1,700,800,15,10,\n')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['errors'], [], 'row must not silently fail')
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('600.0000'))
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.stock, 15)
        self.assertEqual(self.coffee.cost, Decimal('600.00'))
        self.assertEqual(
            InventoryCostMovement.objects.filter(source_document_type='csv_import').count(), 1,
        )

    def test_update_row_not_raising_stock_ignores_cost_column(self):
        # stock column equal to current stock (10) — no quantity basis to blend.
        resp = self._import(f'Coffee,{self.coffee.barcode},SKU-B3-1,700,999,10,10,\n')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['errors'], [], 'row must not silently fail')
        inv = InventoryCost.objects.get(product=self.coffee)
        self.assertEqual(inv.avg_unit_cost, Decimal('500.0000'), 'unchanged stock — cost column ignored')
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.cost, Decimal('500.00'))

    def test_create_row_initializes_inventory_cost(self):
        resp = self._import('New Import Item,B3-CSV-NEW,SKU-CSV-NEW,90,55,20,10,\n')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['errors'], [], 'row must not silently fail')
        product = Product.objects.get(tenant=self.tenant, barcode='B3-CSV-NEW')
        inv = InventoryCost.objects.get(product=product)
        self.assertEqual(inv.avg_unit_cost, Decimal('55.0000'))
        self.assertEqual(
            InventoryCostMovement.objects.filter(product=product).count(), 0,
            'opening value at create time is not a movement',
        )
