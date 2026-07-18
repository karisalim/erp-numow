"""AVCO (weighted moving-average cost) engine (Sprint 3 Batch 2).

Single authority for reading and updating `InventoryCost.avg_unit_cost`.
Nothing else in the codebase may write to `InventoryCost` directly, or
derive a cost by any means other than the functions here — the same
"single authority" discipline `pos/services/pricing.py` and
`pos/services/units.py` already establish for price and quantity.

Golden rule (per D-07/D-09/D-13/D-35 and the standard AVCO practice used by
SAP/Oracle/Odoo — confirmed with the Business Owner 2026-07-16), matching
`FLOW_v3_6.md` §7:

    The average cost updates on exactly two kinds of event — a **quantity
    increase with a known cost**:
        1. Purchase receipt          -> `apply_purchase_receipt`
        2. Positive inventory count  -> `update_cost_from_adjustment`

    Every other movement CONSUMES the current average without changing it:
    sale, sale return, purchase return, negative/shrinkage adjustment,
    warehouse transfer, damage/wastage, recipe consumption. Those read
    through `get_cost_for_sale` / `get_cost_for_return` (both pure reads —
    neither ever writes `InventoryCost`).

`update_cost_from_adjustment` was added in Batch 2 and wired into two call
sites in Batch 3: `views.stock_adjustment` (a positive physical count with
`unit_cost` given) and `views._import_row`'s CSV-update branch (a row that
raises `stock`, using its `cost` column as the found-quantity's cost).
Batch 3 also closed the two other uncoordinated write paths — `Product.cost`
is no longer a writable field on `ProductSerializer.update()` for an
existing product; only `initialize_inventory_cost` (on create) and the two
functions below (via those two call sites, or a purchase receipt) may move
it, so every change stays in the `InventoryCostMovement` audit trail.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction

from pos.models import InventoryCost, InventoryCostMovement, Product

_COST_4DP = Decimal('0.0001')   # D-13 internal unit-cost precision
_CENTS    = Decimal('0.01')     # D-12 money display precision (Product.cost mirror)


class CostingError(Exception):
    """Service-level rule violation. The serializer/view turns this into a 400."""

    code = 'costing_invalid'


def quantize_cost(value) -> Decimal:
    """4dp HALF_UP — internal average-cost precision (D-13)."""
    return Decimal(str(value or 0)).quantize(_COST_4DP, rounding=ROUND_HALF_UP)


def quantize_money(value) -> Decimal:
    """2dp HALF_UP — display/mirror precision (D-12), matches `Product.cost`."""
    return Decimal(str(value or 0)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def moving_average_cost(current_stock, current_avg_cost, qty, unit_cost) -> Decimal:
    """Weighted moving-average cost after receiving `qty` at `unit_cost`.

    new_cost = (current_stock × current_avg_cost + qty × unit_cost)
               ÷ (current_stock + qty)

    Falls back to `unit_cost` when the resulting denominator is <= 0 (e.g.
    the product was oversold to a negative balance) so we never divide by
    zero or carry a nonsensical average. Pure function — quantizes to 4dp
    (D-13); callers that need the 2dp `Product.cost` mirror value call
    `quantize_money` on the result themselves.
    """
    current_stock   = Decimal(str(current_stock or 0))
    current_avg_cost = Decimal(str(current_avg_cost or 0))
    qty       = Decimal(str(qty))
    unit_cost = Decimal(str(unit_cost))

    denom = current_stock + qty
    if denom <= 0:
        return unit_cost.quantize(_COST_4DP, rounding=ROUND_HALF_UP)
    new_cost = (current_stock * current_avg_cost + qty * unit_cost) / denom
    return new_cost.quantize(_COST_4DP, rounding=ROUND_HALF_UP)


def get_or_create_inventory_cost(product: Product) -> InventoryCost:
    """Defensive lazy fetch. A product created before Batch 1's seed command
    ran (or in a tenant that skipped it) still gets a correct row here,
    opened from its current `Product.cost` mirror — mirrors
    `units.get_base_product_unit()`'s graceful handling of unconfigured
    legacy products."""
    row, _ = InventoryCost.objects.get_or_create(
        product=product,
        defaults={'tenant_id': product.tenant_id, 'avg_unit_cost': quantize_cost(product.cost)},
    )
    return row


def initialize_inventory_cost(*, product: Product, opening_cost=None) -> InventoryCost:
    """Seed the opening average at product-CREATE time. No
    `InventoryCostMovement` row is written — an opening value is not a
    "movement" (same convention D-17 uses for FinancialAccount/Customer/
    Supplier opening balances: stored, never posted)."""
    cost = quantize_cost(opening_cost if opening_cost is not None else product.cost)
    row, created = InventoryCost.objects.get_or_create(
        product=product,
        defaults={'tenant_id': product.tenant_id, 'avg_unit_cost': cost},
    )
    return row


@transaction.atomic
def apply_purchase_receipt(
    *, product: Product, qty, unit_cost, source_document_type: str,
    source_document_id: Optional[int] = None, actor_user=None,
) -> InventoryCost:
    """Blend a purchase receipt into the average cost.

    Locks `Product` (for `.stock`, read BEFORE the increase — the caller is
    expected to apply the stock increase itself, after this call, in the
    same transaction) and `InventoryCost`, computes the new average via
    `moving_average_cost`, syncs the `Product.cost` 2dp display mirror, and
    writes one `InventoryCostMovement` audit row.
    """
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    inv_cost = InventoryCost.objects.select_for_update().filter(product=locked_product).first()
    if inv_cost is None:
        inv_cost = get_or_create_inventory_cost(locked_product)
        inv_cost = InventoryCost.objects.select_for_update().get(pk=inv_cost.pk)

    qty = Decimal(str(qty))
    unit_cost = quantize_cost(unit_cost)
    avg_before = inv_cost.avg_unit_cost
    avg_after = moving_average_cost(locked_product.stock, avg_before, qty, unit_cost)

    inv_cost.avg_unit_cost = avg_after
    inv_cost.save(update_fields=['avg_unit_cost', 'updated_at'])
    Product.objects.filter(pk=locked_product.pk).update(cost=quantize_money(avg_after))

    InventoryCostMovement.objects.create(
        tenant=locked_product.tenant, product=locked_product, inventory_cost=inv_cost,
        quantity_before=locked_product.stock, quantity_received=qty,
        unit_cost_received=unit_cost, avg_cost_before=avg_before, avg_cost_after=avg_after,
        source_document_type=source_document_type, source_document_id=source_document_id,
        actor_user=actor_user,
    )
    return inv_cost


@transaction.atomic
def update_cost_from_adjustment(
    *, product: Product, qty, adjustment_cost, source_document_type: str = 'stock_adjustment',
    source_document_id: Optional[int] = None, actor_user=None, note: str = '',
) -> InventoryCost:
    """Blend a POSITIVE inventory count (stock found during a count, valued
    at `adjustment_cost`) into the average cost — the one other event
    besides a purchase receipt that legitimately updates the average
    (per the Business Owner's confirmed AVCO rule set, matching SAP/Oracle/
    Odoo: shrinkage/negative adjustments, sales, returns, transfers, and
    recipe consumption all CONSUME the average via `get_cost_for_sale`/
    `get_cost_for_return` instead — they never call this function).

    `qty` must be > 0 — a negative/shrinkage adjustment has no cost to
    blend in and must not call this function at all.

    Wired to two call sites as of Batch 3: `views.stock_adjustment` (a
    positive count with `unit_cost` given) and `views._import_row`'s
    CSV-update branch (a row that raises `stock`).
    """
    qty = Decimal(str(qty))
    if qty <= 0:
        raise CostingError(
            'update_cost_from_adjustment requires qty > 0 (a positive count '
            'only) — shrinkage/negative adjustments consume the current '
            'average via get_cost_for_sale instead, they never call this function',
        )

    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    inv_cost = InventoryCost.objects.select_for_update().filter(product=locked_product).first()
    if inv_cost is None:
        inv_cost = get_or_create_inventory_cost(locked_product)
        inv_cost = InventoryCost.objects.select_for_update().get(pk=inv_cost.pk)

    adjustment_cost = quantize_cost(adjustment_cost)
    avg_before = inv_cost.avg_unit_cost
    avg_after = moving_average_cost(locked_product.stock, avg_before, qty, adjustment_cost)

    inv_cost.avg_unit_cost = avg_after
    inv_cost.save(update_fields=['avg_unit_cost', 'updated_at'])
    Product.objects.filter(pk=locked_product.pk).update(cost=quantize_money(avg_after))

    InventoryCostMovement.objects.create(
        tenant=locked_product.tenant, product=locked_product, inventory_cost=inv_cost,
        quantity_before=locked_product.stock, quantity_received=qty,
        unit_cost_received=adjustment_cost, avg_cost_before=avg_before, avg_cost_after=avg_after,
        source_document_type=source_document_type, source_document_id=source_document_id,
        actor_user=actor_user, note=note,
    )
    return inv_cost


def get_cost_for_sale(product: Product) -> Decimal:
    """The current average cost, for a sale line to snapshot. Read-only —
    never updates `InventoryCost`; a sale consumes the average, it does not
    change it."""
    return get_or_create_inventory_cost(product).avg_unit_cost


def get_cost_for_return(product: Product) -> Decimal:
    """The current average cost, for a return line to snapshot. Read-only,
    identical to `get_cost_for_sale` today — kept as a distinct name because
    a purchase return should eventually be valued at the ORIGINAL purchase
    line's cost snapshot (not the live average, which may have moved since),
    while a sale return uses the current average like a sale does. Neither
    return document exists yet (no PurchaseReturn/SalesReturn model) — this
    function is a placeholder read accessor so that future work slots in
    without touching the costing engine itself."""
    return get_or_create_inventory_cost(product).avg_unit_cost


__all__ = [
    'CostingError', 'quantize_cost', 'quantize_money', 'moving_average_cost',
    'get_or_create_inventory_cost', 'initialize_inventory_cost',
    'apply_purchase_receipt', 'update_cost_from_adjustment',
    'get_cost_for_sale', 'get_cost_for_return',
]
