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

from pos.services import costing as pos_costing_svc
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


def get_active_recipe(product, variant=None) -> Optional[RecipeVersion]:
    """The currently-ACTIVE `RecipeVersion` for `(product, variant)`, or
    `None` if the product/variant has no recipe at all, or has one but no
    version is currently active (e.g. still in draft)."""
    recipe = Recipe.objects.filter(product=product, variant=variant, is_active=True).first()
    if recipe is None:
        return None
    return recipe.versions.filter(status=RecipeVersion.Status.ACTIVE).first()


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


__all__ = [
    'RecipeError', 'RecipeCostLine', 'RecipeCostResult', 'MAX_RECIPE_DEPTH',
    'get_active_recipe', 'compute_recipe_cost', 'validate_recipe_lines',
    'activate_recipe_version',
]
