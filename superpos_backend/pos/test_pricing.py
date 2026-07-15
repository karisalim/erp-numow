"""Sprint 2 Batch 4 remainder — unit-aware pricing foundation tests.

Covers:
    * PriceTier catalog CRUD + tenant isolation + deactivate
    * ProductUnitTierPrice CRUD nested under /products/{pk}/units/{pk}/tier-prices/
      — uniqueness is (product_unit, price_tier), NOT product_unit alone
    * ProductUnit.minimum_order_qty validation (nullable, > 0 when set)
    * pos.services.pricing.resolve_unit_price — tier price found, tier given
      but no matching row (fallback to Product.price), no tier at all
      (fallback), and an explicit regression guard proving the resolver never
      derives a price from conversion_to_base
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import (
    Category, PriceTier, Product, ProductUnit, ProductUnitTierPrice, Unit,
    UnitGroup,
)
from pos.services import pricing as pricing_svc


class _PricingTestBase(APITestCase):
    """Two-tenant fixture: tenant A fully populated, tenant B for isolation."""

    @classmethod
    def setUpTestData(cls):
        # ── Tenant A ──
        cls.tenant = Tenant.objects.create(name='Pricing Tenant A')
        cls.manager = User.objects.create_user(
            username='pmgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='pcsh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Beverages')
        cls.milk = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Milk', barcode='PMILK-1', sku='SKU-PMILK',
            price=Decimal('30.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.volume = UnitGroup.objects.create(tenant=cls.tenant, name='Volume')
        cls.packaging = UnitGroup.objects.create(tenant=cls.tenant, name='Packaging')
        cls.ml = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.volume, name='Milliliter',
            symbol='ml', factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.carton = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.packaging, name='Carton',
            symbol='ctn', factor_to_base=Decimal('1'), allow_decimal=False,
        )
        cls.base_unit = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.milk, unit=cls.ml,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.carton_unit = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.milk, unit=cls.carton,
            conversion_to_base=Decimal('12000'), is_purchase_unit=True,
        )
        cls.retail = PriceTier.objects.create(tenant=cls.tenant, name='Retail')
        cls.wholesale = PriceTier.objects.create(tenant=cls.tenant, name='Wholesale')

        # ── Tenant B (isolation) ──
        cls.tenant_b = Tenant.objects.create(name='Pricing Tenant B')
        cls.manager_b = User.objects.create_user(
            username='pmgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant_b,
        )
        cls.category_b = Category.objects.create(tenant=cls.tenant_b, name='B-Cat')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, category=cls.category_b,
            name='B-Item', barcode='PB-1', sku='SKU-PB',
            price=Decimal('10.00'), cost=Decimal('5.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.group_b = UnitGroup.objects.create(tenant=cls.tenant_b, name='Mass')
        cls.gram_b = Unit.objects.create(
            tenant=cls.tenant_b, unit_group=cls.group_b, name='Gram', symbol='g',
            factor_to_base=Decimal('1'),
        )
        cls.base_unit_b = ProductUnit.objects.create(
            tenant=cls.tenant_b, product=cls.product_b, unit=cls.gram_b,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.tier_b = PriceTier.objects.create(tenant=cls.tenant_b, name='Retail')


# ══════════════════════════════════════════════════════════════════════════════
#  PriceTier catalog CRUD
# ══════════════════════════════════════════════════════════════════════════════

class PriceTierApiTests(_PricingTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_manager_creates_price_tier(self):
        resp = self.client.post(reverse('price-tier-list'), {'name': 'VIP'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(PriceTier.objects.get(pk=resp.json()['id']).tenant_id, self.tenant.id)

    def test_duplicate_tier_name_rejected_within_tenant(self):
        resp = self.client.post(reverse('price-tier-list'), {'name': 'Retail'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.json())

    def test_same_tier_name_allowed_for_other_tenant(self):
        # Tenant A already has 'Wholesale'; tenant B (which only has its own
        # 'Retail' from the fixture) can still create that same name.
        self.client.force_authenticate(user=self.manager_b)
        resp = self.client.post(reverse('price-tier-list'), {'name': 'Wholesale'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_cashier_cannot_write_but_can_read(self):
        self.client.force_authenticate(user=self.cashier)
        self.assertEqual(
            self.client.post(reverse('price-tier-list'), {'name': 'X'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(reverse('price-tier-list')).status_code, status.HTTP_200_OK)

    def test_tier_list_is_tenant_scoped(self):
        names = {t['name'] for t in self.client.get(reverse('price-tier-list')).json()['results']}
        self.assertEqual(names, {'Retail', 'Wholesale'})

    def test_tier_deactivate_endpoint(self):
        resp = self.client.post(reverse('price-tier-deactivate', args=[self.wholesale.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.wholesale.refresh_from_db()
        self.assertFalse(self.wholesale.is_active)

    def test_cross_tenant_tier_detail_404s(self):
        resp = self.client.get(reverse('price-tier-detail', args=[self.tier_b.pk]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ══════════════════════════════════════════════════════════════════════════════
#  ProductUnitTierPrice — CRUD, (product_unit, price_tier) uniqueness
# ══════════════════════════════════════════════════════════════════════════════

class ProductUnitTierPriceApiTests(_PricingTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _url(self, product, product_unit):
        return reverse(
            'product-unit-tier-price-list',
            kwargs={'product_pk': product.pk, 'unit_pk': product_unit.pk},
        )

    def test_create_tier_price(self):
        resp = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.retail.pk, 'price': '340.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        row = ProductUnitTierPrice.objects.get(pk=resp.json()['id'])
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertEqual(row.product_id, self.milk.pk)
        self.assertEqual(row.product_unit_id, self.carton_unit.pk)
        self.assertEqual(row.price, Decimal('340.00'))

    def test_same_unit_supports_multiple_tiers(self):
        """The core requirement: one product_unit, more than one price_tier."""
        self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.retail.pk, 'price': '340.00',
        }, format='json')
        resp = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.wholesale.pk, 'price': '300.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            ProductUnitTierPrice.objects.filter(product_unit=self.carton_unit).count(), 2)

    def test_duplicate_unit_tier_pair_rejected(self):
        self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.retail.pk, 'price': '340.00',
        }, format='json')
        resp = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.retail.pk, 'price': '350.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price_tier', resp.json())

    def test_nonpositive_price_rejected(self):
        for price in ('0', '-5'):
            resp = self.client.post(self._url(self.milk, self.carton_unit), {
                'price_tier': self.retail.pk, 'price': price,
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('price', resp.json())

    def test_cross_tenant_price_tier_rejected(self):
        resp = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.tier_b.pk, 'price': '340.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price_tier', resp.json())

    def test_inactive_price_tier_rejected(self):
        self.wholesale.is_active = False
        self.wholesale.save(update_fields=['is_active'])
        resp = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.wholesale.pk, 'price': '300.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price_tier', resp.json())

    def test_cross_tenant_product_scope_404s(self):
        resp = self.client.get(reverse(
            'product-unit-tier-price-list',
            kwargs={'product_pk': self.product_b.pk, 'unit_pk': self.base_unit_b.pk},
        ))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cashier_cannot_write_but_can_read(self):
        self.client.force_authenticate(user=self.cashier)
        self.assertEqual(
            self.client.post(self._url(self.milk, self.carton_unit), {
                'price_tier': self.retail.pk, 'price': '340.00',
            }, format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(self._url(self.milk, self.carton_unit)).status_code,
            status.HTTP_200_OK)

    def test_deactivate_via_patch(self):
        create = self.client.post(self._url(self.milk, self.carton_unit), {
            'price_tier': self.retail.pk, 'price': '340.00',
        }, format='json')
        detail_url = reverse(
            'product-unit-tier-price-detail',
            kwargs={'product_pk': self.milk.pk, 'unit_pk': self.carton_unit.pk, 'pk': create.json()['id']},
        )
        resp = self.client.patch(detail_url, {'is_active': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertFalse(ProductUnitTierPrice.objects.get(pk=create.json()['id']).is_active)


# ══════════════════════════════════════════════════════════════════════════════
#  ProductUnit.minimum_order_qty validation
# ══════════════════════════════════════════════════════════════════════════════

class MinimumOrderQtyApiTests(_PricingTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_null_minimum_order_qty_allowed(self):
        resp = self.client.patch(
            reverse('product-unit-detail', kwargs={'product_pk': self.milk.pk, 'pk': self.carton_unit.pk}),
            {'minimum_order_qty': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertIsNone(ProductUnit.objects.get(pk=self.carton_unit.pk).minimum_order_qty)

    def test_positive_minimum_order_qty_accepted(self):
        resp = self.client.patch(
            reverse('product-unit-detail', kwargs={'product_pk': self.milk.pk, 'pk': self.carton_unit.pk}),
            {'minimum_order_qty': '3'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(
            ProductUnit.objects.get(pk=self.carton_unit.pk).minimum_order_qty, Decimal('3.000'))

    def test_nonpositive_minimum_order_qty_rejected(self):
        for value in ('0', '-1'):
            resp = self.client.patch(
                reverse('product-unit-detail', kwargs={'product_pk': self.milk.pk, 'pk': self.carton_unit.pk}),
                {'minimum_order_qty': value}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('minimum_order_qty', resp.json())


# ══════════════════════════════════════════════════════════════════════════════
#  pos.services.pricing.resolve_unit_price
# ══════════════════════════════════════════════════════════════════════════════

class ResolveUnitPriceServiceTests(_PricingTestBase):

    def test_tier_price_used_when_present(self):
        ProductUnitTierPrice.objects.create(
            tenant=self.tenant, product=self.milk, product_unit=self.carton_unit,
            price_tier=self.retail, price=Decimal('340.00'),
        )
        price = pricing_svc.resolve_unit_price(
            product_unit=self.carton_unit, price_tier=self.retail)
        self.assertEqual(price, Decimal('340.00'))

    def test_falls_back_to_product_price_when_tier_given_but_no_row(self):
        # Wholesale tier exists but has no price row for this product_unit.
        price = pricing_svc.resolve_unit_price(
            product_unit=self.carton_unit, price_tier=self.wholesale)
        self.assertEqual(price, self.milk.price)

    def test_falls_back_to_product_price_when_no_tier_given(self):
        ProductUnitTierPrice.objects.create(
            tenant=self.tenant, product=self.milk, product_unit=self.carton_unit,
            price_tier=self.retail, price=Decimal('340.00'),
        )
        price = pricing_svc.resolve_unit_price(product_unit=self.carton_unit, price_tier=None)
        self.assertEqual(price, self.milk.price)

    def test_inactive_tier_price_row_ignored(self):
        ProductUnitTierPrice.objects.create(
            tenant=self.tenant, product=self.milk, product_unit=self.carton_unit,
            price_tier=self.retail, price=Decimal('340.00'), is_active=False,
        )
        price = pricing_svc.resolve_unit_price(
            product_unit=self.carton_unit, price_tier=self.retail)
        self.assertEqual(price, self.milk.price)

    def test_never_derives_price_from_conversion_to_base(self):
        """Regression guard: a carton (conversion_to_base=12000) must NEVER
        resolve to product.price * 12000 or any other conversion-derived
        value — only an explicit ProductUnitTierPrice row or the flat
        Product.price fallback are legal outcomes."""
        naive_calculated = self.milk.price * self.carton_unit.conversion_to_base
        price = pricing_svc.resolve_unit_price(
            product_unit=self.carton_unit, price_tier=self.retail)
        self.assertNotEqual(price, naive_calculated)
        self.assertEqual(price, self.milk.price)

        ProductUnitTierPrice.objects.create(
            tenant=self.tenant, product=self.milk, product_unit=self.carton_unit,
            price_tier=self.retail, price=Decimal('340.00'),
        )
        price = pricing_svc.resolve_unit_price(
            product_unit=self.carton_unit, price_tier=self.retail)
        self.assertNotEqual(price, naive_calculated)
        self.assertEqual(price, Decimal('340.00'))

    def test_base_unit_uses_product_price_fallback(self):
        price = pricing_svc.resolve_unit_price(product_unit=self.base_unit, price_tier=None)
        self.assertEqual(price, self.milk.price)
