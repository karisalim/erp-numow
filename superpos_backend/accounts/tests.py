"""Phase 1.5 Slice A — Dynamic Branch Management backend tests.

Covers the new /api/branches/ surface:

  * list / create / update branches (tenant-scoped)
  * deactivate action (no DELETE)
  * branch settings GET / PATCH (lazy create)
  * branch user assignment GET / POST (idempotent)
  * tenant isolation (cross-tenant access forbidden)
  * existing accounts/Branch reuse — no model duplication
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch,
    BranchSettings,
    BranchUserAssignment,
    Tenant,
    User,
)


class _BranchTestMixin:
    """Shared two-tenant fixture with manager + cashier users in tenant A."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')

        cls.branch_a_main = Branch.objects.create(
            tenant=cls.tenant_a, name='Main Branch A',
        )
        cls.branch_b = Branch.objects.create(
            tenant=cls.tenant_b, name='Branch B',
        )

        cls.manager_a = User.objects.create_user(
            username='mgr_a', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_a,
            branch=cls.branch_a_main,
        )
        cls.cashier_a = User.objects.create_user(
            username='cash_a', password='pw',
            role=User.Role.CASHIER, tenant=cls.tenant_a,
            branch=cls.branch_a_main,
        )
        cls.manager_b = User.objects.create_user(
            username='mgr_b', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_b,
            branch=cls.branch_b,
        )


class BranchListCreateTests(_BranchTestMixin, APITestCase):
    url = '/api/branches/'

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_list_returns_only_caller_tenant_branches(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        # Django pagination may wrap results; handle both shapes.
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        names = {row['name'] for row in rows}
        self.assertEqual(names, {'Main Branch A'})

    def test_create_branch_scopes_to_caller_tenant(self):
        resp = self.client.post(self.url, {
            'name': 'Downtown',
            'code': 'DT-01',
            'branch_type': 'store',
            'address': '1 Tahrir Sq',
            'phone': '01234567890',
            'tax_number': 'TX-001',
            'currency': 'EGP',
            'timezone': 'Africa/Cairo',
            'is_main': False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['name'], 'Downtown')
        self.assertEqual(data['code'], 'DT-01')
        self.assertEqual(data['branch_type'], 'store')
        self.assertEqual(data['tenant'], self.tenant_a.id)
        self.assertTrue(data['is_active'])

        # And the row really lives in the caller's tenant.
        branch = Branch.objects.get(code='DT-01')
        self.assertEqual(branch.tenant_id, self.tenant_a.id)

    def test_cashier_can_list_but_not_create(self):
        self.client.force_authenticate(user=self.cashier_a)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        resp = self.client.post(self.url, {'name': 'Forbidden'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_is_blocked(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_same_branch_code_in_other_tenant_is_allowed(self):
        # Partial UNIQUE (tenant, code) WHERE code != '' is scoped per tenant.
        Branch.objects.create(tenant=self.tenant_a, name='X', code='DUP-1')
        # Cross-tenant duplicate code is fine.
        Branch.objects.create(tenant=self.tenant_b, name='Same Code OK', code='DUP-1')
        self.assertEqual(
            Branch.objects.filter(code='DUP-1').count(), 2,
        )

    def test_empty_code_default_is_not_subject_to_uniqueness(self):
        # The default '' value must be allowed across many rows in the same
        # tenant — legacy fixtures rely on it. `Main Branch A` already has
        # code='' from setUpTestData; add two more to prove the constraint
        # is partial, not absolute.
        before = Branch.objects.filter(tenant=self.tenant_a, code='').count()
        Branch.objects.create(tenant=self.tenant_a, name='blank-1', code='')
        Branch.objects.create(tenant=self.tenant_a, name='blank-2', code='')
        self.assertEqual(
            Branch.objects.filter(tenant=self.tenant_a, code='').count(),
            before + 2,
        )


class BranchDetailAndDeactivateTests(_BranchTestMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_get_branch_detail(self):
        resp = self.client.get(f'/api/branches/{self.branch_a_main.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['id'], self.branch_a_main.id)

    def test_patch_updates_fields(self):
        resp = self.client.patch(
            f'/api/branches/{self.branch_a_main.id}/',
            {'phone': '0100-NEW', 'tax_number': 'TX-XYZ', 'timezone': 'UTC'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        self.assertEqual(body['phone'], '0100-NEW')
        self.assertEqual(body['tax_number'], 'TX-XYZ')
        self.assertEqual(body['timezone'], 'UTC')

    def test_delete_is_not_allowed(self):
        resp = self.client.delete(f'/api/branches/{self.branch_a_main.id}/')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        # Branch must still exist.
        self.assertTrue(Branch.objects.filter(pk=self.branch_a_main.id).exists())

    def test_deactivate_action_flips_active_false(self):
        url = f'/api/branches/{self.branch_a_main.id}/deactivate/'
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertFalse(resp.json()['is_active'])
        self.branch_a_main.refresh_from_db()
        self.assertFalse(self.branch_a_main.active)

    def test_deactivate_is_idempotent(self):
        url = f'/api/branches/{self.branch_a_main.id}/deactivate/'
        self.client.post(url)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.json()['is_active'])

    def test_cannot_access_foreign_tenant_branch(self):
        resp = self.client.get(f'/api/branches/{self.branch_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.patch(
            f'/api/branches/{self.branch_b.id}/', {'phone': 'pwned'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp = self.client.post(f'/api/branches/{self.branch_b.id}/deactivate/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # Foreign branch is still active.
        self.branch_b.refresh_from_db()
        self.assertTrue(self.branch_b.active)


class BranchSettingsApiTests(_BranchTestMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_get_creates_settings_lazily_with_defaults(self):
        url = f'/api/branches/{self.branch_a_main.id}/settings/'
        self.assertFalse(BranchSettings.objects.filter(branch=self.branch_a_main).exists())

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertEqual(data['branch'], self.branch_a_main.id)
        self.assertEqual(data['tenant'], self.tenant_a.id)
        self.assertFalse(data['require_shift_for_pos'])
        self.assertFalse(data['allow_negative_stock'])
        self.assertFalse(data['allow_shift_close_with_open_orders'])
        self.assertEqual(data['receipt_header'], '')
        self.assertEqual(data['receipt_footer'], '')
        # Default *_id placeholders are null until the master tables exist.
        self.assertIsNone(data['default_cashbox_id'])
        self.assertIsNone(data['default_sales_warehouse_id'])

        # Row was created.
        self.assertTrue(
            BranchSettings.objects.filter(branch=self.branch_a_main).exists(),
        )

    def test_patch_updates_only_provided_fields(self):
        url = f'/api/branches/{self.branch_a_main.id}/settings/'
        self.client.get(url)  # lazy create
        resp = self.client.patch(url, {
            'require_shift_for_pos': True,
            'allow_negative_stock': True,
            'receipt_header': 'Hello',
            'default_cashbox_id': 42,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertTrue(data['require_shift_for_pos'])
        self.assertTrue(data['allow_negative_stock'])
        self.assertEqual(data['receipt_header'], 'Hello')
        self.assertEqual(data['default_cashbox_id'], 42)
        # Untouched defaults retained.
        self.assertEqual(data['receipt_footer'], '')

    def test_settings_tenant_and_branch_are_not_writeable(self):
        url = f'/api/branches/{self.branch_a_main.id}/settings/'
        self.client.get(url)
        resp = self.client.patch(url, {
            'tenant': self.tenant_b.id,
            'branch': self.branch_b.id,
            'receipt_header': 'ok',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        # The privileged fields are read-only, so the server keeps the originals.
        self.assertEqual(body['tenant'], self.tenant_a.id)
        self.assertEqual(body['branch'], self.branch_a_main.id)

    def test_cannot_access_settings_for_foreign_branch(self):
        url = f'/api/branches/{self.branch_b.id}/settings/'
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {'receipt_header': 'pwned'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )


class BranchUsersApiTests(_BranchTestMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_list_returns_assignments_only_for_branch(self):
        url = f'/api/branches/{self.branch_a_main.id}/users/'
        BranchUserAssignment.objects.create(
            tenant=self.tenant_a, branch=self.branch_a_main, user=self.cashier_a,
            role_at_branch=User.Role.CASHIER,
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['user'], self.cashier_a.id)
        self.assertEqual(rows[0]['user_username'], 'cash_a')
        self.assertEqual(rows[0]['role_at_branch'], 'Cashier')

    def test_post_creates_assignment(self):
        url = f'/api/branches/{self.branch_a_main.id}/users/'
        resp = self.client.post(url, {
            'user': self.cashier_a.id,
            'role_at_branch': User.Role.CASHIER,
            'is_default_branch': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['user'], self.cashier_a.id)
        self.assertTrue(data['is_default_branch'])

    def test_post_is_idempotent_on_repeat(self):
        url = f'/api/branches/{self.branch_a_main.id}/users/'
        first = self.client.post(url, {'user': self.cashier_a.id}, format='json')
        second = self.client.post(url, {
            'user': self.cashier_a.id,
            'role_at_branch': User.Role.MANAGER,
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        # Only one row exists; the role was upgraded.
        rows = BranchUserAssignment.objects.filter(
            tenant=self.tenant_a, branch=self.branch_a_main, user=self.cashier_a,
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().role_at_branch, 'Manager')

    def test_cannot_assign_cross_tenant_user(self):
        url = f'/api/branches/{self.branch_a_main.id}/users/'
        # Try to assign tenant B's manager to a tenant A branch.
        resp = self.client.post(url, {'user': self.manager_b.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_user_id_rejected(self):
        url = f'/api/branches/{self.branch_a_main.id}/users/'
        resp = self.client.post(url, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class LegacyBranchSurfaceUnchangedTests(_BranchTestMixin, APITestCase):
    """The legacy /api/auth/branches/ + /api/accounts/branches/ mounts must
    keep behaving the way the existing frontend expects — additive changes
    must not break either of them.
    """

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def test_legacy_branch_list_still_works(self):
        for mount in ('/api/auth/branches/', '/api/accounts/branches/'):
            resp = self.client.get(mount)
            self.assertEqual(resp.status_code, status.HTTP_200_OK, f'mount={mount}')
            body = resp.json()
            rows = body['results'] if isinstance(body, dict) and 'results' in body else body
            self.assertTrue(any(row['name'] == 'Main Branch A' for row in rows))

    def test_legacy_branch_serializer_shape_unchanged(self):
        resp = self.client.get('/api/auth/branches/')
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        first = next(row for row in rows if row['name'] == 'Main Branch A')
        # Legacy keys remain; the new master-data keys are NOT here.
        self.assertEqual(
            set(first.keys()),
            {'id', 'name', 'address', 'phone', 'active', 'created_at'},
        )
