"""Phase 1.5 Slice E — Customer + Supplier master-data tests.

Both parties share an identical API contract; the test cases are factored
into a `_PartyApiTestsMixin` that's instantiated twice (once per party)
so changes to the rule stay in lock-step across both surfaces.
"""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Customer, Supplier, Tenant, User


class _TwoTenantFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a = Branch.objects.create(tenant=cls.tenant_a, name='Branch A1')
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


class _PartyApiTestsMixin(_TwoTenantFixtureMixin):
    """Shared scenarios for Customer + Supplier APIs.

    Subclasses set:
        url            — list/create URL
        model          — Customer or Supplier
        create_payload — minimal valid POST body
        extra_fields   — extra read-only fields to assert on the response
    """

    url: str = ''
    model = None
    create_payload: dict = {}
    extra_fields: tuple = ()

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    # ── List + create ────────────────────────────────────────────────────────

    def test_list_returns_only_caller_tenant_rows(self):
        self.model.objects.create(tenant=self.tenant_a, name='A-Co')
        self.model.objects.create(tenant=self.tenant_b, name='B-Co')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual({r['name'] for r in rows}, {'A-Co'})

    def test_create_scopes_to_caller_tenant(self):
        payload = dict(self.create_payload, default_branch=self.branch_a.id)
        resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['tenant'], self.tenant_a.id)
        self.assertEqual(data['default_branch'], self.branch_a.id)
        self.assertTrue(data['is_active'])
        # Server-side defaults are stored, not zero-valued strings.
        self.assertEqual(data['opening_balance'], '0.00')

        obj = self.model.objects.get(pk=data['id'])
        self.assertEqual(obj.tenant_id, self.tenant_a.id)

    def test_cashier_can_list_but_not_create(self):
        self.client.force_authenticate(user=self.cashier_a)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        resp = self.client.post(self.url, self.create_payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_blocked(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    # ── default_branch tenant scoping ────────────────────────────────────────

    def test_create_rejects_foreign_default_branch(self):
        payload = dict(self.create_payload, default_branch=self.branch_b.id)
        resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('default_branch', resp.json())

    def test_patch_rejects_foreign_default_branch(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='X')
        resp = self.client.patch(
            f'{self.url}{obj.id}/',
            {'default_branch': self.branch_b.id},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    # ── code uniqueness ─────────────────────────────────────────────────────

    def test_same_code_allowed_across_tenants(self):
        self.model.objects.create(tenant=self.tenant_a, name='X', code='C-1')
        self.model.objects.create(tenant=self.tenant_b, name='Y', code='C-1')
        self.assertEqual(self.model.objects.filter(code='C-1').count(), 2)

    def test_duplicate_code_in_same_tenant_rejected(self):
        self.model.objects.create(tenant=self.tenant_a, name='X', code='DUP')
        payload = dict(self.create_payload, code='DUP')
        resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('code', resp.json())

    def test_empty_code_default_is_allowed_repeatedly(self):
        # Walk-in/unnamed parties may share '' — partial unique excludes ''.
        for label in ('a', 'b', 'c'):
            self.model.objects.create(tenant=self.tenant_a, name=label, code='')
        self.assertEqual(
            self.model.objects.filter(tenant=self.tenant_a, code='').count(),
            3,
        )

    # ── Detail / PATCH ──────────────────────────────────────────────────────

    def test_detail_returns_row(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='Detail Co')
        resp = self.client.get(f'{self.url}{obj.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['id'], obj.id)

    def test_patch_updates_writable_fields(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='Old')
        resp = self.client.patch(
            f'{self.url}{obj.id}/',
            {'name': 'New', 'phone': '01234', 'tax_number': 'TX-9'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        self.assertEqual(body['name'], 'New')
        self.assertEqual(body['phone'], '01234')
        self.assertEqual(body['tax_number'], 'TX-9')

    def test_tenant_is_not_writable_via_patch(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='Locked')
        resp = self.client.patch(
            f'{self.url}{obj.id}/',
            {'tenant': self.tenant_b.id, 'name': 'still in A'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['tenant'], self.tenant_a.id)
        obj.refresh_from_db()
        self.assertEqual(obj.tenant_id, self.tenant_a.id)

    # ── Tenant isolation ────────────────────────────────────────────────────

    def test_foreign_tenant_detail_is_404(self):
        foreign = self.model.objects.create(tenant=self.tenant_b, name='Foreign')
        for method, url, body in (
            ('get',   f'{self.url}{foreign.id}/',             None),
            ('patch', f'{self.url}{foreign.id}/',             {'name': 'pwn'}),
            ('post',  f'{self.url}{foreign.id}/deactivate/',  None),
        ):
            kwargs = {'format': 'json'} if body is not None else {}
            resp = getattr(self.client, method)(url, body or {}, **kwargs) if body is not None \
                   else getattr(self.client, method)(url)
            self.assertEqual(
                resp.status_code, status.HTTP_404_NOT_FOUND,
                f'{method.upper()} {url} expected 404',
            )

    # ── No DELETE ───────────────────────────────────────────────────────────

    def test_delete_is_not_allowed(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='Keep')
        resp = self.client.delete(f'{self.url}{obj.id}/')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(self.model.objects.filter(pk=obj.id).exists())

    # ── Deactivate action ───────────────────────────────────────────────────

    def test_deactivate_is_idempotent(self):
        obj = self.model.objects.create(tenant=self.tenant_a, name='Z')
        url = f'{self.url}{obj.id}/deactivate/'
        first  = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code,  status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.json()['is_active'])
        obj.refresh_from_db()
        self.assertFalse(obj.is_active)

    def test_is_active_filter(self):
        self.model.objects.create(tenant=self.tenant_a, name='Live')
        dead = self.model.objects.create(tenant=self.tenant_a, name='Dead')
        dead.is_active = False
        dead.save(update_fields=['is_active', 'updated_at'])
        resp = self.client.get(self.url, {'is_active': 'true'})
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual({r['name'] for r in rows}, {'Live'})

    # ── No ledger movement created ──────────────────────────────────────────

    def test_opening_balance_is_stored_but_no_ledger_movement(self):
        from accounts.models import FinancialAccountMovement
        before = FinancialAccountMovement.objects.count()
        payload = dict(self.create_payload, opening_balance='250.00')
        resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['opening_balance'], '250.00')
        # Slice E is master-data only — no AR/AP movement should be created.
        self.assertEqual(FinancialAccountMovement.objects.count(), before)


# Concrete test cases ────────────────────────────────────────────────────────

class CustomerApiTests(_PartyApiTestsMixin, APITestCase):
    url   = '/api/customers/'
    model = Customer
    create_payload = {
        'name':  'Acme Corp',
        'code':  'CUS-01',
        'phone': '01000000000',
        'email': 'acme@example.com',
        'tax_number': 'TX-100',
    }

    def test_customer_specific_fields_round_trip(self):
        resp = self.client.post(self.url, {
            'name':            'VIP Cust',
            'credit_limit':    '5000.00',
            'price_tier_id':   42,    # placeholder — PriceTier model not yet defined
            'opening_balance': '120.50',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['credit_limit'],    '5000.00')
        self.assertEqual(data['price_tier_id'],   42)
        self.assertEqual(data['opening_balance'], '120.50')


class SupplierApiTests(_PartyApiTestsMixin, APITestCase):
    url   = '/api/suppliers/'
    model = Supplier
    create_payload = {
        'name':       'ACME Wholesale',
        'code':       'SUP-01',
        'phone':      '01100000000',
        'email':      'wholesale@example.com',
        'tax_number': 'TX-S-001',
    }

    def test_supplier_has_no_credit_or_price_tier_fields(self):
        resp = self.client.post(self.url, {
            'name': 'Plain Supplier', 'opening_balance': '0.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertNotIn('credit_limit',  resp.json())
        self.assertNotIn('price_tier_id', resp.json())
