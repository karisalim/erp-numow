"""Recipe cost calculation + nesting/cycle validation (Sprint 5 Batch 3).

Mirrors `pos.services.costing`'s house style: pure functions, a
service-level exception, `__all__`. This module never writes
`InventoryCost` itself — recipe cost is always a *read*, rolled up live
from each component's branch-scoped average cost
(`pos.services.costing.get_cost_for_sale`), per the owner's own
requirement: "the recipe stays the same, but the cost of the new sale
changes automatically" when an ingredient's price moves. Nothing here is
cached — a café's menu is small enough that computing this fresh on every
read/sale is cheap, and caching it would just be a staleness bug waiting
to happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, List, Optional

from django.db import transaction
from django.db.models import Q

from pos.models import BranchWarehouse
from pos.services import costing as pos_costing_svc
from pos.services.product_types import ProductType
from recipes.models import Recipe, RecipeVersion

# D-26 (Sprint 5 Phase 0, 2026-07-22): recipe -> sub-recipe -> raw
# ingredient. A component whose own chain would exceed this total depth is
# rejected at save time.
MAX_RECIPE_DEPTH = 2


class RecipeError(Exception):
    """Service-level rule violation. The serializer/view turns this into a 400."""

    code = 'recipe_invalid'


@dataclass
class RecipeCostLine:
    """One per-source cost line. `qty_base`/`line_cost` are the raw,
    unrounded values for that single source (a base `RecipeLine` or one
    modifier's `ModifierOptionConsumption` row) — never netted against any
    other line here. A modifier's removal delta (`qty_base < 0`) keeps its
    real negative sign, both in `qty_base` and in the resulting
    `line_cost`. Callers that need a per-component NET quantity (stock
    deduction) or a rounded total (the sale-item cost snapshot) compute
    that themselves from a list of these lines — see
    `compute_recipe_sale_lines`'s docstring."""

    component_product_id: int
    component_name: str
    qty_base: Decimal
    unit_cost: Decimal
    line_cost: Decimal
    is_modifier_line: bool = False
    source_modifier_option_id: Optional[int] = None


@dataclass
class RecipeCostResult:
    total_cost: Decimal
    lines: List[RecipeCostLine] = field(default_factory=list)


def is_recipe_eligible(product) -> bool:
    """Whether `product` sells through the Sprint 5 recipe path
    (branch-scoped cost roll-up + `RECIPE_CONSUME` depletion) rather than
    the legacy stock-item path (`Product.cost` snapshot + `SALE_OUT`). This
    is the single, centralized gate — `SaleSerializer.validate()`/
    `create()`/`_apply_stock()` all call this instead of re-deriving the
    condition inline, matching the "ask the centralized matrix, never
    branch on raw flags in more than one place" discipline
    `pos.services.product_types` already established.

    Deliberately narrower than the raw `can_have_recipe` behavior-matrix
    flag. Three product types carry `can_have_recipe=True`:
    `RECIPE_PRODUCT`, `PREP_ITEM`, and `BUNDLE` — but only the first two
    are in scope here:

      * `RECIPE_PRODUCT` / `PREP_ITEM` — a genuine recipe/BOM of measured
        ingredients (grams, ml, …), costed via AVCO and consumed through
        base-unit quantities. This is exactly what Sprint 5 builds.
      * `BUNDLE` is EXCLUDED on purpose. `can_have_recipe=True` on `BUNDLE`
        is a Sprint 2 placeholder for a future, different feature — "bundle
        explosion": a combo of already-stocked FINISHED goods (e.g. "Combo
        Meal = 1 Burger + 1 Fries + 1 Drink"), each consumed as a whole-unit
        multiple, not a measured/converted recipe quantity. Nothing in this
        sprint's scope (owner's request, Sprint 5 plan) designs or builds
        that mechanism. A `BUNDLE`-typed product — even if a `Recipe` is
        attached to it via the Batch 3 API, which has no type restriction —
        falls through to the exact legacy stock-item sale path unchanged
        (its own `Product.stock`/`SALE_OUT`, same as before Sprint 5, same
        as `SERVICE`/`FIXED_ASSET` today) until real bundle-explosion logic
        is designed and built as its own slice.
    """
    behavior = product.type_behavior
    return (
        not behavior.affects_stock and behavior.can_have_recipe
        and product.product_type != ProductType.BUNDLE
    )


def get_active_recipe(product, variant=None) -> Optional[RecipeVersion]:
    """The currently-ACTIVE `RecipeVersion` for `(product, variant)`, or
    `None` if the product/variant has no recipe at all, or has one but no
    version is currently active (e.g. still in draft)."""
    recipe = Recipe.objects.filter(product=product, variant=variant, is_active=True).first()
    if recipe is None:
        return None
    return recipe.versions.filter(status=RecipeVersion.Status.ACTIVE).first()


def check_recipe_readiness(product, variant=None) -> RecipeVersion:
    """The Batch 8 production-readiness gate — the same concept mature
    ERPs call an "availability check" before allowing a sale/production
    order (e.g. Dynamics 365's material availability check). Raises
    `RecipeError` with a message naming the SPECIFIC failed condition —
    never a generic "not ready" — so `SaleSerializer` can surface it
    directly to the cashier/manager.

    Conditions checked HERE (deliberately query-cheap — identical cost to
    the old bare `get_active_recipe()` this replaces, 2 queries):
      1. A Recipe exists for (product, variant).
      2. That Recipe has an ACTIVE version.

    Two further conditions — (3) the active version has at least one
    active ingredient line, (4) every referenced ingredient is still an
    active `Product` — are enforced by `compute_recipe_sale_lines`
    instead of here, deliberately: that function already fetches every
    line with `select_related('component_product')` to compute cost, so
    checking there costs ZERO extra queries. Checking here too would
    fetch the same rows twice — a measured regression this codebase
    treats as a real regression, not a rounding error (see
    `RecipeSalePostingTests.test_recipe_sale_query_count_regression_
    guard`). `SaleSerializer.create()` calls both functions in the same
    request, so the net effect for a caller is identical either way; only
    the query cost differs.

    Unit correctness (D-26-style "every unit resolves") is NOT re-checked
    at all: `RecipeLine.qty_base` is computed and frozen once, at
    line-creation time (`RecipeLineSerializer.create`) — there is no live
    unit resolution left to fail at sale time.
    """
    recipe = Recipe.objects.filter(product=product, variant=variant, is_active=True).first()
    if recipe is None:
        raise RecipeError(f'"{product.name}" has no recipe configured yet.')
    # select_related so `compute_recipe_sale_lines`' failure-path messages
    # (recipe_version.recipe.product.name) cost a JOIN, not an extra query.
    version = (
        recipe.versions.filter(status=RecipeVersion.Status.ACTIVE)
        .select_related('recipe__product').first()
    )
    if version is None:
        raise RecipeError(f'"{product.name}" has no active recipe version yet.')
    return version


def compute_recipe_cost(recipe_version: RecipeVersion, branch=None) -> RecipeCostResult:
    """Roll up a `RecipeVersion`'s cost from its components' current
    branch-scoped average cost (Sprint 5 Batch 1). Each line is quantized
    to money (2dp, D-12 line-level rounding) before summing — the total is
    Σ of already-rounded lines, not a rounded sum of raw Decimals."""
    lines = []
    total = Decimal('0.00')
    qs = (
        recipe_version.lines.filter(is_active=True)
        .select_related('component_product')
        .order_by('sort_order', 'id')
    )
    for line in qs:
        unit_cost = pos_costing_svc.get_cost_for_sale(line.component_product, branch=branch)
        line_cost = pos_costing_svc.quantize_money(line.qty_base * unit_cost)
        total += line_cost
        lines.append(RecipeCostLine(
            component_product_id=line.component_product_id,
            component_name=line.component_product.name,
            qty_base=line.qty_base,
            unit_cost=unit_cost,
            line_cost=line_cost,
        ))
    return RecipeCostResult(total_cost=total, lines=lines)


def _max_sub_recipe_depth(component_product, visited_product_ids: frozenset) -> int:
    """How many further levels of active recipe hang off `component_product`
    (0 = a raw ingredient with no recipe of its own). Raises `RecipeError`
    the moment the walk revisits a product already in the current chain
    (D-27 — a component chain looping back to an ancestor product, tracked
    by base product id only, not variant-aware; simpler and sufficient for
    this sprint's scope)."""
    if component_product.id in visited_product_ids:
        raise RecipeError(
            f'circular recipe reference detected: product "{component_product.name}" '
            f'(id={component_product.id}) is already an ancestor in this recipe chain',
        )
    version = get_active_recipe(component_product, variant=None)
    if version is None:
        return 0
    sub_lines = list(
        version.lines.filter(is_active=True).select_related('component_product'),
    )
    if not sub_lines:
        return 0
    next_visited = visited_product_ids | {component_product.id}
    return 1 + max(
        _max_sub_recipe_depth(line.component_product, next_visited) for line in sub_lines
    )


def validate_recipe_lines(*, product, component_products: Iterable) -> None:
    """Enforce D-26 (max nesting depth) and D-27 (no circular references)
    for a new/edited `RecipeVersion`'s lines, BEFORE anything is saved.

    `component_products` is the list of `Product` instances the new
    version's lines would reference. `variant` is deliberately not part of
    the cycle key — a chain looping back to the same base product,
    regardless of which variant's recipe started it, is treated as a
    cycle.
    """
    for component in component_products:
        if component.id == product.id:
            raise RecipeError(
                f'a recipe cannot use its own product ("{product.name}") as an ingredient',
            )
        depth = 1 + _max_sub_recipe_depth(component, frozenset({product.id}))
        if depth > MAX_RECIPE_DEPTH:
            raise RecipeError(
                f'recipe nesting exceeds the maximum depth of {MAX_RECIPE_DEPTH} (D-26): '
                f'"{component.name}" would nest too deep',
            )


def _resolve_modifier_consumptions(modifier_option, variant=None) -> List:
    """`ModifierOptionConsumption` rows for `modifier_option`, scoped to
    this exact `variant` OR variant-agnostic (`variant=NULL`); when both
    exist for the same component, the variant-specific row wins. Shared by
    every function below that reads modifier consumption — the one place
    this dedup rule is expressed."""
    consumptions = list(
        modifier_option.consumptions.filter(is_active=True)
        .filter(Q(variant=variant) | Q(variant__isnull=True))
        .select_related('component_product')
    )
    by_component = {}
    for consumption in consumptions:
        existing = by_component.get(consumption.component_product_id)
        is_more_specific = existing is not None and existing.variant_id is None and consumption.variant_id is not None
        if existing is None or is_more_specific:
            by_component[consumption.component_product_id] = consumption
    return list(by_component.values())


def compute_modifier_deltas(modifier_option, variant=None, branch=None) -> RecipeCostResult:
    """Cost contribution of one selected `ModifierOption` in isolation, for
    a given `variant` (or `variant=None` for a product with no size
    variants). Per D-34, a **negative** consumption delta (e.g. "No
    Onion", `qty_base < 0`) is not consumed at sale time and contributes
    **zero** cost here — removing an ingredient must never produce a
    negative COGS line; a free modifier (`price_delta=0`) still
    contributes its full consumption cost.

    This function looks at ONE modifier on its own — it does not know
    about the recipe's own quantities, so it cannot tell whether a removal
    delta is actually satisfiable (e.g. "No Onion" -40g when the recipe
    only has 20g). For a real sale line, `compute_recipe_sale_lines` is
    the function that nets a recipe against every selected modifier
    together and enforces that. This one stays useful on its own for a
    "preview this modifier's cost" API/report.
    """
    lines = []
    total = Decimal('0.00')
    for consumption in _resolve_modifier_consumptions(modifier_option, variant):
        if consumption.qty_base <= 0:
            continue  # negative/removal delta — not consumed, zero cost (D-34)
        unit_cost = pos_costing_svc.get_cost_for_sale(consumption.component_product, branch=branch)
        line_cost = pos_costing_svc.quantize_money(consumption.qty_base * unit_cost)
        total += line_cost
        lines.append(RecipeCostLine(
            component_product_id=consumption.component_product_id,
            component_name=consumption.component_product.name,
            qty_base=consumption.qty_base, unit_cost=unit_cost, line_cost=line_cost,
            is_modifier_line=True, source_modifier_option_id=modifier_option.id,
        ))
    return RecipeCostResult(total_cost=total, lines=lines)


def compute_recipe_sale_lines(
    recipe_version: RecipeVersion, *, modifier_options: Iterable = (), variant=None, branch=None,
) -> RecipeCostResult:
    """The single authoritative computation for one real recipe sale line
    — `SaleSerializer.create()` calls this exactly once per recipe line;
    its result is what gets frozen into the immutable
    `SaleItemRecipeCostSnapshot`(+lines), and everything downstream
    (`_apply_stock`'s `RECIPE_CONSUME` movements, any future void/refund)
    reads that snapshot only — nothing calls this function, or
    `compute_recipe_cost`/`compute_modifier_deltas`, a second time for an
    already-posted sale.

    Post-review revision (pre-Batch-6 review, snapshot-granularity
    question): the returned `.lines` are **NOT netted per component**.
    Every active base `RecipeLine` becomes its own line
    (`is_modifier_line=False`), and every selected modifier's resolved
    `ModifierOptionConsumption` becomes its own line
    (`is_modifier_line=True`) — even when a base line and a modifier line
    touch the same `component_product_id`. A removal modifier's negative
    `qty_base` (and the resulting negative `line_cost`) is preserved as-is.
    This keeps the sale-item snapshot fully auditable: "the recipe called
    for 20g onion; 'No Onion' removed 20g" is two visible rows, not one
    silently-merged zero.

    Netting still happens, but only for two narrow purposes that need a
    single per-component number, neither of which touches the stored
    lines:

    1. **Validation here, at sale-creation time.** The net quantity for
       any component (Σ base lines + Σ selected modifier deltas for that
       component) can never go negative — if a modifier is configured to
       remove MORE of an ingredient than the recipe (plus any other
       selected modifier) actually provides, that is a data/configuration
       problem: this function raises `RecipeError` (the caller turns it
       into a 400) instead of accepting a sale whose stock deduction could
       never be satisfied without going negative. A net of exactly zero
       (fully, validly removed) is not an error.
    2. **Stock deduction, at `_apply_stock` time**, which nets the
       *stored, unnetted* snapshot lines back down to one quantity per
       component before writing a `RECIPE_CONSUME` movement — see that
       function's own comment. It does not call this function again; it
       re-derives the net from `.lines` directly, per the snapshot's
       "sole source of truth" contract.

    Rounding: each stored line's `.line_cost` is the raw, unrounded
    `qty_base * unit_cost` (the DB column itself is `DecimalField(10,2)`
    and rounds it on write — an incidental storage-precision effect, not a
    deliberate per-line quantization). `RecipeCostResult.total_cost` is
    computed by summing every line's *raw* cost first and quantizing to
    money (2dp) exactly once at the end — not by summing already-rounded
    per-line amounts — so the total never accumulates per-line rounding
    drift across a recipe with many ingredients.
    """
    net_qty: dict = {}
    component_by_id: dict = {}
    unit_cost_cache: dict = {}

    def _unit_cost(component):
        cid = component.id
        cost = unit_cost_cache.get(cid)
        if cost is None:
            cost = pos_costing_svc.get_cost_for_sale(component, branch=branch)
            unit_cost_cache[cid] = cost
        return cost

    base_lines = list(
        recipe_version.lines.filter(is_active=True).select_related('component_product'),
    )
    # Batch 8 production-readiness pass — the two remaining
    # check_recipe_readiness() conditions (non-empty version, no
    # discontinued ingredient), checked HERE instead of in that function
    # so they cost zero extra queries: `base_lines` above is already the
    # exact fetch those checks need, with `component_product` already
    # select_related. See check_recipe_readiness's docstring.
    if not base_lines:
        raise RecipeError(
            f'"{recipe_version.recipe.product.name}"\'s active recipe version '
            f'(v{recipe_version.version_no}) has no ingredient lines.',
        )
    discontinued = sorted({
        line.component_product.name for line in base_lines if not line.component_product.active
    })
    if discontinued:
        raise RecipeError(
            f'"{recipe_version.recipe.product.name}" cannot be sold — its recipe uses '
            f'discontinued ingredient(s): {", ".join(discontinued)}.',
        )
    for line in base_lines:
        cid = line.component_product_id
        net_qty[cid] = net_qty.get(cid, Decimal('0')) + line.qty_base
        component_by_id[cid] = line.component_product

    modifier_consumptions = []  # [(option, consumption), ...]
    for option in modifier_options:
        for consumption in _resolve_modifier_consumptions(option, variant):
            cid = consumption.component_product_id
            net_qty[cid] = net_qty.get(cid, Decimal('0')) + consumption.qty_base
            component_by_id[cid] = consumption.component_product
            modifier_consumptions.append((option, consumption))

    for cid, qty in net_qty.items():
        if qty < 0:
            raise RecipeError(
                f'modifier selection would consume a negative quantity of '
                f'"{component_by_id[cid].name}" ({qty}) — a removal modifier '
                f'cannot take away more of an ingredient than the recipe '
                f'actually provides',
            )

    lines = []
    total_raw = Decimal('0')
    for line in base_lines:
        unit_cost = _unit_cost(line.component_product)
        raw_cost = line.qty_base * unit_cost
        total_raw += raw_cost
        lines.append(RecipeCostLine(
            component_product_id=line.component_product_id,
            component_name=line.component_product.name,
            qty_base=line.qty_base, unit_cost=unit_cost, line_cost=raw_cost,
            is_modifier_line=False,
        ))
    for option, consumption in modifier_consumptions:
        unit_cost = _unit_cost(consumption.component_product)
        raw_cost = consumption.qty_base * unit_cost
        total_raw += raw_cost
        lines.append(RecipeCostLine(
            component_product_id=consumption.component_product_id,
            component_name=consumption.component_product.name,
            qty_base=consumption.qty_base, unit_cost=unit_cost, line_cost=raw_cost,
            is_modifier_line=True, source_modifier_option_id=option.id,
        ))

    total_cost = pos_costing_svc.quantize_money(total_raw)
    return RecipeCostResult(total_cost=total_cost, lines=lines)


@transaction.atomic
def activate_recipe_version(version: RecipeVersion) -> RecipeVersion:
    """Flip `version` to ACTIVE, archiving whatever was previously active
    on the same recipe — atomically, so the "at most one ACTIVE version"
    invariant is never briefly violated."""
    (
        RecipeVersion.objects
        .filter(recipe_id=version.recipe_id, status=RecipeVersion.Status.ACTIVE)
        .exclude(pk=version.pk)
        .update(status=RecipeVersion.Status.ARCHIVED)
    )
    version.status = RecipeVersion.Status.ACTIVE
    version.save(update_fields=['status', 'updated_at'])
    return version


def resolve_kitchen_warehouse(*, tenant, branch):
    """The warehouse a `RECIPE_CONSUME` movement lands in for `branch` —
    mirrors `pos.services.purchase_invoices._resolve_line_warehouse`'s
    exact pattern: prefer the branch's active default `BranchWarehouse`
    with `role=KITCHEN`, fall back to `role=SALES` (many small cafés won't
    bother separating them), raise if neither is configured.
    """
    for role in (BranchWarehouse.Role.KITCHEN, BranchWarehouse.Role.SALES):
        link = (
            BranchWarehouse.objects
            .filter(tenant=tenant, branch=branch, role=role, is_default=True, is_active=True)
            .select_related('warehouse')
            .first()
        )
        if link is not None and link.warehouse_id is not None:
            return link.warehouse
    raise RecipeError(
        'no default kitchen or sales warehouse is configured for this branch — '
        'recipe consumption has nowhere to deplete stock from',
    )


__all__ = [
    'RecipeError', 'RecipeCostLine', 'RecipeCostResult', 'MAX_RECIPE_DEPTH',
    'is_recipe_eligible', 'get_active_recipe', 'check_recipe_readiness', 'compute_recipe_cost',
    'validate_recipe_lines', 'compute_modifier_deltas', 'compute_recipe_sale_lines',
    'activate_recipe_version', 'resolve_kitchen_warehouse',
]
