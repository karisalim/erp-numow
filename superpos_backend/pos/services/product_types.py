"""Product type classification + behavior matrix (Sprint 2 Batch 3).

Single source of truth for BOTH the `Product.product_type` choices and what
each type is allowed to do. Nothing else in the codebase may branch on
`product_type` directly — consumers ask this module (directly or through
`Product.type_behavior`) so future types are added in exactly one place.

The flags are CLASSIFICATION ONLY in this batch (MASTER_DATA_CONTRACT §11 +
approved Sprint 2 re-plan): no Recipe/BOM, no automatic consumption, no
costing/COGS/GL is wired to them yet. They are exposed read-only through the
product API so the frontend and later slices (Recipe — Sprint 3+, bundle
explosion, purchase flows) share one authority instead of re-deriving rules.

Enum note: the type list follows the owner's Batch 3 instruction of
2026-07-15 (`resale`, `bundle`, `fixed_asset`), which supersedes the older
contract §11 spellings (`non_stock`, `bundle_combo`,
`fixed_asset_purchase_only`). `service` covers the contract's non-stock
intent. Recorded for the Batch 0 ADR upgrade.
"""

from __future__ import annotations

from typing import NamedTuple

from django.db import models


class ProductType(models.TextChoices):
    STOCK_ITEM     = 'stock_item',     'Stock item'
    INGREDIENT     = 'ingredient',     'Ingredient'
    PREP_ITEM      = 'prep_item',      'Prep item'
    RECIPE_PRODUCT = 'recipe_product', 'Recipe product'
    RESALE         = 'resale',         'Resale'
    PACKAGING      = 'packaging',      'Packaging'
    SERVICE        = 'service',        'Service'
    BUNDLE         = 'bundle',         'Bundle'
    FIXED_ASSET    = 'fixed_asset',    'Fixed asset'


class ProductTypeBehavior(NamedTuple):
    """What a product of this type may participate in.

    `affects_stock` is about DOCUMENT posting (does selling/consuming it move
    a stock ledger), while `track_inventory` is about carrying an on-hand
    balance at all — a recipe product affects nothing itself (its ingredients
    do, via the future Recipe slice), so both are False there.
    """

    can_sell:        bool
    can_purchase:    bool
    track_inventory: bool
    affects_stock:   bool
    requires_cost:   bool
    can_have_recipe: bool


#: The behavior matrix. Keys are `ProductType` values; a missing key is a
#: programming error surfaced loudly by `get_behavior` (never a silent
#: default) so adding a type without classifying it cannot slip through.
PRODUCT_TYPE_BEHAVIOR: dict[str, ProductTypeBehavior] = {
    # Classic on-shelf goods: bought, sold, counted, costed.
    ProductType.STOCK_ITEM: ProductTypeBehavior(
        can_sell=True,  can_purchase=True,  track_inventory=True,
        affects_stock=True,  requires_cost=True,  can_have_recipe=False,
    ),
    # Raw material consumed by recipes; purchased and counted, never on the menu.
    ProductType.INGREDIENT: ProductTypeBehavior(
        can_sell=False, can_purchase=True,  track_inventory=True,
        affects_stock=True,  requires_cost=True,  can_have_recipe=False,
    ),
    # In-house prepared intermediate (sauce, dough): produced from a recipe,
    # counted as stock, not purchased and not sold directly.
    ProductType.PREP_ITEM: ProductTypeBehavior(
        can_sell=False, can_purchase=False, track_inventory=True,
        affects_stock=True,  requires_cost=True,  can_have_recipe=True,
    ),
    # Menu item assembled at sale time from ingredients; carries no own
    # balance — consumption happens through its (future) recipe, and its cost
    # is derived from the recipe rather than entered.
    ProductType.RECIPE_PRODUCT: ProductTypeBehavior(
        can_sell=True,  can_purchase=False, track_inventory=False,
        affects_stock=False, requires_cost=False, can_have_recipe=True,
    ),
    # Bought-to-sell-as-is goods; behaviorally a stock item, kept as its own
    # classification for purchasing/reporting.
    ProductType.RESALE: ProductTypeBehavior(
        can_sell=True,  can_purchase=True,  track_inventory=True,
        affects_stock=True,  requires_cost=True,  can_have_recipe=False,
    ),
    # Boxes, bags, cups: purchased and counted, consumed operationally,
    # never sold as a line of their own.
    ProductType.PACKAGING: ProductTypeBehavior(
        can_sell=False, can_purchase=True,  track_inventory=True,
        affects_stock=True,  requires_cost=True,  can_have_recipe=False,
    ),
    # Delivery fee, table service, repair labor: sellable, no inventory
    # existence at all.
    ProductType.SERVICE: ProductTypeBehavior(
        can_sell=True,  can_purchase=False, track_inventory=False,
        affects_stock=False, requires_cost=False, can_have_recipe=False,
    ),
    # A sellable grouping of other products. Carries no own balance; the
    # future bundle-explosion slice moves its components' stock.
    ProductType.BUNDLE: ProductTypeBehavior(
        can_sell=True,  can_purchase=False, track_inventory=False,
        affects_stock=False, requires_cost=False, can_have_recipe=True,
    ),
    # Equipment bought for the business (oven, fridge): purchase-only,
    # costed, never part of sellable inventory.
    ProductType.FIXED_ASSET: ProductTypeBehavior(
        can_sell=False, can_purchase=True,  track_inventory=False,
        affects_stock=False, requires_cost=True,  can_have_recipe=False,
    ),
}


def get_behavior(product_type: str) -> ProductTypeBehavior:
    """The behavior row for a type value; raises for unknown types.

    Raising (instead of defaulting to stock_item) keeps a typo or an
    unclassified new enum member from silently inheriting full stock
    behavior.
    """
    try:
        return PRODUCT_TYPE_BEHAVIOR[product_type]
    except KeyError:
        raise ValueError(
            f'Unknown product_type {product_type!r} — add it to '
            f'PRODUCT_TYPE_BEHAVIOR in pos/services/product_types.py.',
        ) from None


def behavior_flags(product_type: str) -> dict[str, bool]:
    """`get_behavior` as a plain dict — the API read-only representation."""
    return get_behavior(product_type)._asdict()


#: Field-level requirements per type, derived from the SAME behavior matrix
#: above (never a second, independently-maintained rule set). Split into two
#: honest tiers so the metadata payload never claims more than the backend
#: actually does:
#:   * `required_fields`  — the backend REJECTS a write missing this field
#:     for this type (`Product.price`/`Product.cost` have no DB default and
#:     no `null=True`, so DRF already requires them; `name`/`barcode` are
#:     always required). Every name here is a hard 400 if omitted.
#:   * `recommended_fields` — a real business-rule gap review finding (a
#:     sellable product with no `sales_category`, or a stock-tracked one
#:     with no `inventory_category`, is bad menu/purchasing hygiene) that is
#:     DELIBERATELY not backend-enforced: both FKs are `null=True,
#:     blank=True` on `Product` (uncategorized is a valid, permanent state —
#:     the same "Uncategorized" fallback every mainstream ERP allows — and
#:     hard-requiring them would break the Quick Add fast-entry path this
#:     app's POS relies on). The frontend nudges for these; the backend
#:     never 400s over them.
def _required_fields(behavior: ProductTypeBehavior) -> list[str]:
    fields: list[str] = ['name', 'barcode']
    if behavior.can_sell:
        fields.append('price')
    if behavior.requires_cost:
        fields.append('cost')  # opening cost, create-time only — see ProductSerializer.create()
    return fields


def _recommended_fields(behavior: ProductTypeBehavior) -> list[str]:
    fields: list[str] = []
    if behavior.can_sell:
        fields.append('sales_category')
    if behavior.track_inventory:
        fields.append('inventory_category')
    return fields


def product_type_metadata() -> list[dict]:
    """The full per-type picture the frontend needs to render a dynamic
    form: label, behavior flags, and required/recommended fields — all read
    straight off `PRODUCT_TYPE_BEHAVIOR`/`_required_fields`/
    `_recommended_fields`, zero duplication. Powers
    `GET /api/catalog/product-types/`.
    """
    return [
        {
            'value': value,
            'label': label,
            'behavior': behavior_flags(value),
            'required_fields': _required_fields(get_behavior(value)),
            'recommended_fields': _recommended_fields(get_behavior(value)),
        }
        for value, label in ProductType.choices
    ]


__all__ = [
    'ProductType',
    'ProductTypeBehavior',
    'PRODUCT_TYPE_BEHAVIOR',
    'get_behavior',
    'behavior_flags',
    'product_type_metadata',
]
