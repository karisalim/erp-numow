"""Sprint 3 Batch 1 — InventoryCost / InventoryCostMovement model tests.

Batch 1 ships the data model dark (no service layer, no purchase-posting
wiring yet — that's Batch 2). These tests cover only what Batch 1 actually
changes: the models themselves, their constraints, and the
`seed_inventory_costs` backfill command.
"""

from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import Tenant, User
from pos.models import Category, InventoryCost, InventoryCostMovement, Product


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
