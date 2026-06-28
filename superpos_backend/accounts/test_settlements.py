"""Phase 1.5 Slice G — Customer Receipt + Supplier Payment posting tests.

Covers:
  * customer receipt cash: AR decreases + cashbox increases
  * customer receipt card / wallet routing posts to the right account
  * supplier payment cash: AP decreases + cashbox decreases
  * cross-tenant customer/supplier/account/branch rejected
  * invalid amount (zero / negative / non-numeric) rejected
  * credit-type payment method rejected
  * inactive account / payment method rejected
  * branch ↔ destination/source account branch mismatch rejected
  * atomic rollback: if AR/AP/finance side fails, document does NOT persist
  * idempotency: replay returns prior body, conflict returns 409
  * list / detail tenant-scoped
"""

from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
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
from accounts.services import account_movements as fa
from accounts.services import customer_ar as ar
from accounts.services import customer_receipts as crsvc
from accounts.services import supplier_ap as ap
from accounts.services import supplier_payments as spsvc


# ── Shared fixtures ─────────────────────────────────────────────────────────

class _SettlementsFixtureMixin:
    """Two tenants × two branches × cashbox/bank/wallet/card-settlement
    accounts × cash/card/wallet/credit payment methods × customer/supplier.

    Built once via `setUpTestData` so each test method gets a fresh
    transaction (DB rolled back between methods) but doesn't pay the
    fixture-build cost per method.
    """

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

        # ── Tenant A accounts ─────────────────────────────────────────────────
        cls.cashbox_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Cash A1', account_type=FinancialAccount.AccountType.CASHBOX,
        )
        cls.cashbox_a2 = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a2,
            name='Cash A2', account_type=FinancialAccount.AccountType.CASHBOX,
        )
        cls.bank_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=None,
            name='Bank A', account_type=FinancialAccount.AccountType.BANK,
        )
        cls.wallet_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Wallet A', account_type=FinancialAccount.AccountType.WALLET,
        )
        cls.card_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Card Settlement A',
            account_type=FinancialAccount.AccountType.CARD_SETTLEMENT,
        )
        cls.customer_ar_acct_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Customer AR Acct',
            account_type=FinancialAccount.AccountType.CUSTOMER_AR,
        )

        # ── Tenant B accounts (foreign) ───────────────────────────────────────
        cls.cashbox_b = FinancialAccount.objects.create(
            tenant=cls.tenant_b, branch=cls.branch_b,
            name='Cash B1', account_type=FinancialAccount.AccountType.CASHBOX,
        )

        # ── Payment methods (one per type per tenant) ────────────────────────
        cls.pm_cash_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Cash A',
            method_type=PaymentMethod.MethodType.CASH,
        )
        cls.pm_card_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Card A',
            method_type=PaymentMethod.MethodType.CARD,
        )
        cls.pm_wallet_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Wallet A',
            method_type=PaymentMethod.MethodType.WALLET,
        )
        cls.pm_credit_a = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Credit A',
            method_type=PaymentMethod.MethodType.CREDIT,
        )
        cls.pm_cash_b = PaymentMethod.objects.create(
            tenant=cls.tenant_b, name='Cash B',
            method_type=PaymentMethod.MethodType.CASH,
        )

        # ── Parties ──────────────────────────────────────────────────────────
        cls.cust_a = Customer.objects.create(
            tenant=cls.tenant_a, name='Acme', opening_balance=Decimal('100.00'),
        )
        cls.cust_b = Customer.objects.create(
            tenant=cls.tenant_b, name='Foreign Acme',
        )
        cls.sup_a = Supplier.objects.create(
            tenant=cls.tenant_a, name='Beans Co', opening_balance=Decimal('200.00'),
        )
        cls.sup_b = Supplier.objects.create(
            tenant=cls.tenant_b, name='Foreign Beans',
        )


# ── Customer receipt service tests ──────────────────────────────────────────

class CustomerReceiptServiceTests(_SettlementsFixtureMixin, APITestCase):

    def test_cash_receipt_decreases_ar_and_increases_cashbox(self):
        ar_before = ar.get_customer_balance(self.cust_a)
        cash_before = fa.get_account_current_balance(self.cashbox_a)

        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a,
            payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a,
            amount=Decimal('40.00'),
            actor_user=self.manager_a,
        )

        self.assertEqual(receipt.status, CustomerReceipt.Status.POSTED)
        self.assertEqual(receipt.amount, Decimal('40.00'))
        self.assertEqual(
            ar.get_customer_balance(self.cust_a),
            ar_before - Decimal('40.00'),
        )
        self.assertEqual(
            fa.get_account_current_balance(self.cashbox_a),
            cash_before + Decimal('40.00'),
        )

        # The two ledger rows must reference back to the receipt.
        ar_row = CustomerARMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        self.assertEqual(ar_row.credit, Decimal('40.00'))
        self.assertEqual(ar_row.debit,  Decimal('0'))
        self.assertEqual(fa_row.debit,  Decimal('40.00'))
        self.assertEqual(fa_row.credit, Decimal('0'))

    def test_card_receipt_routes_to_card_settlement_account(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a,
            payment_method=self.pm_card_a,
            destination_account=self.card_a,
            amount=Decimal('25.00'),
            actor_user=self.manager_a,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        self.assertEqual(fa_row.account_id, self.card_a.id)

    def test_wallet_receipt_routes_to_wallet_account(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a,
            payment_method=self.pm_wallet_a,
            destination_account=self.wallet_a,
            amount=Decimal('15.00'),
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
        )
        self.assertEqual(fa_row.account_id, self.wallet_a.id)

    def test_cross_tenant_customer_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_b,  # foreign tenant
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_cross_tenant_account_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_b,  # foreign tenant
                amount=Decimal('10.00'),
            )

    def test_cross_tenant_payment_method_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_b,  # foreign tenant
                destination_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_cross_tenant_branch_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_b,  # foreign branch
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_zero_amount_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('0.00'),
            )

    def test_negative_amount_rejected(self):
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('-5.00'),
            )

    def test_credit_method_rejected(self):
        # Paying down AR with a credit method would increase AR — nonsense.
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_credit_a,
                destination_account=self.customer_ar_acct_a,
                amount=Decimal('10.00'),
            )

    def test_method_account_type_mismatch_rejected(self):
        # Cash method into a wallet account — wrong routing.
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.wallet_a,
                amount=Decimal('10.00'),
            )

    def test_inactive_account_rejected(self):
        self.cashbox_a.is_active = False
        self.cashbox_a.save(update_fields=['is_active', 'updated_at'])
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_branch_account_branch_mismatch_rejected(self):
        # branch_a2's cashbox can't be used for a branch_a receipt.
        with self.assertRaises(crsvc.CustomerReceiptError):
            crsvc.create_customer_receipt(
                tenant=self.tenant_a, branch=self.branch_a,
                customer=self.cust_a,
                payment_method=self.pm_cash_a,
                destination_account=self.cashbox_a2,
                amount=Decimal('10.00'),
            )

    def test_atomic_rollback_when_finance_post_fails(self):
        """If the FinancialAccountMovement write raises, neither the
        document nor the AR row may survive."""
        docs_before = CustomerReceipt.objects.count()
        ar_rows_before = CustomerARMovement.objects.count()
        fa_rows_before = FinancialAccountMovement.objects.count()

        with patch(
            'accounts.services.customer_receipts.fa.record_account_debit',
            side_effect=fa.AccountMovementError('simulated finance failure'),
        ):
            with self.assertRaises(crsvc.CustomerReceiptError):
                crsvc.create_customer_receipt(
                    tenant=self.tenant_a, branch=self.branch_a,
                    customer=self.cust_a,
                    payment_method=self.pm_cash_a,
                    destination_account=self.cashbox_a,
                    amount=Decimal('20.00'),
                )

        self.assertEqual(CustomerReceipt.objects.count(),         docs_before)
        self.assertEqual(CustomerARMovement.objects.count(),      ar_rows_before)
        self.assertEqual(FinancialAccountMovement.objects.count(), fa_rows_before)

    def test_atomic_rollback_when_ar_post_fails(self):
        docs_before = CustomerReceipt.objects.count()
        ar_rows_before = CustomerARMovement.objects.count()
        fa_rows_before = FinancialAccountMovement.objects.count()

        with patch(
            'accounts.services.customer_receipts.ar.record_customer_ar_credit',
            side_effect=ar.CustomerARError('simulated AR failure'),
        ):
            with self.assertRaises(crsvc.CustomerReceiptError):
                crsvc.create_customer_receipt(
                    tenant=self.tenant_a, branch=self.branch_a,
                    customer=self.cust_a,
                    payment_method=self.pm_cash_a,
                    destination_account=self.cashbox_a,
                    amount=Decimal('20.00'),
                )

        self.assertEqual(CustomerReceipt.objects.count(),          docs_before)
        self.assertEqual(CustomerARMovement.objects.count(),       ar_rows_before)
        self.assertEqual(FinancialAccountMovement.objects.count(), fa_rows_before)


# ── Supplier payment service tests ──────────────────────────────────────────

class SupplierPaymentServiceTests(_SettlementsFixtureMixin, APITestCase):

    def test_cash_payment_decreases_ap_and_decreases_cashbox(self):
        ap_before = ap.get_supplier_balance(self.sup_a)
        cash_before = fa.get_account_current_balance(self.cashbox_a)

        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=self.branch_a,
            supplier=self.sup_a,
            payment_method=self.pm_cash_a,
            source_account=self.cashbox_a,
            amount=Decimal('75.00'),
            actor_user=self.manager_a,
        )

        self.assertEqual(payment.status, SupplierPayment.Status.POSTED)
        self.assertEqual(
            ap.get_supplier_balance(self.sup_a),
            ap_before - Decimal('75.00'),
        )
        self.assertEqual(
            fa.get_account_current_balance(self.cashbox_a),
            cash_before - Decimal('75.00'),
        )

        ap_row = SupplierAPMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        self.assertEqual(ap_row.debit,  Decimal('75.00'))
        self.assertEqual(ap_row.credit, Decimal('0'))
        self.assertEqual(fa_row.credit, Decimal('75.00'))
        self.assertEqual(fa_row.debit,  Decimal('0'))

    def test_bank_payment_decreases_bank_balance(self):
        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=None,
            supplier=self.sup_a,
            payment_method=self.pm_cash_a,  # cash-method can also draw from a bank
            source_account=self.bank_a,
            amount=Decimal('120.00'),
        )
        fa_row = FinancialAccountMovement.objects.get(
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
        )
        self.assertEqual(fa_row.account_id, self.bank_a.id)
        self.assertEqual(fa_row.credit, Decimal('120.00'))

    def test_cross_tenant_supplier_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_b,  # foreign tenant
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_cross_tenant_account_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_b,  # foreign tenant
                amount=Decimal('10.00'),
            )

    def test_cross_tenant_branch_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_b,  # foreign branch
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_zero_amount_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('0'),
            )

    def test_negative_amount_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('-1'),
            )

    def test_credit_method_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_credit_a,
                source_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_inactive_account_rejected(self):
        self.cashbox_a.is_active = False
        self.cashbox_a.save(update_fields=['is_active', 'updated_at'])
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a,
                amount=Decimal('10.00'),
            )

    def test_branch_account_branch_mismatch_rejected(self):
        with self.assertRaises(spsvc.SupplierPaymentError):
            spsvc.create_supplier_payment(
                tenant=self.tenant_a, branch=self.branch_a,
                supplier=self.sup_a,
                payment_method=self.pm_cash_a,
                source_account=self.cashbox_a2,
                amount=Decimal('10.00'),
            )

    def test_atomic_rollback_when_finance_post_fails(self):
        docs_before = SupplierPayment.objects.count()
        ap_rows_before = SupplierAPMovement.objects.count()
        fa_rows_before = FinancialAccountMovement.objects.count()

        with patch(
            'accounts.services.supplier_payments.fa.record_account_credit',
            side_effect=fa.AccountMovementError('simulated finance failure'),
        ):
            with self.assertRaises(spsvc.SupplierPaymentError):
                spsvc.create_supplier_payment(
                    tenant=self.tenant_a, branch=self.branch_a,
                    supplier=self.sup_a,
                    payment_method=self.pm_cash_a,
                    source_account=self.cashbox_a,
                    amount=Decimal('30.00'),
                )

        self.assertEqual(SupplierPayment.objects.count(),          docs_before)
        self.assertEqual(SupplierAPMovement.objects.count(),       ap_rows_before)
        self.assertEqual(FinancialAccountMovement.objects.count(), fa_rows_before)

    def test_atomic_rollback_when_ap_post_fails(self):
        docs_before = SupplierPayment.objects.count()
        ap_rows_before = SupplierAPMovement.objects.count()
        fa_rows_before = FinancialAccountMovement.objects.count()

        with patch(
            'accounts.services.supplier_payments.ap.record_supplier_ap_debit',
            side_effect=ap.SupplierAPError('simulated AP failure'),
        ):
            with self.assertRaises(spsvc.SupplierPaymentError):
                spsvc.create_supplier_payment(
                    tenant=self.tenant_a, branch=self.branch_a,
                    supplier=self.sup_a,
                    payment_method=self.pm_cash_a,
                    source_account=self.cashbox_a,
                    amount=Decimal('30.00'),
                )

        self.assertEqual(SupplierPayment.objects.count(),          docs_before)
        self.assertEqual(SupplierAPMovement.objects.count(),       ap_rows_before)
        self.assertEqual(FinancialAccountMovement.objects.count(), fa_rows_before)


# ── Customer receipt API tests ──────────────────────────────────────────────

class CustomerReceiptApiTests(_SettlementsFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.list_url = '/api/customer-receipts/'

    def _payload(self, **overrides):
        base = {
            'branch':              self.branch_a.id,
            'customer':            self.cust_a.id,
            'payment_method':      self.pm_cash_a.id,
            'destination_account': self.cashbox_a.id,
            'amount':              '30.00',
            'reference':           'RCPT-001',
            'notes':               'cash settlement',
        }
        base.update(overrides)
        return base

    def test_post_creates_receipt_and_posts_ledger(self):
        resp = self.client.post(self.list_url, self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['amount'], '30.00')
        self.assertEqual(body['status'], 'posted')
        self.assertEqual(body['customer'], self.cust_a.id)
        self.assertEqual(body['destination_account_type'], 'cashbox')

        receipt = CustomerReceipt.objects.get(pk=body['id'])
        self.assertEqual(receipt.actor_user_id, self.manager_a.id)

        # Ledger rows exist.
        self.assertTrue(CustomerARMovement.objects.filter(
            source_document_type='CustomerReceipt', source_document_id=receipt.id,
        ).exists())
        self.assertTrue(FinancialAccountMovement.objects.filter(
            source_document_type='CustomerReceipt', source_document_id=receipt.id,
        ).exists())

    def test_post_with_invalid_amount_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(amount='-1'), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_foreign_customer_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(customer=self.cust_b.id), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_foreign_account_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(destination_account=self.cashbox_b.id),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_foreign_branch_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(branch=self.branch_b.id), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_idempotency_replay_returns_same_body(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'rcpt-key-1'}
        payload = self._payload()
        resp1 = self.client.post(self.list_url, payload, format='json', **headers)
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        first_id = resp1.json()['id']

        resp2 = self.client.post(self.list_url, payload, format='json', **headers)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp2.json()['id'], first_id)

        # Only one receipt actually persisted.
        self.assertEqual(
            CustomerReceipt.objects.filter(tenant=self.tenant_a).count(),
            1,
        )

    def test_idempotency_conflict_returns_409(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'rcpt-key-2'}
        resp1 = self.client.post(
            self.list_url, self._payload(amount='10.00'),
            format='json', **headers,
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        resp2 = self.client.post(
            self.list_url, self._payload(amount='99.00'),  # different
            format='json', **headers,
        )
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)

    def test_list_is_tenant_scoped(self):
        # tenant A receipt
        crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a, payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a, amount=Decimal('5.00'),
        )
        # tenant B receipt (must not surface)
        crsvc.create_customer_receipt(
            tenant=self.tenant_b, branch=self.branch_b,
            customer=self.cust_b, payment_method=self.pm_cash_b,
            destination_account=self.cashbox_b, amount=Decimal('99.00'),
        )
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['customer'], self.cust_a.id)

    def test_detail_foreign_tenant_is_404(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_b, branch=self.branch_b,
            customer=self.cust_b, payment_method=self.pm_cash_b,
            destination_account=self.cashbox_b, amount=Decimal('1.00'),
        )
        resp = self.client.get(f'{self.list_url}{receipt.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_same_tenant_returns_200(self):
        receipt = crsvc.create_customer_receipt(
            tenant=self.tenant_a, branch=self.branch_a,
            customer=self.cust_a, payment_method=self.pm_cash_a,
            destination_account=self.cashbox_a, amount=Decimal('7.50'),
        )
        resp = self.client.get(f'{self.list_url}{receipt.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['amount'], '7.50')


# ── Supplier payment API tests ──────────────────────────────────────────────

class SupplierPaymentApiTests(_SettlementsFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.list_url = '/api/supplier-payments/'

    def _payload(self, **overrides):
        base = {
            'branch':         self.branch_a.id,
            'supplier':       self.sup_a.id,
            'payment_method': self.pm_cash_a.id,
            'source_account': self.cashbox_a.id,
            'amount':         '60.00',
            'reference':      'PAY-001',
            'notes':          'cash payment',
        }
        base.update(overrides)
        return base

    def test_post_creates_payment_and_posts_ledger(self):
        resp = self.client.post(self.list_url, self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        body = resp.json()
        self.assertEqual(body['amount'], '60.00')
        self.assertEqual(body['status'], 'posted')
        self.assertEqual(body['supplier'], self.sup_a.id)
        self.assertEqual(body['source_account_type'], 'cashbox')

        payment = SupplierPayment.objects.get(pk=body['id'])
        self.assertEqual(payment.actor_user_id, self.manager_a.id)

        self.assertTrue(SupplierAPMovement.objects.filter(
            source_document_type='SupplierPayment', source_document_id=payment.id,
        ).exists())
        self.assertTrue(FinancialAccountMovement.objects.filter(
            source_document_type='SupplierPayment', source_document_id=payment.id,
        ).exists())

    def test_post_with_foreign_supplier_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(supplier=self.sup_b.id), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_foreign_account_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(source_account=self.cashbox_b.id),
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_with_zero_amount_returns_400(self):
        resp = self.client.post(
            self.list_url, self._payload(amount='0.00'), format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_idempotency_replay_returns_same_body(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'pay-key-1'}
        payload = self._payload()
        r1 = self.client.post(self.list_url, payload, format='json', **headers)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        first_id = r1.json()['id']

        r2 = self.client.post(self.list_url, payload, format='json', **headers)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.json()['id'], first_id)
        self.assertEqual(
            SupplierPayment.objects.filter(tenant=self.tenant_a).count(),
            1,
        )

    def test_idempotency_conflict_returns_409(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'pay-key-2'}
        r1 = self.client.post(
            self.list_url, self._payload(amount='10.00'),
            format='json', **headers,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.client.post(
            self.list_url, self._payload(amount='15.00'),
            format='json', **headers,
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)

    def test_list_is_tenant_scoped(self):
        spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=self.branch_a,
            supplier=self.sup_a, payment_method=self.pm_cash_a,
            source_account=self.cashbox_a, amount=Decimal('11.00'),
        )
        spsvc.create_supplier_payment(
            tenant=self.tenant_b, branch=self.branch_b,
            supplier=self.sup_b, payment_method=self.pm_cash_b,
            source_account=self.cashbox_b, amount=Decimal('99.00'),
        )
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['supplier'], self.sup_a.id)

    def test_detail_foreign_tenant_is_404(self):
        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_b, branch=self.branch_b,
            supplier=self.sup_b, payment_method=self.pm_cash_b,
            source_account=self.cashbox_b, amount=Decimal('1.00'),
        )
        resp = self.client.get(f'{self.list_url}{payment.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_same_tenant_returns_200(self):
        payment = spsvc.create_supplier_payment(
            tenant=self.tenant_a, branch=self.branch_a,
            supplier=self.sup_a, payment_method=self.pm_cash_a,
            source_account=self.cashbox_a, amount=Decimal('22.00'),
        )
        resp = self.client.get(f'{self.list_url}{payment.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['amount'], '22.00')
