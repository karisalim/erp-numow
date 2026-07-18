"""Slice fix — direct POST /api/stock-movements/ now routes through the
running-quantity service so newly-created rows always carry
`quantity_before` / `quantity_after`.

Captures the bug found in manual Swagger testing:
    POST purchase_in qty 10  → row had quantity_before=null, quantity_after=null
    POST sale_out  qty 3     → row had quantity_before=null, quantity_after=null
    /stock-balance reported the right cached_stock but the ledger rows
    were missing the running columns.

The fix is in `StockMovementSerializer.create`: it now calls
`record_stock_in` / `record_stock_out` instead of doing
`StockMovement.objects.create(**validated_data)` directly. These tests
hit the live endpoint to make sure the wiring stays connected.
"""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Tenant, User
from pos.models import Category, Product, StockMovement


class _Fixture:
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a = Branch.objects.create(tenant=cls.tenant_a, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='Branch B')

        cls.manager_a = User.objects.create_user(
            username='direct_mgr_a', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_a, branch=cls.branch_a,
        )

        cls.category_a = Category.objects.create(tenant=cls.tenant_a, name='Pantry')
        # Clean baseline so the very first POST should chain from stock=0.
        cls.product_a = Product.objects.create(
            tenant=cls.tenant_a, category=cls.category_a,
            name='Apples-Direct', barcode='DIR-A-1', sku='DIR-SKU-A',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, name='Foreign Item',
            barcode='DIR-B-1', sku='DIR-SKU-B',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )


class DirectPostRoutingTests(_Fixture, APITestCase):
    """The exact scenario from the manual Swagger test that surfaced the
    bug: two sequential POSTs against a clean product, asserting the
    response rows carry the running ledger columns.
    """

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = '/api/stock-movements/'

    def _post(self, **payload):
        body = {
            'product':       self.product_a.id,
            'qty':           '0',
            'movement_type': StockMovement.MovementType.RECEIVE_IN,
        }
        body.update(payload)
        return self.client.post(self.url, body, format='json')

    def test_purchase_in_creates_row_with_correct_running_quantities(self):
        resp = self._post(
            qty='10',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        # The bug: before this fix the response had quantity_before=None,
        # quantity_after=None. The fix wires the create through the
        # service so both columns land populated.
        self.assertEqual(body['quantity_before'], '0.000')
        self.assertEqual(body['quantity_after'],  '10.000')
        self.assertEqual(body['quantity_in'],     '10.000')
        self.assertEqual(body['quantity_out'],    '0.000')

    def test_subsequent_sale_out_chains_from_previous_after(self):
        # First, a purchase-in to seed the chain.
        self._post(
            qty='10',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        # Then a sale-out that should chain off the prior quantity_after.
        resp = self._post(
            qty='3',
            movement_type=StockMovement.MovementType.SALE_OUT,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['quantity_before'], '10.000')
        self.assertEqual(body['quantity_after'],  '7.000')
        self.assertEqual(body['quantity_in'],     '0.000')
        self.assertEqual(body['quantity_out'],    '3.000')

    def test_balance_endpoint_agrees_with_ledger_after_direct_posts(self):
        self._post(
            qty='10',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        self._post(
            qty='3',
            movement_type=StockMovement.MovementType.SALE_OUT,
        )
        resp = self.client.get(
            f'/api/products/{self.product_a.id}/stock-balance/',
        )
        body = resp.json()
        self.assertEqual(Decimal(body['cached_stock']), Decimal('7'))
        self.assertEqual(Decimal(body['ledger_stock']), Decimal('7'))

    def test_post_cannot_spoof_quantity_before_or_after(self):
        resp = self._post(
            qty='10',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
            # Spoof attempts — must be ignored by the read-only field set.
            quantity_before='99999.000',
            quantity_after='88888.000',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['quantity_before'], '0.000')
        self.assertEqual(body['quantity_after'],  '10.000')

        # And the persisted row is correct too — not just the response.
        row = StockMovement.objects.get(pk=body['id'])
        self.assertEqual(row.quantity_before, Decimal('0.000'))
        self.assertEqual(row.quantity_after,  Decimal('10.000'))

    def test_post_cross_tenant_product_rejected(self):
        # Belongs to tenant B; the serializer queryset is tenant-scoped so
        # this should 400 (not 500, not silently create).
        resp = self._post(
            product=self.product_b.id,
            qty='5',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            StockMovement.objects.filter(product=self.product_b).exists()
        )

    def test_post_cross_tenant_branch_rejected(self):
        resp = self._post(
            qty='5',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
            branch=self.branch_b.id,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Nothing persisted — service-layer rule violations roll back
        # because they raise before the row is created.
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_post_adjustment_positive_qty_increases_stock(self):
        # Adjustment with a positive magnitude routes through
        # record_stock_in (matches the legacy serializer behavior).
        resp = self._post(
            qty='4',
            movement_type=StockMovement.MovementType.ADJUSTMENT,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body['quantity_before'], '0.000')
        self.assertEqual(body['quantity_after'],  '4.000')
        # Hotfix Pack: the stored row now uses the unambiguous
        # ADJUSTMENT_IN value (translated from the legacy 'adjustment'
        # input the client sent), so a positive adjustment finally reads
        # as an inflow — this used to be misreported as an outflow (see
        # git history for the pre-hotfix assertion this replaces).
        self.assertEqual(body['movement_type'], StockMovement.MovementType.ADJUSTMENT_IN)
        self.assertEqual(body['quantity_in'],     '4.000')
        self.assertEqual(body['quantity_out'],    '0.000')

    def test_post_adjustment_negative_qty_decreases_stock(self):
        # Seed inventory.
        self._post(
            qty='10',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        resp = self._post(
            qty='-3',
            movement_type=StockMovement.MovementType.ADJUSTMENT,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body['quantity_before'], '10.000')
        self.assertEqual(body['quantity_after'],  '7.000')

    def test_post_zero_qty_rejected(self):
        resp = self._post(
            qty='0',
            movement_type=StockMovement.MovementType.PURCHASE_IN,
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
