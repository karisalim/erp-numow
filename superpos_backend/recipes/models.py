"""Recipes, size variants, and modifiers (Sprint 5).

A separate Django app from `pos` — these are new domain concepts (not
extensions of an existing `pos` model), following the same
one-app-per-domain split `accounts`/`pos` already establish. Cross-app
references to `pos.Product`/`pos.ProductUnit` and `accounts.Branch` use
string FKs to avoid a circular import between `pos` and `recipes`.
"""

from django.db import models


class ProductVariant(models.Model):
    """A size/option variant of a parent product (D-24: "variant-of-one-
    product" — Small/Medium/Large as rows under one `Product`, each with
    its own sell price and, later, its own `Recipe`).

    Deliberately has **no barcode field** — per D-24's own recommendation,
    the primary POS flow for a variant is menu/category selection or an
    optional PLU, never routed through `pos.ProductBarcodeUnit`.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='product_variants', db_index=True,
    )
    product = models.ForeignKey(
        'pos.Product', on_delete=models.CASCADE, related_name='variants',
    )
    name = models.CharField(max_length=60)
    sku = models.CharField(max_length=40, blank=True, default='')
    plu = models.CharField(max_length=10, blank=True, default='')
    # The variant's own sell price — never a multiplier of the parent
    # product's price (the owner's explicit requirement: each size is an
    # independent price point, not a computed scale-up).
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'product', 'name'],
                name='recipes_variant_tenant_product_name_uniq',
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='recipes_variant_price_nonneg',
            ),
        ]

    def __str__(self):
        return f'{self.product_id} — {self.name}'


class Recipe(models.Model):
    """The BOM container for one sellable entity — either a plain `Product`
    (`variant=NULL`) or one `ProductVariant` of that product. Holds no
    quantities itself; those live on the currently-`ACTIVE` `RecipeVersion`
    (§`RecipeVersion`).
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='recipes', db_index=True,
    )
    product = models.ForeignKey(
        'pos.Product', on_delete=models.CASCADE, related_name='recipes',
    )
    # NULL = the base product's own recipe (no variant). A real variant's
    # recipe is entirely independent of the base product's — sizing a
    # pizza is not a multiplier of one master recipe (the owner's explicit
    # requirement).
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='recipes',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'variant'],
                name='recipes_recipe_product_variant_uniq',
            ),
            # Postgres treats NULL as distinct per row, so the constraint
            # above alone would allow several variant=NULL rows for the
            # same product — mirrors InventoryCost.branch's paired
            # partial-unique pattern (Sprint 5 Batch 1).
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(variant__isnull=True),
                name='recipes_recipe_product_null_variant_uniq',
            ),
        ]

    def __str__(self):
        return f'Recipe product={self.product_id} variant={self.variant_id}'


class RecipeVersion(models.Model):
    """A dated, statused snapshot of a `Recipe`'s component quantities.

    At most one `ACTIVE` version per recipe at a time (enforced by the
    partial unique constraint below, mirroring `ProductUnit.is_base`'s
    "one default" pattern). Activating a new version must archive the
    previous one in the same transaction (`recipes.services.costing
    .activate_recipe_version`) — never done by editing this field directly.
    Recipe *cost* is never cached here: it's always computed fresh from the
    live component costs at read/sale time (`compute_recipe_cost`) — only
    the *quantities* are versioned/frozen.
    """

    class Status(models.TextChoices):
        DRAFT    = 'draft',    'Draft'
        ACTIVE   = 'active',   'Active'
        ARCHIVED = 'archived', 'Archived'

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='recipe_versions', db_index=True,
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='versions',
    )
    version_no = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version_no']
        constraints = [
            models.UniqueConstraint(
                fields=['recipe', 'version_no'],
                name='recipes_version_recipe_no_uniq',
            ),
            models.UniqueConstraint(
                fields=['recipe'],
                condition=models.Q(status='active'),
                name='recipes_version_recipe_one_active_uniq',
            ),
        ]

    def __str__(self):
        return f'RecipeVersion recipe={self.recipe_id} v{self.version_no} ({self.status})'


class RecipeLine(models.Model):
    """One component (ingredient) of a `RecipeVersion`, in the component's
    own base unit (R-B: `qty_base` is always base-unit-denominated, same
    convention as `SaleItem.qty`/`PurchaseInvoiceLine.qty`).

    `component_product` is `PROTECT`ed — a recipe referencing a product
    blocks that product's deletion, matching `InventoryCategory.parent`'s
    PROTECT precedent elsewhere in this codebase.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='recipe_lines', db_index=True,
    )
    recipe_version = models.ForeignKey(
        RecipeVersion, on_delete=models.CASCADE, related_name='lines',
    )
    component_product = models.ForeignKey(
        'pos.Product', on_delete=models.PROTECT, related_name='recipe_lines',
    )
    # Nullable/SET_NULL for the same reason SaleItem.product_unit is: a
    # unit mapping may be deactivated later without invalidating a
    # historical recipe line. Resolved to the component's base unit by the
    # service layer when omitted on input — never left unresolved at save
    # time (see recipes.serializers.RecipeLineSerializer).
    component_unit = models.ForeignKey(
        'pos.ProductUnit', on_delete=models.SET_NULL, null=True, blank=True,
    )
    entered_qty = models.DecimalField(max_digits=14, decimal_places=3)
    qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(entered_qty__gt=0),
                name='recipes_line_entered_qty_positive',
            ),
        ]

    def __str__(self):
        return f'RecipeLine version={self.recipe_version_id} component={self.component_product_id}'


class ModifierGroup(models.Model):
    """A named set of options a product offers at sale time (e.g. "Pizza
    Toppings"). `selection_type` distinguishes "pick exactly one" (e.g. a
    bread choice) from "pick any number of extras" — `min_select`/
    `max_select` refine either further and are both optional (no cap by
    default).
    """

    class SelectionType(models.TextChoices):
        SINGLE   = 'single',   'Single'
        MULTIPLE = 'multiple', 'Multiple'

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='modifier_groups', db_index=True,
    )
    name = models.CharField(max_length=80)
    selection_type = models.CharField(
        max_length=10, choices=SelectionType.choices, default=SelectionType.MULTIPLE,
    )
    min_select = models.PositiveIntegerField(null=True, blank=True)
    max_select = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'], name='recipes_modgroup_tenant_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class ProductModifierGroup(models.Model):
    """Which products offer which modifier groups (e.g. "Pizza Toppings"
    attached to every pizza product)."""

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='product_modifier_groups', db_index=True,
    )
    product = models.ForeignKey(
        'pos.Product', on_delete=models.CASCADE, related_name='modifier_group_links',
    )
    modifier_group = models.ForeignKey(
        ModifierGroup, on_delete=models.CASCADE, related_name='product_links',
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'modifier_group'],
                name='recipes_prodmodgroup_product_group_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.product_id} <- {self.modifier_group_id}'


class ModifierOption(models.Model):
    """One selectable option within a `ModifierGroup` (e.g. "Extra
    Cheese", "No Onion"). `price_delta` can be zero (a free option still
    consumes inventory — D-34) or, in principle, negative."""

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='modifier_options', db_index=True,
    )
    modifier_group = models.ForeignKey(
        ModifierGroup, on_delete=models.CASCADE, related_name='options',
    )
    name = models.CharField(max_length=80)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'modifier_group', 'name'],
                name='recipes_modoption_tenant_group_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class ModifierOptionConsumption(models.Model):
    """The per-variant ingredient consumption delta a `ModifierOption`
    causes (TARGET_BOUNDARIES.md §6.10's "RecipeConsumptionDelta"). E.g.
    Extra Cheese: +40g Mozzarella; No Onion: -20g Onion.

    `variant=NULL` means "applies regardless of variant" (a product with
    no size variants, or a delta that doesn't scale by size). Both
    `entered_qty` and `qty_base` are **signed** — unlike `RecipeLine`,
    which only ever adds an ingredient, a modifier may also *remove* one.
    A negative delta is not consumed at sale time and contributes zero
    cost (`recipes.services.costing.compute_modifier_deltas`) — removing
    an ingredient doesn't create negative COGS, it simply isn't consumed.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='modifier_option_consumptions', db_index=True,
    )
    modifier_option = models.ForeignKey(
        ModifierOption, on_delete=models.CASCADE, related_name='consumptions',
    )
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='modifier_consumptions',
    )
    component_product = models.ForeignKey(
        'pos.Product', on_delete=models.PROTECT, related_name='modifier_consumptions',
    )
    component_unit = models.ForeignKey(
        'pos.ProductUnit', on_delete=models.SET_NULL, null=True, blank=True,
    )
    entered_qty = models.DecimalField(max_digits=14, decimal_places=3)
    qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~models.Q(entered_qty=0),
                name='recipes_modconsumption_entered_qty_nonzero',
            ),
            models.UniqueConstraint(
                fields=['modifier_option', 'variant', 'component_product'],
                name='recipes_modconsumption_option_variant_component_uniq',
            ),
            # Same paired pattern as InventoryCost.branch / Recipe.variant —
            # caps the variant=NULL (variant-agnostic) row at one per
            # (option, component), since NULL is otherwise distinct-per-row.
            models.UniqueConstraint(
                fields=['modifier_option', 'component_product'],
                condition=models.Q(variant__isnull=True),
                name='recipes_modconsumption_option_component_null_variant_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.modifier_option_id}: {self.entered_qty} of {self.component_product_id}'


class SaleItemModifier(models.Model):
    """Snapshot of one selected modifier on a sale line (Sprint 5 Batch 5).
    `group_name`/`option_name`/`price_delta` are all frozen at sale time —
    a later rename, regrouping, price change, or deletion of the
    `ModifierGroup`/`ModifierOption` never alters a historical sale line.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='sale_item_modifiers', db_index=True,
    )
    sale_item = models.ForeignKey(
        'pos.SaleItem', on_delete=models.CASCADE, related_name='modifiers',
    )
    modifier_option = models.ForeignKey(
        ModifierOption, on_delete=models.SET_NULL, null=True, blank=True,
    )
    group_name = models.CharField(max_length=80, blank=True, default='')
    option_name = models.CharField(max_length=80)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.sale_item_id}: {self.group_name} / {self.option_name}'


class SaleItemRecipeCostSnapshot(models.Model):
    """The immutable recipe-cost snapshot taken at sale time (D-31 Option B
    — normalized rows, not a JSON blob, matching `InventoryCostMovement`'s
    established pattern). One per recipe-product sale line;
    `total_recipe_cost` is also mirrored onto `SaleItem.unit_cost` itself,
    so the entire existing COGS/gross-profit/dashboard pipeline
    (`cogs = Σ(unit_cost × qty)`) works for recipe sales with zero code
    changes — this snapshot exists purely for the detailed "why" breakdown
    a food-cost report needs.

    Contract (pre-Batch-6 architecture review, point 5): once written, this
    row (and its `.lines`) is the SOLE source of truth for this sale item's
    recipe cost and ingredient consumption, forever. No later operation —
    void, refund, or any future feature — may call
    `recipes.services.costing.compute_recipe_cost()`,
    `compute_modifier_deltas()`, or `compute_recipe_sale_lines()` again for
    an already-posted sale item. Those functions read the *current* recipe
    definition and *current* ingredient costs, which is correct only at the
    moment of sale; re-invoking them later would silently let a historical
    sale's recorded cost/consumption drift as recipes are edited or
    ingredient prices change. `pos.serializers.SaleSerializer._apply_stock`
    and `pos.views.void_sale` both read `.lines` directly for this reason.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='sale_item_recipe_cost_snapshots', db_index=True,
    )
    sale_item = models.OneToOneField(
        'pos.SaleItem', on_delete=models.CASCADE, related_name='recipe_cost_snapshot',
    )
    recipe_version = models.ForeignKey(
        RecipeVersion, on_delete=models.SET_NULL, null=True, blank=True,
    )
    total_recipe_cost = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'RecipeCostSnapshot sale_item={self.sale_item_id} total={self.total_recipe_cost}'


class SaleItemRecipeCostSnapshotLine(models.Model):
    """One component's frozen cost contribution within a
    `SaleItemRecipeCostSnapshot` — a base-recipe ingredient or a selected
    modifier's consumption delta (`is_modifier_line` distinguishes them).
    `component_name`/`unit_cost` are frozen text/values, independent of
    whatever the component's live average cost is by the time anyone reads
    this row later.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='sale_item_recipe_cost_snapshot_lines', db_index=True,
    )
    snapshot = models.ForeignKey(
        SaleItemRecipeCostSnapshot, on_delete=models.CASCADE, related_name='lines',
    )
    component_product = models.ForeignKey(
        'pos.Product', on_delete=models.SET_NULL, null=True, blank=True,
    )
    component_name = models.CharField(max_length=120)
    qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    line_cost = models.DecimalField(max_digits=10, decimal_places=2)
    is_modifier_line = models.BooleanField(default=False)
    source_modifier_option = models.ForeignKey(
        ModifierOption, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.snapshot_id}: {self.component_name} = {self.line_cost}'
