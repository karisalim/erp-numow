"""Slice — receipt/payment posting hardening fixes.

Covers:
  * branch is required at service + view layers for both documents
  * Idempotency-Key is mandatory; missing key → 400
  * Idempotent replay returns exactly one document + one pair of movements
  * Different payload + same key → 409
  * CustomerARMovement.currency / SupplierAPMovement.currency default to
    the tenant currency (EGP in our fixtures)
  * Document.branch + AR/AP-row.branch + finance-row.branch all match
  * Branch-payment-method default-row behavior — documents the current
    behavior (multiple defaults are NOT prevented today)
"""

import uuid
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    BranchPaymentMethod,
    Customer,
    CustomerARMovement,
    CustomerReceipt,
    FinancialAccount,
    FinancialAccountMovement,
    PaymentMethod,
    Supplier,
    SupplierAPMovement,
    SupplierPayment,
    Tenant,
    User,
)
from accounts.services import customer_ar as ar
from accounts.services import customer_receipts as crsvc
from accounts.services import supplier_ap as ap
from accounts.services import supplier_payments as spsvc


def _idem_headers(key=None):
    return {'HTTP_IDEMPOTENCY_KEY': key or uuid.uuid4().hex}


# ── Fixtures ────────────────────────────────────────────────────────────────

class _Fixture:
    @classmethod
    def setUpTestData(cls):
        # Tenant.currency defaults to 'EGP' (see Tenant.currency field).
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a = Branch.objects.create(tenant=cls.tenant_a, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='Branch B')

        cls.manager_a = User.objects.create_user(
            username='mgr_a', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_a, branch=cls.branch_a,
        )

        cls.cashbox_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Cash A', account_type=FinancialAccount.AccountType.CASHBOX,
        )

        cls.pm_cash_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Cash A',
            method_type=PaymentMethod.MethodType.CASH,
        )
        cls.pm_card_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Card A',
            method_type=PaymentMethod.MethodType.CARD,
        )

        cls.cust_a = Customer.objects.create(
            tenant=cls.tenant_a, name='Acme',
            opening_balance=Decimal('100.00'),
        )
        cls.sup_a = Supplier.objects.create(
            tenant=cls.tenant_a, name='Beans Co',
            opening_balance=Decimal('200.00'),
        )


# ── Branch required at service layer ────────────────────────────────────────

class BranchRequiredAtServiceLayerTests(_Fixture, APITestCase):

    def test_customer_receipt_service_rejects_none_branch(self):
        with self.assertRaises(crsvc.CustomerReceiptError) as ctx:
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=None,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )
        self.assertIn('branch is required', str(ctx.exception).lower())

    def test_supplier_payment_service_rejects_none_branch(self):
        with self.assertRaises(spsvc.SupplierPaymentError) as ctx:
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=None,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )
        self.assertIn('branch is required', str(ctx.exception).lower())


# ── Branch required at API layer ────────────────────────────────────────────

class BranchRequiredAtApiLayerTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_customer_receipt_post_without_branch_returns_400(self):
        payload = {
            # 'branch' deliberately omitted
            'customer':            self.cust_a.id,
            'payment_method':      self.pm_cash_a.id,
            'destination_account': self.cashbox_a.id,
            'amount':              '12.00',
        }
        resp = self.client.post(
            '/api/customer-receipts/', payload,
            format='json', **_idem_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_supplier_payment_post_without_branch_returns_400(self):
        payload = {
            # 'branch' deliberately omitted
            'supplier':       self.sup_a.id,
            'payment_method': self.pm_cash_a.id,
            'source_account': self.cashbox_a.id,
            'amount':         '12.00',
        }
        resp = self.client.post(
            '/api/supplier-payments/', payload,
            format='json', **_idem_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_receipt_post_with_blank_branch_returns_400(self):
        payload = {
            'branch':              '',
            'customer':            self.cust_a.id,
            'payment_method':      self.pm_cash_a.id,
            'destination_account': self.cashbox_a.id,
            'amount':              '12.00',
        }
        resp = self.client.post(
            '/api/customer-receipts/', payload,
            format='json', **_idem_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ── Document + ledger pair branch consistency ───────────────────────────────

class BranchConsistencyTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_customer_receipt_stores_same_branch_on_all_three_rows(self):
        payload = {
            'branch':              self.branch_a.id,
            'customer':            self.cust_a.id,
            'payment_method':      self.pm_cash_a.id,
            'destination_account': self.cashbox_a.id,
            'amount':              '25.00',
        }
        resp = self.client.post(
            '/api/customer-receipts/', payload,
            format='json', **_idem_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        receipt = CustomerReceipt.objects.get(pk=resp.json()['id'])

        ar_row = CustomerARMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        self.assertEqual(receipt.branch_id, self.branch_a.id)
        self.assertEqual(ar_row.branch_id,  self.branch_a.id)
        self.assertEqual(fa_row.branch_id,  self.branch_a.id)

    def test_supplier_payment_stores_same_branch_on_all_three_rows(self):
        payload = {
            'branch':         self.branch_a.id,
            'supplier':       self.sup_a.id,
            'payment_method': self.pm_cash_a.id,
            'source_account': self.cashbox_a.id,
            'amount':         '25.00',
        }
        resp = self.client.post(
            '/api/supplier-payments/', payload,
            format='json', **_idem_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        payment = SupplierPayment.objects.get(pk=resp.json()['id'])

        ap_row = SupplierAPMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        self.assertEqual(payment.branch_id, self.branch_a.id)
        self.assertEqual(ap_row.branch_id,  self.branch_a.id)
        self.assertEqual(fa_row.branch_id,  self.branch_a.id)


# ── Currency default ────────────────────────────────────────────────────────

class MovementCurrencyDefaultTests(_Fixture, APITestCase):

    def test_customer_ar_movement_uses_tenant_currency(self):
        # Tenant.currency defaults to 'EGP' (see Tenant model field).
        self.assertEqual(self.tenant_a.currency, 'EGP')

        mvmt = ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('10.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.currency, 'EGP')

    def test_supplier_ap_movement_uses_tenant_currency(self):
        self.assertEqual(self.tenant_a.currency, 'EGP')
        mvmt = ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('10.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.currency, 'EGP')

    def test_customer_receipt_writes_ar_movement_with_tenant_currency(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a,
            payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a,
            amount=Decimal('20.00'),
        )
        ar_row = CustomerARMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        self.assertEqual(ar_row.currency, 'EGP')

    def test_supplier_payment_writes_ap_movement_with_tenant_currency(self):
        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=self.branch_a,
            supplier=self.sup_a,
            payment_method=self.pm_cash_a,
            source_account=self.cashbox_a,
            amount=Decimal('20.00'),
        )
        ap_row = SupplierAPMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        self.assertEqual(ap_row.currency, 'EGP')


# ── Idempotency required ────────────────────────────────────────────────────

class IdempotencyRequiredTests(_Fixture, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def _customer_payload(self):
        return {
            'branch':              self.branch_a.id,
            'customer':            self.cust_a.id,
            'payment_method':      self.pm_cash_a.id,
            'destination_account': self.cashbox_a.id,
            'amount':              '15.00',
        }

    def _supplier_payload(self):
        return {
            'branch':         self.branch_a.id,
            'supplier':       self.sup_a.id,
            'payment_method': self.pm_cash_a.id,
            'source_account': self.cashbox_a.id,
            'amount':         '15.00',
        }

    def test_customer_receipt_missing_key_returns_400(self):
        resp = self.client.post(
            '/api/customer-receipts/', self._customer_payload(), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.json()['error']['code'], 'IDEMPOTENCY_KEY_REQUIRED',
        )
        # And nothing was posted.
        self.assertFalse(CustomerReceipt.objects.exists())
        self.assertFalse(CustomerARMovement.objects.exists())
        self.assertFalse(FinancialAccountMovement.objects.exists())

    def test_customer_receipt_blank_key_returns_400(self):
        resp = self.client.post(
            '/api/customer-receipts/', self._customer_payload(),
            format='json', HTTP_IDEMPOTENCY_KEY='   ',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_supplier_payment_missing_key_returns_400(self):
        resp = self.client.post(
            '/api/supplier-payments/', self._supplier_payload(), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.json()['error']['code'], 'IDEMPOTENCY_KEY_REQUIRED',
        )

    def test_customer_receipt_same_key_same_body_creates_only_one_document(self):
        headers = _idem_headers('rcpt-once')
        payload = self._customer_payload()

        r1 = self.client.post(
            '/api/customer-receipts/', payload, format='json', **headers,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        first_id = r1.json()['id']

        r2 = self.client.post(
            '/api/customer-receipts/', payload, format='json', **headers,
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.json()['id'], first_id)

        # Exactly one document + one AR row + one finance row.
        self.assertEqual(
            CustomerReceipt.objects.filter(tenant=self.tenant_a).count(), 1,
        )
        self.assertEqual(
            CustomerARMovement.objects.filter(
                source_document_type='CustomerReceipt',
                source_document_id=first_id,
            ).count(),
            1,
        )
        self.assertEqual(
            FinancialAccountMovement.objects.filter(
                source_document_type='CustomerReceipt',
                source_document_id=first_id,
            ).count(),
            1,
        )

    def test_supplier_payment_same_key_same_body_creates_only_one_document(self):
        headers = _idem_headers('pay-once')
        payload = self._supplier_payload()

        r1 = self.client.post(
            '/api/supplier-payments/', payload, format='json', **headers,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        first_id = r1.json()['id']

        r2 = self.client.post(
            '/api/supplier-payments/', payload, format='json', **headers,
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.json()['id'], first_id)

        self.assertEqual(
            SupplierPayment.objects.filter(tenant=self.tenant_a).count(), 1,
        )
        self.assertEqual(
            SupplierAPMovement.objects.filter(
                source_document_type='SupplierPayment',
                source_document_id=first_id,
            ).count(),
            1,
        )
        self.assertEqual(
            FinancialAccountMovement.objects.filter(
                source_document_type='SupplierPayment',
                source_document_id=first_id,
            ).count(),
            1,
        )

    def test_customer_receipt_same_key_different_body_returns_409(self):
        headers = _idem_headers('rcpt-collide')
        r1 = self.client.post(
            '/api/customer-receipts/',
            {**self._customer_payload(), 'amount': '5.00'},
            format='json', **headers,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(
            '/api/customer-receipts/',
            {**self._customer_payload(), 'amount': '7.00'},
            format='json', **headers,
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)

    def test_supplier_payment_same_key_different_body_returns_409(self):
        headers = _idem_headers('pay-collide')
        r1 = self.client.post(
            '/api/supplier-payments/',
            {**self._supplier_payload(), 'amount': '5.00'},
            format='json', **headers,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(
            '/api/supplier-payments/',
            {**self._supplier_payload(), 'amount': '7.00'},
            format='json', **headers,
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)


# ── BranchPaymentMethod default behavior (documented limitation) ────────────

class BranchPaymentMethodDefaultBehaviorTests(_Fixture, APITestCase):
    """Documents the *current* behavior — multiple is_default=True rows
    are NOT prevented today. A future slice should either:
        * enforce a partial unique constraint
          (tenant, branch, method_type, is_default=True), or
        * auto-flip prior defaults to False at the serializer layer.
    For now we capture the limitation so a future fix has a concrete
    regression target.
    """

    def setUp(self):
        # Need a destination account that matches the method type rules.
        # Cash → cashbox_a (already in the fixture).
        self.bpm1 = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a,
            is_default=True,
        )
        self.bpm2 = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_card_a,
            destination_account=FinancialAccount.objects.create(
                tenant=self.tenant_a, branch=self.branch_a,
                name='Card Settle A',
                account_type=FinancialAccount.AccountType.CARD_SETTLEMENT,
            ),
            is_default=True,
        )

    def test_multiple_default_branch_payment_methods_currently_allowed(self):
        # Today: nothing prevents two rows on the same branch from both
        # carrying is_default=True. A future hardening slice should fix
        # this; this test exists so the fix can flip the assertion.
        defaults = BranchPaymentMethod.objects.filter(
            tenant=self.tenant_a, branch=self.branch_a, is_default=True,
        ).count()
        self.assertEqual(defaults, 2)
