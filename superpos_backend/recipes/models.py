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
