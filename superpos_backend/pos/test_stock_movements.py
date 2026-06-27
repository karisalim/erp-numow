"""Phase 1.5 Slice D — stock_movements service + per-product API tests.

Reuses the existing `pos.StockMovement` model (no new table). Focuses on:
  * stock IN increases product balance through the service
  * stock OUT decreases product balance through the service
  * per-product stock balance derives from the ledger, not Product.stock
  * tenant + branch isolation on the statement
  * the new /api/products/{id}/stock-movements/ and /stock-balance/ endpoints
"""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Tenant, User
from pos.models import Category, Product, StockMovement
from pos.services import stock_movements as svc


class _StockFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a  = Branch.objects.create(tenant=cls.tenant_a, name='Branch A1')
        cls.branch_a2 = Branch.objects.create(tenant=cls.tenant_a, name='Branch A2')
        cls.branch_b  = Branch.objects.create(tenant=cls.tenant_b, name='Branch B1')

        cls.manager_a = User.objects.create_user(
            username='mgr_a', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_a, branch=cls.branch_a,
        )

        cls.category_a = Category.objects.create(tenant=cls.tenant_a, name='Food')
        cls.product_a = Product.objects.create(
            tenant=cls.tenant_a, category=cls.category_a,
            name='Apples', barcode='A-1', sku='SKU-A',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, name='B-Item', barcode='B-1', sku='SKU-B',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )


class StockMovementServiceTests(_StockFixtureMixin, APITestCase):

    def test_stock_in_increases_balance_and_cached_stock(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('12'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
            source_document_type='Receipt', source_document_id=1,
        )
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, Decimal('12.000'))
        self.assertEqual(
            svc.get_product_stock_balance(self.product_a),
            Decimal('12.000'),
        )

    def test_stock_out_decreases_balance(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('20'),
            movement_type=StockMovement.MovementType.PURCHASE_IN,
            branch=self.branch_a,
            source_document_type='Purchase', source_document_id=1,
        )
        svc.record_stock_out(
            product=self.product_a, quantity=Decimal('7'),
            movement_type=StockMovement.MovementType.SALE_OUT,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=2,
        )
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, Decimal('13.000'))
        self.assertEqual(
            svc.get_product_stock_balance(self.product_a),
            Decimal('13.000'),
        )

    def test_in_rejects_out_movement_type(self):
        with self.assertRaises(svc.StockMovementError):
            svc.record_stock_in(
                product=self.product_a, quantity=Decimal('1'),
                movement_type=StockMovement.MovementType.SALE_OUT,
                branch=self.branch_a,
            )

    def test_out_rejects_in_movement_type(self):
        with self.assertRaises(svc.StockMovementError):
            svc.record_stock_out(
                product=self.product_a, quantity=Decimal('1'),
                movement_type=StockMovement.MovementType.PURCHASE_IN,
                branch=self.branch_a,
            )

    def test_zero_or_negative_qty_rejected(self):
        with self.assertRaises(svc.StockMovementError):
            svc.record_stock_in(
                product=self.product_a, quantity=Decimal('0'),
                branch=self.branch_a,
            )
        with self.assertRaises(svc.StockMovementError):
            svc.record_stock_out(
                product=self.product_a, quantity=Decimal('-3'),
                branch=self.branch_a,
            )

    def test_cross_tenant_branch_rejected(self):
        with self.assertRaises(svc.StockMovementError):
            svc.record_stock_in(
                product=self.product_a, quantity=Decimal('5'),
                branch=self.branch_b,   # tenant B branch
            )

    def test_statement_is_tenant_and_branch_scoped(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('5'),
            branch=self.branch_a, source_document_type='Receipt',
            source_document_id=10,
        )
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('8'),
            branch=self.branch_a2, source_document_type='Receipt',
            source_document_id=11,
        )
        # Direct-ORM write on a foreign tenant — must not appear in tenant A's statement.
        StockMovement.objects.create(
            tenant=self.tenant_b, product=self.product_b,
            qty=Decimal('99'), movement_type='receive_in',
        )

        rows = list(svc.get_product_stock_statement(self.product_a))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.tenant_id == self.tenant_a.id for r in rows))

        rows = list(svc.get_product_stock_statement(
            self.product_a, branch=self.branch_a,
        ))
        self.assertEqual([r.source_document_id for r in rows], [10])


class StockMovementApiTests(_StockFixtureMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_product_stock_movements_endpoint(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('4'),
            branch=self.branch_a,
            source_document_type='Receipt', source_document_id=1,
        )
        url = f'/api/products/{self.product_a.id}/stock-movements/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0]['qty'])), Decimal('4'))

    def test_product_stock_balance_endpoint(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('10'),
            branch=self.branch_a,
            source_document_type='Receipt', source_document_id=1,
        )
        svc.record_stock_out(
            product=self.product_a, quantity=Decimal('3'),
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=2,
        )
        url = f'/api/products/{self.product_a.id}/stock-balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        self.assertEqual(body['product_id'],   self.product_a.id)
        self.assertEqual(Decimal(body['ledger_stock']), Decimal('7.000'))
        self.assertEqual(Decimal(body['cached_stock']), Decimal('7.000'))

    def test_stock_balance_404_on_foreign_product(self):
        url = f'/api/products/{self.product_b.id}/stock-balance/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
