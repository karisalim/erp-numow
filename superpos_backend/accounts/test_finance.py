"""Phase 1.5 Slice C — Finance + Payment Methods backend tests.

Covers:
  * FinancialAccount CRUD + deactivate (no DELETE)
  * PaymentMethod CRUD + deactivate
  * BranchPaymentMethod create / patch / deactivate
  * Tenant isolation (cross-tenant access forbidden; cross-tenant FK rejected)
  * Branch isolation
  * Method ↔ destination-account-type compatibility
"""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    BranchPaymentMethod,
    FinancialAccount,
    PaymentMethod,
    Tenant,
    User,
)


class _FinanceFixtureMixin:
    """Two tenants, one branch each, manager+cashier on tenant A."""

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
        cls.cashier_a = User.objects.create_user(
            username='cash_a', password='pw',
            role=User.Role.CASHIER, tenant=cls.tenant_a, branch=cls.branch_a,
        )
        cls.manager_b = User.objects.create_user(
            username='mgr_b', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_b, branch=cls.branch_b,
        )


# ── FinancialAccount ─────────────────────────────────────────────────────────

class FinancialAccountApiTests(_FinanceFixtureMixin, APITestCase):
    url = '/api/finance/accounts/'

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_create_lists_only_tenant_rows(self):
        # Seed one row in tenant_a, one in tenant_b.
        a = FinancialAccount.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            name='Main Cashbox', account_type=FinancialAccount.AccountType.CASHBOX,
            currency='EGP', opening_balance=Decimal('500.00'),
        )
        FinancialAccount.objects.create(
            tenant=self.tenant_b, name='Foreign', account_type='cashbox',
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        ids = {row['id'] for row in rows}
        self.assertEqual(ids, {a.id})

    def test_create_scopes_to_caller_tenant(self):
        resp = self.client.post(self.url, {
            'name': 'Visa Settlement',
            'account_type': 'card_settlement',
            'currency': 'EGP',
            'opening_balance': '0.00',
            'branch': self.branch_a.id,
            'code': 'VISA-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['tenant'], self.tenant_a.id)
        self.assertEqual(data['account_type'], 'card_settlement')
        self.assertEqual(data['code'], 'VISA-01')

    def test_create_rejects_foreign_branch(self):
        resp = self.client.post(self.url, {
            'name': 'Bad', 'account_type': 'cashbox', 'currency': 'EGP',
            'branch': self.branch_b.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('branch', resp.json())

    def test_cashier_can_list_but_not_create(self):
        self.client.force_authenticate(user=self.cashier_a)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        resp = self.client.post(self.url, {
            'name': 'X', 'account_type': 'cashbox',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_updates_writable_fields(self):
        acct = FinancialAccount.objects.create(
            tenant=self.tenant_a, name='Old Name', account_type='cashbox',
        )
        resp = self.client.patch(f'{self.url}{acct.id}/', {
            'name': 'New Name', 'opening_balance': '1000.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['name'], 'New Name')
        self.assertEqual(resp.json()['opening_balance'], '1000.00')

    def test_delete_is_not_allowed(self):
        acct = FinancialAccount.objects.create(
            tenant=self.tenant_a, name='Keep', account_type='cashbox',
        )
        resp = self.client.delete(f'{self.url}{acct.id}/')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_deactivate_action_is_idempotent(self):
        acct = FinancialAccount.objects.create(
            tenant=self.tenant_a, name='Z', account_type='cashbox',
        )
        url = f'{self.url}{acct.id}/deactivate/'
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.json()['is_active'])
        acct.refresh_from_db()
        self.assertFalse(acct.is_active)

    def test_cross_tenant_detail_is_404(self):
        foreign = FinancialAccount.objects.create(
            tenant=self.tenant_b, name='X', account_type='cashbox',
        )
        self.assertEqual(
            self.client.get(f'{self.url}{foreign.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(f'{self.url}{foreign.id}/', {'name': 'pwned'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(f'{self.url}{foreign.id}/deactivate/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_filter_by_account_type(self):
        FinancialAccount.objects.create(
            tenant=self.tenant_a, name='C1', account_type='cashbox',
        )
        FinancialAccount.objects.create(
            tenant=self.tenant_a, name='B1', account_type='bank',
        )
        resp = self.client.get(self.url, {'account_type': 'cashbox'})
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        types = {row['account_type'] for row in rows}
        self.assertEqual(types, {'cashbox'})


# ── PaymentMethod ────────────────────────────────────────────────────────────

class PaymentMethodApiTests(_FinanceFixtureMixin, APITestCase):
    url = '/api/finance/payment-methods/'

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_create_credit_auto_sets_requires_customer(self):
        resp = self.client.post(self.url, {
            'name': 'In-store Credit',
            'method_type': 'credit',
            # requires_customer NOT supplied — serializer should set it to True
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertTrue(data['requires_customer'])
        self.assertEqual(data['method_type'], 'credit')
        self.assertEqual(data['tenant'], self.tenant_a.id)

    def test_create_cash_default_requires_customer_false(self):
        resp = self.client.post(self.url, {
            'name': 'Cash', 'method_type': 'cash',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertFalse(resp.json()['requires_customer'])

    def test_credit_method_forces_requires_customer_true_even_on_explicit_false(self):
        """Hard invariant: a credit method must always require a customer.

        DOMAIN.md §10.2 — credit sales create CustomerARMovement; without a
        customer the AR has nowhere to land. The flag is forced server-side
        rather than 400-ing so the API stays forgiving while the contract
        stays intact.
        """
        resp = self.client.post(self.url, {
            'name': 'Credit-no-customer-attempt',
            'method_type': 'credit',
            'requires_customer': False,   # ← deliberately wrong
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.json()['requires_customer'])

        # Patch-down attempt must also be silently corrected.
        pk = resp.json()['id']
        patch_resp = self.client.patch(
            f'{self.url}{pk}/', {'requires_customer': False}, format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.content)
        self.assertTrue(patch_resp.json()['requires_customer'])

    def test_credit_model_save_forces_requires_customer(self):
        """Direct ORM writes (fixtures, signals, future services) follow the
        same rule via `PaymentMethod.save()`."""
        pm = PaymentMethod(
            tenant=self.tenant_a, name='Direct ORM Credit',
            method_type='credit', requires_customer=False,
        )
        pm.save()
        pm.refresh_from_db()
        self.assertTrue(pm.requires_customer)

        # Flipping it on an existing row also gets normalized on save.
        pm.requires_customer = False
        pm.save()
        pm.refresh_from_db()
        self.assertTrue(pm.requires_customer)

    def test_unique_name_per_tenant(self):
        PaymentMethod.objects.create(
            tenant=self.tenant_a, name='Cash', method_type='cash',
        )
        # Same name across tenants is fine.
        PaymentMethod.objects.create(
            tenant=self.tenant_b, name='Cash', method_type='cash',
        )
        # Same name in same tenant must fail at the API layer.
        resp = self.client.post(self.url, {
            'name': 'Cash', 'method_type': 'cash',
        }, format='json')
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, 500))

    def test_patch_and_deactivate(self):
        pm = PaymentMethod.objects.create(
            tenant=self.tenant_a, name='Visa', method_type='card',
        )
        resp = self.client.patch(f'{self.url}{pm.id}/', {
            'provider_name': 'Visa Egypt',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['provider_name'], 'Visa Egypt')

        resp = self.client.post(f'{self.url}{pm.id}/deactivate/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.json()['is_active'])

    def test_cross_tenant_detail_is_404(self):
        foreign = PaymentMethod.objects.create(
            tenant=self.tenant_b, name='X', method_type='card',
        )
        self.assertEqual(
            self.client.get(f'{self.url}{foreign.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_list_returns_only_tenant_rows(self):
        PaymentMethod.objects.create(tenant=self.tenant_a, name='Cash', method_type='cash')
        PaymentMethod.objects.create(tenant=self.tenant_b, name='Other', method_type='cash')
        resp = self.client.get(self.url)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        names = {row['name'] for row in rows}
        self.assertEqual(names, {'Cash'})


# ── BranchPaymentMethod ──────────────────────────────────────────────────────

class BranchPaymentMethodApiTests(_FinanceFixtureMixin, APITestCase):
    """The contract's most-loaded surface: payment routing.

    These tests lock the cross-tenant linkage rules and the
    method-type ↔ account-type compatibility matrix.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Tenant A accounts (the legal routing targets).
        cls.acct_a_cashbox = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Drawer A1', account_type='cashbox', currency='EGP',
        )
        cls.acct_a_card = FinancialAccount.objects.create(
            tenant=cls.tenant_a, branch=cls.branch_a,
            name='Visa Settlement A1', account_type='card_settlement',
            currency='EGP',
        )
        cls.acct_a_bank = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='Bank A', account_type='bank',
            currency='EGP',
        )
        cls.acct_a_expense = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='Card Fees A', account_type='expense',
            currency='EGP',
        )
        cls.acct_a_ar = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='AR A', account_type='customer_ar',
        )
        cls.acct_a_wallet = FinancialAccount.objects.create(
            tenant=cls.tenant_a, name='Vodafone Cash A', account_type='wallet',
        )
        # Tenant A methods.
        cls.pm_a_cash = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Cash', method_type='cash',
        )
        cls.pm_a_card = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Visa', method_type='card',
        )
        cls.pm_a_credit = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='Credit', method_type='credit',
            requires_customer=True,
        )
        cls.pm_a_wallet = PaymentMethod.objects.create(
            tenant=cls.tenant_a, name='VC', method_type='wallet',
        )
        # Tenant B fixtures (for cross-tenant rejection tests).
        cls.acct_b_cashbox = FinancialAccount.objects.create(
            tenant=cls.tenant_b, branch=cls.branch_b,
            name='Drawer B', account_type='cashbox',
        )
        cls.pm_b_cash = PaymentMethod.objects.create(
            tenant=cls.tenant_b, name='Cash', method_type='cash',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def _url(self, branch_id, suffix=''):
        return f'/api/branches/{branch_id}/payment-methods/{suffix}'

    # ── Create / route compatibility ──────────────────────────────────────────

    def test_cash_method_routes_to_cashbox(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':       self.pm_a_cash.id,
            'destination_account':  self.acct_a_cashbox.id,
            'is_default':           True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['payment_method'],      self.pm_a_cash.id)
        self.assertEqual(data['destination_account'], self.acct_a_cashbox.id)
        self.assertEqual(data['payment_method_type'], 'cash')
        self.assertEqual(data['destination_account_type'], 'cashbox')
        self.assertEqual(data['branch'], self.branch_a.id)

    def test_cash_cannot_route_to_main_safe(self):
        """Main safe is reserved for cash drops / internal transfers — never
        the direct POS landing account for cash payments. Drop the link
        attempt at write time so misconfiguration can't accidentally pool
        register cash into the safe and break shift reconciliation later.
        """
        main_safe = FinancialAccount.objects.create(
            tenant=self.tenant_a, name='Main Safe A',
            account_type='main_safe', currency='EGP',
        )
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_cash.id,
            'destination_account': main_safe.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('destination_account', resp.json())

    def test_card_method_must_route_to_card_settlement_not_cashbox(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_card.id,
            'destination_account': self.acct_a_cashbox.id,   # wrong on purpose
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('destination_account', resp.json())

        # Correct routing succeeds.
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_card.id,
            'destination_account': self.acct_a_card.id,
            'settlement_bank_account': self.acct_a_bank.id,
            'commission_expense_account': self.acct_a_expense.id,
            'commission_percent': '2.50',
            'fixed_fee': '0.50',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_wallet_must_route_to_wallet(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_wallet.id,
            'destination_account': self.acct_a_cashbox.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_wallet.id,
            'destination_account': self.acct_a_wallet.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_credit_must_route_to_customer_ar(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_credit.id,
            'destination_account': self.acct_a_cashbox.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_credit.id,
            'destination_account': self.acct_a_ar.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_settlement_bank_must_be_bank_account_type(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_card.id,
            'destination_account': self.acct_a_card.id,
            'settlement_bank_account': self.acct_a_cashbox.id,   # not a bank
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('settlement_bank_account', resp.json())

    def test_commission_expense_must_be_expense_account_type(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_card.id,
            'destination_account': self.acct_a_card.id,
            'commission_expense_account': self.acct_a_bank.id,   # not expense
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('commission_expense_account', resp.json())

    # ── Cross-tenant linkage ──────────────────────────────────────────────────

    def test_rejects_foreign_payment_method(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_b_cash.id,        # tenant B
            'destination_account': self.acct_a_cashbox.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('payment_method', resp.json())

    def test_rejects_foreign_destination_account(self):
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method':      self.pm_a_cash.id,
            'destination_account': self.acct_b_cashbox.id,   # tenant B
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('destination_account', resp.json())

    def test_branch_in_url_must_belong_to_caller_tenant(self):
        resp = self.client.get(self._url(self.branch_b.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.post(self._url(self.branch_b.id), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── List / branch isolation ───────────────────────────────────────────────

    def test_list_returns_only_this_branch_rows(self):
        link_a = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_a_cash,
            destination_account=self.acct_a_cashbox,
        )
        # Another branch in same tenant — should NOT appear in branch A list.
        BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a2,
            payment_method=self.pm_a_cash,
            destination_account=self.acct_a_cashbox,
        )
        resp = self.client.get(self._url(self.branch_a.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {row['id'] for row in resp.json()}
        self.assertEqual(ids, {link_a.id})

    # ── Uniqueness ────────────────────────────────────────────────────────────

    def test_same_method_cannot_be_enabled_twice_on_same_branch(self):
        self.client.post(self._url(self.branch_a.id), {
            'payment_method': self.pm_a_cash.id,
            'destination_account': self.acct_a_cashbox.id,
        }, format='json')
        resp = self.client.post(self._url(self.branch_a.id), {
            'payment_method': self.pm_a_cash.id,
            'destination_account': self.acct_a_cashbox.id,
        }, format='json')
        # Unique (tenant, branch, payment_method) constraint fires.
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, 500))

    # ── Patch / deactivate ────────────────────────────────────────────────────

    def test_patch_updates_commission(self):
        link = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_a_card,
            destination_account=self.acct_a_card,
            commission_percent=Decimal('2.00'),
        )
        resp = self.client.patch(
            self._url(self.branch_a.id, f'{link.id}/'),
            {'commission_percent': '3.25', 'fixed_fee': '1.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['commission_percent'], '3.25')
        self.assertEqual(resp.json()['fixed_fee'], '1.00')

    def test_patch_rejects_incompatible_destination_swap(self):
        link = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_a_card,
            destination_account=self.acct_a_card,
        )
        # Try to move the card link onto the cashbox — must fail.
        resp = self.client.patch(
            self._url(self.branch_a.id, f'{link.id}/'),
            {'destination_account': self.acct_a_cashbox.id},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_is_idempotent(self):
        link = BranchPaymentMethod.objects.create(
            tenant=self.tenant_a, branch=self.branch_a,
            payment_method=self.pm_a_cash,
            destination_account=self.acct_a_cashbox,
        )
        url = self._url(self.branch_a.id, f'{link.id}/deactivate/')
        self.assertEqual(self.client.post(url).status_code, status.HTTP_200_OK)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.json()['is_active'])

    def test_patch_404_for_foreign_branch_link(self):
        # Create a tenant_b link, attempt patch under tenant_b's branch via tenant_a auth.
        link_b = BranchPaymentMethod.objects.create(
            tenant=self.tenant_b, branch=self.branch_b,
            payment_method=self.pm_b_cash,
            destination_account=self.acct_b_cashbox,
        )
        url = self._url(self.branch_b.id, f'{link_b.id}/')
        resp = self.client.patch(url, {'commission_percent': '1.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
