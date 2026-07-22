"""Sprint 5 Batch 3 — Recipe / RecipeVersion / RecipeLine + cost service.

Model/service-level tests (cost roll-up, branch scoping, depth/cycle
validation, one-active-version invariant, PROTECT) plus a smaller set of
API-level CRUD/activation tests, mirroring the depth of coverage
`pos/test_costing.py` established for the AVCO engine.
"""

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    Branch, BranchPaymentMethod, Customer, CustomerARMovement,
    FinancialAccount, FinancialAccountMovement, PaymentMethod, Tenant, User,
)
from pos.models import (
    BranchWarehouse, Category, InventoryCost, Product, ProductUnit, Sale,
    StockMovement, Unit, UnitGroup, Warehouse, WarehouseStock,
)
from pos.services import costing as pos_costing_svc
from pos.services import stock_movements as stock_svc
from pos.services.product_types import ProductType
from recipes.models import (
    ModifierGroup, ModifierOption, ModifierOptionConsumption,
    ProductModifierGroup, ProductVariant, Recipe, RecipeLine, RecipeVersion,
    SaleItemModifier, SaleItemRecipeCostSnapshot,
)
from recipes.services import costing as recipes_costing_svc


def _grant_default_routing(tenant, branch):
    """Mirrors `pos.tests._grant_default_routing` (private to that module) —
    under strict routing (GA-2) every completed sale must resolve a
    payment route, so any test posting a real sale needs this."""
    accounts = {}
    for acct_type, name in [
        (FinancialAccount.AccountType.CASHBOX,         'Main Cashbox'),
        (FinancialAccount.AccountType.CARD_SETTLEMENT, 'Card Settlement'),
        (FinancialAccount.AccountType.WALLET,          'Wallet'),
    ]:
        accounts[acct_type] = FinancialAccount.objects.create(
            tenant=tenant, name=f'{name} ({branch.name})', account_type=acct_type,
        )
    for mtype, acct_type in [
        (PaymentMethod.MethodType.CASH,   FinancialAccount.AccountType.CASHBOX),
        (PaymentMethod.MethodType.CARD,   FinancialAccount.AccountType.CARD_SETTLEMENT),
        (PaymentMethod.MethodType.WALLET, FinancialAccount.AccountType.WALLET),
    ]:
        pm = PaymentMethod.objects.create(
            tenant=tenant, name=f'{mtype} ({branch.name})', method_type=mtype,
        )
        BranchPaymentMethod.objects.create(
            tenant=tenant, branch=branch, payment_method=pm,
            destination_account=accounts[acct_type],
            is_default=True, is_active=True,
        )
    return accounts


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

    def test_recipe_detail_get_and_patch(self):
        """Batch 7 verification (coverage gap review) — RecipeDetailView
        (GET/PATCH one recipe) was never called by any test before this;
        every prior test only ever POSTed to recipe-list or nested versions."""
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        get_resp = self.client.get(reverse('recipe-detail', args=[self.sandwich.id, recipe.id]))
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK, get_resp.content)
        self.assertEqual(get_resp.json()['id'], recipe.id)
        self.assertTrue(get_resp.json()['is_active'])

        patch_resp = self.client.patch(
            reverse('recipe-detail', args=[self.sandwich.id, recipe.id]),
            {'is_active': False}, format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.content)
        recipe.refresh_from_db()
        self.assertFalse(recipe.is_active)

    def test_recipe_detail_cashier_can_read_but_not_write(self):
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        self.client.force_authenticate(user=self.cashier)
        get_resp = self.client.get(reverse('recipe-detail', args=[self.sandwich.id, recipe.id]))
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        patch_resp = self.client.patch(
            reverse('recipe-detail', args=[self.sandwich.id, recipe.id]),
            {'is_active': False}, format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_recipe_list_filters_by_variant_id(self):
        """The `?variant_id=` filter on RecipeListCreateView.get_queryset
        was defined in Batch 3 but never exercised by any test."""
        base_recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich, variant=None)
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('90.00'),
        )
        variant_recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich, variant=variant)

        resp_all = self.client.get(reverse('recipe-list', args=[self.sandwich.id]))
        self.assertEqual(resp_all.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {r['id'] for r in resp_all.json()['results']}, {base_recipe.id, variant_recipe.id},
        )

        resp_filtered = self.client.get(
            reverse('recipe-list', args=[self.sandwich.id]), {'variant_id': variant.id},
        )
        self.assertEqual(resp_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [r['id'] for r in resp_filtered.json()['results']], [variant_recipe.id],
        )

    def test_recipe_version_detail_get(self):
        """RecipeVersionDetailView (GET one version) was never called
        directly by any test before this — only the list/create and
        activate endpoints were exercised."""
        recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich)
        version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=recipe, version_no=1, status=RecipeVersion.Status.DRAFT,
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=version,
            component_product=self.chicken, component_unit=self.chicken_unit,
            entered_qty=Decimal('100'), qty_base=Decimal('100'),
        )
        resp = self.client.get(
            reverse('recipe-version-detail', args=[self.sandwich.id, recipe.id, version.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['id'], version.id)
        self.assertEqual(len(resp.json()['lines']), 1)


# ── Sprint 5 Batch 4: Modifiers ──────────────────────────────────────────────

class ModifierDeltaCalculationTests(_RecipeTestBase):
    def _make_group_and_option(self, *, name='Extras', option_name='Extra Cheese', price_delta='6.00'):
        group = ModifierGroup.objects.create(tenant=self.tenant, name=name)
        option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=group, name=option_name,
            price_delta=Decimal(price_delta),
        )
        return group, option

    def test_positive_delta_contributes_cost(self):
        _, option = self._make_group_and_option()
        cheese, cheese_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Mozzarella', barcode='ING-MOZ', sku='SKU-MOZ', cost=Decimal('0.15'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=cheese, component_unit=cheese_unit,
            entered_qty=Decimal('40'), qty_base=Decimal('40'),
        )
        result = recipes_costing_svc.compute_modifier_deltas(option)
        self.assertEqual(result.total_cost, Decimal('6.00'))  # 40 * 0.15
        self.assertEqual(len(result.lines), 1)

    def test_negative_delta_contributes_zero_cost(self):
        """D-34: 'No Onion' removes an ingredient — it must not create a
        negative COGS line."""
        _, option = self._make_group_and_option(name='Removals', option_name='No Onion', price_delta='0.00')
        onion, onion_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Onion', barcode='ING-ONI', sku='SKU-ONI', cost=Decimal('0.02'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=onion, component_unit=onion_unit,
            entered_qty=Decimal('-20'), qty_base=Decimal('-20'),
        )
        result = recipes_costing_svc.compute_modifier_deltas(option)
        self.assertEqual(result.total_cost, Decimal('0.00'))
        self.assertEqual(len(result.lines), 0)

    def test_free_modifier_still_contributes_full_cost(self):
        _, option = self._make_group_and_option(option_name='Free Extra Sauce', price_delta='0.00')
        sauce, sauce_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='House Sauce', barcode='ING-HSAUCE', sku='SKU-HSAUCE', cost=Decimal('0.10'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=sauce, component_unit=sauce_unit,
            entered_qty=Decimal('30'), qty_base=Decimal('30'),
        )
        self.assertEqual(option.price_delta, Decimal('0.00'))
        result = recipes_costing_svc.compute_modifier_deltas(option)
        self.assertEqual(result.total_cost, Decimal('3.00'), 'free modifier still counts as COGS (D-34)')

    def test_variant_specific_consumption_preferred_over_agnostic(self):
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('120.00'),
        )
        _, option = self._make_group_and_option()
        cheese, cheese_unit = _make_ingredient(
            self.tenant, self.ingredients_cat, self.gram,
            name='Cheddar', barcode='ING-CHD', sku='SKU-CHD', cost=Decimal('0.20'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=cheese, component_unit=cheese_unit,
            entered_qty=Decimal('40'), qty_base=Decimal('40'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=variant,
            component_product=cheese, component_unit=cheese_unit,
            entered_qty=Decimal('80'), qty_base=Decimal('80'),
        )
        result_no_variant = recipes_costing_svc.compute_modifier_deltas(option, variant=None)
        result_variant = recipes_costing_svc.compute_modifier_deltas(option, variant=variant)
        self.assertEqual(result_no_variant.total_cost, Decimal('8.00'))   # 40 * 0.20
        self.assertEqual(result_variant.total_cost, Decimal('16.00'))    # 80 * 0.20 (variant-specific row wins)


class ModifierApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Modifier Api Tenant')
        cls.manager = User.objects.create_user(
            username='modmgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='modcsh', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.ingredients_cat = Category.objects.create(tenant=cls.tenant, name='Ingredients')
        cls.mass = UnitGroup.objects.create(tenant=cls.tenant, name='Mass')
        cls.gram = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.mass, name='Gram', symbol='g',
            factor_to_base=Decimal('1'), allow_decimal=True,
        )
        cls.pizza = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Pizza', barcode='MOD-PZ', sku='SKU-MOD-PZ',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.cheese, cls.cheese_unit = _make_ingredient(
            cls.tenant, cls.ingredients_cat, cls.gram,
            name='Cheese', barcode='MOD-CHZ', sku='SKU-MOD-CHZ', cost=Decimal('0.15'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_create_group_option_consumption_and_attach_to_product(self):
        resp = self.client.post(reverse('modifier-group-list'), {'name': 'Pizza Toppings'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        group_id = resp.json()['id']

        resp2 = self.client.post(
            reverse('modifier-option-list', args=[group_id]),
            {'name': 'Extra Cheese', 'price_delta': '6.00'}, format='json',
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.content)
        option_id = resp2.json()['id']

        resp3 = self.client.post(
            reverse('modifier-option-consumption-list', args=[option_id]),
            {'component_product': self.cheese.id, 'entered_qty': '40'}, format='json',
        )
        self.assertEqual(resp3.status_code, status.HTTP_201_CREATED, resp3.content)
        self.assertEqual(resp3.json()['qty_base'], '40.0000')

        resp4 = self.client.post(
            reverse('product-modifier-group-list', args=[self.pizza.id]),
            {'modifier_group': group_id}, format='json',
        )
        self.assertEqual(resp4.status_code, status.HTTP_201_CREATED, resp4.content)
        self.assertEqual(ProductModifierGroup.objects.filter(product=self.pizza).count(), 1)

    def test_negative_entered_qty_accepted_for_removal_modifier(self):
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Removals')
        option = ModifierOption.objects.create(tenant=self.tenant, modifier_group=group, name='No Onion')
        resp = self.client.post(
            reverse('modifier-option-consumption-list', args=[option.id]),
            {'component_product': self.cheese.id, 'entered_qty': '-20'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['qty_base'], '-20.0000')

    def test_zero_entered_qty_rejected(self):
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Zero Test')
        option = ModifierOption.objects.create(tenant=self.tenant, modifier_group=group, name='Nothing')
        resp = self.client.post(
            reverse('modifier-option-consumption-list', args=[option.id]),
            {'component_product': self.cheese.id, 'entered_qty': '0'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_forbidden_to_create_group(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(reverse('modifier-group-list'), {'name': 'Cashier Group'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_group_name_rejected(self):
        ModifierGroup.objects.create(tenant=self.tenant, name='Dup Group')
        resp = self.client.post(reverse('modifier-group-list'), {'name': 'Dup Group'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_detach_modifier_group_from_product(self):
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Detach Group')
        link = ProductModifierGroup.objects.create(
            tenant=self.tenant, product=self.pizza, modifier_group=group,
        )
        resp = self.client.delete(
            reverse('product-modifier-group-detail', args=[self.pizza.id, link.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProductModifierGroup.objects.filter(pk=link.id).exists())

    def test_modifier_group_detail_get_patch_and_deactivate(self):
        """Batch 7 verification (coverage gap review) — ModifierGroupDetailView
        and ModifierGroupDeactivateView were defined in Batch 4 but never
        called by any test; only modifier-group-list (create) was exercised."""
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Sauces')
        get_resp = self.client.get(reverse('modifier-group-detail', args=[group.id]))
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK, get_resp.content)
        self.assertEqual(get_resp.json()['name'], 'Sauces')

        patch_resp = self.client.patch(
            reverse('modifier-group-detail', args=[group.id]), {'name': 'Sauces Renamed'}, format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.content)
        group.refresh_from_db()
        self.assertEqual(group.name, 'Sauces Renamed')

        deactivate_resp = self.client.post(reverse('modifier-group-deactivate', args=[group.id]))
        self.assertEqual(deactivate_resp.status_code, status.HTTP_200_OK, deactivate_resp.content)
        group.refresh_from_db()
        self.assertFalse(group.is_active)

        self.client.force_authenticate(user=self.cashier)
        get_resp_cashier = self.client.get(reverse('modifier-group-detail', args=[group.id]))
        self.assertEqual(get_resp_cashier.status_code, status.HTTP_200_OK)
        patch_resp_cashier = self.client.patch(
            reverse('modifier-group-detail', args=[group.id]), {'name': 'Blocked'}, format='json',
        )
        self.assertEqual(patch_resp_cashier.status_code, status.HTTP_403_FORBIDDEN)
        deactivate_resp_cashier = self.client.post(reverse('modifier-group-deactivate', args=[group.id]))
        self.assertEqual(deactivate_resp_cashier.status_code, status.HTTP_403_FORBIDDEN)

    def test_modifier_option_detail_get_patch_and_deactivate(self):
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Toppings')
        option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=group, name='Olives', price_delta=Decimal('3.00'),
        )
        get_resp = self.client.get(reverse('modifier-option-detail', args=[group.id, option.id]))
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK, get_resp.content)
        self.assertEqual(get_resp.json()['name'], 'Olives')

        patch_resp = self.client.patch(
            reverse('modifier-option-detail', args=[group.id, option.id]),
            {'price_delta': '4.00'}, format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.content)
        option.refresh_from_db()
        self.assertEqual(option.price_delta, Decimal('4.00'))

        deactivate_resp = self.client.post(
            reverse('modifier-option-deactivate', args=[group.id, option.id]),
        )
        self.assertEqual(deactivate_resp.status_code, status.HTTP_200_OK, deactivate_resp.content)
        option.refresh_from_db()
        self.assertFalse(option.is_active)

    def test_modifier_option_consumption_detail_get(self):
        """ModifierOptionConsumptionDetailView (GET/PATCH one consumption
        row) was never called directly by any test — only the list/create
        endpoint was exercised."""
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Extras Detail')
        option = ModifierOption.objects.create(tenant=self.tenant, modifier_group=group, name='Bacon')
        consumption = ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=self.cheese, component_unit=self.cheese_unit,
            entered_qty=Decimal('25'), qty_base=Decimal('25'),
        )
        resp = self.client.get(
            reverse('modifier-option-consumption-detail', args=[option.id, consumption.id]),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['id'], consumption.id)


# ── Sprint 5 Batch 5: RECIPE_CONSUME sale-posting integration ──────────────
# Highest regression risk in the sprint — touches the shared SaleSerializer
# create()/_apply_stock() path. pos.tests' full 213-test sale-posting suite
# was re-run unmodified before writing anything below and stayed green,
# confirming zero behavior change for every non-recipe (stock_item) line.

class RecipeSalePostingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Recipe Sale Tenant')
        cls.branch_a = Branch.objects.create(tenant=cls.tenant, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant, name='Branch B')
        cls.manager_a = User.objects.create_user(
            username='rsmgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch_a,
        )
        cls.manager_b = User.objects.create_user(
            username='rsmgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch_b,
        )
        _grant_default_routing(cls.tenant, cls.branch_a)
        _grant_default_routing(cls.tenant, cls.branch_b)

        # Batch 7 verification: a branch with NO default kitchen/sales
        # warehouse configured at all — exercises `resolve_kitchen_
        # warehouse`'s RecipeError path (a real "new branch not fully set
        # up yet" scenario), previously untested (0% coverage on that
        # branch per `coverage run`).
        cls.branch_c = Branch.objects.create(tenant=cls.tenant, name='Branch C (no kitchen)')
        cls.manager_c = User.objects.create_user(
            username='rsmgr_c', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch_c,
        )

        cls.category = Category.objects.create(tenant=cls.tenant, name='Menu')
        cls.ingredients_cat = Category.objects.create(tenant=cls.tenant, name='Ingredients')
        cls.mass = UnitGroup.objects.create(tenant=cls.tenant, name='Mass')
        cls.gram = Unit.objects.create(
            tenant=cls.tenant, unit_group=cls.mass, name='Gram', symbol='g',
            factor_to_base=Decimal('1'), allow_decimal=True,
        )

        cls.wh_a = Warehouse.objects.create(tenant=cls.tenant, code='KIT-A', name='Kitchen A')
        cls.wh_b = Warehouse.objects.create(tenant=cls.tenant, code='KIT-B', name='Kitchen B')
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_a, warehouse=cls.wh_a,
            role=BranchWarehouse.Role.KITCHEN, is_default=True, is_active=True,
        )
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch_b, warehouse=cls.wh_b,
            role=BranchWarehouse.Role.KITCHEN, is_default=True, is_active=True,
        )

        cls.chicken = Product.objects.create(
            tenant=cls.tenant, category=cls.ingredients_cat,
            name='Chicken', barcode='RS-CHK', sku='SKU-RS-CHK',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.chicken_unit = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.chicken, unit=cls.gram,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.lettuce = Product.objects.create(
            tenant=cls.tenant, category=cls.ingredients_cat,
            name='Lettuce', barcode='RS-LET', sku='SKU-RS-LET',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.lettuce_unit = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.lettuce, unit=cls.gram,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        cls.cheese = Product.objects.create(
            tenant=cls.tenant, category=cls.ingredients_cat,
            name='Cheese', barcode='RS-CHZ', sku='SKU-RS-CHZ',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.cheese_unit = ProductUnit.objects.create(
            tenant=cls.tenant, product=cls.cheese, unit=cls.gram,
            conversion_to_base=Decimal('1'), is_base=True,
        )

        # Stock both branches with plenty of ingredients — branch A's
        # chicken is deliberately priced differently from branch B's, to
        # prove branch-scoped costing flows all the way into a real sale.
        for branch, warehouse, chicken_cost in (
            (cls.branch_a, cls.wh_a, Decimal('0.10')),
            (cls.branch_b, cls.wh_b, Decimal('0.20')),
        ):
            for product, unit_cost in (
                (cls.chicken, chicken_cost),
                (cls.lettuce, Decimal('0.02')),
                (cls.cheese, Decimal('0.15')),
            ):
                qty = Decimal('50000')  # StockMovement.qty is Decimal(8,3): must stay < 10^5
                pos_costing_svc.apply_purchase_receipt(
                    product=product, qty=qty, unit_cost=unit_cost, branch=branch,
                    source_document_type='purchase_invoice',
                )
                stock_svc.record_stock_in(
                    product=product, quantity=qty,
                    movement_type=StockMovement.MovementType.PURCHASE_IN,
                    branch=branch, warehouse=warehouse,
                    source_document_type='purchase_invoice',
                )

        cls.sandwich = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Chicken Sandwich', barcode='RS-SW', sku='SKU-RS-SW',
            price=Decimal('50.00'), cost=Decimal('0.00'), stock=Decimal('0'),
            product_type=ProductType.RECIPE_PRODUCT,
        )
        cls.recipe = Recipe.objects.create(tenant=cls.tenant, product=cls.sandwich)
        cls.recipe_version = RecipeVersion.objects.create(
            tenant=cls.tenant, recipe=cls.recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        RecipeLine.objects.create(
            tenant=cls.tenant, recipe_version=cls.recipe_version,
            component_product=cls.chicken, component_unit=cls.chicken_unit,
            entered_qty=Decimal('150'), qty_base=Decimal('150'), sort_order=0,
        )
        RecipeLine.objects.create(
            tenant=cls.tenant, recipe_version=cls.recipe_version,
            component_product=cls.lettuce, component_unit=cls.lettuce_unit,
            entered_qty=Decimal('50'), qty_base=Decimal('50'), sort_order=1,
        )
        # Base recipe cost @ branch A: 150*0.10 + 50*0.02 = 16.00.

        cls.cheese_group = ModifierGroup.objects.create(tenant=cls.tenant, name='Extras')
        cls.cheese_option = ModifierOption.objects.create(
            tenant=cls.tenant, modifier_group=cls.cheese_group,
            name='Extra Cheese', price_delta=Decimal('6.00'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=cls.tenant, modifier_option=cls.cheese_option, variant=None,
            component_product=cls.cheese, component_unit=cls.cheese_unit,
            entered_qty=Decimal('40'), qty_base=Decimal('40'),
        )
        # Batch 7 gate: the sale path now rejects a modifier that isn't
        # offered for the product, so the fixture must attach the group.
        ProductModifierGroup.objects.create(
            tenant=cls.tenant, product=cls.sandwich, modifier_group=cls.cheese_group,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)

    def _post_sale(self, items, user=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        body = {'items': items, 'method': 'cash', 'amount_paid': '1000.00'}
        return self.client.post(reverse('sale-list'), body, format='json')

    def test_recipe_sale_end_to_end_deducts_ingredients_and_snapshots_cost(self):
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        self.assertEqual(item.unit_cost, Decimal('16.00'))
        self.assertEqual(item.price_each, Decimal('50.00'))

        chicken_mv = StockMovement.objects.get(
            product=self.chicken, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            source_document_id=sale.id,
        )
        self.assertEqual(chicken_mv.qty, Decimal('-150.000'))
        self.assertEqual(chicken_mv.branch_id, self.branch_a.id)
        self.assertEqual(chicken_mv.warehouse_id, self.wh_a.id)

        lettuce_mv = StockMovement.objects.get(
            product=self.lettuce, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            source_document_id=sale.id,
        )
        self.assertEqual(lettuce_mv.qty, Decimal('-50.000'))

        snapshot = SaleItemRecipeCostSnapshot.objects.get(sale_item=item)
        self.assertEqual(snapshot.total_recipe_cost, Decimal('16.00'))
        self.assertEqual(snapshot.lines.count(), 2)

        # The recipe product itself has no stock of its own — no SALE_OUT.
        self.assertFalse(StockMovement.objects.filter(product=self.sandwich).exists())

    def test_recipe_sale_with_modifier_adds_cost_and_price(self):
        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [self.cheese_option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        self.assertEqual(item.unit_cost, Decimal('22.00'))    # 16.00 + 40*0.15
        self.assertEqual(item.price_each, Decimal('56.00'))   # 50.00 + 6.00

        self.assertTrue(
            SaleItemModifier.objects.filter(sale_item=item, option_name='Extra Cheese').exists()
        )
        cheese_mv = StockMovement.objects.get(
            product=self.cheese, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            source_document_id=sale.id,
        )
        self.assertEqual(cheese_mv.qty, Decimal('-40.000'))

    def test_credit_recipe_sale_posts_correct_ar_charge_unaffected_by_recipe_logic(self):
        """User question (pre-close-out review): does the AR/GL pipeline
        stay correct for a recipe sale? `SaleSerializer.create()` calls
        `sale_posting.post_sale_ledgers(sale=sale, method=..., customer=...)`
        exactly ONCE per sale, after every item (recipe or plain stock-item)
        has already been processed — it reads only `sale.total`/`method`/
        `customer`, never `SaleItem.variant`/`SaleItemModifier`/the recipe
        cost snapshot, so it structurally cannot be affected by anything
        Sprint 5 added. This proves it end-to-end for a CREDIT sale (the
        one payment method that actually touches `CustomerARMovement`) of a
        recipe product with a modifier."""
        customer = Customer.objects.create(tenant=self.tenant, name='Regular Customer')
        ar_before = CustomerARMovement.objects.filter(customer=customer).count()
        fam_before = FinancialAccountMovement.objects.count()

        resp = self.client.post(reverse('sale-list'), {
            'items': [{
                'product': self.sandwich.id, 'qty': '1',
                'modifier_option_ids': [self.cheese_option.id],
            }],
            'method': 'credit', 'customer': customer.id, 'amount_paid': '0.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        # 50.00 base + 6.00 modifier price delta, plus the product's default
        # tax rate — whatever `sale.total` actually is, the AR charge must
        # match it exactly (that's the property under test, not the literal
        # number).
        self.assertGreater(sale.total, Decimal('56.00'))

        ar_rows = CustomerARMovement.objects.filter(customer=customer)
        self.assertEqual(ar_rows.count(), ar_before + 1)
        ar_mv = ar_rows.latest('id')
        self.assertEqual(ar_mv.debit, sale.total)  # a sale is a debit — customer owes more
        self.assertEqual(ar_mv.credit, Decimal('0'))
        self.assertEqual(ar_mv.source_document_type, 'sale')
        self.assertEqual(ar_mv.source_document_id, sale.id)

        # Credit sales never touch the cash-drawer ledger.
        self.assertEqual(FinancialAccountMovement.objects.count(), fam_before)

    def test_recipe_sale_with_variant_uses_variant_recipe_and_price(self):
        large = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('70.00'),
        )
        large_recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich, variant=large)
        large_version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=large_recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=large_version,
            component_product=self.chicken, component_unit=self.chicken_unit,
            entered_qty=Decimal('300'), qty_base=Decimal('300'),
        )

        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1', 'variant': large.id}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        self.assertEqual(item.unit_cost, Decimal('30.00'))   # 300*0.10, NOT the base recipe
        self.assertEqual(item.price_each, Decimal('70.00'))
        self.assertEqual(item.variant_id, large.id)

        chicken_mv = StockMovement.objects.get(
            product=self.chicken, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            source_document_id=sale.id,
        )
        self.assertEqual(chicken_mv.qty, Decimal('-300.000'))
        # The base recipe's lettuce line must NOT fire — a variant's recipe
        # is fully independent, not the base recipe plus a multiplier.
        self.assertFalse(
            StockMovement.objects.filter(
                product=self.lettuce, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                source_document_id=sale.id,
            ).exists()
        )

    def test_branch_scoped_cost_in_real_sale(self):
        resp_a = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}], user=self.manager_a)
        resp_b = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}], user=self.manager_b)
        self.assertEqual(resp_a.status_code, status.HTTP_201_CREATED, resp_a.content)
        self.assertEqual(resp_b.status_code, status.HTTP_201_CREATED, resp_b.content)

        item_a = Sale.objects.get(sale_uuid=resp_a.json()['sale_uuid']).items.get(product=self.sandwich)
        item_b = Sale.objects.get(sale_uuid=resp_b.json()['sale_uuid']).items.get(product=self.sandwich)
        self.assertEqual(item_a.unit_cost, Decimal('16.00'))  # branch A: chicken @ 0.10
        self.assertEqual(item_b.unit_cost, Decimal('31.00'))  # branch B: chicken @ 0.20 -> 30.00 + 1.00

    def test_snapshot_immutable_after_later_purchase_changes_average(self):
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)
        original_cost = item.unit_cost
        self.assertEqual(original_cost, Decimal('16.00'))

        # A later purchase moves branch A's chicken average sharply.
        pos_costing_svc.apply_purchase_receipt(
            product=self.chicken, qty=Decimal('1'), unit_cost=Decimal('999.00'),
            branch=self.branch_a, source_document_type='purchase_invoice',
        )

        item.refresh_from_db()
        self.assertEqual(item.unit_cost, original_cost, 'a sale snapshot must never drift')
        snapshot = SaleItemRecipeCostSnapshot.objects.get(sale_item=item)
        self.assertEqual(snapshot.total_recipe_cost, original_cost)
        chicken_line = snapshot.lines.get(component_product=self.chicken)
        self.assertEqual(chicken_line.unit_cost, Decimal('0.1000'))

    def test_oversell_recipe_ingredient_still_succeeds_with_warning(self):
        self.chicken.stock = Decimal('10')  # far below the recipe's 150g requirement
        self.chicken.save(update_fields=['stock'])

        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(
            any('Chicken' in w for w in resp.json().get('warnings', [])),
            'oversold recipe ingredient must surface a warning',
        )
        self.chicken.refresh_from_db()
        self.assertLess(self.chicken.stock, Decimal('0'))

    def test_no_active_recipe_returns_clean_400(self):
        unconfigured = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Unconfigured Recipe Item', barcode='RS-UNCFG', sku='SKU-RS-UNCFG',
            price=Decimal('30.00'), cost=Decimal('0.00'), stock=Decimal('0'),
            product_type=ProductType.RECIPE_PRODUCT,
        )
        resp = self._post_sale([{'product': unconfigured.id, 'qty': '1'}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dashboard_summary_cogs_reflects_recipe_sale_with_zero_new_code(self):
        """Proves the Sprint 3/4 COGS pipeline works for recipe sales with
        no changes to dashboard_summary itself — it just reads
        SaleItem.unit_cost, which this batch now populates correctly for a
        recipe line."""
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '2'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)
        self.assertEqual(item.unit_cost, Decimal('16.00'))
        self.assertEqual(item.qty, Decimal('2'))

        today = sale.created_at.date().isoformat()
        dash_resp = self.client.get(
            reverse('dashboard-summary'), {'start_date': today, 'end_date': today},
        )
        self.assertEqual(dash_resp.status_code, status.HTTP_200_OK)
        self.assertAlmostEqual(dash_resp.json()['kpis']['cogs'], 32.00, places=2)  # 16.00 * 2

    def test_plain_stock_item_sale_unaffected(self):
        """Sanity check alongside the full pos.tests regression run: a plain
        stock-item line still uses Product.cost directly, never the recipe
        path."""
        water = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Bottled Water', barcode='RS-WATER', sku='SKU-RS-WATER',
            price=Decimal('10.00'), cost=Decimal('4.00'), stock=Decimal('100'),
        )
        resp = self._post_sale([{'product': water.id, 'qty': '1', 'price_each': '10.00'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=water)
        self.assertEqual(item.unit_cost, Decimal('4.00'))
        self.assertTrue(
            StockMovement.objects.filter(
                product=water, movement_type=StockMovement.MovementType.SALE_OUT,
            ).exists()
        )


    # ── Sprint 5 Batch 5 hotfix — pre-Batch-6 architecture review ──────────
    # (2026-07-22). Reuses this class's fixture (branches, ingredients,
    # sandwich recipe, cheese modifier) directly.

    def test_bundle_type_recipe_ignored_falls_through_to_legacy_stock_path(self):
        """Point 1 — `can_have_recipe=True` is shared by RECIPE_PRODUCT,
        PREP_ITEM, and BUNDLE, but only the first two are recipe-eligible.
        A BUNDLE with a Recipe attached must still sell through the legacy
        stock-item path (its own Product.stock/SALE_OUT), never through
        RECIPE_CONSUME on its "recipe"'s ingredients."""
        bundle = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Combo Bundle', barcode='RS-BND', sku='SKU-RS-BND',
            price=Decimal('20.00'), cost=Decimal('5.00'), stock=Decimal('100'),
            product_type=ProductType.BUNDLE,
        )
        bundle_recipe = Recipe.objects.create(tenant=self.tenant, product=bundle)
        bundle_version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=bundle_recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=bundle_version,
            component_product=self.chicken, component_unit=self.chicken_unit,
            entered_qty=Decimal('10'), qty_base=Decimal('10'),
        )

        resp = self._post_sale([{'product': bundle.id, 'qty': '2', 'price_each': '20.00'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=bundle)

        self.assertTrue(
            StockMovement.objects.filter(
                product=bundle, movement_type=StockMovement.MovementType.SALE_OUT,
                source_document_id=sale.id,
            ).exists()
        )
        bundle.refresh_from_db()
        self.assertEqual(bundle.stock, Decimal('98'))
        self.assertFalse(
            StockMovement.objects.filter(
                product=bundle, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            ).exists()
        )
        self.assertFalse(
            StockMovement.objects.filter(
                product=self.chicken, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                source_document_id=sale.id,
            ).exists()
        )
        self.assertFalse(SaleItemRecipeCostSnapshot.objects.filter(sale_item=item).exists())

    def test_variant_snapshot_fields_survive_variant_rename_and_deletion(self):
        """Point 2 — SaleItem.variant_name/variant_price freeze the
        variant's name/price at sale time, independent of the live
        ProductVariant row (later renamed, repriced, or deleted)."""
        large = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('70.00'),
        )
        large_recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich, variant=large)
        large_version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=large_recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=large_version,
            component_product=self.chicken, component_unit=self.chicken_unit,
            entered_qty=Decimal('300'), qty_base=Decimal('300'),
        )

        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1', 'variant': large.id}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        self.assertEqual(item.variant_name, 'Large')
        self.assertEqual(item.variant_price, Decimal('70.00'))

        large.name = 'XL Renamed'
        large.price = Decimal('99.00')
        large.save()
        large.delete()  # cascades: Recipe(variant=large) is deleted too

        item.refresh_from_db()
        self.assertEqual(item.variant_name, 'Large')
        self.assertEqual(item.variant_price, Decimal('70.00'))
        self.assertIsNone(item.variant_id)  # SET_NULL on the variant FK itself

    def test_modifier_group_name_snapshot_survives_group_rename(self):
        """Point 3 — SaleItemModifier.group_name freezes the modifier
        group's name at sale time; a later rename of the ModifierGroup must
        not alter an already-recorded sale line."""
        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [self.cheese_option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)
        sim = SaleItemModifier.objects.get(sale_item=item, option_name='Extra Cheese')
        self.assertEqual(sim.group_name, 'Extras')

        self.cheese_group.name = 'Renamed Extras'
        self.cheese_group.save()

        sim.refresh_from_db()
        self.assertEqual(sim.group_name, 'Extras')

    def _add_onion_ingredient(self, *, name, barcode):
        onion = Product.objects.create(
            tenant=self.tenant, category=self.ingredients_cat,
            name=name, barcode=barcode, sku=f'SKU-{barcode}',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        onion_unit = ProductUnit.objects.create(
            tenant=self.tenant, product=onion, unit=self.gram,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        for branch, warehouse in ((self.branch_a, self.wh_a), (self.branch_b, self.wh_b)):
            pos_costing_svc.apply_purchase_receipt(
                product=onion, qty=Decimal('50000'), unit_cost=Decimal('0.05'),
                branch=branch, source_document_type='purchase_invoice',
            )
            stock_svc.record_stock_in(
                product=onion, quantity=Decimal('50000'),
                movement_type=StockMovement.MovementType.PURCHASE_IN,
                branch=branch, warehouse=warehouse,
                source_document_type='purchase_invoice',
            )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=self.recipe_version,
            component_product=onion, component_unit=onion_unit,
            entered_qty=Decimal('20'), qty_base=Decimal('20'), sort_order=2,
        )
        return onion, onion_unit

    def test_negative_net_consumption_from_modifier_is_rejected(self):
        """Point 6 — a removal modifier taking away MORE of an ingredient
        than the recipe actually provides must be rejected with a clean
        validation error, never floored to zero and never posted as a
        negative RECIPE_CONSUME movement."""
        onion, onion_unit = self._add_onion_ingredient(name='Onion', barcode='RS-ONI')
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Removals')
        option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=group,
            name='Too Much No Onion', price_delta=Decimal('0.00'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=onion, component_unit=onion_unit,
            entered_qty=Decimal('-40'), qty_base=Decimal('-40'),
        )
        ProductModifierGroup.objects.create(
            tenant=self.tenant, product=self.sandwich, modifier_group=group,
        )

        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertFalse(
            StockMovement.objects.filter(
                product=onion, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            ).exists()
        )
        self.assertFalse(
            SaleItemRecipeCostSnapshot.objects.filter(lines__component_product=onion).exists()
        )

    def test_modifier_reduces_recipe_line_to_valid_zero_net(self):
        """Point 6 — a removal modifier taking away EXACTLY the recipe's own
        quantity nets to zero: valid, no error, no RECIPE_CONSUME movement
        and no cost contribution for that component, and (the actual bug
        this hotfix fixes) the base recipe's own onion line must NOT still
        fire at its original quantity — the modifier must net against it,
        not just be dropped from the cost total.

        Post-Batch-6 review (split-snapshot-line redesign): a net of zero
        does NOT mean the snapshot has zero rows for that component — the
        base recipe's onion line (+20) and the modifier's removal line
        (-20) both stay in the snapshot, unmerged, each with its own real
        sign. Only the derived NET (used for stock deduction) is zero."""
        onion, onion_unit = self._add_onion_ingredient(name='Onion Zero', barcode='RS-ONI0')
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Removals Zero')
        option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=group,
            name='No Onion', price_delta=Decimal('0.00'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=onion, component_unit=onion_unit,
            entered_qty=Decimal('-20'), qty_base=Decimal('-20'),
        )
        ProductModifierGroup.objects.create(
            tenant=self.tenant, product=self.sandwich, modifier_group=group,
        )

        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        # Base recipe cost (chicken+lettuce only) unchanged — onion's two
        # lines net to zero and contribute nothing to the total, and no
        # stock actually moves for onion.
        self.assertEqual(item.unit_cost, Decimal('16.00'))
        self.assertFalse(
            StockMovement.objects.filter(
                product=onion, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                source_document_id=sale.id,
            ).exists()
        )
        snapshot = SaleItemRecipeCostSnapshot.objects.get(sale_item=item)
        onion_lines = list(snapshot.lines.filter(component_product=onion))
        self.assertEqual(len(onion_lines), 2)
        base_line = next(l for l in onion_lines if not l.is_modifier_line)
        modifier_line = next(l for l in onion_lines if l.is_modifier_line)
        self.assertEqual(base_line.qty_base, Decimal('20'))
        self.assertEqual(base_line.line_cost, Decimal('1.00'))
        self.assertIsNone(base_line.source_modifier_option_id)
        self.assertEqual(modifier_line.qty_base, Decimal('-20'))
        self.assertEqual(modifier_line.line_cost, Decimal('-1.00'))
        self.assertEqual(modifier_line.source_modifier_option_id, option.id)

    def test_recipe_and_modifier_lines_for_same_component_stay_separate_and_total_rounds_once(self):
        """Post-Batch-6 review — when a base recipe line and a modifier's
        consumption BOTH touch the same component with a non-zero net, the
        snapshot keeps them as two separate audit rows (never merged into
        one netted line), and `total_recipe_cost` is computed by summing
        every line's RAW cost and rounding ONCE at the end — not by
        rounding each line first and summing already-rounded amounts,
        which would silently drift the total for a component whose raw
        cost isn't already a clean 2dp value."""
        precise = Product.objects.create(
            tenant=self.tenant, category=self.ingredients_cat,
            name='Precise Ingredient', barcode='RS-PRECISE', sku='SKU-RS-PRECISE',
            price=Decimal('0.00'), cost=Decimal('0.00'), stock=Decimal('0'),
        )
        precise_unit = ProductUnit.objects.create(
            tenant=self.tenant, product=precise, unit=self.gram,
            conversion_to_base=Decimal('1'), is_base=True,
        )
        pos_costing_svc.apply_purchase_receipt(
            product=precise, qty=Decimal('1000'), unit_cost=Decimal('0.126'),
            branch=self.branch_a, source_document_type='purchase_invoice',
        )
        stock_svc.record_stock_in(
            product=precise, quantity=Decimal('1000'),
            movement_type=StockMovement.MovementType.PURCHASE_IN,
            branch=self.branch_a, warehouse=self.wh_a,
            source_document_type='purchase_invoice',
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=self.recipe_version,
            component_product=precise, component_unit=precise_unit,
            entered_qty=Decimal('1'), qty_base=Decimal('1'), sort_order=3,
        )
        group = ModifierGroup.objects.create(tenant=self.tenant, name='Precise Extras')
        option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=group,
            name='Extra Precise', price_delta=Decimal('0.00'),
        )
        ModifierOptionConsumption.objects.create(
            tenant=self.tenant, modifier_option=option, variant=None,
            component_product=precise, component_unit=precise_unit,
            entered_qty=Decimal('1'), qty_base=Decimal('1'),
        )
        ProductModifierGroup.objects.create(
            tenant=self.tenant, product=self.sandwich, modifier_group=group,
        )

        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        # Base sandwich (16.00) + 1g*0.126 (base line) + 1g*0.126 (modifier
        # line) = 16.252 raw, rounded ONCE -> 16.25. Rounding each 0.126
        # line to 2dp first (0.13 each) before summing would have produced
        # 16.26 — this assertion is the regression guard against that.
        self.assertEqual(item.unit_cost, Decimal('16.25'))

        snapshot = SaleItemRecipeCostSnapshot.objects.get(sale_item=item)
        self.assertEqual(snapshot.total_recipe_cost, Decimal('16.25'))
        precise_lines = list(snapshot.lines.filter(component_product=precise))
        self.assertEqual(len(precise_lines), 2)
        self.assertEqual({l.is_modifier_line for l in precise_lines}, {False, True})
        for line in precise_lines:
            self.assertEqual(line.qty_base, Decimal('1'))

        # Netting happens only at stock-deduction time — one RECIPE_CONSUME
        # movement for the combined 2g, not two separate movements.
        precise_movements = StockMovement.objects.filter(
            product=precise, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            source_document_id=sale.id,
        )
        self.assertEqual(precise_movements.count(), 1)
        self.assertEqual(precise_movements.first().qty, Decimal('-2.000'))

    def test_recipe_consume_counts_as_outflow_in_movement_derived_balance(self):
        """Batch 7 gate fix — RECIPE_CONSUME is classified as an OUT movement
        (`stock_movements._OUT_TYPES`), so the movement-derived balance
        (`get_product_stock_balance`, backing the /stock-balance/ and
        /stock-movements/ reconciliation endpoints) reflects recipe
        ingredient consumption. Before the fix, RECIPE_CONSUME was in neither
        direction set and was silently ignored, overstating an ingredient's
        stock on those reads."""
        before = stock_svc.get_product_stock_balance(self.chicken)

        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])

        after = stock_svc.get_product_stock_balance(self.chicken)
        # Recipe uses 150g chicken → the ledger-derived balance must drop by
        # exactly that, matching the authoritative Product.stock decrement.
        self.assertEqual(before - after, Decimal('150'))

        # And a void's RETURN_IN (an IN type) brings it back symmetrically.
        void_resp = self.client.post(
            reverse('sale-void', kwargs={'sale_uuid': sale.sale_uuid}), {}, format='json',
        )
        self.assertEqual(void_resp.status_code, status.HTTP_200_OK, void_resp.content)
        restored = stock_svc.get_product_stock_balance(self.chicken)
        self.assertEqual(restored, before)

    def test_modifier_not_offered_for_product_is_rejected(self):
        """Batch 7 gate fix — the backend must not trust the client's
        modifier selection: a modifier option whose group is NOT attached to
        the product via ProductModifierGroup is rejected with a 400, so a
        buggy/hostile client can't apply an arbitrary price delta or
        ingredient consumption to a recipe product. No sale/snapshot is
        written."""
        stray_group = ModifierGroup.objects.create(tenant=self.tenant, name='Not Offered Here')
        stray_option = ModifierOption.objects.create(
            tenant=self.tenant, modifier_group=stray_group,
            name='Sneaky Discount', price_delta=Decimal('-5.00'),
        )
        # Deliberately NOT linked to the sandwich via ProductModifierGroup.

        sales_before = Sale.objects.count()
        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [stray_option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('modifier', str(resp.content).lower())
        self.assertEqual(Sale.objects.count(), sales_before)

    def test_void_recipe_sale_restores_ingredient_stock(self):
        """Point 5/void-awareness — voiding a recipe-product sale must
        restore the actual ingredients consumed via RECIPE_CONSUME (read
        from the frozen StockMovement ledger), not bump the recipe
        product's own (never-decremented) stock counter."""
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])

        self.chicken.refresh_from_db()
        self.lettuce.refresh_from_db()
        chicken_after_sale = self.chicken.stock
        lettuce_after_sale = self.lettuce.stock

        void_resp = self.client.post(
            reverse('sale-void', kwargs={'sale_uuid': sale.sale_uuid}), {}, format='json',
        )
        self.assertEqual(void_resp.status_code, status.HTTP_200_OK, void_resp.content)

        self.chicken.refresh_from_db()
        self.lettuce.refresh_from_db()
        self.assertEqual(self.chicken.stock, chicken_after_sale + Decimal('150'))
        self.assertEqual(self.lettuce.stock, lettuce_after_sale + Decimal('50'))

        return_movements = StockMovement.objects.filter(
            sale=sale, movement_type=StockMovement.MovementType.RETURN_IN,
        )
        self.assertEqual(
            set(return_movements.values_list('product_id', flat=True)),
            {self.chicken.id, self.lettuce.id},
        )
        for mv in return_movements:
            self.assertIn(mv.qty, (Decimal('150'), Decimal('50')))

        # The recipe product itself must NOT get a phantom stock bump / a
        # meaningless RETURN_IN on its own (never-decremented) product row.
        self.assertFalse(
            StockMovement.objects.filter(sale=sale, product=self.sandwich).exists()
        )

    def test_void_recipe_sale_with_variant_modifier_and_oversell_combined(self):
        """Point 6 (user-requested, pre-close-out review) — the existing
        void test only covers a plain base-recipe sale; the variant,
        modifier, and oversell paths are each covered independently at
        SALE time but were never combined with each other, nor with VOID,
        in any prior test. This is the missing combined case: a sale of
        the 'Large' variant (its own independent recipe: 300g chicken) plus
        the Extra Cheese modifier (40g cheese, variant-agnostic), where the
        variant's own ingredient is oversold — voiding must correctly
        reverse every RECIPE_CONSUME row from both the variant recipe and
        the modifier, using the real consumed quantities read off the
        ledger (not recomputed from the current recipe definition), even
        though one of those quantities pushed stock negative."""
        large = ProductVariant.objects.create(
            tenant=self.tenant, product=self.sandwich, name='Large', price=Decimal('70.00'),
        )
        large_recipe = Recipe.objects.create(tenant=self.tenant, product=self.sandwich, variant=large)
        large_version = RecipeVersion.objects.create(
            tenant=self.tenant, recipe=large_recipe, version_no=1,
            status=RecipeVersion.Status.ACTIVE,
        )
        RecipeLine.objects.create(
            tenant=self.tenant, recipe_version=large_version,
            component_product=self.chicken, component_unit=self.chicken_unit,
            entered_qty=Decimal('300'), qty_base=Decimal('300'),
        )

        # Oversell the variant's own ingredient — far below the 300g the
        # Large recipe requires.
        self.chicken.stock = Decimal('10')
        self.chicken.save(update_fields=['stock'])
        chicken_stock_before_sale = self.chicken.stock
        self.cheese.refresh_from_db()
        cheese_stock_before_sale = self.cheese.stock

        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1', 'variant': large.id,
            'modifier_option_ids': [self.cheese_option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(
            any('Chicken' in w for w in resp.json().get('warnings', [])),
            'oversold variant ingredient must surface a warning at sale time',
        )
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)
        self.assertEqual(item.variant_id, large.id)
        self.assertEqual(item.unit_cost, Decimal('36.00'))  # 300*0.10 + 40*0.15

        self.chicken.refresh_from_db()
        self.cheese.refresh_from_db()
        chicken_stock_after_sale = self.chicken.stock
        cheese_stock_after_sale = self.cheese.stock
        self.assertLess(chicken_stock_after_sale, Decimal('0'))  # confirms the oversell really happened
        self.assertEqual(chicken_stock_after_sale, chicken_stock_before_sale - Decimal('300'))
        self.assertEqual(cheese_stock_after_sale, cheese_stock_before_sale - Decimal('40'))

        void_resp = self.client.post(
            reverse('sale-void', kwargs={'sale_uuid': sale.sale_uuid}), {}, format='json',
        )
        self.assertEqual(void_resp.status_code, status.HTTP_200_OK, void_resp.content)

        self.chicken.refresh_from_db()
        self.cheese.refresh_from_db()
        # Void restores exactly what was consumed (300g/40g), regardless of
        # the fact that the chicken leg went negative — it does not clamp
        # to zero or otherwise "correct" the oversold state, it reverses
        # the ledger row byte-for-byte.
        self.assertEqual(self.chicken.stock, chicken_stock_after_sale + Decimal('300'))
        self.assertEqual(self.chicken.stock, chicken_stock_before_sale)
        self.assertEqual(self.cheese.stock, cheese_stock_before_sale)

        return_movements = StockMovement.objects.filter(
            sale=sale, movement_type=StockMovement.MovementType.RETURN_IN,
        )
        self.assertEqual(
            set(return_movements.values_list('product_id', flat=True)),
            {self.chicken.id, self.cheese.id},
        )
        for mv in return_movements:
            self.assertIn(mv.qty, (Decimal('300'), Decimal('40')))

        # The base recipe's own lettuce line must not appear anywhere —
        # the variant's recipe is fully independent of the base recipe.
        self.assertFalse(
            StockMovement.objects.filter(sale=sale, product=self.lettuce).exists()
        )
        self.assertFalse(
            StockMovement.objects.filter(sale=sale, product=self.sandwich).exists()
        )

    def test_recipe_sale_rejected_when_branch_has_no_kitchen_or_sales_warehouse(self):
        """Batch 7 verification — a branch with no default KITCHEN or SALES
        `BranchWarehouse` configured has nowhere for `RECIPE_CONSUME` to
        deplete stock from. `resolve_kitchen_warehouse` raises `RecipeError`;
        `_apply_stock` must turn that into a clean 400 (not an unhandled
        500), and the whole sale (including the already-created `Sale` row)
        must roll back — this exercises the transaction boundary, not just
        the exception translation."""
        sales_before = Sale.objects.count()
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}], user=self.manager_c)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('warehouse', str(resp.content).lower())
        self.assertEqual(Sale.objects.count(), sales_before)
        self.assertFalse(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                branch=self.branch_c,
            ).exists()
        )

    def test_recipe_sale_query_count_regression_guard(self):
        """Batch 7 verification (B7V-2) — measured, not reasoned, via
        `CaptureQueriesContext`. A sale of one recipe product with 2 base
        recipe lines + 1 modifier line (3 distinct components) took 63
        queries before this batch's `get_or_create_inventory_cost` fix
        (every component paid 2 InventoryCost queries even when its row
        already existed — the common case after a branch's first
        purchase); 60 after. This test pins the number so a future N+1
        regression on this hot path (called on every recipe sale) shows up
        as a failing test with an exact delta, not a vague slowdown
        someone has to notice separately."""
        with CaptureQueriesContext(connection) as ctx:
            resp = self._post_sale([{
                'product': self.sandwich.id, 'qty': '1',
                'modifier_option_ids': [self.cheese_option.id],
            }])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertLessEqual(
            len(ctx.captured_queries), 60,
            f'recipe sale query count regressed: {len(ctx.captured_queries)} > 60 '
            f'(2 base recipe lines + 1 modifier line, 3 distinct components)',
        )

    def test_recipe_void_query_count_regression_guard(self):
        """Batch 7 verification (B7V-2) — measured: voiding a 2-ingredient
        recipe sale takes 31 queries (occasional manager action, not a hot
        path — no optimization applied here, just a pinned ceiling so a
        future change doesn't silently make void scale badly per
        ingredient)."""
        resp = self._post_sale([{'product': self.sandwich.id, 'qty': '1'}])
        sale_uuid = resp.json()['sale_uuid']
        with CaptureQueriesContext(connection) as ctx:
            void_resp = self.client.post(
                reverse('sale-void', kwargs={'sale_uuid': sale_uuid}), {}, format='json',
            )
        self.assertEqual(void_resp.status_code, 200, void_resp.content)
        self.assertLessEqual(
            len(ctx.captured_queries), 35,
            f'recipe void query count regressed: {len(ctx.captured_queries)} > 35',
        )

    def test_end_to_end_data_integrity_sale_to_reports(self):
        """Batch 7 verification (B7V-3) — a real recipe sale, posted
        through the actual API at two branches with different branch-scoped
        ingredient costs, must produce IDENTICAL numbers across every
        downstream read surface: the SaleItem snapshot, the
        RECIPE_CONSUME ledger, dashboard_summary's COGS, the
        recipe-profitability report, and the ingredient-consumption
        report. This is the strongest guard against the two pipelines
        (Sprint 3/4's COGS math and Sprint 5's recipe costing) silently
        drifting apart, since they're independently computed from
        different tables (SaleItem vs StockMovement) but must reconcile.

        Branch A: chicken@0.10, lettuce@0.02, cheese@0.15 -> recipe cost
        150*0.10 + 50*0.02 + 40*0.15 = 22.00 (matches the existing
        `test_recipe_sale_with_modifier_adds_cost_and_price` baseline).
        Branch B: chicken@0.20 (only chicken differs by branch in this
        fixture) -> 150*0.20 + 50*0.02 + 40*0.15 = 37.00.
        Both sales price identically: 50.00 base + 6.00 modifier = 56.00.
        """
        resp_a = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [self.cheese_option.id],
        }], user=self.manager_a)
        self.assertEqual(resp_a.status_code, status.HTTP_201_CREATED, resp_a.content)
        resp_b = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [self.cheese_option.id],
        }], user=self.manager_b)
        self.assertEqual(resp_b.status_code, status.HTTP_201_CREATED, resp_b.content)

        sale_a = Sale.objects.get(sale_uuid=resp_a.json()['sale_uuid'])
        sale_b = Sale.objects.get(sale_uuid=resp_b.json()['sale_uuid'])
        item_a = sale_a.items.get(product=self.sandwich)
        item_b = sale_b.items.get(product=self.sandwich)

        # ── Layer 1: the SaleItem snapshot itself ──────────────────────
        self.assertEqual(item_a.unit_cost, Decimal('22.00'))
        self.assertEqual(item_b.unit_cost, Decimal('37.00'))
        self.assertEqual(item_a.price_each, Decimal('56.00'))
        self.assertEqual(item_b.price_each, Decimal('56.00'))

        snap_a = SaleItemRecipeCostSnapshot.objects.get(sale_item=item_a)
        snap_b = SaleItemRecipeCostSnapshot.objects.get(sale_item=item_b)
        self.assertEqual(snap_a.total_recipe_cost, item_a.unit_cost)
        self.assertEqual(snap_b.total_recipe_cost, item_b.unit_cost)

        # ── Layer 2: the RECIPE_CONSUME ledger — net qty per ingredient
        # per branch must match the recipe+modifier definition exactly ──
        for sale, branch in ((sale_a, self.branch_a), (sale_b, self.branch_b)):
            moves = {
                mv.product_id: -mv.qty
                for mv in StockMovement.objects.filter(
                    sale=sale, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                )
            }
            self.assertEqual(moves[self.chicken.id], Decimal('150.000'))
            self.assertEqual(moves[self.lettuce.id], Decimal('50.000'))
            self.assertEqual(moves[self.cheese.id], Decimal('40.000'))
            self.assertTrue(all(mv.branch_id == branch.id for mv in StockMovement.objects.filter(
                sale=sale, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            )))

        # ── Layer 3: dashboard_summary COGS, branch-filtered, must equal
        # each sale's own unit_cost exactly (tax=0 in this fixture, so
        # net_revenue == price_each) ──
        for branch, item in ((self.branch_a, item_a), (self.branch_b, item_b)):
            resp = self.client.get(reverse('dashboard-summary'), {'branch_id': branch.id})
            kpis = resp.json()['kpis']
            self.assertEqual(Decimal(str(kpis['cogs'])), item.unit_cost)
            self.assertEqual(Decimal(str(kpis['net_revenue'])), item.price_each)

        # Unfiltered dashboard COGS = sum of both branches' recipe cost.
        resp_all = self.client.get(reverse('dashboard-summary'))
        total_cogs = Decimal(str(resp_all.json()['kpis']['cogs']))
        self.assertEqual(total_cogs, item_a.unit_cost + item_b.unit_cost)  # 22.00 + 37.00 = 59.00

        # ── Layer 4: recipe-profitability report reconciles to the SAME
        # total food_cost as dashboard_summary's COGS (independently
        # computed: one groups SaleItem by product, the other aggregates
        # the whole window) ──
        resp_profit = self.client.get(reverse('recipe-profitability'))
        rows = resp_profit.json()['results']
        self.assertEqual(len(rows), 1)  # both sales are the same product+variant(None)
        row = rows[0]
        self.assertEqual(row['product_name'], 'Chicken Sandwich')
        self.assertEqual(row['units_sold'], 2.0)
        self.assertEqual(Decimal(str(row['food_cost'])), total_cogs)
        self.assertEqual(Decimal(str(row['revenue'])), item_a.price_each + item_b.price_each)

        # ── Layer 5: ingredient-consumption report — summing cost_consumed
        # across every ingredient row must ALSO reconcile to the same
        # total, even though this report is computed from a completely
        # different table (StockMovement, not SaleItem) ──
        resp_ingredients = self.client.get(reverse('ingredient-consumption-report'))
        ing_rows = {r['product_name']: r for r in resp_ingredients.json()['results']}
        self.assertEqual(ing_rows['Chicken']['qty_consumed'], 300.0)
        self.assertEqual(Decimal(str(ing_rows['Chicken']['cost_consumed'])), Decimal('45.00'))
        self.assertEqual(ing_rows['Lettuce']['qty_consumed'], 100.0)
        self.assertEqual(Decimal(str(ing_rows['Lettuce']['cost_consumed'])), Decimal('2.00'))
        self.assertEqual(ing_rows['Cheese']['qty_consumed'], 80.0)
        self.assertEqual(Decimal(str(ing_rows['Cheese']['cost_consumed'])), Decimal('12.00'))

        ingredient_cost_total = sum(
            (Decimal(str(r['cost_consumed'])) for r in ing_rows.values()), Decimal('0'),
        )
        # The cross-pipeline reconciliation: ledger-derived ingredient
        # cost (StockMovement) == sale-derived recipe cost (SaleItem) ==
        # dashboard COGS. Three independent computations, one number.
        self.assertEqual(ingredient_cost_total, total_cogs)
        self.assertEqual(ingredient_cost_total, Decimal('59.00'))
