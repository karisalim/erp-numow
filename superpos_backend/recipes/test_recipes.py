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

from accounts.models import (
    Branch, BranchPaymentMethod, FinancialAccount, PaymentMethod, Tenant, User,
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
        not just be dropped from the cost total."""
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

        resp = self._post_sale([{
            'product': self.sandwich.id, 'qty': '1',
            'modifier_option_ids': [option.id],
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        item = sale.items.get(product=self.sandwich)

        # Base recipe cost (chicken+lettuce only) unchanged — onion nets to
        # zero, contributes nothing to cost, and is never actually consumed.
        self.assertEqual(item.unit_cost, Decimal('16.00'))
        self.assertFalse(
            StockMovement.objects.filter(
                product=onion, movement_type=StockMovement.MovementType.RECIPE_CONSUME,
                source_document_id=sale.id,
            ).exists()
        )
        snapshot = SaleItemRecipeCostSnapshot.objects.get(sale_item=item)
        self.assertFalse(snapshot.lines.filter(component_product=onion).exists())

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
