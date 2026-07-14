"""Sprint 2 Batch 1 — dynamic unit foundation tests (MASTER_DATA_CONTRACT §2).

Covers:
    * UnitGroup / Unit catalog CRUD + tenant isolation + deactivate
    * ProductUnit mapping rules (one base, base conversion = 1, uniqueness,
      base immutability once stock history exists)
    * ProductBarcodeUnit per-pack barcodes (per-tenant uniqueness + collision
      with the legacy Product.barcode namespace)
    * pos.services.units conversion math — the literal milk (carton = 12,000 ml)
      and chocolate (bag = 5,000 g) examples from the brief
    * zero behavior change: a product with unit mappings still sells exactly
      as before (stock stays denominated in the base unit — R-B)
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import (
    Category, Product, ProductBarcodeUnit, ProductUnit, Sale, StockMovement,
    Unit, UnitGroup,
)
from pos.services import stock_movements as stock_movement_service
from pos.services import units as units_svc
from pos.tests import _grant_default_routing


class _UnitsTestBase(APITestCase):
    """Two-tenant fixture: tenant A fully populated, tenant B for isolation."""

    @classmethod
    def setUpTestData(cls):
        # ── Tenant A ──
        cls.tenant = Tenant.objects.create(name='Units Tenant A')
        cls.manager = User.objects.create_user(
            username='umgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='ucsh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Dairy')
        cls.milk = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Milk', barcode='MILK-1', sku='SKU-MILK',
            price=Decimal('30.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.choco = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Chocolate', barcode='CHOC-1', sku='SKU-CHOC',
            price=Decimal('50.00'), cost=Decimal('35.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

        # Unit substrate for tenant A — all rows, no enums (contract §2.5).
        cls.volume = UnitGroup.objects.create(tenant=cls.tenant, name='Volume')
        cls.mass = UnitGroup.objects.create(tenant=cls.tenant, name='Mass')
        cls.packaging = UnitGroup.objects.create(tenant=cls.tenant, name='Packaging')
        cls.ml = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.volume, name='Milliliter',
            symbol='ml', factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.gram = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.mass, name='Gram',
            symbol='g', factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.carton = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.packaging, name='Carton',
            symbol='ctn', factor_to_base=Decimal('1'), allow_decimal=False,
        )
        cls.bag = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.packaging, name='Bag',
            symbol='bag', factor_to_base=Decimal('1'), allow_decimal=False,
        )

        # ── Tenant B (isolation) ──
        cls.tenant_b = Tenant.objects.create(name='Units Tenant B')
        cls.manager_b = User.objects.create_user(
            username='umgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant_b,
        )
        cls.category_b = Category.objects.create(tenant=cls.tenant_b, name='B-Cat')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, category=cls.category_b,
            name='B-Item', barcode='B-1', sku='SKU-B',
            price=Decimal('10.00'), cost=Decimal('5.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.group_b = UnitGroup.objects.create(tenant=cls.tenant_b, name='Mass')
        cls.gram_b = Unit.objects.create(
            tenant=cls.tenant_b, unit_group=cls.group_b, name='Gram',
            symbol='g', factor_to_base=Decimal('1'),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _map(self, product, unit, conversion, *, is_base=False, **flags):
        return ProductUnit.objects.create(
            tenant=product.tenant, product=product, unit=unit,
            conversion_to_base=Decimal(str(conversion)), is_base=is_base, **flags,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Catalog CRUD — UnitGroup / Unit
# ══════════════════════════════════════════════════════════════════════════════

class UnitCatalogApiTests(_UnitsTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_manager_creates_unit_group(self):
        resp = self.client.post(reverse('unit-group-list'), {'name': 'Count'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            UnitGroup.objects.get(pk=resp.json()['id']).tenant_id, self.tenant.id)

    def test_duplicate_group_name_rejected_within_tenant(self):
        resp = self.client.post(reverse('unit-group-list'), {'name': 'Volume'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.json())

    def test_same_group_name_allowed_for_other_tenant(self):
        # Tenant B already has 'Mass'; tenant A's own 'Mass' exists too — and B
        # can still create names A holds.
        self.client.force_authenticate(user=self.manager_b)
        resp = self.client.post(reverse('unit-group-list'), {'name': 'Volume'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_cashier_cannot_write_but_can_read(self):
        self.client.force_authenticate(user=self.cashier)
        self.assertEqual(
            self.client.post(reverse('unit-group-list'), {'name': 'X'},
                             format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(reverse('unit-group-list')).status_code,
            status.HTTP_200_OK)

    def test_group_list_is_tenant_scoped(self):
        names = {g['name'] for g in self.client.get(
            reverse('unit-group-list')).json()['results']}
        self.assertIn('Volume', names)
        # Tenant B's rows never leak into A's list (B has its own 'Mass';
        # equality of the full set proves no extras).
        self.assertEqual(names, {'Volume', 'Mass', 'Packaging'})

    def test_group_deactivate_endpoint(self):
        resp = self.client.post(
            reverse('unit-group-deactivate', args=[self.volume.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.volume.refresh_from_db()
        self.assertFalse(self.volume.is_active)

    def test_cross_tenant_group_detail_404s(self):
        resp = self.client.get(reverse('unit-group-detail', args=[self.group_b.pk]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_unit_in_group(self):
        resp = self.client.post(reverse('unit-list'), {
            'unit_group': self.mass.pk, 'name': 'Kilogram', 'symbol': 'kg',
            'factor_to_base': '1000', 'allow_decimal': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        unit = Unit.objects.get(pk=resp.json()['id'])
        self.assertEqual(unit.factor_to_base, Decimal('1000.000000'))
        self.assertEqual(unit.tenant_id, self.tenant.id)

    def test_nonpositive_factor_rejected(self):
        for factor in ('0', '-5'):
            resp = self.client.post(reverse('unit-list'), {
                'unit_group': self.mass.pk, 'name': f'Bad{factor}',
                'factor_to_base': factor,
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('factor_to_base', resp.json())

    def test_cross_tenant_unit_group_rejected(self):
        resp = self.client.post(reverse('unit-list'), {
            'unit_group': self.group_b.pk, 'name': 'Sneaky',
            'factor_to_base': '1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_unit_name_in_group_rejected(self):
        resp = self.client.post(reverse('unit-list'), {
            'unit_group': self.mass.pk, 'name': 'Gram', 'factor_to_base': '1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.json())

    def test_unit_list_is_tenant_scoped_and_filterable(self):
        resp = self.client.get(reverse('unit-list'), {'unit_group': self.packaging.pk})
        names = {u['name'] for u in resp.json()['results']}
        self.assertEqual(names, {'Carton', 'Bag'})

    def test_unit_deactivate_endpoint(self):
        resp = self.client.post(reverse('unit-deactivate', args=[self.bag.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.bag.refresh_from_db()
        self.assertFalse(self.bag.is_active)


# ══════════════════════════════════════════════════════════════════════════════
#  ProductUnit mapping rules
# ══════════════════════════════════════════════════════════════════════════════

class ProductUnitApiTests(_UnitsTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _url(self, product):
        return reverse('product-unit-list', kwargs={'product_pk': product.pk})

    def test_create_base_mapping(self):
        resp = self.client.post(self._url(self.milk), {
            'unit': self.ml.pk, 'conversion_to_base': '1', 'is_base': True,
            'is_recipe_unit': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        pu = ProductUnit.objects.get(pk=resp.json()['id'])
        self.assertTrue(pu.is_base)
        self.assertEqual(pu.tenant_id, self.tenant.id)
        self.assertEqual(pu.product_id, self.milk.pk)

    def test_base_mapping_with_conversion_not_1_rejected(self):
        resp = self.client.post(self._url(self.milk), {
            'unit': self.ml.pk, 'conversion_to_base': '2', 'is_base': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('conversion_to_base', resp.json())

    def test_second_base_mapping_rejected(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        resp = self.client.post(self._url(self.milk), {
            'unit': self.carton.pk, 'conversion_to_base': '1', 'is_base': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('is_base', resp.json())

    def test_packaging_mapping_with_product_specific_conversion(self):
        """The milk example: 1 carton = 12,000 ml — a packaging-group unit
        (group factor 1) carries its real meaning per product."""
        self._map(self.milk, self.ml, 1, is_base=True)
        resp = self.client.post(self._url(self.milk), {
            'unit': self.carton.pk, 'conversion_to_base': '12000',
            'is_purchase_unit': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            ProductUnit.objects.get(pk=resp.json()['id']).conversion_to_base,
            Decimal('12000.000000'))

    def test_duplicate_unit_mapping_rejected(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        resp = self.client.post(self._url(self.milk), {
            'unit': self.ml.pk, 'conversion_to_base': '5',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('unit', resp.json())

    def test_cross_tenant_unit_rejected(self):
        resp = self.client.post(self._url(self.milk), {
            'unit': self.gram_b.pk, 'conversion_to_base': '1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_product_404s(self):
        resp = self.client.post(self._url(self.product_b), {
            'unit': self.ml.pk, 'conversion_to_base': '1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonpositive_conversion_rejected(self):
        resp = self.client.post(self._url(self.milk), {
            'unit': self.ml.pk, 'conversion_to_base': '0',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_nonbase_conversion_allowed(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        carton_map = self._map(self.milk, self.carton, 12000)
        resp = self.client.patch(
            reverse('product-unit-detail',
                    kwargs={'product_pk': self.milk.pk, 'pk': carton_map.pk}),
            {'conversion_to_base': '6000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        carton_map.refresh_from_db()
        self.assertEqual(carton_map.conversion_to_base, Decimal('6000.000000'))

    # ── Base immutability once stock history exists ──────────────────────────

    def _base_with_history(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        stock_movement_service.record_stock_in(
            product=self.milk, quantity=Decimal('500'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
        )
        return base

    def test_base_mapping_immutable_once_movements_exist(self):
        base = self._base_with_history()
        url = reverse('product-unit-detail',
                      kwargs={'product_pk': self.milk.pk, 'pk': base.pk})
        # Demoting the base is a re-denomination — rejected.
        resp = self.client.patch(url, {'is_base': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('is_base', resp.json())
        # Changing the unit under the base flag is rejected too.
        resp = self.client.patch(url, {'unit': self.carton.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_harmless_edit_of_base_row_still_allowed_with_history(self):
        base = self._base_with_history()
        resp = self.client.patch(
            reverse('product-unit-detail',
                    kwargs={'product_pk': self.milk.pk, 'pk': base.pk}),
            {'is_recipe_unit': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

    def test_first_base_mapping_allowed_for_legacy_product_with_history(self):
        """Seeding a legacy product's base mapping (what the Batch-4 command
        will do) must stay legal even though movements already exist."""
        stock_movement_service.record_stock_in(
            product=self.choco, quantity=Decimal('100'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
        )
        resp = self.client.post(self._url(self.choco), {
            'unit': self.gram.pk, 'conversion_to_base': '1', 'is_base': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_list_is_product_scoped(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        self._map(self.choco, self.gram, 1, is_base=True)
        rows = self.client.get(self._url(self.milk)).json()['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['unit'], self.ml.pk)


# ══════════════════════════════════════════════════════════════════════════════
#  Conversion service — the literal brief examples
# ══════════════════════════════════════════════════════════════════════════════

class UnitConversionServiceTests(_UnitsTestBase):

    def test_milk_carton_converts_to_ml(self):
        """Milk: base ml; 1 carton = 12,000 ml → 3 cartons = 36,000 ml."""
        self._map(self.milk, self.ml, 1, is_base=True)
        carton_map = self._map(self.milk, self.carton, 12000)
        self.assertEqual(
            units_svc.convert_to_base(
                product=self.milk, qty=3, product_unit=carton_map),
            Decimal('36000.000'))

    def test_chocolate_bag_converts_to_grams(self):
        """Chocolate: base g; 1 bag = 5,000 g → 2 bags = 10,000 g."""
        self._map(self.choco, self.gram, 1, is_base=True)
        bag_map = self._map(self.choco, self.bag, 5000)
        self.assertEqual(
            units_svc.convert_to_base(
                product=self.choco, qty=2, product_unit=bag_map),
            Decimal('10000.000'))

    def test_fractional_quantity_supported(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        carton_map = self._map(self.milk, self.carton, 12000)
        self.assertEqual(
            units_svc.convert_to_base(
                product=self.milk, qty=Decimal('0.5'), product_unit=carton_map),
            Decimal('6000.000'))

    def test_base_unit_is_identity(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        self.assertEqual(
            units_svc.convert_to_base(
                product=self.milk, qty=Decimal('123.456'), product_unit=base),
            Decimal('123.456'))

    def test_result_quantized_to_3dp_half_up(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        # 1000 ml per odd-pack; a third of a pack → 333.333333.. → 333.333
        pack = self._map(self.milk, self.carton, 1000)
        self.assertEqual(
            units_svc.convert_to_base(
                product=self.milk, qty=Decimal('0.333333'), product_unit=pack),
            Decimal('333.333'))

    def test_wrong_products_mapping_rejected(self):
        self._map(self.choco, self.gram, 1, is_base=True)
        bag_map = self._map(self.choco, self.bag, 5000)
        with self.assertRaises(units_svc.UnitConversionError):
            units_svc.convert_to_base(
                product=self.milk, qty=1, product_unit=bag_map)

    def test_inactive_mapping_rejected(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        carton_map = self._map(self.milk, self.carton, 12000, is_active=False)
        with self.assertRaises(units_svc.UnitConversionError):
            units_svc.convert_to_base(
                product=self.milk, qty=1, product_unit=carton_map)

    def test_nonpositive_qty_rejected(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        for qty in (0, -3):
            with self.assertRaises(units_svc.UnitConversionError):
                units_svc.convert_to_base(
                    product=self.milk, qty=qty, product_unit=base)

    def test_get_base_product_unit(self):
        self.assertIsNone(units_svc.get_base_product_unit(self.milk))
        base = self._map(self.milk, self.ml, 1, is_base=True)
        self.assertEqual(units_svc.get_base_product_unit(self.milk).pk, base.pk)


# ══════════════════════════════════════════════════════════════════════════════
#  Per-pack barcodes
# ══════════════════════════════════════════════════════════════════════════════

class ProductBarcodeUnitApiTests(_UnitsTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)
        self.base_map = self._map(self.milk, self.ml, 1, is_base=True)
        self.carton_map = self._map(self.milk, self.carton, 12000)

    def _url(self, product):
        return reverse('product-barcode-list', kwargs={'product_pk': product.pk})

    def test_create_pack_barcode(self):
        resp = self.client.post(self._url(self.milk), {
            'product_unit': self.carton_map.pk, 'barcode': 'CTN-MILK-12',
            'is_default': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        row = ProductBarcodeUnit.objects.get(pk=resp.json()['id'])
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertEqual(row.product_id, self.milk.pk)

    def test_duplicate_barcode_within_tenant_rejected(self):
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant, product=self.milk,
            product_unit=self.carton_map, barcode='CTN-MILK-12')
        resp = self.client.post(self._url(self.milk), {
            'product_unit': self.base_map.pk, 'barcode': 'CTN-MILK-12',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('barcode', resp.json())

    def test_same_barcode_allowed_for_other_tenant(self):
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant, product=self.milk,
            product_unit=self.carton_map, barcode='SHARED-99')
        gram_b_map = ProductUnit.objects.create(
            tenant=self.tenant_b, product=self.product_b, unit=self.gram_b,
            conversion_to_base=Decimal('1'), is_base=True)
        self.client.force_authenticate(user=self.manager_b)
        resp = self.client.post(self._url(self.product_b), {
            'product_unit': gram_b_map.pk, 'barcode': 'SHARED-99',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_collision_with_legacy_product_barcode_rejected(self):
        # 'CHOC-1' is choco's legacy Product.barcode in the same tenant.
        resp = self.client.post(self._url(self.milk), {
            'product_unit': self.carton_map.pk, 'barcode': 'CHOC-1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('barcode', resp.json())

    def test_product_unit_must_belong_to_product(self):
        choco_base = self._map(self.choco, self.gram, 1, is_base=True)
        resp = self.client.post(self._url(self.milk), {
            'product_unit': choco_base.pk, 'barcode': 'X-1',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_unit', resp.json())

    def test_list_is_product_scoped(self):
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant, product=self.milk,
            product_unit=self.carton_map, barcode='CTN-MILK-12')
        rows = self.client.get(self._url(self.choco)).json()['results']
        self.assertEqual(rows, [])


# ══════════════════════════════════════════════════════════════════════════════
#  Zero behavior change — legacy compatibility
# ══════════════════════════════════════════════════════════════════════════════

class UnitsLegacyCompatibilityTests(_UnitsTestBase):
    """Adding unit mappings must not change how an existing product sells:
    stock stays denominated in the base unit (R-B) and the legacy sale flow is
    untouched by this batch."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from accounts.models import Branch, Terminal
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='A-Main')
        cls.terminal = Terminal.objects.create(branch=cls.branch, name='T1', serial='T-1')
        cls.pos_cashier = User.objects.create_user(
            username='ucsh_pos', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        _grant_default_routing(cls.tenant, cls.branch)

    def test_product_with_unit_mappings_still_sells_unchanged(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        self._map(self.milk, self.carton, 12000, is_purchase_unit=True)
        self.milk.stock = Decimal('100')
        self.milk.save(update_fields=['stock'])

        self.client.force_authenticate(user=self.pos_cashier)
        resp = self.client.post(reverse('sale-list'), {
            'items': [{'product': self.milk.pk, 'qty': '2', 'price_each': '30.00'}],
            'method': 'cash', 'amount_paid': '60.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        # Stock deducted in the base denomination exactly as before — the
        # carton mapping changed nothing about the sale flow.
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.stock, Decimal('98.000'))
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 1)
