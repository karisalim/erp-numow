"""Phase 1.5 — StockMovement running-quantity hardening tests.

Covers:
  * First stock-in row records quantity_before/quantity_after
  * Stock-in, stock-out, adjustment-in, adjustment-out apply correct sign
  * Multiple movements chain quantity_before == previous quantity_after
  * Statement summary returns the envelope shape (opening/totals/closing)
  * Date filters work
  * Branch filter works
  * actor_user filter works
  * Tenant isolation preserved
  * Product stock balance endpoint still works
  * Legacy rows (quantity_before IS NULL) tolerated in summary
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Tenant, User
from pos.models import Category, Product, StockMovement
from pos.services import stock_movements as svc


class _Fixture:
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
        cls.other_user_a = User.objects.create_user(
            username='other_a', password='pw',
            role=User.Role.CASHIER, tenant=cls.tenant_a, branch=cls.branch_a,
        )

        cls.category_a = Category.objects.create(tenant=cls.tenant_a, name='Food')
        # `stock=0` baseline so the first ledger movement starts the chain
        # from a known point.
        cls.product_a = Product.objects.create(
            tenant=cls.tenant_a, category=cls.category_a,
            name='Apples', barcode='HARD-A-1', sku='HARD-SKU-A',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, name='B-Item',
            barcode='HARD-B-1', sku='HARD-SKU-B',
            price=Decimal('1.00'), cost=Decimal('0.50'),
            tax_rate=Decimal('0'), stock=Decimal('0'),
        )


# ── Service-layer running-quantity tests ────────────────────────────────────

class RunningQuantityServiceTests(_Fixture, APITestCase):

    def test_first_stock_in_records_quantity_before_after(self):
        mvmt = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('5'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.quantity_before, Decimal('0.000'))
        self.assertEqual(mvmt.quantity_after,  Decimal('5.000'))

    def test_first_stock_in_anchors_to_existing_product_stock(self):
        # Seed: product_a has a non-zero baseline.
        self.product_a.stock = Decimal('7')
        self.product_a.save(update_fields=['stock', 'updated_at'])

        mvmt = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('3'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        # Anchors at current Product.stock so we don't pretend the
        # pre-existing inventory disappeared.
        self.assertEqual(mvmt.quantity_before, Decimal('7.000'))
        self.assertEqual(mvmt.quantity_after,  Decimal('10.000'))

    def test_subsequent_movements_chain_correctly(self):
        m1 = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('10'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        m2 = svc.record_stock_out(
            product=self.product_a, quantity=Decimal('3'),
            movement_type=StockMovement.MovementType.SALE_OUT,
            branch=self.branch_a,
        )
        m3 = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('2'),
            movement_type=StockMovement.MovementType.RETURN_IN,
            branch=self.branch_a,
        )
        self.assertEqual(m2.quantity_before, m1.quantity_after)
        self.assertEqual(m3.quantity_before, m2.quantity_after)
        self.assertEqual(m1.quantity_after,  Decimal('10.000'))
        self.assertEqual(m2.quantity_after,  Decimal('7.000'))
        self.assertEqual(m3.quantity_after,  Decimal('9.000'))

    def test_adjustment_in_increases_quantity(self):
        # ADJUSTMENT now lives in both IN and OUT sets; routing through
        # `record_stock_in` makes it an in-movement.
        mvmt = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('4'),
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.quantity_before, Decimal('0.000'))
        self.assertEqual(mvmt.quantity_after,  Decimal('4.000'))

    def test_adjustment_out_decreases_quantity(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('6'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        mvmt = svc.record_stock_out(
            product=self.product_a, quantity=Decimal('2'),
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.quantity_before, Decimal('6.000'))
        self.assertEqual(mvmt.quantity_after,  Decimal('4.000'))

    def test_balance_endpoint_still_reads_from_ledger(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('12'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        svc.record_stock_out(
            product=self.product_a, quantity=Decimal('5'),
            movement_type=StockMovement.MovementType.SALE_OUT,
            branch=self.branch_a,
        )
        self.assertEqual(
            svc.get_product_stock_balance(self.product_a),
            Decimal('7'),
        )


# ── Statement summary envelope ─────────────────────────────────────────────

class StockStatementSummaryTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = f'/api/products/{self.product_a.id}/stock-movements/'

    def _post_three_movements(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('10'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a, actor_user=self.manager_a,
        )
        svc.record_stock_out(
            product=self.product_a, quantity=Decimal('3'),
            movement_type=StockMovement.MovementType.SALE_OUT,
            branch=self.branch_a, actor_user=self.manager_a,
        )
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('2'),
            movement_type=StockMovement.MovementType.RETURN_IN,
            branch=self.branch_a, actor_user=self.manager_a,
        )

    def test_envelope_shape_and_totals(self):
        self._post_three_movements()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        for key in (
            'opening_quantity', 'total_in', 'total_out',
            'net_change', 'closing_quantity',
            'date_from', 'date_to', 'filters', 'movements',
        ):
            self.assertIn(key, body, f'missing key {key!r}')

        self.assertEqual(body['opening_quantity'], '0.000')
        self.assertEqual(body['total_in'],         '12.000')
        self.assertEqual(body['total_out'],        '3.000')
        self.assertEqual(body['net_change'],       '9.000')
        self.assertEqual(body['closing_quantity'], '9.000')
        self.assertEqual(len(body['movements']),   3)

        first = body['movements'][0]
        self.assertEqual(first['quantity_before'], '0.000')
        self.assertEqual(first['quantity_after'],  '10.000')
        self.assertEqual(first['quantity_in'],     '10.000')
        self.assertEqual(first['quantity_out'],    '0.000')
        # filters echo
        self.assertEqual(body['filters']['product'], self.product_a.id)

    def test_envelope_with_no_movements(self):
        resp = self.client.get(self.url)
        body = resp.json()
        # Totals are quantized to 3 decimal places so the frontend always
        # gets a stable string format regardless of whether the window
        # contains data.
        self.assertEqual(body['opening_quantity'], '0.000')
        self.assertEqual(body['total_in'],         '0.000')
        self.assertEqual(body['total_out'],        '0.000')
        self.assertEqual(body['net_change'],       '0.000')
        self.assertEqual(body['closing_quantity'], '0.000')
        self.assertEqual(body['movements'],        [])

    def test_branch_filter(self):
        # branch_a movement (counted)
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('5'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        # branch_a2 movement (filtered out)
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('8'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a2,
        )
        resp = self.client.get(self.url, {'branch': self.branch_a.id})
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_in'], '5.000')
        self.assertEqual(body['filters']['branch'], self.branch_a.id)

    def test_movement_type_filter(self):
        self._post_three_movements()
        resp = self.client.get(self.url, {'movement_type': 'sale_out'})
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['movements'][0]['movement_type'], 'sale_out')
        self.assertEqual(body['total_in'],  '0.000')
        self.assertEqual(body['total_out'], '3.000')

    def test_actor_user_filter(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('4'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a, actor_user=self.manager_a,
        )
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('6'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a, actor_user=self.other_user_a,
        )
        resp = self.client.get(self.url, {'actor_user': self.manager_a.id})
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_in'], '4.000')

    def test_date_to_filter_excludes_later_rows(self):
        # Cannot easily set `created_at` directly (auto_now_add); craft
        # rows by post-update of created_at via update().
        m1 = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('4'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        m2 = svc.record_stock_in(
            product=self.product_a, quantity=Decimal('11'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        early = timezone.now() - timezone.timedelta(days=10)
        later = timezone.now() + timezone.timedelta(days=10)
        StockMovement.objects.filter(pk=m1.pk).update(created_at=early)
        StockMovement.objects.filter(pk=m2.pk).update(created_at=later)

        cutoff = (timezone.now() + timezone.timedelta(days=1)).date().isoformat()
        resp = self.client.get(self.url, {'date_to': cutoff})
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_in'], '4.000')

    def test_source_document_filter(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('3'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=42,
        )
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('7'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
            source_document_type='ManualReceipt', source_document_id=99,
        )
        resp = self.client.get(
            self.url, {
                'source_document_type': 'PurchaseInvoice',
                'source_document_id':   '42',
            },
        )
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_in'], '3.000')


# ── Cross-tenant isolation + endpoint sanity ───────────────────────────────

class StockStatementIsolationTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_foreign_product_is_404(self):
        url = f'/api/products/{self.product_b.id}/stock-movements/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_branch_filter_is_404(self):
        url = f'/api/products/{self.product_a.id}/stock-movements/'
        resp = self.client.get(url, {'branch': self.branch_b.id})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_balance_endpoint_unchanged(self):
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('10'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        svc.record_stock_out(
            product=self.product_a, quantity=Decimal('4'),
            movement_type=StockMovement.MovementType.SALE_OUT,
            branch=self.branch_a,
        )
        url = f'/api/products/{self.product_a.id}/stock-balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(Decimal(body['ledger_stock']), Decimal('6'))
        self.assertEqual(Decimal(body['cached_stock']), Decimal('6'))


# ── Legacy / mixed data tolerated by the summary ───────────────────────────

class StockStatementLegacyToleranceTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = f'/api/products/{self.product_a.id}/stock-movements/'

    def test_summary_handles_legacy_null_quantity_rows(self):
        # Simulate a pre-hardening row: written directly to the model
        # without going through the service, so quantity_before/after
        # are NULL.
        StockMovement.objects.create(
            tenant=self.tenant_a, product=self.product_a,
            branch=self.branch_a,
            qty=Decimal('8'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
        )
        # Followed by a hardened row through the service.
        svc.record_stock_in(
            product=self.product_a, quantity=Decimal('2'),
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            branch=self.branch_a,
        )
        resp = self.client.get(self.url)
        body = resp.json()
        # Two rows show up. The hardened row chains off whatever the
        # service computed (legacy row has no quantity_after so the chain
        # falls back to Product.stock = 8 before the second post).
        self.assertEqual(len(body['movements']), 2)
        self.assertEqual(body['total_in'], '10.000')
