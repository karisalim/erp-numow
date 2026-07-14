"""Sprint 2 Batches 3+4 — product master-data foundation tests.

Batch 3 (Product Type Foundation):
    * `product_type` choices + default, invalid values rejected
    * centralized behavior matrix (services/product_types) — every type is
      classified, flags surface read-only through the API
    * `sales_category` / `inventory_category` links: tenant isolation,
      active-only assignment, SET_NULL wiring
    * `show_on_pos` / `is_discountable` defaults + round-trip
    * reverse barcode-collision guard (Product.barcode vs ProductBarcodeUnit)
    * type-change guard once stock history exists
    * legacy compatibility: pre-Batch-3 payloads still create products, the
      legacy `category` FK and the sale flow behave exactly as before

Batch 4 (Product Unit Integration):
    * multiple ProductUnits per product + conversion compatibility (the
      literal milk / chocolate examples)
    * `seed_product_units` command: dry-run writes nothing, --apply mirrors
      the legacy enum 1:1, pack_qty > 1 seeds a carton mapping, idempotent,
      --tenant scoped, stock quantities never change
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import (
    Category, InventoryCategory, Product, ProductBarcodeUnit, ProductUnit,
    Sale, SalesCategory, StockMovement, Unit, UnitGroup,
)
from pos.services import stock_movements as stock_movement_service
from pos.services import units as units_svc
from pos.services.product_types import (
    PRODUCT_TYPE_BEHAVIOR, ProductType, behavior_flags, get_behavior,
)
from pos.tests import _grant_default_routing


class _ProductFoundationTestBase(APITestCase):
    """Two-tenant fixture: tenant A fully populated, tenant B for isolation."""

    @classmethod
    def setUpTestData(cls):
        # ── Tenant A ──
        cls.tenant = Tenant.objects.create(name='PF Tenant A')
        cls.manager = User.objects.create_user(
            username='pfmgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='pfcsh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant,
        )
        cls.legacy_category = Category.objects.create(tenant=cls.tenant, name='Dairy')
        cls.sales_cat = SalesCategory.objects.create(tenant=cls.tenant, name='Beverages')
        cls.sales_cat_child = SalesCategory.objects.create(
            tenant=cls.tenant, name='Cold Drinks', parent=cls.sales_cat)
        cls.inv_cat = InventoryCategory.objects.create(
            tenant=cls.tenant, name='Chilled Goods')
        cls.inactive_sales_cat = SalesCategory.objects.create(
            tenant=cls.tenant, name='Retired Menu', is_active=False)

        cls.milk = Product.objects.create(
            tenant=cls.tenant, category=cls.legacy_category,
            name='Milk', barcode='PF-MILK-1', sku='PF-SKU-MILK',
            price=Decimal('30.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.choco = Product.objects.create(
            tenant=cls.tenant, category=cls.legacy_category,
            name='Chocolate', barcode='PF-CHOC-1', sku='PF-SKU-CHOC',
            price=Decimal('50.00'), cost=Decimal('35.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

        # Unit substrate (Batch 1 shapes) for the multi-unit tests.
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
        cls.bottle = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.packaging, name='Bottle',
            symbol='btl', factor_to_base=Decimal('1'), allow_decimal=False,
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
        cls.tenant_b = Tenant.objects.create(name='PF Tenant B')
        cls.manager_b = User.objects.create_user(
            username='pfmgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant_b,
        )
        cls.sales_cat_b = SalesCategory.objects.create(
            tenant=cls.tenant_b, name='B Menu')
        cls.inv_cat_b = InventoryCategory.objects.create(
            tenant=cls.tenant_b, name='B Stock')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, name='B-Item', barcode='PF-B-1', sku='PF-SKU-B',
            price=Decimal('10.00'), cost=Decimal('5.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _payload(self, **overrides):
        """A minimal valid product payload in the pre-Batch-3 (legacy) shape."""
        data = {
            'name': 'New Product', 'barcode': 'PF-NEW-1', 'sku': 'PF-SKU-NEW',
            'price': '12.00', 'cost': '8.00', 'tax_rate': '0.00',
        }
        data.update(overrides)
        return data

    def _map(self, product, unit, conversion, *, is_base=False, **flags):
        return ProductUnit.objects.create(
            tenant=product.tenant, product=product, unit=unit,
            conversion_to_base=Decimal(str(conversion)), is_base=is_base, **flags,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Behavior matrix (service layer)
# ══════════════════════════════════════════════════════════════════════════════

class ProductTypeBehaviorMatrixTests(APITestCase):
    """The centralized matrix is the single authority for type behavior."""

    def test_every_declared_type_is_classified(self):
        self.assertEqual(
            set(PRODUCT_TYPE_BEHAVIOR.keys()), set(ProductType.values))

    def test_unknown_type_raises_loudly(self):
        with self.assertRaises(ValueError):
            get_behavior('hologram')

    def test_stock_item_full_inventory_behavior(self):
        b = get_behavior(ProductType.STOCK_ITEM)
        self.assertTrue(b.can_sell and b.can_purchase and b.track_inventory
                        and b.affects_stock and b.requires_cost)
        self.assertFalse(b.can_have_recipe)

    def test_ingredient_purchasable_not_sellable(self):
        b = get_behavior(ProductType.INGREDIENT)
        self.assertFalse(b.can_sell)
        self.assertTrue(b.can_purchase and b.track_inventory and b.affects_stock)

    def test_prep_item_produced_in_house(self):
        b = get_behavior(ProductType.PREP_ITEM)
        self.assertFalse(b.can_sell or b.can_purchase)
        self.assertTrue(b.track_inventory and b.can_have_recipe)

    def test_recipe_product_sellable_without_own_stock(self):
        b = get_behavior(ProductType.RECIPE_PRODUCT)
        self.assertTrue(b.can_sell and b.can_have_recipe)
        self.assertFalse(b.can_purchase or b.track_inventory
                         or b.affects_stock or b.requires_cost)

    def test_resale_behaves_like_stock_item(self):
        self.assertEqual(
            get_behavior(ProductType.RESALE), get_behavior(ProductType.STOCK_ITEM))

    def test_packaging_counted_never_sold(self):
        b = get_behavior(ProductType.PACKAGING)
        self.assertFalse(b.can_sell)
        self.assertTrue(b.can_purchase and b.track_inventory and b.affects_stock)

    def test_service_no_inventory_existence(self):
        b = get_behavior(ProductType.SERVICE)
        self.assertTrue(b.can_sell)
        self.assertFalse(b.can_purchase or b.track_inventory
                         or b.affects_stock or b.requires_cost or b.can_have_recipe)

    def test_bundle_sellable_components_move_stock(self):
        b = get_behavior(ProductType.BUNDLE)
        self.assertTrue(b.can_sell and b.can_have_recipe)
        self.assertFalse(b.can_purchase or b.track_inventory or b.affects_stock)

    def test_fixed_asset_purchase_only(self):
        b = get_behavior(ProductType.FIXED_ASSET)
        self.assertTrue(b.can_purchase and b.requires_cost)
        self.assertFalse(b.can_sell or b.track_inventory or b.affects_stock)

    def test_behavior_flags_dict_shape(self):
        flags = behavior_flags(ProductType.STOCK_ITEM)
        self.assertEqual(
            set(flags.keys()),
            {'can_sell', 'can_purchase', 'track_inventory', 'affects_stock',
             'requires_cost', 'can_have_recipe'},
        )

    def test_model_property_delegates_to_matrix(self):
        product = Product(product_type=ProductType.SERVICE)
        self.assertEqual(product.type_behavior, get_behavior(ProductType.SERVICE))


# ══════════════════════════════════════════════════════════════════════════════
#  Product API — product_type + behavior flags
# ══════════════════════════════════════════════════════════════════════════════

class ProductTypeApiTests(_ProductFoundationTestBase):

    def test_default_type_is_stock_item(self):
        resp = self.client.post(reverse('product-list'), self._payload(),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['product_type'], 'stock_item')
        self.assertEqual(body['product_type_display'], 'Stock item')

    def test_each_type_round_trips_with_matching_flags(self):
        for i, value in enumerate(ProductType.values):
            resp = self.client.post(reverse('product-list'), self._payload(
                name=f'Typed {value}', barcode=f'PF-T-{i}', sku=f'PF-SKU-T-{i}',
                product_type=value,
            ), format='json')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
            body = resp.json()
            self.assertEqual(body['product_type'], value)
            self.assertEqual(body['behavior'], behavior_flags(value))

    def test_invalid_type_rejected(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            product_type='hologram'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_type', resp.json())

    def test_behavior_is_read_only_calculated(self):
        # A spoofed `behavior` payload key is ignored, never stored.
        resp = self.client.post(reverse('product-list'), self._payload(
            product_type='service',
            behavior={'can_sell': False, 'track_inventory': True},
        ), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['behavior'], behavior_flags('service'))

    def test_type_change_allowed_without_stock_history(self):
        resp = self.client.patch(
            reverse('product-detail', args=[self.milk.pk]),
            {'product_type': 'service'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.product_type, 'service')

    def test_type_change_blocked_once_stock_history_exists(self):
        stock_movement_service.record_stock_in(
            product=self.milk, quantity=Decimal('10'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
        )
        resp = self.client.patch(
            reverse('product-detail', args=[self.milk.pk]),
            {'product_type': 'service'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_type', resp.json())
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.product_type, 'stock_item')

    def test_type_change_between_inventory_types_allowed_with_history(self):
        stock_movement_service.record_stock_in(
            product=self.milk, quantity=Decimal('10'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
        )
        resp = self.client.patch(
            reverse('product-detail', args=[self.milk.pk]),
            {'product_type': 'resale'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)


# ══════════════════════════════════════════════════════════════════════════════
#  Product API — tree category links
# ══════════════════════════════════════════════════════════════════════════════

class ProductTreeCategoryApiTests(_ProductFoundationTestBase):

    def test_assign_both_tree_categories(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            sales_category=self.sales_cat_child.pk,
            inventory_category=self.inv_cat.pk,
        ), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['sales_category'], self.sales_cat_child.pk)
        self.assertEqual(body['sales_category_name'], 'Cold Drinks')
        self.assertEqual(body['inventory_category'], self.inv_cat.pk)
        self.assertEqual(body['inventory_category_name'], 'Chilled Goods')

    def test_tree_categories_default_null(self):
        resp = self.client.post(reverse('product-list'), self._payload(),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertIsNone(body['sales_category'])
        self.assertIsNone(body['inventory_category'])

    def test_cross_tenant_sales_category_rejected(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            sales_category=self.sales_cat_b.pk), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sales_category', resp.json())

    def test_cross_tenant_inventory_category_rejected(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            inventory_category=self.inv_cat_b.pk), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('inventory_category', resp.json())

    def test_inactive_sales_category_rejected(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            sales_category=self.inactive_sales_cat.pk), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sales_category', resp.json())

    def test_clearing_category_via_patch(self):
        self.milk.sales_category = self.sales_cat
        self.milk.save(update_fields=['sales_category'])
        resp = self.client.patch(
            reverse('product-detail', args=[self.milk.pk]),
            {'sales_category': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.milk.refresh_from_db()
        self.assertIsNone(self.milk.sales_category)

    def test_category_delete_sets_null_keeps_product(self):
        product = Product.objects.create(
            tenant=self.tenant, name='Linked', barcode='PF-LNK-1',
            sku='PF-SKU-LNK', price=Decimal('5.00'), cost=Decimal('2.00'),
            sales_category=self.sales_cat_child, inventory_category=self.inv_cat,
        )
        self.sales_cat_child.delete()
        product.refresh_from_db()
        self.assertIsNone(product.sales_category)
        self.assertEqual(product.inventory_category, self.inv_cat)

    def test_legacy_category_untouched_by_tree_links(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            category=self.legacy_category.pk,
            sales_category=self.sales_cat.pk,
        ), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['category'], self.legacy_category.pk)
        self.assertEqual(body['category_name'], 'Dairy')


# ══════════════════════════════════════════════════════════════════════════════
#  Product API — POS visibility / discountable flags + barcode guard
# ══════════════════════════════════════════════════════════════════════════════

class ProductFlagsAndBarcodeGuardTests(_ProductFoundationTestBase):

    def test_visibility_flags_default_true(self):
        resp = self.client.post(reverse('product-list'), self._payload(),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertTrue(body['show_on_pos'])
        self.assertTrue(body['is_discountable'])

    def test_visibility_flags_settable(self):
        resp = self.client.post(reverse('product-list'), self._payload(
            show_on_pos=False, is_discountable=False), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertFalse(body['show_on_pos'])
        self.assertFalse(body['is_discountable'])

    def test_existing_products_backfilled_visible(self):
        # Rows created before Batch 3 (fixture rows) read as visible +
        # discountable — the migration hides nothing.
        self.milk.refresh_from_db()
        self.assertTrue(self.milk.show_on_pos)
        self.assertTrue(self.milk.is_discountable)

    def test_product_barcode_may_not_collide_with_pack_barcode(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        carton_map = self._map(self.milk, self.carton, 12000)
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant, product=self.milk,
            product_unit=carton_map, barcode='CTN-MILK-12',
        )
        resp = self.client.post(reverse('product-list'), self._payload(
            barcode='CTN-MILK-12'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('barcode', resp.json())

        # …and via update of an existing product too.
        resp = self.client.patch(
            reverse('product-detail', args=[self.choco.pk]),
            {'barcode': 'CTN-MILK-12'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('barcode', resp.json())

    def test_pack_barcode_in_other_tenant_does_not_block(self):
        base_b = ProductUnit.objects.create(
            tenant=self.tenant_b, product=self.product_b,
            unit=Unit.objects.create(
                tenant=self.tenant_b,
                unit_group=UnitGroup.objects.create(
                    tenant=self.tenant_b, name='Count'),
                name='Piece', factor_to_base=Decimal('1')),
            conversion_to_base=Decimal('1'), is_base=True,
        )
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant_b, product=self.product_b,
            product_unit=base_b, barcode='SHARED-CODE',
        )
        resp = self.client.post(reverse('product-list'), self._payload(
            barcode='SHARED-CODE'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_patch_without_barcode_unaffected_by_guard(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        ProductBarcodeUnit.objects.create(
            tenant=self.tenant, product=self.milk,
            product_unit=base, barcode=self.choco.barcode,
        )  # pre-existing ORM-level collision (Batch 4 audit reports these)
        resp = self.client.patch(
            reverse('product-detail', args=[self.choco.pk]),
            {'name': 'Chocolate Deluxe'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)


# ══════════════════════════════════════════════════════════════════════════════
#  Multiple ProductUnits + conversion compatibility (Batch 4 shapes)
# ══════════════════════════════════════════════════════════════════════════════

class MultipleProductUnitsTests(_ProductFoundationTestBase):

    def test_milk_three_units_convert_to_base(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        bottle = self._map(self.milk, self.bottle, 1000, is_sale_unit=True)
        carton = self._map(self.milk, self.carton, 12000, is_purchase_unit=True)

        self.assertEqual(units_svc.get_base_product_unit(self.milk), base)
        self.assertEqual(
            units_svc.convert_to_base(product=self.milk, qty=2, product_unit=bottle),
            Decimal('2000.000'))
        self.assertEqual(
            units_svc.convert_to_base(product=self.milk, qty=3, product_unit=carton),
            Decimal('36000.000'))

    def test_chocolate_bag_converts_to_grams(self):
        self._map(self.choco, self.gram, 1, is_base=True)
        bag = self._map(self.choco, self.bag, 5000, is_sale_unit=True)
        self.assertEqual(
            units_svc.convert_to_base(product=self.choco, qty=Decimal('0.5'),
                                      product_unit=bag),
            Decimal('2500.000'))

    def test_unit_of_other_product_rejected_for_conversion(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        bag = self._map(self.choco, self.bag, 5000)
        with self.assertRaises(units_svc.UnitConversionError):
            units_svc.convert_to_base(product=self.milk, qty=1, product_unit=bag)

    def test_barcode_unit_must_belong_to_product(self):
        self._map(self.milk, self.ml, 1, is_base=True)
        choco_base = self._map(self.choco, self.gram, 1, is_base=True)
        resp = self.client.post(
            reverse('product-barcode-list', args=[self.milk.pk]),
            {'product_unit': choco_base.pk, 'barcode': 'PF-X-1'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_unit', resp.json())

    def test_pack_barcode_rejects_legacy_product_barcode(self):
        base = self._map(self.milk, self.ml, 1, is_base=True)
        resp = self.client.post(
            reverse('product-barcode-list', args=[self.milk.pk]),
            {'product_unit': base.pk, 'barcode': self.choco.barcode},
            format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('barcode', resp.json())


# ══════════════════════════════════════════════════════════════════════════════
#  seed_product_units management command
# ══════════════════════════════════════════════════════════════════════════════

class SeedProductUnitsCommandTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Seed Tenant A')
        cls.piece_product = Product.objects.create(
            tenant=cls.tenant, name='Soda Can', barcode='SD-1', sku='SKU-SD',
            price=Decimal('5.00'), cost=Decimal('3.00'),
            unit=Product.Unit.PIECE, pack_qty=Decimal('24'),
            stock=Decimal('120'),
        )
        cls.kg_product = Product.objects.create(
            tenant=cls.tenant, name='Cheese', barcode='CH-1', sku='SKU-CH',
            price=Decimal('90.00'), cost=Decimal('60.00'),
            unit=Product.Unit.KG, pack_qty=Decimal('1'),
            stock=Decimal('14.5'), weighted=True,
        )
        cls.carton_product = Product.objects.create(
            tenant=cls.tenant, name='Water Case', barcode='WC-1', sku='SKU-WC',
            price=Decimal('40.00'), cost=Decimal('28.00'),
            unit=Product.Unit.CARTON, pack_qty=Decimal('12'),
            stock=Decimal('7'),
        )

        cls.tenant_b = Tenant.objects.create(name='Seed Tenant B')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, name='B Juice', barcode='BJ-1', sku='SKU-BJ',
            price=Decimal('8.00'), cost=Decimal('4.00'),
            unit=Product.Unit.LITER, stock=Decimal('30'),
        )

    def _run(self, *args):
        out = StringIO()
        call_command('seed_product_units', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_is_default_and_writes_nothing(self):
        output = self._run()
        self.assertIn('DRY-RUN', output)
        self.assertEqual(ProductUnit.objects.count(), 0)
        self.assertEqual(Unit.objects.count(), 0)
        self.assertEqual(UnitGroup.objects.count(), 0)

    def test_apply_mirrors_legacy_enum_one_to_one(self):
        self._run('--apply')

        base = units_svc.get_base_product_unit(self.piece_product)
        self.assertIsNotNone(base)
        self.assertEqual(base.unit.name, 'Piece')
        self.assertEqual(base.conversion_to_base, Decimal('1'))
        self.assertTrue(base.is_sale_unit and base.is_purchase_unit)

        # kg stays kg — no re-denomination to grams.
        kg_base = units_svc.get_base_product_unit(self.kg_product)
        self.assertEqual(kg_base.unit.name, 'Kilogram')
        self.assertEqual(kg_base.conversion_to_base, Decimal('1'))

        carton_base = units_svc.get_base_product_unit(self.carton_product)
        self.assertEqual(carton_base.unit.name, 'Carton')

        liter_base = units_svc.get_base_product_unit(self.product_b)
        self.assertEqual(liter_base.unit.name, 'Liter')
        self.assertEqual(liter_base.tenant_id, self.tenant_b.id)

    def test_apply_seeds_pack_mapping_from_pack_qty(self):
        self._run('--apply')
        pack = ProductUnit.objects.get(
            product=self.piece_product, unit__name='Carton')
        self.assertEqual(pack.conversion_to_base, Decimal('24'))
        self.assertFalse(pack.is_base)
        self.assertTrue(pack.is_sale_unit)

    def test_carton_based_product_gets_no_pack_mapping(self):
        self._run('--apply')
        # Base carton mapping only — pack_qty=12 describes inner pieces and
        # must not become a second carton row.
        rows = ProductUnit.objects.filter(product=self.carton_product)
        self.assertEqual(rows.count(), 1)
        self.assertTrue(rows.get().is_base)

    def test_apply_is_idempotent(self):
        self._run('--apply')
        first = {
            'product_units': ProductUnit.objects.count(),
            'units': Unit.objects.count(),
            'groups': UnitGroup.objects.count(),
        }
        output = self._run('--apply')
        self.assertEqual(ProductUnit.objects.count(), first['product_units'])
        self.assertEqual(Unit.objects.count(), first['units'])
        self.assertEqual(UnitGroup.objects.count(), first['groups'])
        self.assertIn('0 base mapping(s) created', output)

    def test_tenant_scoping(self):
        self._run('--apply', f'--tenant={self.tenant.id}')
        self.assertTrue(
            ProductUnit.objects.filter(tenant=self.tenant, is_base=True).exists())
        self.assertFalse(
            ProductUnit.objects.filter(tenant=self.tenant_b).exists())

    def test_existing_base_mapping_is_respected(self):
        group = UnitGroup.objects.create(tenant=self.tenant, name='Custom')
        cup = Unit.objects.create(
            tenant=self.tenant, unit_group=group, name='Cup',
            factor_to_base=Decimal('1'))
        manual_base = ProductUnit.objects.create(
            tenant=self.tenant, product=self.piece_product, unit=cup,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        self._run('--apply')
        # Still exactly one base — the manual configuration wins.
        self.assertEqual(
            units_svc.get_base_product_unit(self.piece_product), manual_base)

    def test_stock_quantities_never_change(self):
        before = {
            p.pk: p.stock
            for p in Product.objects.all()
        }
        self._run('--apply')
        for product in Product.objects.all():
            self.assertEqual(product.stock, before[product.pk])
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_unknown_tenant_id_errors(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._run('--tenant=999999')


# ══════════════════════════════════════════════════════════════════════════════
#  Legacy compatibility
# ══════════════════════════════════════════════════════════════════════════════

class LegacyCompatibilityTests(_ProductFoundationTestBase):
    """Pre-Batch-3 payloads and flows keep working byte-for-byte."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from accounts.models import Branch, Terminal
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='PF-Main')
        cls.terminal = Terminal.objects.create(
            branch=cls.branch, name='T1', serial='PF-T-1')
        cls.pos_cashier = User.objects.create_user(
            username='pfcsh_pos', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        _grant_default_routing(cls.tenant, cls.branch)

    def test_legacy_payload_still_creates_product(self):
        resp = self.client.post(reverse('product-list'), {
            'name': 'Legacy Shape', 'barcode': 'PF-LEG-1', 'sku': 'PF-SKU-LEG',
            'price': '9.00', 'cost': '6.00', 'tax_rate': '0.10',
            'category': self.legacy_category.pk,
            'unit': 'kg', 'pack_qty': '1', 'weighted': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        # New fields materialize with safe defaults.
        self.assertEqual(body['product_type'], 'stock_item')
        self.assertTrue(body['show_on_pos'])
        self.assertTrue(body['is_discountable'])
        self.assertIsNone(body['sales_category'])
        # Legacy fields keep their exact shape.
        self.assertEqual(body['unit'], 'kg')
        self.assertEqual(body['category_name'], 'Dairy')

    def test_response_keeps_every_legacy_key(self):
        resp = self.client.get(reverse('product-detail', args=[self.milk.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        for key in ['id', 'barcode', 'sku', 'name', 'category', 'category_name',
                    'price', 'cost', 'tax_rate', 'stock', 'reorder', 'color',
                    'weighted', 'unit', 'unit_display', 'pack_qty', 'plu',
                    'active', 'margin', 'created_at', 'updated_at']:
            self.assertIn(key, body)

    def test_sale_flow_untouched_by_new_classification(self):
        self.milk.product_type = 'service'  # even a non-stock classification…
        self.milk.show_on_pos = False
        self.milk.stock = Decimal('100')
        self.milk.save(update_fields=['product_type', 'show_on_pos', 'stock'])

        self.client.force_authenticate(user=self.pos_cashier)
        resp = self.client.post(reverse('sale-list'), {
            'items': [{'product': self.milk.pk, 'qty': '2', 'price_each': '30.00'}],
            'method': 'cash', 'amount_paid': '60.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        # …still deducts stock exactly as before: classification only, no
        # behavior is wired to the flags in this batch.
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.stock, Decimal('98.000'))
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 1)

    def test_seeded_product_sells_unchanged(self):
        call_command('seed_product_units', '--apply',
                     f'--tenant={self.tenant.id}', stdout=StringIO())
        self.milk.stock = Decimal('50')
        self.milk.save(update_fields=['stock'])

        self.client.force_authenticate(user=self.pos_cashier)
        resp = self.client.post(reverse('sale-list'), {
            'items': [{'product': self.milk.pk, 'qty': '3', 'price_each': '30.00'}],
            'method': 'cash', 'amount_paid': '90.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.stock, Decimal('47.000'))
