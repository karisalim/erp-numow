"""Sprint 2 Batch 5a — POS integration (backend only) tests.

Covers:
    * Barcode resolution service — ProductBarcodeUnit -> ProductUnit ->
      Product chain first, legacy Product.barcode fallback second, never a
      direct product lookup that skips the pack-unit chain.
    * `product_scan` endpoint wired to the resolution service.
    * Unit-aware Sale lines (`product_unit` + `entered_qty`): qty converted
      to the base unit via `convert_to_base`, price resolved via
      `resolve_unit_price` (with/without an explicit `price_tier`), the
      audit snapshot (`product_unit`, `entered_qty`, `qty`, `price_each`)
      persisted, and zero change to the legacy (no `product_unit`) shape.
    * Unit-aware PurchaseInvoiceLine: same conversion + audit snapshot,
      `minimum_order_qty` enforcement, moving-average cost computed per
      base unit (never a price/cost scaled by `conversion_to_base` — the
      per-base rate is real total money paid ÷ real base quantity received).
    * `show_on_pos` catalog filter — opt-in, zero default-behavior change.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Supplier, Tenant, Terminal, User
from pos.models import (
    BranchWarehouse, Category, PriceTier, Product, ProductBarcodeUnit,
    ProductUnit, ProductUnitTierPrice, StockMovement, Unit, UnitGroup,
    Warehouse,
)
from pos.services import barcode_resolution
from pos.tests import _grant_default_routing


class _PosIntegrationTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='POS Integration Tenant A')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Main')
        cls.terminal = Terminal.objects.create(branch=cls.branch, name='POS-1', serial='SER-5A')
        cls.manager = User.objects.create_user(
            username='pos5a_mgr', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.cashier = User.objects.create_user(
            username='pos5a_csh', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        _grant_default_routing(cls.tenant, cls.branch)

        cls.category = Category.objects.create(tenant=cls.tenant, name='Dairy')
        cls.milk = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Milk', barcode='MILK-5A', sku='SKU-MILK-5A',
            price=Decimal('30.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('1000000'),
        )

        cls.volume = UnitGroup.objects.create(tenant=cls.tenant, name='Volume')
        cls.packaging = UnitGroup.objects.create(tenant=cls.tenant, name='Packaging')
        cls.ml = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.volume, name='Milliliter',
            symbol='ml', factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.carton_unit = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.packaging, name='Carton',
            symbol='ctn', factor_to_base=Decimal('1'), allow_decimal=False,
        )

        cls.base_pu = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.milk, unit=cls.ml,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.carton_pu = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.milk, unit=cls.carton_unit,
            conversion_to_base=Decimal('12000'),
            is_sale_unit=True, is_purchase_unit=True,
            minimum_order_qty=Decimal('2'),
        )
        cls.pack_barcode = ProductBarcodeUnit.objects.create(
            tenant=cls.tenant, product=cls.milk, product_unit=cls.carton_pu,
            barcode='CTN-MILK-5A-12', is_default=True,
        )

        cls.retail = PriceTier.objects.create(tenant=cls.tenant, name='Retail')
        cls.wholesale = PriceTier.objects.create(tenant=cls.tenant, name='Wholesale')
        cls.carton_wholesale_price = ProductUnitTierPrice.objects.create(
            tenant=cls.tenant, product=cls.milk, product_unit=cls.carton_pu,
            price_tier=cls.wholesale, price=Decimal('500.00'),
        )

        # Second tenant — isolation checks.
        cls.tenant_b = Tenant.objects.create(name='POS Integration Tenant B')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='B-Main')
        cls.category_b = Category.objects.create(tenant=cls.tenant_b, name='B-Cat')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, category=cls.category_b,
            name='B-Item', barcode='B-ITEM-5A', sku='SKU-B-5A',
            price=Decimal('10.00'), cost=Decimal('5.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Barcode resolution service
# ══════════════════════════════════════════════════════════════════════════════

class BarcodeResolutionServiceTests(_PosIntegrationTestBase):

    def test_pack_barcode_resolves_through_product_unit_chain(self):
        resolved = barcode_resolution.resolve_barcode(
            tenant=self.tenant, code='CTN-MILK-5A-12')
        self.assertIsNotNone(resolved)
        product, product_unit = resolved
        self.assertEqual(product.pk, self.milk.pk)
        self.assertEqual(product_unit.pk, self.carton_pu.pk)

    def test_legacy_barcode_falls_back_with_base_unit(self):
        resolved = barcode_resolution.resolve_barcode(tenant=self.tenant, code='MILK-5A')
        self.assertIsNotNone(resolved)
        product, product_unit = resolved
        self.assertEqual(product.pk, self.milk.pk)
        self.assertEqual(product_unit.pk, self.base_pu.pk)

    def test_legacy_barcode_with_no_configured_unit_returns_none_unit(self):
        resolved = barcode_resolution.resolve_barcode(tenant=self.tenant_b, code='B-ITEM-5A')
        self.assertIsNotNone(resolved)
        product, product_unit = resolved
        self.assertEqual(product.pk, self.product_b.pk)
        self.assertIsNone(product_unit)

    def test_unknown_code_resolves_to_none(self):
        self.assertIsNone(
            barcode_resolution.resolve_barcode(tenant=self.tenant, code='NOPE-999'))

    def test_pack_barcode_is_tenant_isolated(self):
        self.assertIsNone(
            barcode_resolution.resolve_barcode(tenant=self.tenant_b, code='CTN-MILK-5A-12'))


class ProductScanEndpointTests(_PosIntegrationTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def test_scan_pack_barcode_returns_product_unit(self):
        resp = self.client.get(reverse('product-scan', args=['CTN-MILK-5A-12']))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['type'], 'barcode')
        self.assertEqual(body['product']['id'], self.milk.pk)
        self.assertEqual(body['product_unit']['id'], self.carton_pu.pk)
        self.assertEqual(body['product_unit']['conversion_to_base'], '12000.000000')

    def test_scan_legacy_barcode_returns_base_product_unit(self):
        resp = self.client.get(reverse('product-scan', args=['MILK-5A']))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['type'], 'barcode')
        self.assertEqual(body['product_unit']['id'], self.base_pu.pk)

    def test_scan_unknown_code_404s(self):
        resp = self.client.get(reverse('product-scan', args=['NOPE-999']))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ══════════════════════════════════════════════════════════════════════════════
#  Unit-aware Sale lines
# ══════════════════════════════════════════════════════════════════════════════

class SaleUnitAwareTests(_PosIntegrationTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _post(self, **over):
        body = {
            'items': [{
                'product': self.milk.pk, 'product_unit': self.carton_pu.pk,
                'entered_qty': '2',
            }],
            'method': 'cash', 'amount_paid': '1000.00',
        }
        body.update(over)
        return self.client.post(reverse('sale-list'), body, format='json')

    def test_unit_aware_line_with_price_tier_resolves_tier_price(self):
        resp = self._post(price_tier=self.wholesale.pk, amount_paid='1000.00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        item = resp.json()['items'][0]
        # 2 cartons at the wholesale tier price (500.00/carton) = 1000.00.
        self.assertEqual(item['price_each'], '500.00')
        self.assertEqual(item['line_total'], '1000.00')
        self.assertEqual(item['qty'], '24000.000')       # base ml, 2 * 12000
        self.assertEqual(item['entered_qty'], '2.000')
        self.assertEqual(item['product_unit'], self.carton_pu.pk)

        self.milk.refresh_from_db()
        self.assertEqual(self.milk.stock, Decimal('976000.000'))  # 1000000 - 24000
        mv = StockMovement.objects.get(
            product=self.milk, movement_type=StockMovement.MovementType.SALE_OUT)
        self.assertEqual(abs(mv.qty), Decimal('24000.000'))

    def test_unit_aware_line_without_price_tier_falls_back_to_product_price(self):
        resp = self._post(amount_paid='60.00')  # no price_tier
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        item = resp.json()['items'][0]
        self.assertEqual(item['price_each'], '30.00')     # Product.price fallback
        self.assertEqual(item['line_total'], '60.00')      # 2 * 30.00
        self.assertEqual(item['qty'], '24000.000')

    def test_missing_entered_qty_rejected(self):
        resp = self._post(items=[{'product': self.milk.pk, 'product_unit': self.carton_pu.pk}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('items[0].entered_qty', resp.json())

    def test_product_unit_belonging_to_other_product_rejected(self):
        other = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Juice', barcode='JUICE-5A', sku='SKU-JUICE-5A',
            price=Decimal('15.00'), cost=Decimal('10.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        resp = self._post(items=[{
            'product': other.pk, 'product_unit': self.carton_pu.pk, 'entered_qty': '1',
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('items[0].product_unit', resp.json())

    def test_legacy_line_shape_unaffected(self):
        """No `product_unit` at all — byte-identical to pre-Batch-5a behavior."""
        resp = self.client.post(reverse('sale-list'), {
            'items': [{'product': self.milk.pk, 'qty': '2', 'price_each': '30.00'}],
            'method': 'cash', 'amount_paid': '60.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        item = resp.json()['items'][0]
        self.assertEqual(item['qty'], '2.000')
        self.assertEqual(item['price_each'], '30.00')
        self.assertEqual(item['line_total'], '60.00')
        self.assertIsNone(item['product_unit'])
        self.assertIsNone(item['entered_qty'])


# ══════════════════════════════════════════════════════════════════════════════
#  Unit-aware PurchaseInvoiceLine
# ══════════════════════════════════════════════════════════════════════════════

class PurchaseInvoiceUnitAwareTests(_PosIntegrationTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier = Supplier.objects.create(tenant=cls.tenant, name='Acme Dairy Supply')
        cls.warehouse = Warehouse.objects.create(tenant=cls.tenant, code='WH-5A', name='Main Store')
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch, warehouse=cls.warehouse,
            role=BranchWarehouse.Role.PURCHASE_RECEIVING,
            is_default=True, is_active=True,
        )
        # Fresh product with zero stock/cost so the moving-average assertion
        # is a clean division (see class docstring reasoning in the tests).
        cls.fresh = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Fresh Milk', barcode='FRESH-MILK-5A', sku='SKU-FRESH-5A',
            price=Decimal('35.00'), cost=Decimal('0.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.fresh_base_pu = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.fresh, unit=cls.ml,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.fresh_carton_pu = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.fresh, unit=cls.carton_unit,
            conversion_to_base=Decimal('12000'), is_purchase_unit=True,
            minimum_order_qty=Decimal('2'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _post(self, **line_over):
        line = {
            'product': self.fresh.pk, 'warehouse': self.warehouse.pk,
            'product_unit': self.fresh_carton_pu.pk, 'entered_qty': '2',
            'unit_cost': '1200.00',
        }
        line.update(line_over)
        return self.client.post(reverse('purchase-invoice-list'), {
            'branch': self.branch.pk, 'supplier': self.supplier.pk,
            'lines': [line],
        }, format='json')

    def test_unit_aware_line_converts_qty_and_updates_moving_average(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        line = resp.json()['lines'][0]
        self.assertEqual(line['qty'], '24000.000')          # 2 cartons * 12000 ml
        self.assertEqual(line['entered_qty'], '2.000')
        self.assertEqual(line['product_unit'], self.fresh_carton_pu.pk)
        self.assertEqual(line['line_total'], '2400.00')     # 2 * 1200.00 (entered_qty basis)

        self.fresh.refresh_from_db()
        self.assertEqual(self.fresh.stock, Decimal('24000.000'))
        # Moving average from a zero base: (0*0 + 24000*0.10) / 24000 = 0.10
        # (0.10 = 1200.00 / 12000, the real cost-per-carton re-denominated to
        # cost-per-ml — never conversion_to_base multiplied into a price).
        self.assertEqual(self.fresh.cost, Decimal('0.10'))

        mv = StockMovement.objects.get(
            product=self.fresh, movement_type=StockMovement.MovementType.PURCHASE_IN)
        self.assertEqual(mv.qty, Decimal('24000.000'))

    def test_below_minimum_order_qty_rejected(self):
        resp = self._post(entered_qty='1')  # minimum_order_qty is 2
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.fresh.refresh_from_db()
        self.assertEqual(self.fresh.stock, Decimal('0.000'))  # rolled back, no partial effect

    def test_legacy_line_shape_unaffected(self):
        resp = self.client.post(reverse('purchase-invoice-list'), {
            'branch': self.branch.pk, 'supplier': self.supplier.pk,
            'lines': [{
                'product': self.fresh.pk, 'warehouse': self.warehouse.pk,
                'qty': '50.000', 'unit_cost': '0.15',
            }],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        line = resp.json()['lines'][0]
        self.assertEqual(line['qty'], '50.000')
        self.assertIsNone(line['product_unit'])
        self.assertIsNone(line['entered_qty'])
        self.assertEqual(line['line_total'], '7.50')  # 50 * 0.15, unchanged legacy math


# ══════════════════════════════════════════════════════════════════════════════
#  show_on_pos catalog filtering (opt-in, zero default-behavior change)
# ══════════════════════════════════════════════════════════════════════════════

class ShowOnPosFilterTests(_PosIntegrationTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.hidden = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Kitchen Only Ingredient', barcode='HIDDEN-5A', sku='SKU-HIDDEN-5A',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'), show_on_pos=False,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def test_default_listing_is_unfiltered(self):
        ids = {p['id'] for p in self.client.get(reverse('product-list')).json()['results']}
        self.assertIn(self.milk.pk, ids)
        self.assertIn(self.hidden.pk, ids)  # still visible — admin screens unaffected

    def test_show_on_pos_true_hides_non_pos_products(self):
        resp = self.client.get(reverse('product-list'), {'show_on_pos': 'true'})
        ids = {p['id'] for p in resp.json()['results']}
        self.assertIn(self.milk.pk, ids)
        self.assertNotIn(self.hidden.pk, ids)

    def test_show_on_pos_false_returns_only_hidden(self):
        resp = self.client.get(reverse('product-list'), {'show_on_pos': 'false'})
        ids = {p['id'] for p in resp.json()['results']}
        self.assertNotIn(self.milk.pk, ids)
        self.assertIn(self.hidden.pk, ids)
