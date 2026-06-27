"""Phase 1.5 Slice F — Customer AR + Supplier AP ledger tests.

Covers:
  * customer AR debit increases / credit decreases balance (asset rule)
  * supplier AP credit increases / debit decreases balance (liability rule)
  * opening_balance is the starting balance for the first movement
  * invalid debit+credit / zero-zero rejected at service + DB layers
  * tenant + branch isolation on both writes and reads
  * statement filtering by branch, movement_type, source
  * per-party balance endpoints reflect the running total
  * tenant-wide flat /movements/ streams
  * foreign-tenant detail returns 404
  * AR/AP writes never create FinancialAccountMovement
"""

from decimal import Decimal

from django.db.utils import IntegrityError
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    Customer,
    CustomerARMovement,
    FinancialAccountMovement,
    Supplier,
    SupplierAPMovement,
    Tenant,
    User,
)
from accounts.services import customer_ar as ar
from accounts.services import supplier_ap as ap


class _PartiesFixtureMixin:
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
        cls.manager_b = User.objects.create_user(
            username='mgr_b', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_b, branch=cls.branch_b,
        )

        cls.cust_a = Customer.objects.create(
            tenant=cls.tenant_a, name='Acme', code='C-A',
            opening_balance=Decimal('100.00'),
        )
        cls.cust_b = Customer.objects.create(
            tenant=cls.tenant_b, name='Foreign Acme', code='C-B',
        )
        cls.sup_a = Supplier.objects.create(
            tenant=cls.tenant_a, name='Beans Co', code='S-A',
            opening_balance=Decimal('200.00'),
        )
        cls.sup_b = Supplier.objects.create(
            tenant=cls.tenant_b, name='Foreign Beans', code='S-B',
        )


# ── Customer AR service ──────────────────────────────────────────────────────

class CustomerARServiceTests(_PartiesFixtureMixin, APITestCase):

    def test_opening_balance_is_starting_balance_when_no_movements(self):
        self.assertEqual(
            ar.get_customer_balance(self.cust_a),
            Decimal('100.00'),
        )

    def test_debit_increases_customer_balance(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('50.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
            actor_user=self.manager_a,
        )
        self.assertEqual(
            ar.get_customer_balance(self.cust_a),
            Decimal('150.00'),  # 100 opening + 50 debit
        )

    def test_credit_decreases_customer_balance(self):
        ar.record_customer_ar_credit(
            customer=self.cust_a, amount=Decimal('30.00'),
            movement_type=ar.MovementType.CUSTOMER_RECEIPT,
            branch=self.branch_a,
            source_document_type='CustomerReceipt', source_document_id=2,
        )
        self.assertEqual(
            ar.get_customer_balance(self.cust_a),
            Decimal('70.00'),
        )

    def test_running_balance_chain_is_monotonic(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('40'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
        )
        ar.record_customer_ar_credit(
            customer=self.cust_a, amount=Decimal('20'),
            movement_type=ar.MovementType.CUSTOMER_RECEIPT,
            branch=self.branch_a,
            source_document_type='CustomerReceipt', source_document_id=2,
        )
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('10'),
            movement_type=ar.MovementType.ADJUSTMENT,
            branch=self.branch_a,
            source_document_type='Adjustment', source_document_id=3,
        )
        # opening(100) + 40 - 20 + 10 = 130
        self.assertEqual(ar.get_customer_balance(self.cust_a), Decimal('130.00'))
        chain = list(self.cust_a.ar_movements
                                .order_by('id')
                                .values_list('balance_after', flat=True))
        self.assertEqual(chain, [Decimal('140.00'), Decimal('120.00'), Decimal('130.00')])

    def test_invalid_pair_rejected(self):
        with self.assertRaises(ar.CustomerARError):
            ar.record_customer_ar_movement(
                customer=self.cust_a,
                movement_type=ar.MovementType.OTHER,
                debit=Decimal('10'), credit=Decimal('10'),
                branch=self.branch_a,
            )

    def test_zero_movement_rejected(self):
        with self.assertRaises(ar.CustomerARError):
            ar.record_customer_ar_movement(
                customer=self.cust_a,
                movement_type=ar.MovementType.OTHER,
                debit=Decimal('0'), credit=Decimal('0'),
                branch=self.branch_a,
            )

    def test_negative_amount_rejected(self):
        with self.assertRaises(ar.CustomerARError):
            ar.record_customer_ar_debit(
                customer=self.cust_a, amount=Decimal('-5'),
                movement_type=ar.MovementType.OTHER,
                branch=self.branch_a,
            )

    def test_foreign_branch_rejected(self):
        with self.assertRaises(ar.CustomerARError):
            ar.record_customer_ar_debit(
                customer=self.cust_a, amount=Decimal('1'),
                movement_type=ar.MovementType.SALES_CREDIT,
                branch=self.branch_b,
            )

    def test_db_check_blocks_both_positive(self):
        with self.assertRaises(IntegrityError):
            CustomerARMovement.objects.create(
                tenant=self.tenant_a, branch=self.branch_a, customer=self.cust_a,
                movement_type='other',
                debit=Decimal('1'), credit=Decimal('1'),
                balance_after=Decimal('0'),
                occurred_at='2026-06-28T10:00:00Z',
            )

    def test_statement_is_tenant_and_branch_scoped(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('10'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=10,
        )
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('20'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a2,
            source_document_type='SalesInvoice', source_document_id=11,
        )
        # Foreign-tenant write — must never appear in cust_a's statement.
        ar.record_customer_ar_debit(
            customer=self.cust_b, amount=Decimal('99'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_b,
            source_document_type='SalesInvoice', source_document_id=99,
        )

        rows = list(ar.get_customer_statement(self.cust_a))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.tenant_id == self.tenant_a.id for r in rows))

        rows = list(ar.get_customer_statement(self.cust_a, branch=self.branch_a))
        self.assertEqual([r.source_document_id for r in rows], [10])

    def test_ar_write_does_not_create_financial_account_movement(self):
        before = FinancialAccountMovement.objects.count()
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('5'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
        )
        # AR ledger is decoupled from finance accounts in this slice.
        self.assertEqual(FinancialAccountMovement.objects.count(), before)


# ── Supplier AP service ──────────────────────────────────────────────────────

class SupplierAPServiceTests(_PartiesFixtureMixin, APITestCase):

    def test_opening_balance_is_starting_balance_when_no_movements(self):
        self.assertEqual(
            ap.get_supplier_balance(self.sup_a),
            Decimal('200.00'),
        )

    def test_credit_increases_supplier_balance(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('500.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        self.assertEqual(
            ap.get_supplier_balance(self.sup_a),
            Decimal('700.00'),  # 200 opening + 500 credit
        )

    def test_debit_decreases_supplier_balance(self):
        ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('120.00'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
            source_document_type='SupplierPayment', source_document_id=2,
        )
        self.assertEqual(
            ap.get_supplier_balance(self.sup_a),
            Decimal('80.00'),
        )

    def test_running_balance_chain_is_monotonic(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('300'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('100'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
            source_document_type='SupplierPayment', source_document_id=2,
        )
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('50'),
            movement_type=ap.MovementType.ADJUSTMENT,
            branch=self.branch_a,
            source_document_type='Adjustment', source_document_id=3,
        )
        # opening(200) + 300 - 100 + 50 = 450
        self.assertEqual(ap.get_supplier_balance(self.sup_a), Decimal('450.00'))
        chain = list(self.sup_a.ap_movements
                                .order_by('id')
                                .values_list('balance_after', flat=True))
        self.assertEqual(chain, [Decimal('500.00'), Decimal('400.00'), Decimal('450.00')])

    def test_invalid_pair_rejected(self):
        with self.assertRaises(ap.SupplierAPError):
            ap.record_supplier_ap_movement(
                supplier=self.sup_a,
                movement_type=ap.MovementType.OTHER,
                debit=Decimal('5'), credit=Decimal('5'),
                branch=self.branch_a,
            )

    def test_zero_movement_rejected(self):
        with self.assertRaises(ap.SupplierAPError):
            ap.record_supplier_ap_movement(
                supplier=self.sup_a,
                movement_type=ap.MovementType.OTHER,
                debit=Decimal('0'), credit=Decimal('0'),
                branch=self.branch_a,
            )

    def test_foreign_branch_rejected(self):
        with self.assertRaises(ap.SupplierAPError):
            ap.record_supplier_ap_credit(
                supplier=self.sup_a, amount=Decimal('1'),
                movement_type=ap.MovementType.PURCHASE_CREDIT,
                branch=self.branch_b,
            )

    def test_db_check_blocks_both_positive(self):
        with self.assertRaises(IntegrityError):
            SupplierAPMovement.objects.create(
                tenant=self.tenant_a, branch=self.branch_a, supplier=self.sup_a,
                movement_type='other',
                debit=Decimal('1'), credit=Decimal('1'),
                balance_after=Decimal('0'),
                occurred_at='2026-06-28T10:00:00Z',
            )

    def test_statement_filter_by_movement_type(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('100'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('50'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
            source_document_type='SupplierPayment', source_document_id=2,
        )
        rows = list(ap.get_supplier_statement(
            self.sup_a, movement_type=ap.MovementType.SUPPLIER_PAYMENT,
        ))
        self.assertEqual([r.source_document_id for r in rows], [2])


# ── API tests ────────────────────────────────────────────────────────────────

class CustomerARApiTests(_PartiesFixtureMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_balance_endpoint_uses_opening_when_no_movements(self):
        url = f'/api/customers/{self.cust_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['opening_balance'], '100.00')
        self.assertEqual(body['balance'],         '100.00')

    def test_balance_endpoint_reflects_running_total(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('77.50'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
        )
        url = f'/api/customers/{self.cust_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.json()['balance'], '177.50')

    def test_statement_endpoint(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('10'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
        )
        url = f'/api/customers/{self.cust_a.id}/statement/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]['movement_type'], 'sales_credit')
        self.assertEqual(body[0]['balance_after'], '110.00')

    def test_foreign_customer_balance_is_404(self):
        url = f'/api/customers/{self.cust_b.id}/balance/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_customer_statement_is_404(self):
        url = f'/api/customers/{self.cust_b.id}/statement/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_flat_movement_list_is_tenant_scoped(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('25'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            source_document_type='SalesInvoice', source_document_id=1,
        )
        ar.record_customer_ar_debit(
            customer=self.cust_b, amount=Decimal('99'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_b,
            source_document_type='SalesInvoice', source_document_id=2,
        )
        resp = self.client.get('/api/customer-ar/movements/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['customer'], self.cust_a.id)


class SupplierAPApiTests(_PartiesFixtureMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_balance_endpoint_uses_opening_when_no_movements(self):
        url = f'/api/suppliers/{self.sup_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['opening_balance'], '200.00')
        self.assertEqual(body['balance'],         '200.00')

    def test_balance_endpoint_reflects_running_total(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('33.33'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        url = f'/api/suppliers/{self.sup_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.json()['balance'], '233.33')

    def test_statement_endpoint_filterable(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('100'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=10,
        )
        ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('40'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
            source_document_type='SupplierPayment', source_document_id=11,
        )
        url = f'/api/suppliers/{self.sup_a.id}/statement/?movement_type=supplier_payment'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual([r['source_document_id'] for r in body], [11])

    def test_foreign_supplier_statement_is_404(self):
        url = f'/api/suppliers/{self.sup_b.id}/statement/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_supplier_balance_is_404(self):
        url = f'/api/suppliers/{self.sup_b.id}/balance/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_flat_movement_list_is_tenant_scoped(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('60'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        ap.record_supplier_ap_credit(
            supplier=self.sup_b, amount=Decimal('99'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_b,
            source_document_type='PurchaseInvoice', source_document_id=2,
        )
        resp = self.client.get('/api/supplier-ap/movements/')
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['supplier'], self.sup_a.id)

    def test_flat_movement_list_filter_by_supplier(self):
        # Two suppliers, both in tenant A.
        sup_a2 = Supplier.objects.create(tenant=self.tenant_a, name='Sup A2')
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('10'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=1,
        )
        ap.record_supplier_ap_credit(
            supplier=sup_a2, amount=Decimal('20'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            source_document_type='PurchaseInvoice', source_document_id=2,
        )
        resp = self.client.get(f'/api/supplier-ap/movements/?supplier={sup_a2.id}')
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual({r['supplier'] for r in rows}, {sup_a2.id})
