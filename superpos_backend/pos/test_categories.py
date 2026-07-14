"""Sprint 2 Batch 2 — hierarchical category tree tests (MASTER_DATA_CONTRACT §3).

Covers, for BOTH independent trees (SalesCategory / InventoryCategory) via a
shared mixin:
    * CRUD: root create, child create, multi-level hierarchy, rename, deactivate
    * validation: self-parent, descendant-as-parent (cycle), cross-tenant
      parent, inactive parent, sibling/root name uniqueness
    * tenant isolation: list scoping, cross-tenant detail 404, role gates

Plus legacy compatibility: the flat `Category` model, its `categories/` route,
`Product.category`, and POS category filtering are all untouched by this batch.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from pos.models import Category, InventoryCategory, Product, SalesCategory


class _CategoryTreeTestsMixin:
    """Runs the full rule matrix against one tree model; concrete classes pin
    `model`, `list_url`, `detail_url`, `deactivate_url`."""

    model          = None
    list_url       = ''
    detail_url     = ''
    deactivate_url = ''

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Cat Tenant A')
        cls.manager = User.objects.create_user(
            username=f'cmgr_a_{cls.__name__}', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username=f'ccsh_a_{cls.__name__}', password='pw',
            role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.tenant_b = Tenant.objects.create(name='Cat Tenant B')
        cls.manager_b = User.objects.create_user(
            username=f'cmgr_b_{cls.__name__}', password='pw',
            role=User.Role.MANAGER, tenant=cls.tenant_b,
        )
        cls.root_b = cls.model.objects.create(tenant=cls.tenant_b, name='B-Root')

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _node(self, name, parent=None, tenant=None, **kw):
        return self.model.objects.create(
            tenant=tenant or self.tenant, name=name, parent=parent, **kw,
        )

    def _post(self, body):
        return self.client.post(reverse(self.list_url), body, format='json')

    def _patch(self, pk, body):
        return self.client.patch(reverse(self.detail_url, args=[pk]), body, format='json')

    # ── CRUD + hierarchy ─────────────────────────────────────────────────────

    def test_create_root_category(self):
        resp = self._post({'name': 'Beverages'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        row = self.model.objects.get(pk=resp.json()['id'])
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertIsNone(row.parent_id)
        self.assertTrue(row.is_active)

    def test_create_child_category(self):
        root = self._node('Beverages')
        resp = self._post({'name': 'Coffee', 'parent': root.pk})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['parent'], root.pk)
        self.assertEqual(resp.json()['parent_name'], 'Beverages')

    def test_multi_level_hierarchy(self):
        """Beverages → Coffee → Hot Coffee → Espresso (unlimited depth)."""
        beverages = self._node('Beverages')
        coffee = self._node('Coffee', parent=beverages)
        hot = self._node('Hot Coffee', parent=coffee)
        resp = self._post({'name': 'Espresso', 'parent': hot.pk})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        espresso = self.model.objects.get(pk=resp.json()['id'])
        chain = [espresso.name]
        node = espresso.parent
        while node is not None:
            chain.append(node.name)
            node = node.parent
        self.assertEqual(
            chain, ['Espresso', 'Hot Coffee', 'Coffee', 'Beverages'])

    def test_patch_rename(self):
        node = self._node('Old Drinks')
        resp = self._patch(node.pk, {'name': 'Drinks'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        node.refresh_from_db()
        self.assertEqual(node.name, 'Drinks')

    def test_reparent_to_valid_node_allowed(self):
        a = self._node('A')
        b = self._node('B')
        resp = self._patch(b.pk, {'parent': a.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        b.refresh_from_db()
        self.assertEqual(b.parent_id, a.pk)

    def test_deactivate_endpoint(self):
        node = self._node('Old Drinks')
        resp = self.client.post(reverse(self.deactivate_url, args=[node.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        node.refresh_from_db()
        self.assertFalse(node.is_active)

    # ── Validation rules ─────────────────────────────────────────────────────

    def test_self_parent_rejected(self):
        node = self._node('Coffee')
        resp = self._patch(node.pk, {'parent': node.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('parent', resp.json())

    def test_descendant_as_parent_rejected(self):
        """A → B → C; C cannot become the parent of A (would close a cycle)."""
        a = self._node('A')
        b = self._node('B', parent=a)
        c = self._node('C', parent=b)
        resp = self._patch(a.pk, {'parent': c.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('parent', resp.json())
        a.refresh_from_db()
        self.assertIsNone(a.parent_id)

    def test_direct_child_as_parent_rejected(self):
        coffee = self._node('Coffee')
        latte = self._node('Latte', parent=coffee)
        resp = self._patch(coffee.pk, {'parent': latte.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_parent_rejected(self):
        resp = self._post({'name': 'Sneaky', 'parent': self.root_b.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('parent', resp.json())

    def test_inactive_parent_rejected_for_new_assignment(self):
        old = self._node('Old Drinks', is_active=False)
        resp = self._post({'name': 'New Soda', 'parent': old.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('parent', resp.json())

    def test_duplicate_sibling_name_rejected_but_ok_under_other_parent(self):
        bev = self._node('Beverages')
        raw = self._node('Raw')
        self._node('Milk', parent=bev)
        dup = self._post({'name': 'Milk', 'parent': bev.pk})
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', dup.json())
        # Same name under a different parent is fine — that's the whole point
        # of split trees (Milk under Beverages AND under Raw Materials).
        ok = self._post({'name': 'Milk', 'parent': raw.pk})
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.content)

    def test_duplicate_root_name_rejected(self):
        self._node('Beverages')
        resp = self._post({'name': 'Beverages'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.json())

    # ── Tenant isolation + roles ─────────────────────────────────────────────

    def test_list_is_tenant_scoped(self):
        self._node('Mine')
        names = {r['name'] for r in self.client.get(
            reverse(self.list_url)).json()['results']}
        self.assertEqual(names, {'Mine'})   # B-Root never leaks

    def test_cross_tenant_detail_404s(self):
        resp = self.client.get(reverse(self.detail_url, args=[self.root_b.pk]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_tenant_patch_404s(self):
        resp = self._patch(self.root_b.pk, {'name': 'Hijack'})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.root_b.refresh_from_db()
        self.assertEqual(self.root_b.name, 'B-Root')

    def test_cashier_cannot_write_but_can_read(self):
        node = self._node('Readable')
        self.client.force_authenticate(user=self.cashier)
        self.assertEqual(
            self._post({'name': 'X'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self._patch(node.pk, {'name': 'Y'}).status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(reverse(self.list_url)).status_code,
            status.HTTP_200_OK)

    def test_root_filter(self):
        root = self._node('Root')
        self._node('Child', parent=root)
        rows = self.client.get(
            reverse(self.list_url), {'root': 'true'}).json()['results']
        self.assertEqual([r['name'] for r in rows], ['Root'])


class SalesCategoryApiTests(_CategoryTreeTestsMixin, APITestCase):
    model          = SalesCategory
    list_url       = 'sales-category-list'
    detail_url     = 'sales-category-detail'
    deactivate_url = 'sales-category-deactivate'


class InventoryCategoryApiTests(_CategoryTreeTestsMixin, APITestCase):
    model          = InventoryCategory
    list_url       = 'inventory-category-list'
    detail_url     = 'inventory-category-detail'
    deactivate_url = 'inventory-category-deactivate'


class CategoryTreeIndependenceTests(APITestCase):
    """The two trees are separate tables — same names can exist in both, and
    a node of one tree can never be used as a parent in the other (distinct
    FKs make it a validation error by construction)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Cat Tenant Ind')
        cls.manager = User.objects.create_user(
            username='cmgr_ind', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_same_name_in_both_trees(self):
        """The brief's Milk example: sales Beverages→Dairy Drinks→Milk AND
        inventory Raw Materials→Dairy→Milk coexist."""
        bev = SalesCategory.objects.create(tenant=self.tenant, name='Beverages')
        dairy_drinks = SalesCategory.objects.create(
            tenant=self.tenant, name='Dairy Drinks', parent=bev)
        raw = InventoryCategory.objects.create(tenant=self.tenant, name='Raw Materials')
        dairy = InventoryCategory.objects.create(
            tenant=self.tenant, name='Dairy', parent=raw)

        s = self.client.post(reverse('sales-category-list'),
                             {'name': 'Milk', 'parent': dairy_drinks.pk}, format='json')
        i = self.client.post(reverse('inventory-category-list'),
                             {'name': 'Milk', 'parent': dairy.pk}, format='json')
        self.assertEqual(s.status_code, status.HTTP_201_CREATED, s.content)
        self.assertEqual(i.status_code, status.HTTP_201_CREATED, i.content)

    def test_sales_node_cannot_parent_inventory_node(self):
        sales_root = SalesCategory.objects.create(tenant=self.tenant, name='Beverages')
        resp = self.client.post(
            reverse('inventory-category-list'),
            # Same pk namespace trick: even if an InventoryCategory with this
            # pk existed, the queryset is tree- and tenant-scoped.
            {'name': 'Sneaky', 'parent': sales_root.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class LegacyCategoryCompatibilityTests(APITestCase):
    """Batch 2 is additive: the flat Category model, its route, and
    Product.category keep working exactly as before."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Legacy Cat Tenant')
        cls.manager = User.objects.create_user(
            username='lcmgr', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant,
        )
        cls.legacy = Category.objects.create(tenant=cls.tenant, name='Drinks')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.legacy,
            name='Cola', barcode='LC-1', sku='SKU-LC',
            price=Decimal('10.00'), cost=Decimal('6.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('10'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_legacy_category_route_still_lists_and_creates(self):
        listing = self.client.get(reverse('category-list'))
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        created = self.client.post(
            reverse('category-list'), {'name': 'Snacks'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)

    def test_product_category_fk_unchanged(self):
        resp = self.client.get(reverse('product-detail', args=[self.product.pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['category'], self.legacy.pk)
        self.assertEqual(resp.json()['category_name'], 'Drinks')

    def test_pos_category_filter_unchanged(self):
        """`?category=<name>` on the product list is the POS filter path —
        still keyed to the legacy flat Category."""
        resp = self.client.get(reverse('product-list'), {'category': 'drinks'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [r['id'] for r in resp.json()['results']], [self.product.pk])
