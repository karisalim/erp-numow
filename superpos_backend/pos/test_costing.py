"""Sprint 3 Batch 1/2/3/4 — InventoryCost / InventoryCostMovement / costing.py.

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
Batch 4 is read/reporting-only — COGS/gross-profit/margin wired into
`dashboard_summary`, a new `products/{pk}/cost-movements/` audit-trail
endpoint, and `SaleItemSerializer.line_cogs` — tests live in
`DashboardCogsGrossProfitTests`, `ProductCostMovementsApiTests`,
`SaleItemLineCogsApiTests`, and `Batch4NoGlPostingTests` below.
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

from accounts.models import Branch, FinancialAccountMovement, Tenant, User
from pos.models import (
    BranchWarehouse, Category, InventoryCost, InventoryCostMovement, Product,
    Sale, SaleItem, Warehouse, WarehouseStock,
)
from pos.services import costing as costing_svc
from pos.services import stock_movements as stock_svc


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

    def test_product_branch_uniqueness_enforced(self):
        """`(product, branch)` unique constraint (Sprint 5 Batch 1, D-09
        Option B) — a second row for the same `(product, branch)` pair must
        fail at the DB level, including the `branch=None` (tenant-wide)
        pair specifically, via the paired partial-unique index."""
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=None, avg_unit_cost=Decimal('500'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryCost.objects.create(
                    tenant=self.tenant, product=self.coffee, branch=None, avg_unit_cost=Decimal('600'),
                )

    def test_product_can_have_one_row_per_branch(self):
        """A product may have a `branch=None` row AND one row per real
        branch simultaneously — this is the whole point of the Sprint 5
        Batch 1 upgrade."""
        branch_a = Branch.objects.create(tenant=self.tenant, name='Branch A')
        branch_b = Branch.objects.create(tenant=self.tenant, name='Branch B')
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=None, avg_unit_cost=Decimal('500'),
        )
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=branch_a, avg_unit_cost=Decimal('510'),
        )
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=branch_b, avg_unit_cost=Decimal('520'),
        )
        self.assertEqual(InventoryCost.objects.filter(product=self.coffee).count(), 3)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryCost.objects.create(
                    tenant=self.tenant, product=self.coffee, branch=branch_a,
                    avg_unit_cost=Decimal('999'),
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

    def test_update_cost_from_adjustment_on_product_with_no_prior_inventory_cost_row(self):
        """Batch 7 verification (coverage gap review) — every other
        `update_cost_from_adjustment` test calls `apply_purchase_receipt`
        first, which always creates the `InventoryCost` row via its own
        `get_or_create_inventory_cost` call — so the `if inv_cost is None`
        cold-start branch inside `update_cost_from_adjustment` itself
        (lines 258-260) had zero coverage. This is a real production
        scenario: a product counted into stock for the first time via a
        physical count, before it was ever purchased through the system
        (e.g. opening inventory entered as a count, not a purchase invoice)."""
        self.assertFalse(InventoryCost.objects.filter(product=self.coffee).exists())

        costing_svc.update_cost_from_adjustment(
            product=self.coffee, qty=Decimal('20'), adjustment_cost=Decimal('300'),
            source_document_type='stock_adjustment', source_document_id=99,
            note='Opening count, never purchased before',
        )
        inv = InventoryCost.objects.get(product=self.coffee)
        # No prior row, no prior stock: denom=20, (0*0 + 20*300)/20 = 300.0000.
        self.assertEqual(inv.avg_unit_cost, Decimal('300.0000'))
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.cost, Decimal('300.00'))

        mv = InventoryCostMovement.objects.get(source_document_id=99)
        self.assertEqual(mv.avg_cost_before, Decimal('0.0000'))
        self.assertEqual(mv.avg_cost_after, Decimal('300.0000'))

    def test_multi_step_negative_stock_recovery(self):
        """Pre-Batch-5 architecture review coverage gap: the existing
        negative-stock regression only proves the SINGLE-step fallback
        formula. This walks a realistic multi-step sequence — oversell,
        purchase (still net-negative, fallback triggers), oversell again,
        then a purchase large enough to pull stock back positive (real
        blend, not the fallback) — and confirms the average lands on the
        mathematically correct value at each step, not just after the
        first fallback."""
        product = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Negative Stock Widget', barcode='CSVC-NEG-1', sku='SKU-CSVC-NEG-1',
            price=Decimal('300.00'), cost=Decimal('0.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        InventoryCost.objects.create(
            tenant=self.tenant, product=product, avg_unit_cost=Decimal('0.0000'),
        )

        # Step 1: oversold to -5 with no purchase history yet (simulates a
        # sale posting elsewhere — costing.py never touches Product.stock
        # itself, so the test applies the stock effect directly, same as
        # every other test in this file).
        product.stock = Decimal('-5')
        product.save(update_fields=['stock'])
        self.assertEqual(costing_svc.get_cost_for_sale(product), Decimal('0.0000'))

        # Step 2: a purchase arrives, but -5 + 3 = -2 is still <= 0 — the
        # fallback fires (average becomes the purchase's own unit_cost).
        costing_svc.apply_purchase_receipt(
            product=product, qty=Decimal('3'), unit_cost=Decimal('100'),
            source_document_type='purchase_invoice', source_document_id=1,
        )
        inv = InventoryCost.objects.get(product=product)
        self.assertEqual(inv.avg_unit_cost, Decimal('100.0000'))
        product.stock = Decimal('-2')  # -5 + 3
        product.save(update_fields=['stock'])

        # Step 3: oversold further to -6 — average must stay untouched by
        # this pure-consumption event.
        product.stock = Decimal('-6')
        product.save(update_fields=['stock'])
        self.assertEqual(costing_svc.get_cost_for_sale(product), Decimal('100.0000'))

        # Step 4: a bigger purchase finally pulls stock positive again:
        # -6 + 10 = 4 > 0 — this is a REAL weighted blend now, not the
        # fallback, and it must correctly net the negative pre-purchase
        # stock against the positive purchase quantity:
        #   (-6 * 100 + 10 * 150) / 4 = (-600 + 1500) / 4 = 225.0000
        costing_svc.apply_purchase_receipt(
            product=product, qty=Decimal('10'), unit_cost=Decimal('150'),
            source_document_type='purchase_invoice', source_document_id=2,
        )
        inv.refresh_from_db()
        self.assertEqual(inv.avg_unit_cost, Decimal('225.0000'))
        product.stock = Decimal('4')  # -6 + 10
        product.save(update_fields=['stock'])

        # Step 5: a normal sale now reads the recovered, correctly-blended
        # average — not the intermediate fallback value from Step 2.
        self.assertEqual(costing_svc.get_cost_for_sale(product), Decimal('225.0000'))

        # The audit trail recorded both purchases distinctly, in order,
        # with the correct before/after pair at each step.
        movements = list(InventoryCostMovement.objects.filter(product=product).order_by('id'))
        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0].avg_cost_before, Decimal('0.0000'))
        self.assertEqual(movements[0].avg_cost_after, Decimal('100.0000'))
        self.assertEqual(movements[1].avg_cost_before, Decimal('100.0000'))
        self.assertEqual(movements[1].avg_cost_after, Decimal('225.0000'))

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


# ── Sprint 5 Batch 1: branch-scoped AVCO costing (D-09 reopened) ───────────

class GetBranchStockBalanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Branch Stock Balance Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.branch_a = Branch.objects.create(tenant=cls.tenant, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant, name='Branch B')
        cls.wh1 = Warehouse.objects.create(tenant=cls.tenant, code='WH1', name='A Main')
        cls.wh2 = Warehouse.objects.create(tenant=cls.tenant, code='WH2', name='A Kitchen')
        cls.wh_b = Warehouse.objects.create(tenant=cls.tenant, code='WHB', name='B Main')
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_a, warehouse=cls.wh1,
            role=BranchWarehouse.Role.SALES, is_active=True,
        )
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_a, warehouse=cls.wh2,
            role=BranchWarehouse.Role.KITCHEN, is_active=True,
        )
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_b, warehouse=cls.wh_b,
            role=BranchWarehouse.Role.SALES, is_active=True,
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Widget', barcode='GBSB-1', sku='SKU-GBSB-1',
            price=Decimal('10.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )

    def test_zero_for_untouched_branch(self):
        self.assertEqual(
            stock_svc.get_branch_stock_balance(self.product, self.branch_a),
            Decimal('0'),
        )

    def test_sums_across_two_warehouses_same_branch(self):
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=self.wh1,
            quantity=Decimal('30'),
        )
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=self.wh2,
            quantity=Decimal('12'),
        )
        self.assertEqual(
            stock_svc.get_branch_stock_balance(self.product, self.branch_a),
            Decimal('42'),
        )

    def test_excludes_warehouse_linked_to_a_different_branch(self):
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=self.wh1,
            quantity=Decimal('30'),
        )
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=self.wh_b,
            quantity=Decimal('999'),
        )
        self.assertEqual(
            stock_svc.get_branch_stock_balance(self.product, self.branch_a),
            Decimal('30'),
        )

    def test_excludes_inactive_branch_warehouse_link(self):
        wh3 = Warehouse.objects.create(tenant=self.tenant, code='WH3', name='A Damaged')
        BranchWarehouse.objects.create(
            tenant=self.tenant, branch=self.branch_a, warehouse=wh3,
            role=BranchWarehouse.Role.DAMAGED, is_active=False,
        )
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=wh3,
            quantity=Decimal('50'),
        )
        self.assertEqual(
            stock_svc.get_branch_stock_balance(self.product, self.branch_a),
            Decimal('0'),
        )


class BranchScopedCostingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Branch Scoped Costing Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.branch_a = Branch.objects.create(tenant=cls.tenant, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant, name='Branch B')
        cls.wh_a = Warehouse.objects.create(tenant=cls.tenant, code='BWA', name='A Store')
        cls.wh_b = Warehouse.objects.create(tenant=cls.tenant, code='BWB', name='B Store')
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_a, warehouse=cls.wh_a,
            role=BranchWarehouse.Role.SALES, is_active=True,
        )
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_b, warehouse=cls.wh_b,
            role=BranchWarehouse.Role.SALES, is_active=True,
        )
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='BSCS-1', sku='SKU-BSCS-1',
            price=Decimal('700.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )

    def _receive(self, branch, warehouse, qty, unit_cost, source_document_id):
        """Mirrors what post_purchase_invoice does per line: blend the
        branch-scoped average, then apply the stock effect (Product.stock
        + WarehouseStock) — same ordering the real posting service uses."""
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=qty, unit_cost=unit_cost, branch=branch,
            source_document_type='purchase_invoice', source_document_id=source_document_id,
        )
        stock_svc.record_stock_in(
            product=self.coffee, quantity=qty,
            movement_type=stock_svc.StockMovement.MovementType.PURCHASE_IN,
            branch=branch, warehouse=warehouse,
            source_document_type='purchase_invoice', source_document_id=source_document_id,
        )
        self.coffee.refresh_from_db()

    def test_two_branches_blend_independently(self):
        self._receive(self.branch_a, self.wh_a, Decimal('10'), Decimal('500'), 1)
        self._receive(self.branch_b, self.wh_b, Decimal('10'), Decimal('600'), 2)

        inv_a = InventoryCost.objects.get(product=self.coffee, branch=self.branch_a)
        inv_b = InventoryCost.objects.get(product=self.coffee, branch=self.branch_b)
        self.assertEqual(inv_a.avg_unit_cost, Decimal('500.0000'))
        self.assertEqual(inv_b.avg_unit_cost, Decimal('600.0000'))
        # The tenant-wide (branch=None) row is untouched by either purchase.
        self.assertFalse(
            InventoryCost.objects.filter(product=self.coffee, branch=None).exists()
        )

        # A second purchase into branch A blends against branch A's own
        # stock (10 units), not branch B's or the tenant total.
        self._receive(self.branch_a, self.wh_a, Decimal('10'), Decimal('700'), 3)
        inv_a.refresh_from_db()
        # (10*500 + 10*700) / 20 = 600.0000
        self.assertEqual(inv_a.avg_unit_cost, Decimal('600.0000'))
        inv_b.refresh_from_db()
        self.assertEqual(inv_b.avg_unit_cost, Decimal('600.0000'), 'branch B must be unaffected')

    def test_branch_first_purchase_seeds_from_tenant_wide_row_when_present(self):
        # A tenant-wide row already exists (e.g. from before this upgrade,
        # or from a legacy branch=None call site).
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=None,
            avg_unit_cost=Decimal('123.4500'),
        )
        row = costing_svc.get_or_create_inventory_cost(self.coffee, branch=self.branch_a)
        self.assertEqual(row.avg_unit_cost, Decimal('123.4500'))

    def test_branch_first_purchase_seeds_from_product_cost_when_no_tenant_wide_row(self):
        self.coffee.cost = Decimal('42.00')
        self.coffee.save(update_fields=['cost'])
        self.assertFalse(InventoryCost.objects.filter(product=self.coffee, branch=None).exists())
        row = costing_svc.get_or_create_inventory_cost(self.coffee, branch=self.branch_a)
        self.assertEqual(row.avg_unit_cost, Decimal('42.0000'))

    def test_branch_none_path_is_byte_for_byte_unchanged(self):
        """The regression guarantee this whole batch depends on: a caller
        that never passes `branch` gets exactly the pre-Sprint-5 behavior
        (blends against Product.stock, writes the branch=None row)."""
        self.coffee.stock = Decimal('10')
        self.coffee.save(update_fields=['stock'])
        costing_svc.apply_purchase_receipt(
            product=self.coffee, qty=Decimal('10'), unit_cost=Decimal('900'),
            source_document_type='purchase_invoice',
        )
        inv = InventoryCost.objects.get(product=self.coffee, branch=None)
        # (10*0 + 10*900) / 20 = 450.0000 — uses Product.stock (10), not any
        # WarehouseStock/branch balance.
        self.assertEqual(inv.avg_unit_cost, Decimal('450.0000'))

    def test_update_cost_from_adjustment_branch_scoped(self):
        self._receive(self.branch_a, self.wh_a, Decimal('10'), Decimal('500'), 1)
        costing_svc.update_cost_from_adjustment(
            product=self.coffee, qty=Decimal('5'), adjustment_cost=Decimal('800'),
            branch=self.branch_a, source_document_type='stock_adjustment',
        )
        inv_a = InventoryCost.objects.get(product=self.coffee, branch=self.branch_a)
        # (10*500 + 5*800) / 15 = 600.0000 — against branch A's own 10 units.
        self.assertEqual(inv_a.avg_unit_cost, Decimal('600.0000'))

    def test_get_cost_for_sale_branch_scoped(self):
        self._receive(self.branch_a, self.wh_a, Decimal('10'), Decimal('500'), 1)
        self._receive(self.branch_b, self.wh_b, Decimal('10'), Decimal('600'), 2)
        self.assertEqual(
            costing_svc.get_cost_for_sale(self.coffee, branch=self.branch_a),
            Decimal('500.0000'),
        )
        self.assertEqual(
            costing_svc.get_cost_for_sale(self.coffee, branch=self.branch_b),
            Decimal('600.0000'),
        )


class BackfillBranchInventoryCostCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Backfill Branch Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.branch_a = Branch.objects.create(tenant=cls.tenant, name='Branch A', active=True)
        cls.branch_b = Branch.objects.create(tenant=cls.tenant, name='Branch B', active=True)
        cls.inactive_branch = Branch.objects.create(
            tenant=cls.tenant, name='Closed Branch', active=False,
        )
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='BBIC-1', sku='SKU-BBIC-1',
            price=Decimal('700.00'), cost=Decimal('55.00'), stock=Decimal('0'),
        )
        cls.untouched = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='No Base Row Yet', barcode='BBIC-2', sku='SKU-BBIC-2',
            price=Decimal('20.00'), cost=Decimal('5.00'), stock=Decimal('0'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.coffee, branch=None,
            avg_unit_cost=Decimal('55.0000'),
        )
        # `untouched` deliberately has no branch=None row — it must be
        # skipped, not crash the command.

    def test_dry_run_does_not_write(self):
        out = StringIO()
        call_command('backfill_branch_inventory_cost', stdout=out)
        self.assertEqual(
            InventoryCost.objects.filter(product=self.coffee, branch__isnull=False).count(), 0,
        )
        self.assertIn('DRY-RUN', out.getvalue())

    def test_apply_creates_one_row_per_active_branch_only(self):
        out = StringIO()
        call_command('backfill_branch_inventory_cost', '--apply', stdout=out)
        self.assertTrue(
            InventoryCost.objects.filter(product=self.coffee, branch=self.branch_a).exists()
        )
        self.assertTrue(
            InventoryCost.objects.filter(product=self.coffee, branch=self.branch_b).exists()
        )
        self.assertFalse(
            InventoryCost.objects.filter(product=self.coffee, branch=self.inactive_branch).exists(),
            'an inactive branch must not get a backfilled row',
        )
        row_a = InventoryCost.objects.get(product=self.coffee, branch=self.branch_a)
        self.assertEqual(row_a.avg_unit_cost, Decimal('55.0000'))

    def test_apply_skips_product_with_no_tenant_wide_row(self):
        call_command('backfill_branch_inventory_cost', '--apply', stdout=StringIO())
        self.assertFalse(
            InventoryCost.objects.filter(product=self.untouched).exists(),
            'a product with no branch=None row has nothing to seed branch rows from',
        )

    def test_apply_is_idempotent(self):
        call_command('backfill_branch_inventory_cost', '--apply', stdout=StringIO())
        count_after_first = InventoryCost.objects.count()
        call_command('backfill_branch_inventory_cost', '--apply', stdout=StringIO())
        self.assertEqual(InventoryCost.objects.count(), count_after_first)

    def test_apply_never_overwrites_existing_branch_row(self):
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.coffee, branch=self.branch_a,
            avg_unit_cost=Decimal('999.0000'),
        )
        call_command('backfill_branch_inventory_cost', '--apply', stdout=StringIO())
        row_a = InventoryCost.objects.get(product=self.coffee, branch=self.branch_a)
        self.assertEqual(row_a.avg_unit_cost, Decimal('999.0000'))

    def test_tenant_scoping(self):
        other_tenant = Tenant.objects.create(name='Other Backfill Tenant')
        other_branch = Branch.objects.create(tenant=other_tenant, name='Other Branch', active=True)
        other_category = Category.objects.create(tenant=other_tenant, name='Other')
        other_product = Product.objects.create(
            tenant=other_tenant, category=other_category,
            name='Other Product', barcode='BBIC-3', sku='SKU-BBIC-3',
            price=Decimal('10.00'), cost=Decimal('1.00'), stock=Decimal('0'),
        )
        InventoryCost.objects.create(
            tenant=other_tenant, product=other_product, branch=None,
            avg_unit_cost=Decimal('1.0000'),
        )
        call_command('backfill_branch_inventory_cost', f'--tenant={self.tenant.id}', '--apply', stdout=StringIO())
        self.assertFalse(
            InventoryCost.objects.filter(product=other_product, branch=other_branch).exists(),
        )


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


# ── Batch 4: COGS / gross profit / margin reporting (API level) ────────────

class _Batch4ApiTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Batch4 Tenant')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Main')
        cls.manager = User.objects.create_user(
            username='b4mgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='b4cash', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='B4-1', sku='SKU-B4-1',
            price=Decimal('700.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.coffee, avg_unit_cost=Decimal('500.0000'),
        )
        cls.tea = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Tea', barcode='B4-2', sku='SKU-B4-2',
            price=Decimal('200.00'), cost=Decimal('80.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.tea, avg_unit_cost=Decimal('80.0000'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _make_sale(self, items, *, tax_amount=Decimal('0'), sale_status=Sale.Status.COMPLETED):
        """`items`: list of (product, qty, price_each, unit_cost) tuples."""
        subtotal = sum((qty * price_each for _, qty, price_each, _ in items), Decimal('0'))
        total = subtotal + tax_amount
        sale = Sale.objects.create(
            tenant=self.tenant, branch=self.branch, cashier=self.manager,
            subtotal=subtotal, tax_amount=tax_amount, total=total,
            method=Sale.Method.CASH, paid=total, change=Decimal('0'), status=sale_status,
        )
        for product, qty, price_each, unit_cost in items:
            SaleItem.objects.create(
                sale=sale, product=product, product_name=product.name,
                barcode=product.barcode or '', qty=qty, price_each=price_each,
                line_total=qty * price_each, unit_cost=unit_cost,
            )
        return sale


class DashboardCogsGrossProfitTests(_Batch4ApiTestBase):
    def test_kpis_cogs_net_revenue_gross_profit_margin(self):
        # Coffee: 10 @ 700 (cost 500). Tea: 5 @ 200 (cost 80). tax=90.
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00')),
             (self.tea,    Decimal('5'),  Decimal('200.00'), Decimal('80.00'))],
            tax_amount=Decimal('90.00'),
        )
        resp = self.client.get(reverse('dashboard-summary'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        kpis = resp.json()['kpis']

        # subtotal = 10*700 + 5*200 = 8000; total = 8090.
        self.assertEqual(kpis['revenue'], 8090.0, 'existing tax-inclusive revenue key must stay unchanged')
        # net_revenue = total - tax_amount = 8090 - 90 = 8000.
        self.assertEqual(kpis['net_revenue'], 8000.0)
        # cogs = 10*500 + 5*80 = 5000 + 400 = 5400.
        self.assertEqual(kpis['cogs'], 5400.0)
        # gross_profit = 8000 - 5400 = 2600.
        self.assertEqual(kpis['gross_profit'], 2600.0)
        # gross_margin_pct = 2600 / 8000 * 100 = 32.5.
        self.assertEqual(kpis['gross_margin_pct'], 32.5)

    def test_zero_sales_in_window_returns_zeros_not_a_crash(self):
        self._make_sale([(self.coffee, Decimal('1'), Decimal('700.00'), Decimal('500.00'))])
        resp = self.client.get(
            reverse('dashboard-summary'),
            {'start_date': '2020-01-01', 'end_date': '2020-01-02'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        kpis = resp.json()['kpis']
        self.assertEqual(kpis['net_revenue'], 0.0)
        self.assertEqual(kpis['cogs'], 0.0)
        self.assertEqual(kpis['gross_profit'], 0.0)
        self.assertEqual(kpis['gross_margin_pct'], 0.0)

    def test_top_products_per_row_cost_fields(self):
        self._make_sale([
            (self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00')),
            (self.tea,    Decimal('5'),  Decimal('200.00'), Decimal('80.00')),
        ])
        resp = self.client.get(reverse('dashboard-summary'))
        rows = {row['name']: row for row in resp.json()['top_products']}

        coffee_row = rows['Coffee']
        self.assertEqual(coffee_row['revenue'], 7000.0)
        self.assertEqual(coffee_row['cogs'], 5000.0)
        self.assertEqual(coffee_row['gross_profit'], 2000.0)
        self.assertAlmostEqual(coffee_row['gross_margin_pct'], 28.6, places=1)

        tea_row = rows['Tea']
        self.assertEqual(tea_row['revenue'], 1000.0)
        self.assertEqual(tea_row['cogs'], 400.0)
        self.assertEqual(tea_row['gross_profit'], 600.0)
        self.assertEqual(tea_row['gross_margin_pct'], 60.0)

    def test_top_products_zero_revenue_line_does_not_crash(self):
        """A fully-discounted/free line (line_total == 0) must not raise a
        ZeroDivisionError — gross_margin_pct falls back to 0.0."""
        self._make_sale([(self.coffee, Decimal('1'), Decimal('0.00'), Decimal('500.00'))])
        resp = self.client.get(reverse('dashboard-summary'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        row = resp.json()['top_products'][0]
        self.assertEqual(row['revenue'], 0.0)
        self.assertEqual(row['cogs'], 500.0)
        self.assertEqual(row['gross_margin_pct'], 0.0)

    def test_voided_sale_excluded_from_cogs_and_top_products(self):
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
        )
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            sale_status=Sale.Status.VOIDED,
        )
        resp = self.client.get(reverse('dashboard-summary'))
        kpis = resp.json()['kpis']
        # Only the completed Coffee sale should count.
        self.assertEqual(kpis['cogs'], 5000.0)
        self.assertEqual(kpis['net_revenue'], 7000.0)
        names = {row['name'] for row in resp.json()['top_products']}
        self.assertNotIn('Tea', names)


class ProductCostMovementsApiTests(_Batch4ApiTestBase):
    def test_tenant_isolation_returns_empty_not_leaked_data(self):
        other_tenant = Tenant.objects.create(name='Batch4 Other Tenant')
        other_category = Category.objects.create(tenant=other_tenant, name='Grocery')
        other_product = Product.objects.create(
            tenant=other_tenant, category=other_category,
            name='Other Coffee', barcode='B4-OTHER-1', sku='SKU-B4-OTHER-1',
            price=Decimal('700.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        other_inv = InventoryCost.objects.create(
            tenant=other_tenant, product=other_product, avg_unit_cost=Decimal('500.0000'),
        )
        InventoryCostMovement.objects.create(
            tenant=other_tenant, product=other_product, inventory_cost=other_inv,
            avg_cost_before=Decimal('0'), avg_cost_after=Decimal('500'),
            quantity_received=Decimal('10'), unit_cost_received=Decimal('500'),
            source_document_type='purchase_invoice',
        )
        resp = self.client.get(reverse('product-cost-movements', args=[other_product.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['results'], [])

    def test_ordering_newest_first(self):
        inv = InventoryCost.objects.get(product=self.coffee)
        first = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=inv,
            avg_cost_before=Decimal('500'), avg_cost_after=Decimal('550'),
            quantity_received=Decimal('10'), unit_cost_received=Decimal('600'),
            source_document_type='purchase_invoice', source_document_id=1,
        )
        second = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=inv,
            avg_cost_before=Decimal('550'), avg_cost_after=Decimal('600'),
            quantity_received=Decimal('10'), unit_cost_received=Decimal('700'),
            source_document_type='purchase_invoice', source_document_id=2,
        )
        resp = self.client.get(reverse('product-cost-movements', args=[self.coffee.id]))
        ids = [row['id'] for row in resp.json()['results']]
        self.assertEqual(ids, [second.id, first.id])

    def test_pagination(self):
        inv = InventoryCost.objects.get(product=self.coffee)
        for i in range(25):
            InventoryCostMovement.objects.create(
                tenant=self.tenant, product=self.coffee, inventory_cost=inv,
                avg_cost_before=Decimal('500'), avg_cost_after=Decimal('500'),
                quantity_received=Decimal('1'), unit_cost_received=Decimal('500'),
                source_document_type='purchase_invoice', source_document_id=i,
            )
        resp = self.client.get(reverse('product-cost-movements', args=[self.coffee.id]))
        body = resp.json()
        self.assertEqual(body['count'], 25)
        self.assertEqual(len(body['results']), 20, 'StandardPageNumberPagination default page size')
        self.assertIsNotNone(body['next'])

    def test_read_only_write_verbs_rejected(self):
        url = reverse('product-cost-movements', args=[self.coffee.id])
        for verb in ('post', 'patch', 'delete'):
            resp = getattr(self.client, verb)(url, {}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, verb)

    def test_cashier_forbidden(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.get(reverse('product-cost-movements', args=[self.coffee.id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class SaleItemLineCogsApiTests(_Batch4ApiTestBase):
    def test_line_cogs_correct_on_read(self):
        sale = self._make_sale([
            (self.coffee, Decimal('3'), Decimal('700.00'), Decimal('500.00')),
        ])
        resp = self.client.get(reverse('sale-detail-pk', args=[sale.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        item = resp.json()['items'][0]
        self.assertEqual(item['line_cogs'], '1500.00')   # 3 * 500

    def test_line_cogs_zero_when_unit_cost_unset(self):
        """A legacy SaleItem row with unit_cost still at its default 0 must
        render '0.00', not crash."""
        sale = self._make_sale([
            (self.coffee, Decimal('2'), Decimal('700.00'), Decimal('0')),
        ])
        resp = self.client.get(reverse('sale-detail-pk', args=[sale.id]))
        item = resp.json()['items'][0]
        self.assertEqual(item['line_cogs'], '0.00')


class Batch4NoGlPostingTests(_Batch4ApiTestBase):
    """Sprint 3 Batch 4 governance guard (R-L): this batch is read/reporting
    only. Every code path it touches must create ZERO new
    FinancialAccountMovement rows, and the MovementType enum itself must
    not have grown a COGS-shaped member."""

    def test_dashboard_summary_creates_no_financial_movements(self):
        self._make_sale([(self.coffee, Decimal('1'), Decimal('700.00'), Decimal('500.00'))])
        before = FinancialAccountMovement.objects.count()
        resp = self.client.get(reverse('dashboard-summary'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(FinancialAccountMovement.objects.count(), before)

    def test_cost_movements_endpoint_creates_no_financial_movements(self):
        before = FinancialAccountMovement.objects.count()
        resp = self.client.get(reverse('product-cost-movements', args=[self.coffee.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(FinancialAccountMovement.objects.count(), before)

    def test_sale_item_serializer_read_creates_no_financial_movements(self):
        sale = self._make_sale([(self.coffee, Decimal('1'), Decimal('700.00'), Decimal('500.00'))])
        before = FinancialAccountMovement.objects.count()
        resp = self.client.get(reverse('sale-detail-pk', args=[sale.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('line_cogs', resp.json()['items'][0])
        self.assertEqual(FinancialAccountMovement.objects.count(), before)

    def test_no_cogs_shaped_movement_type_added(self):
        values = set(FinancialAccountMovement.MovementType.values)
        self.assertFalse(any('cogs' in v for v in values), values)
