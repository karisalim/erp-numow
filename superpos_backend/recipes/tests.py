"""Sprint 5 Batch 2 — ProductVariant CRUD.

Model-level tests (uniqueness, price constraint) plus API-level CRUD
tests, mirroring the conventions `pos/test_pricing.py`'s PriceTier tests
and `pos/test_units.py`'s ProductUnit tests already establish.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import Category, Product
from recipes.models import ProductVariant


class ProductVariantModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Variant Model Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.pizza = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Margherita Pizza', barcode='PZ-1', sku='SKU-PZ-1',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )

    def test_create_variant(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        self.assertEqual(variant.price, Decimal('80.00'))
        self.assertTrue(variant.is_active)

    def test_uniqueness_per_product_name(self):
        ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(
                    tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('90.00'),
                )

    def test_same_name_allowed_on_different_products(self):
        sandwich = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Club Sandwich', barcode='SW-1', sku='SKU-SW-1',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        # No collision — uniqueness is scoped per (tenant, product, name).
        ProductVariant.objects.create(
            tenant=self.tenant, product=sandwich, name='Small', price=Decimal('40.00'),
        )
        self.assertEqual(ProductVariant.objects.count(), 2)

    def test_negative_price_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(
                    tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('-1.00'),
                )

    def test_no_barcode_field(self):
        """D-24: variants are deliberately barcode-free."""
        self.assertFalse(hasattr(ProductVariant, 'barcode'))


class ProductVariantApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Variant Api Tenant')
        cls.manager = User.objects.create_user(
            username='varmgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='varcsh', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.pizza = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Margherita Pizza', barcode='PZ-2', sku='SKU-PZ-2',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        # Cross-tenant isolation fixture.
        cls.other_tenant = Tenant.objects.create(name='Other Variant Tenant')
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, category=Category.objects.create(tenant=cls.other_tenant, name='M'),
            name='Other Pizza', barcode='PZ-OTHER', sku='SKU-PZ-OTHER',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_manager_can_create_variant(self):
        resp = self.client.post(
            reverse('product-variant-list', args=[self.pizza.id]),
            {'name': 'Small', 'price': '80.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['name'], 'Small')
        self.assertEqual(ProductVariant.objects.filter(product=self.pizza).count(), 1)

    def test_cashier_forbidden_to_create(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(
            reverse('product-variant-list', args=[self.pizza.id]),
            {'name': 'Small', 'price': '80.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cashier_can_list(self):
        ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.get(reverse('product-variant-list', args=[self.pizza.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_duplicate_name_rejected_with_friendly_400(self):
        ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        resp = self.client.post(
            reverse('product-variant-list', args=[self.pizza.id]),
            {'name': 'Small', 'price': '90.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_price_rejected_with_friendly_400(self):
        resp = self.client.post(
            reverse('product-variant-list', args=[self.pizza.id]),
            {'name': 'Small', 'price': '-5.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_updates_price(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        resp = self.client.patch(
            reverse('product-variant-detail', args=[self.pizza.id, variant.id]),
            {'price': '85.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        variant.refresh_from_db()
        self.assertEqual(variant.price, Decimal('85.00'))

    def test_deactivate(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        resp = self.client.post(
            reverse('product-variant-deactivate', args=[self.pizza.id, variant.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        variant.refresh_from_db()
        self.assertFalse(variant.is_active)

    def test_deactivate_forbidden_for_cashier(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(
            reverse('product-variant-deactivate', args=[self.pizza.id, variant.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_product_returns_404(self):
        resp = self.client.get(reverse('product-variant-list', args=[self.other_product.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_delete_verb(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.pizza, name='Small', price=Decimal('80.00'),
        )
        resp = self.client.delete(
            reverse('product-variant-detail', args=[self.pizza.id, variant.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
