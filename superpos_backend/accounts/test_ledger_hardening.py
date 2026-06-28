"""Hardening slice — balance_before population + statement summary tests.

Covers:
  * FinancialAccountMovement stores correct balance_before / balance_after.
  * CustomerARMovement first row balance_before == Customer.opening_balance.
  * SupplierAPMovement first row balance_before == Supplier.opening_balance.
  * Subsequent rows: balance_before == previous balance_after.
  * Asset vs liability sign rule applied correctly to balance_after.
  * CustomerReceipt posting populates AR balance_before/after AND finance
    balance_before/after coherently.
  * SupplierPayment posting populates AP balance_before/after AND finance
    balance_before/after coherently.
  * Statement summary envelope returns opening_balance, totals, net_change,
    closing_balance, date_from, date_to, filters, movements.
  * date_from/date_to filtering works (uses date_to to bound the window).
  * Tenant isolation: foreign-tenant ids still 404 on the statement view.
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    Customer,
    CustomerARMovement,
    FinancialAccount,
    FinancialAccountMovement,
    PaymentMethod,
    Supplier,
    SupplierAPMovement,
    Tenant,
    User,
)
from accounts.services import account_movements as fa
from accounts.services import customer_ar as ar
from accounts.services import customer_receipts as crsvc
from accounts.services import supplier_ap as ap
from accounts.services import supplier_payments as spsvc


class _LedgerFixtureMixin:
    @classmethod
    def setUpTestData(cls):
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
            opening_balance=Decimal('50.00'),
        )
        cls.ap_acct_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Supplier AP Acct',
            account_type=FinancialAccount.AccountType.SUPPLIER_AP,
            opening_balance=Decimal('0.00'),
        )

        cls.pm_cash_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Cash A',
            method_type=PaymentMethod.MethodType.CASH,
        )

        cls.cust_a = Customer.objects.create(
            tenant=cls.tenant_a, name='Acme',
            opening_balance=Decimal('100.00'),
        )
        cls.cust_b = Customer.objects.create(
            tenant=cls.tenant_b, name='Foreign Acme',
        )
        cls.sup_a = Supplier.objects.create(
            tenant=cls.tenant_a, name='Beans Co',
            opening_balance=Decimal('200.00'),
        )
        cls.sup_b = Supplier.objects.create(
            tenant=cls.tenant_b, name='Foreign Beans',
        )


# ── FinancialAccountMovement before/after ───────────────────────────────────

class FinancialAccountBalanceBeforeTests(_LedgerFixtureMixin, APITestCase):

    def test_first_movement_balance_before_uses_opening_balance(self):
        mvmt = fa.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10.00'),
            movement_type=fa.MovementType.CASH_IN,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.balance_before, Decimal('50.00'))
        self.assertEqual(mvmt.balance_after,  Decimal('60.00'))

    def test_subsequent_movement_balance_before_is_prior_balance_after(self):
        m1 = fa.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10.00'),
            movement_type=fa.MovementType.CASH_IN,
            branch=self.branch_a,
        )
        m2 = fa.record_account_credit(
            account=self.cashbox_a, amount=Decimal('4.00'),
            movement_type=fa.MovementType.CASH_OUT,
            branch=self.branch_a,
        )
        self.assertEqual(m2.balance_before, m1.balance_after)
        self.assertEqual(m2.balance_after,  Decimal('56.00'))

    def test_liability_account_sign_rule_for_balance_after(self):
        # Supplier AP is liability-like: credit increases balance.
        m1 = fa.record_account_credit(
            account=self.ap_acct_a, amount=Decimal('80.00'),
            movement_type=fa.MovementType.SUPPLIER_AP_INCREASE,
            branch=self.branch_a,
        )
        self.assertEqual(m1.balance_before, Decimal('0.00'))
        self.assertEqual(m1.balance_after,  Decimal('80.00'))


# ── CustomerARMovement before/after ─────────────────────────────────────────

class CustomerARBalanceBeforeTests(_LedgerFixtureMixin, APITestCase):

    def test_first_movement_balance_before_equals_opening_balance(self):
        mvmt = ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('30.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.balance_before, Decimal('100.00'))
        self.assertEqual(mvmt.balance_after,  Decimal('130.00'))

    def test_credit_decreases_balance_after_and_balance_before_chains(self):
        m1 = ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('40.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
        )
        m2 = ar.record_customer_ar_credit(
            customer=self.cust_a, amount=Decimal('25.00'),
            movement_type=ar.MovementType.CUSTOMER_RECEIPT,
            branch=self.branch_a,
        )
        self.assertEqual(m2.balance_before, m1.balance_after)
        # 100 + 40 - 25 = 115
        self.assertEqual(m2.balance_after,  Decimal('115.00'))


# ── SupplierAPMovement before/after ─────────────────────────────────────────

class SupplierAPBalanceBeforeTests(_LedgerFixtureMixin, APITestCase):

    def test_first_movement_balance_before_equals_opening_balance(self):
        mvmt = ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('50.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
        )
        self.assertEqual(mvmt.balance_before, Decimal('200.00'))
        self.assertEqual(mvmt.balance_after,  Decimal('250.00'))

    def test_debit_decreases_balance_after_for_liability_party(self):
        m1 = ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('100.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
        )
        m2 = ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('60.00'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
        )
        self.assertEqual(m2.balance_before, m1.balance_after)
        # 200 + 100 - 60 = 240
        self.assertEqual(m2.balance_after,  Decimal('240.00'))


# ── Cross-document: receipt + payment populate both ledgers correctly ──────

class CustomerReceiptBalanceFieldsTests(_LedgerFixtureMixin, APITestCase):

    def test_receipt_populates_ar_and_finance_before_after(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a,
            payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a,
            amount=Decimal('40.00'),
            actor_user=self.manager_a,
        )
        ar_row = CustomerARMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        # AR: customer pays down — credit row, balance ↓.
        self.assertEqual(ar_row.balance_before, Decimal('100.00'))
        self.assertEqual(ar_row.balance_after,  Decimal('60.00'))
        # Finance: cash flows in — debit row, balance ↑.
        self.assertEqual(fa_row.balance_before, Decimal('50.00'))
        self.assertEqual(fa_row.balance_after,  Decimal('90.00'))


class SupplierPaymentBalanceFieldsTests(_LedgerFixtureMixin, APITestCase):

    def test_payment_populates_ap_and_finance_before_after(self):
        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=self.branch_a,
            supplier=self.sup_a,
            payment_method=self.pm_cash_a,
            source_account=self.cashbox_a,
            amount=Decimal('30.00'),
            actor_user=self.manager_a,
        )
        ap_row = SupplierAPMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        # AP: we pay supplier — debit row, balance ↓.
        self.assertEqual(ap_row.balance_before, Decimal('200.00'))
        self.assertEqual(ap_row.balance_after,  Decimal('170.00'))
        # Finance: cash flows out — credit row, balance ↓.
        self.assertEqual(fa_row.balance_before, Decimal('50.00'))
        self.assertEqual(fa_row.balance_after,  Decimal('20.00'))


# ── Statement summary envelope ──────────────────────────────────────────────

class FinancialAccountStatementSummaryTests(_LedgerFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = f'/api/finance/accounts/{self.cashbox_a.id}/movements/'

    def _post_two_movements(self):
        fa.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10.00'),
            movement_type=fa.MovementType.CASH_IN,
            branch=self.branch_a,
        )
        fa.record_account_credit(
            account=self.cashbox_a, amount=Decimal('3.00'),
            movement_type=fa.MovementType.CASH_OUT,
            branch=self.branch_a,
        )

    def test_summary_envelope_shape(self):
        self._post_two_movements()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        for key in (
            'opening_balance', 'total_debit', 'total_credit', 'net_change',
            'closing_balance', 'date_from', 'date_to', 'filters', 'movements',
        ):
            self.assertIn(key, body, f'missing key {key!r}')
        self.assertEqual(body['opening_balance'], '50.00')
        self.assertEqual(body['total_debit'],     '10.00')
        self.assertEqual(body['total_credit'],    '3.00')
        self.assertEqual(body['net_change'],      '7.00')
        self.assertEqual(body['closing_balance'], '57.00')
        self.assertEqual(len(body['movements']),  2)
        # Each row carries balance_before + balance_after.
        first = body['movements'][0]
        self.assertEqual(first['balance_before'], '50.00')
        self.assertEqual(first['balance_after'],  '60.00')

    def test_summary_envelope_is_empty_when_no_movements(self):
        resp = self.client.get(self.url)
        body = resp.json()
        self.assertEqual(body['opening_balance'], '50.00')
        self.assertEqual(body['total_debit'],     '0.00')
        self.assertEqual(body['total_credit'],    '0.00')
        self.assertEqual(body['net_change'],      '0.00')
        self.assertEqual(body['closing_balance'], '50.00')
        self.assertEqual(body['movements'],       [])


class CustomerStatementSummaryTests(_LedgerFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = f'/api/customers/{self.cust_a.id}/statement/'

    def test_summary_envelope_with_ar_movements(self):
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('30.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
        )
        ar.record_customer_ar_credit(
            customer=self.cust_a, amount=Decimal('20.00'),
            movement_type=ar.MovementType.CUSTOMER_RECEIPT,
            branch=self.branch_a,
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['opening_balance'], '100.00')
        self.assertEqual(body['total_debit'],     '30.00')
        self.assertEqual(body['total_credit'],    '20.00')
        # AR is asset-like — net change is debit - credit.
        self.assertEqual(body['net_change'],      '10.00')
        self.assertEqual(body['closing_balance'], '110.00')
        rows = body['movements']
        self.assertEqual(rows[0]['balance_before'], '100.00')
        self.assertEqual(rows[1]['balance_before'], rows[0]['balance_after'])

    def test_foreign_customer_statement_is_404(self):
        url = f'/api/customers/{self.cust_b.id}/statement/'
        self.assertEqual(
            self.client.get(url).status_code, status.HTTP_404_NOT_FOUND,
        )


class SupplierStatementSummaryTests(_LedgerFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.url = f'/api/suppliers/{self.sup_a.id}/statement/'

    def test_summary_envelope_with_ap_movements(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('60.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
        )
        ap.record_supplier_ap_debit(
            supplier=self.sup_a, amount=Decimal('25.00'),
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=self.branch_a,
        )
        resp = self.client.get(self.url)
        body = resp.json()
        self.assertEqual(body['opening_balance'], '200.00')
        self.assertEqual(body['total_debit'],     '25.00')
        self.assertEqual(body['total_credit'],    '60.00')
        # AP is liability-like — net change is credit - debit.
        self.assertEqual(body['net_change'],      '35.00')
        self.assertEqual(body['closing_balance'], '235.00')

    def test_foreign_supplier_statement_is_404(self):
        url = f'/api/suppliers/{self.sup_b.id}/statement/'
        self.assertEqual(
            self.client.get(url).status_code, status.HTTP_404_NOT_FOUND,
        )


# ── Date filters ────────────────────────────────────────────────────────────

class StatementDateFilterTests(_LedgerFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_finance_date_to_excludes_later_movements(self):
        # Movement #1 timestamped before the cutoff.
        early_when = timezone.now() - timezone.timedelta(days=5)
        fa.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10.00'),
            movement_type=fa.MovementType.CASH_IN,
            branch=self.branch_a,
            occurred_at=early_when,
        )
        # Movement #2 timestamped after the cutoff.
        later_when = timezone.now() + timezone.timedelta(days=5)
        fa.record_account_debit(
            account=self.cashbox_a, amount=Decimal('20.00'),
            movement_type=fa.MovementType.CASH_IN,
            branch=self.branch_a,
            occurred_at=later_when,
        )
        # Date-only cutoff dodges URL encoding of the `+HH:MM` offset.
        cutoff = (timezone.now() + timezone.timedelta(days=1)).date().isoformat()
        resp = self.client.get(
            f'/api/finance/accounts/{self.cashbox_a.id}/movements/',
            {'date_to': cutoff},
        )
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_debit'], '10.00')

    def test_customer_date_from_excludes_earlier_movements(self):
        early_when = timezone.now() - timezone.timedelta(days=10)
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('5.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
            occurred_at=early_when,
        )
        # Recent movement — inside the window.
        ar.record_customer_ar_debit(
            customer=self.cust_a, amount=Decimal('15.00'),
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=self.branch_a,
        )
        cutoff = (timezone.now() - timezone.timedelta(days=1)).date().isoformat()
        resp = self.client.get(
            f'/api/customers/{self.cust_a.id}/statement/',
            {'date_from': cutoff},
        )
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_debit'], '15.00')
        # Opening for the windowed view should reflect the prior row's
        # `balance_after` (= 105) so the chain stays coherent.
        self.assertEqual(body['opening_balance'], '105.00')

    def test_supplier_actor_user_filter(self):
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('40.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            actor_user=self.manager_a,
        )
        ap.record_supplier_ap_credit(
            supplier=self.sup_a, amount=Decimal('10.00'),
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=self.branch_a,
            actor_user=None,
        )
        resp = self.client.get(
            f'/api/suppliers/{self.sup_a.id}/statement/'
            f'?actor_user={self.manager_a.id}',
        )
        body = resp.json()
        self.assertEqual(len(body['movements']), 1)
        self.assertEqual(body['total_credit'], '40.00')


# ── balance_before is read-only / non-spoofable on writable surfaces ────────

class BalanceBeforeIsReadOnlyTests(_LedgerFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_customer_receipt_post_ignores_client_supplied_balance_before(self):
        # Send a malicious value — the model has no writable
        # balance_before field exposed, so the service still computes the
        # right value from the customer's opening_balance.
        resp = self.client.post(
            '/api/customer-receipts/',
            {
                'branch':              self.branch_a.id,
                'customer':            self.cust_a.id,
                'payment_method':      self.pm_cash_a.id,
                'destination_account': self.cashbox_a.id,
                'amount':              '20.00',
                # Spoof attempts:
                'balance_before':      '99999.00',
                'balance_after':       '88888.00',
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='hardening-test-1',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        receipt_id = resp.json()['id']
        ar_row = CustomerARMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt_id,
        )
        self.assertEqual(ar_row.balance_before, Decimal('100.00'))
        self.assertEqual(ar_row.balance_after,  Decimal('80.00'))
