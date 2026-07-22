"""Sprint 5 Batch 3 — Recipe / RecipeVersion / RecipeLine + cost service.

Model/service-level tests (cost roll-up, branch scoping, depth/cycle
validation, one-active-version invariant, PROTECT) plus a smaller set of
API-level CRUD/activation tests, mirroring the depth of coverage
`pos/test_costing.py` established for the AVCO engine.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Tenant, User
from pos.models import Category, InventoryCost, Product, ProductUnit, Unit, UnitGroup
from pos.services import costing as pos_costing_svc
from recipes.models import ProductVariant, Recipe, RecipeLine, RecipeVersion
from recipes.services import costing as recipes_costing_svc


def _make_ingredient(tenant, category, unit, *, name, barcode, sku, cost):
    """`unit` is a shared `Unit` row (e.g. one "Gram" per tenant) — reused
    across every ingredient product rather than created fresh each time,
    since `Unit` is unique per `(tenant, unit_group, name)`."""
    product = Product.objects.create(
        tenant=tenant, category=category, name=name, barcode=barcode, sku=sku,
        price=Decimal('0.00'), cost=cost, stock=Decimal('0'),
    )
    base = ProductUnit.objects.create(
        tenant=tenant, product=product, unit=unit,
        conversion_to_base=Decimal('1'), is_base=True, is_sale_unit=True, is_purchase_unit=True,
    )
    InventoryCost.objects.create(tenant=tenant, product=product, branch=None, avg_unit_cost=cost)
    return product, base


class _RecipeTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Recipe Tenant')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.ingredients_cat = Category.objects.create(tenant=cls.tenant, name='Ingredients')
        cls.mass = UnitGroup.objects.create(tenant=cls.tenant, name='Mass')
        cls.gram = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.mass, name='Gram', symbol='g',
            factor_to_base=Decimal('1'), allow_decimal=True,
        )

        cls.sandwich = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Chicken Caesar', barcode='SW-CAESAR', sku='SKU-CAESAR',
            price=Decimal('95.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )

        cls.chicken, cls.chicken_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Chicken Breast', barcode='ING-CHK', sku='SKU-CHK', cost=Decimal('0.1250'),
        )
        cls.lettuce, cls.lettuce_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Lettuce', barcode='ING-LET', sku='SKU-LET', cost=Decimal('0.0267'),
        )
        cls.sauce, cls.sauce_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Caesar Sauce', barcode='ING-SAU', sku='SKU-SAU', cost=Decimal('0.1000'),
        )
        cls.parmesan, cls.parmesan_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Parmesan', barcode='ING-PAR', sku='SKU-PAR', cost=Decimal('0.2900'),
        )
        cls.bread, cls.bread_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Bread', barcode='ING-BRD', sku='SKU-BRD', cost=Decimal('0.0417'),
        )

    def _create_recipe(self, product, variant=None):
        return Recipe.objects.create(tenant=self.tenant, product=product, variant=variant)

    def _add_version(self, recipe, lines, status=RecipeVersion.Status.DRAFT, version_no=1):
        version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=version_no, status=status,
        )
        for idx, (component, unit, qty) in enumerate(lines):
            RecipeLine.objects.create(
                tenant=self.tenant, recipe_version=version,
                component_product=component, component_unit=unit,
                entered_qty=Decimal(str(qty)), qty_base=Decimal(str(qty)),
                sort_order=idx,
            )
        return version


class RecipeCostCalculationTests(_RecipeTestBase):
    def test_owner_worked_example_chicken_caesar(self):
        """The Business Owner's own worked example: Chicken 180g, Lettuce
        120g, Caesar Sauce 40g, Parmesan 20g, Bread 60g."""
        recipe = self._create_recipe(self.sandwich)
        version = self._add_version(recipe, [
            (self.chicken, self.chicken_unit, '180'),
            (self.lettuce, self.lettuce_unit, '120'),
            (self.sauce, self.sauce_unit, '40'),
            (self.parmesan, self.parmesan_unit, '20'),
            (self.bread, self.bread_unit, '60'),
        ])
        result = recipes_costing_svc.compute_recipe_cost(version)
        # 180*0.1250=22.50, 120*0.0267=3.20, 40*0.10=4.00, 20*0.29=5.80, 60*0.0417=2.50
        self.assertEqual(result.total_cost, Decimal('38.00'))
        self.assertEqual(len(result.lines), 5)

    def test_branch_scoped_recipe_cost_differs_per_branch(self):
        branch_a = Branch.objects.create(tenant=self.tenant, name='Branch A')
        branch_b = Branch.objects.create(tenant=self.tenant, name='Branch B')
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.chicken, branch=branch_a,
            avg_unit_cost=Decimal('0.1000'),
        )
        InventoryCost.objects.create(
            tenant=self.tenant, product=self.chicken, branch=branch_b,
            avg_unit_cost=Decimal('0.2000'),
        )
        recipe = self._create_recipe(self.sandwich)
        version = self._add_version(recipe, [(self.chicken, self.chicken_unit, '100')])

        result_a = recipes_costing_svc.compute_recipe_cost(version, branch=branch_a)
        result_b = recipes_costing_svc.compute_recipe_cost(version, branch=branch_b)
        self.assertEqual(result_a.total_cost, Decimal('10.00'))
        self.assertEqual(result_b.total_cost, Decimal('20.00'))

    def test_recipe_definition_unchanged_cost_moves_with_ingredient_price(self):
        """The owner's own requirement: 'the recipe stays the same, but the
        cost of the new sale changes automatically' when an ingredient's
        price moves."""
        recipe = self._create_recipe(self.sandwich)
        version = self._add_version(recipe, [(self.chicken, self.chicken_unit, '100')])
        first = recipes_costing_svc.compute_recipe_cost(version)
        self.assertEqual(first.total_cost, Decimal('12.50'))

        pos_costing_svc.apply_purchase_receipt(
            product=self.chicken, qty=Decimal('100'), unit_cost=Decimal('0.5000'),
            source_document_type='purchase_invoice',
        )
        second = recipes_costing_svc.compute_recipe_cost(version)
        self.assertNotEqual(second.total_cost, first.total_cost)
        self.assertEqual(RecipeLine.objects.filter(recipe_version=version).count(), 1, 'lines unchanged')


class RecipeDepthCycleValidationTests(_RecipeTestBase):
    def test_depth_2_sub_recipe_allowed(self):
        """Garlic Sauce is itself a recipe (mayo); a sandwich using Garlic
        Sauce as a component is depth 2 — allowed (D-26)."""
        mayo, mayo_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Mayo', barcode='ING-MAY', sku='SKU-MAY', cost=Decimal('0.05'),
        )
        garlic_sauce, garlic_base = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Garlic Sauce', barcode='ING-GSAUCE', sku='SKU-GSAUCE', cost=Decimal('0.00'),
        )
        garlic_recipe = self._create_recipe(garlic_sauce)
        self._add_version(
            garlic_recipe, [(mayo, mayo_unit, '50')],
            status=RecipeVersion.Status.ACTIVE,
        )

        # Should not raise.
        recipes_costing_svc.validate_recipe_lines(
            product=self.sandwich, component_products=[garlic_sauce],
        )

    def test_depth_3_rejected(self):
        """Garlic Sauce's own component (Mayo) also has an active recipe —
        pushing the sandwich's chain to depth 3, over the D-26 cap of 2."""
        oil, oil_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Oil', barcode='ING-OIL', sku='SKU-OIL', cost=Decimal('0.03'),
        )
        mayo, mayo_base = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Mayo', barcode='ING-MAY2', sku='SKU-MAY2', cost=Decimal('0.00'),
        )
        mayo_recipe = self._create_recipe(mayo)
        self._add_version(mayo_recipe, [(oil, oil_unit, '10')], status=RecipeVersion.Status.ACTIVE)

        garlic_sauce, garlic_base = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Garlic Sauce Deep', barcode='ING-GSAUCE2', sku='SKU-GSAUCE2', cost=Decimal('0.00'),
        )
        garlic_recipe = self._create_recipe(garlic_sauce)
        self._add_version(garlic_recipe, [(mayo, mayo_base, '50')], status=RecipeVersion.Status.ACTIVE)

        with self.assertRaises(recipes_costing_svc.RecipeError):
            recipes_costing_svc.validate_recipe_lines(
                product=self.sandwich, component_products=[garlic_sauce],
            )

    def test_self_reference_rejected(self):
        with self.assertRaises(recipes_costing_svc.RecipeError):
            recipes_costing_svc.validate_recipe_lines(
                product=self.sandwich, component_products=[self.sandwich],
            )

    def test_indirect_cycle_rejected(self):
        """Sandwich would use Garlic Sauce, but Garlic Sauce's own recipe
        references the Sandwich back — a cycle."""
        garlic_sauce, garlic_base = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Circular Sauce', barcode='ING-CIRC', sku='SKU-CIRC', cost=Decimal('0.00'),
        )
        garlic_recipe = self._create_recipe(garlic_sauce)
        self._add_version(
            garlic_recipe, [(self.sandwich, garlic_base, '10')],
            status=RecipeVersion.Status.ACTIVE,
        )
        with self.assertRaises(recipes_costing_svc.RecipeError):
            recipes_costing_svc.validate_recipe_lines(
                product=self.sandwich, component_products=[garlic_sauce],
            )


class RecipeVersionModelTests(_RecipeTestBase):
    def test_only_one_active_version_enforced_at_db_level(self):
        recipe = self._create_recipe(self.sandwich)
        RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RecipeVersion.objects.create(
                    tenant=self.tenant, recipe=recipe, version_no=2,
                    status=RecipeVersion.Status.ACTIVE,
                )

    def test_activate_recipe_version_archives_previous(self):
        recipe = self._create_recipe(self.sandwich)
        v1 = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        v2 = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=2,
            status=RecipeVersion.Status.DRAFT,
        )
        recipes_costing_svc.activate_recipe_version(v2)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, RecipeVersion.Status.ARCHIVED)
        self.assertEqual(v2.status, RecipeVersion.Status.ACTIVE)

    def test_get_active_recipe_returns_none_when_only_draft(self):
        recipe = self._create_recipe(self.sandwich)
        RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=1,
            status=RecipeVersion.Status.DRAFT,
        )
        self.assertIsNone(recipes_costing_svc.get_active_recipe(self.sandwich))

    def test_component_product_protected_from_deletion(self):
        recipe = self._create_recipe(self.sandwich)
        self._add_version(recipe, [(self.chicken, self.chicken_unit, '100')])
        with self.assertRaises(ProtectedError):
            self.chicken.delete()

    def test_recipe_uniqueness_product_variant_pair(self):
        self._create_recipe(self.sandwich)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_recipe(self.sandwich)

    def test_recipe_and_variant_recipe_are_independent(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('120.00'),
        )
        base_recipe = self._create_recipe(self.sandwich)
        variant_recipe = self._create_recipe(self.sandwich, variant=variant)
        self.assertNotEqual(base_recipe.id, variant_recipe.id)
        self.assertEqual(Recipe.objects.filter(product=self.sandwich).count(), 2)


class RecipeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Recipe Api Tenant')
        cls.manager = User.objects.create_user(
            username='recmgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='reccsh', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.ingredients_cat = Category.objects.create(tenant=cls.tenant, name='Ingredients')
        cls.mass = UnitGroup.objects.create(tenant=cls.tenant, name='Mass')
        cls.gram = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.mass, name='Gram', symbol='g',
            factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.sandwich = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Club Sandwich', barcode='API-SW', sku='SKU-API-SW',
            price=Decimal('60.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.chicken, cls.chicken_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Chicken', barcode='API-CHK', sku='SKU-API-CHK', cost=Decimal('0.10'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_create_recipe_then_version_then_activate(self):
        resp = self.client.post(
            reverse('recipe-list', args=[self.sandwich.id]), {}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        recipe_id = resp.json()['id']

        resp2 = self.client.post(
            reverse('recipe-version-list', args=[self.sandwich.id, recipe_id]),
            {'lines': [{'component_product': self.chicken.id, 'entered_qty': '150'}]},
            format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.content)
        version_data = resp2.json()
        self.assertEqual(version_data['status'], 'draft')
        self.assertEqual(len(version_data['lines']), 1)
        self.assertEqual(version_data['lines'][0]['qty_base'], '150.0000')

        resp3 = self.client.post(
            reverse('recipe-version-activate', args=[self.sandwich.id, recipe_id, version_data['id']]),
        )
        self.assertEqual(resp3.status_code, status.HTTP_200_OK, resp3.content)
        self.assertEqual(resp3.json()['status'], 'active')

    def test_version_requires_at_least_one_line(self):
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        resp = self.client.post(
            reverse('recipe-version-list', args=[self.sandwich.id, recipe.id]),
            {'lines': []}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_forbidden_to_write_versions(self):
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(
            reverse('recipe-version-list', args=[self.sandwich.id, recipe.id]),
            {'lines': [{'component_product': self.chicken.id, 'entered_qty': '150'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_self_referencing_recipe_rejected_with_400(self):
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        resp = self.client.post(
            reverse('recipe-version-list', args=[self.sandwich.id, recipe.id]),
            {'lines': [{'component_product': self.sandwich.id, 'entered_qty': '1'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
