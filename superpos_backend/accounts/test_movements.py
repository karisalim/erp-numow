"""Phase 1.5 Slice D — FinancialAccountMovement service + API tests."""

from decimal import Decimal

from django.db.utils import IntegrityError
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    FinancialAccount,
    FinancialAccountMovement,
    Tenant,
    User,
)
from accounts.services import account_movements as svc


class _MovementsFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a = Branch.objects.create(tenant=cls.tenant_a, name='Branch A1')
        cls.branch_a2 = Branch.objects.create(tenant=cls.tenant_a, name='Branch A2')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='Branch B1')

        cls.manager_a = User.objects.create_user(
            username='mgr_a', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_a, branch=cls.branch_a,
        )
        cls.manager_b = User.objects.create_user(
            username='mgr_b', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_b, branch=cls.branch_b,
        )

        # Tenant A accounts.
        cls.cashbox_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Cashbox A', account_type='cashbox',
            currency='EGP', opening_balance=Decimal('100.00'),
        )
        cls.bank_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='Bank A', account_type='bank',
            currency='EGP', opening_balance=Decimal('0.00'),
        )
        cls.card_settle_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='Visa Settlement A',
            account_type='card_settlement', currency='EGP',
        )
        cls.wallet_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='VC A', account_type='wallet',
        )
        cls.supplier_ap_a = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='AP A', account_type='supplier_ap',
            opening_balance=Decimal('0.00'),
        )

        # Tenant B account (isolation tests).
        cls.cashbox_b = FinancialAccount.objects.create(
            tenant=cls.tenant_b, branch=cls.branch_b,
            name='Cashbox B', account_type='cashbox',
        )


# ── Service-layer tests ──────────────────────────────────────────────────────

class AccountMovementServiceTests(_MovementsFixtureMixin, APITestCase):

    def test_asset_debit_increases_cashbox_balance(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('50.00'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=1,
        )
        self.assertEqual(
            svc.get_account_current_balance(self.cashbox_a),
            Decimal('150.00'),  # 100 opening + 50 debit
        )

    def test_asset_credit_decreases_cashbox_balance(self):
        svc.record_account_credit(
            account=self.cashbox_a, amount=Decimal('30.00'),
            movement_type=svc.MovementType.CASH_OUT,
            branch=self.branch_a,
            source_document_type='CashOut', source_document_id=7,
        )
        self.assertEqual(
            svc.get_account_current_balance(self.cashbox_a),
            Decimal('70.00'),
        )

    def test_running_balance_chains_correctly(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('40.00'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=1,
        )
        svc.record_account_credit(
            account=self.cashbox_a, amount=Decimal('10.00'),
            movement_type=svc.MovementType.EXPENSE_OUT,
            branch=self.branch_a,
            source_document_type='Expense', source_document_id=2,
        )
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('5.00'),
            movement_type=svc.MovementType.CASH_IN,
            branch=self.branch_a,
            source_document_type='CashIn', source_document_id=3,
        )
        balance = svc.get_account_current_balance(self.cashbox_a)
        # opening(100) + 40 - 10 + 5 = 135
        self.assertEqual(balance, Decimal('135.00'))

        # Movements appear in id order with the correct balance_after chain.
        rows = list(self.cashbox_a.movements.order_by('id')
                                            .values_list('balance_after', flat=True))
        self.assertEqual(rows, [Decimal('140.00'), Decimal('130.00'), Decimal('135.00')])

    def test_bank_card_settlement_wallet_balances_work(self):
        # Bank: debit increases, credit decreases (asset).
        svc.record_account_debit(
            account=self.bank_a, amount=Decimal('200.00'),
            movement_type=svc.MovementType.SETTLEMENT_TO_BANK,
            source_document_type='Settlement', source_document_id=1,
        )
        self.assertEqual(svc.get_account_current_balance(self.bank_a), Decimal('200.00'))

        # Card settlement: debit (card sale in) then credit (settled to bank).
        svc.record_account_debit(
            account=self.card_settle_a, amount=Decimal('80.00'),
            movement_type=svc.MovementType.SALES_CARD_IN,
            source_document_type='Sale', source_document_id=2,
        )
        svc.record_account_credit(
            account=self.card_settle_a, amount=Decimal('80.00'),
            movement_type=svc.MovementType.SETTLEMENT_TO_BANK,
            source_document_type='Settlement', source_document_id=3,
        )
        self.assertEqual(svc.get_account_current_balance(self.card_settle_a), Decimal('0.00'))

        # Wallet: same asset rule.
        svc.record_account_debit(
            account=self.wallet_a, amount=Decimal('25.50'),
            movement_type=svc.MovementType.SALES_WALLET_IN,
            source_document_type='Sale', source_document_id=4,
        )
        self.assertEqual(svc.get_account_current_balance(self.wallet_a), Decimal('25.50'))

    def test_supplier_ap_uses_credit_as_increase(self):
        """Liability rule: credit grows AP, debit shrinks it."""
        svc.record_account_credit(
            account=self.supplier_ap_a, amount=Decimal('500.00'),
            movement_type=svc.MovementType.SUPPLIER_AP_INCREASE,
            source_document_type='Purchase', source_document_id=1,
        )
        self.assertEqual(svc.get_account_current_balance(self.supplier_ap_a), Decimal('500.00'))

        svc.record_account_debit(
            account=self.supplier_ap_a, amount=Decimal('200.00'),
            movement_type=svc.MovementType.SUPPLIER_PAYMENT_OUT,
            source_document_type='SupplierPayment', source_document_id=2,
        )
        self.assertEqual(svc.get_account_current_balance(self.supplier_ap_a), Decimal('300.00'))

    def test_invalid_pair_rejected(self):
        with self.assertRaises(svc.AccountMovementError):
            svc.record_account_movement(
                account=self.cashbox_a,
                movement_type=svc.MovementType.OTHER,
                debit=Decimal('10'), credit=Decimal('10'),
                branch=self.branch_a,
            )

    def test_zero_movement_rejected(self):
        with self.assertRaises(svc.AccountMovementError):
            svc.record_account_movement(
                account=self.cashbox_a,
                movement_type=svc.MovementType.OTHER,
                debit=Decimal('0'), credit=Decimal('0'),
                branch=self.branch_a,
            )

    def test_negative_amount_rejected(self):
        with self.assertRaises(svc.AccountMovementError):
            svc.record_account_debit(
                account=self.cashbox_a, amount=Decimal('-5'),
                movement_type=svc.MovementType.OTHER,
                branch=self.branch_a,
            )

    def test_cross_tenant_branch_rejected(self):
        with self.assertRaises(svc.AccountMovementError):
            svc.record_account_debit(
                account=self.cashbox_a, amount=Decimal('10'),
                movement_type=svc.MovementType.SALES_CASH_IN,
                branch=self.branch_b,   # belongs to tenant B
            )

    def test_db_constraint_blocks_both_positive(self):
        """Belt-and-braces: even direct ORM write violates the CHECK constraint."""
        with self.assertRaises(IntegrityError):
            FinancialAccountMovement.objects.create(
                tenant=self.tenant_a, branch=self.branch_a, account=self.cashbox_a,
                movement_type='other',
                debit=Decimal('1'), credit=Decimal('1'),
                balance_after=Decimal('0'),
                occurred_at='2026-06-28T10:00:00Z',
            )

    def test_statement_is_tenant_scoped_and_filterable(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=10,
        )
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('20'),
            movement_type=svc.MovementType.CASH_IN,
            branch=self.branch_a2,
            source_document_type='CashIn', source_document_id=11,
        )
        # Also write into tenant B's account — must never appear in tenant A statement.
        svc.record_account_debit(
            account=self.cashbox_b, amount=Decimal('99'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_b,
            source_document_type='Sale', source_document_id=99,
        )

        # No branch filter → both rows.
        rows = list(svc.get_account_statement(self.cashbox_a))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.tenant_id == self.tenant_a.id for r in rows))

        # Branch filter narrows.
        rows = list(svc.get_account_statement(self.cashbox_a, branch=self.branch_a))
        self.assertEqual([r.source_document_id for r in rows], [10])

        # movement_type filter.
        rows = list(svc.get_account_statement(
            self.cashbox_a, movement_type=svc.MovementType.CASH_IN,
        ))
        self.assertEqual([r.source_document_id for r in rows], [11])


# ── API-layer tests ──────────────────────────────────────────────────────────

class FinancialMovementApiTests(_MovementsFixtureMixin, APITestCase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_movements_list_is_tenant_scoped(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('25'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=1,
        )
        svc.record_account_debit(
            account=self.cashbox_b, amount=Decimal('99'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_b,
            source_document_type='Sale', source_document_id=2,
        )
        resp = self.client.get('/api/finance/movements/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        # Only tenant A's row appears.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['account'], self.cashbox_a.id)
        self.assertEqual(rows[0]['debit'], '25.00')

    def test_movements_list_filters_by_account_and_source(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('10'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=42,
        )
        svc.record_account_debit(
            account=self.bank_a, amount=Decimal('77'),
            movement_type=svc.MovementType.SETTLEMENT_TO_BANK,
            source_document_type='Settlement', source_document_id=99,
        )

        resp = self.client.get(f'/api/finance/movements/?account={self.cashbox_a.id}')
        rows = resp.json()
        rows = rows['results'] if isinstance(rows, dict) and 'results' in rows else rows
        self.assertEqual({r['account'] for r in rows}, {self.cashbox_a.id})

        resp = self.client.get(
            '/api/finance/movements/?source_document_type=Settlement',
        )
        rows = resp.json()
        rows = rows['results'] if isinstance(rows, dict) and 'results' in rows else rows
        self.assertEqual({r['source_document_id'] for r in rows}, {99})

    def test_per_account_statement_endpoint(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('5'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=1,
        )
        url = f'/api/finance/accounts/{self.cashbox_a.id}/movements/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]['balance_after'], '105.00')

    def test_per_account_statement_404_on_foreign_account(self):
        url = f'/api/finance/accounts/{self.cashbox_b.id}/movements/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_balance_endpoint_returns_running_total(self):
        svc.record_account_debit(
            account=self.cashbox_a, amount=Decimal('77.50'),
            movement_type=svc.MovementType.SALES_CASH_IN,
            branch=self.branch_a,
            source_document_type='Sale', source_document_id=1,
        )
        url = f'/api/finance/accounts/{self.cashbox_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['account_id'],      self.cashbox_a.id)
        self.assertEqual(body['account_type'],    'cashbox')
        self.assertEqual(body['opening_balance'], '100.00')
        self.assertEqual(body['balance'],         '177.50')

    def test_balance_endpoint_uses_opening_when_no_movements(self):
        url = f'/api/finance/accounts/{self.bank_a.id}/balance/'
        resp = self.client.get(url)
        self.assertEqual(resp.json()['balance'], '0.00')

    def test_balance_endpoint_404_on_foreign_account(self):
        url = f'/api/finance/accounts/{self.cashbox_b.id}/balance/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
