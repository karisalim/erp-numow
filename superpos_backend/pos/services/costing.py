"""AVCO (weighted moving-average cost) engine (Sprint 3 Batch 2; Sprint 5
Batch 1 upgraded it to branch-scoped costing per the reopened D-09).

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

Branch scope (Sprint 5 Batch 1, D-09 reopened to Option B):
    Every write/read function below takes an optional `branch=None`
    keyword. `branch=None` is the tenant-wide fallback row and behaves
    **byte-for-byte identically to before this batch** — same query, same
    `Product.stock`-based blend — so every pre-Sprint-5 call site (the
    legacy `/inventory/purchase/` endpoint, CSV import, any test that
    doesn't pass `branch`) is unaffected. Passing a real `branch` blends
    into that branch's own `InventoryCost` row using
    `stock_movements.get_branch_stock_balance(product, branch)` (a sum of
    that branch's warehouses' `WarehouseStock`, not `Product.stock`) as the
    moving-average's `current_stock` input — stock *quantity* stays
    warehouse-level; only the *average cost* dimension is branch-scoped.
    `Product.cost` (the 2dp display mirror) is still synced unconditionally
    on every call regardless of branch — an intentional simplification:
    it mirrors whichever branch/tenant-wide row last transacted, not a
    partitioned per-branch truth. Read the branch-scoped `InventoryCost`
    row directly (via `get_or_create_inventory_cost(product, branch)`) for
    authoritative per-branch cost.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction

from pos.models import InventoryCost, InventoryCostMovement, Product
from pos.services import stock_movements as stock_svc

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


def get_or_create_inventory_cost(product: Product, branch=None) -> InventoryCost:
    """Defensive lazy fetch, scoped to `(product, branch)`. A product
    created before Batch 1's seed command ran (or in a tenant that skipped
    it) still gets a correct row here — mirrors
    `units.get_base_product_unit()`'s graceful handling of unconfigured
    legacy products.

    `branch=None` seeds straight from `Product.cost`, exactly as before
    Sprint 5 Batch 1 — zero behavior change for callers that never resolve
    a branch. A real `branch` with no row yet seeds from the tenant-wide
    (`branch=None`) row's average when one exists, else from `Product.cost`
    — a branch's first-ever purchase gets a sane opening value instead of
    starting blind at zero.

    Batch 7 verification (measured via `CaptureQueriesContext`, not
    reasoned): the common case — the `(product, branch)` row already
    exists, true for every recipe-sale component after that branch's first
    purchase — used to cost 2 queries every time (an unconditional
    tenant-wide seed lookup, then `get_or_create`'s own SELECT), on a
    function called once per recipe component on every single sale. Try
    the plain lookup FIRST; only pay for the seed-resolution queries on
    the genuine cold-start path (a product/branch combination with no row
    yet), which happens at most once per `(product, branch)` ever.
    """
    row = InventoryCost.objects.filter(product=product, branch=branch).first()
    if row is not None:
        return row

    if branch is not None:
        tenant_wide = InventoryCost.objects.filter(product=product, branch=None).first()
        seed = tenant_wide.avg_unit_cost if tenant_wide is not None else quantize_cost(product.cost)
    else:
        seed = quantize_cost(product.cost)

    row, _ = InventoryCost.objects.get_or_create(
        product=product, branch=branch,
        defaults={'tenant_id': product.tenant_id, 'avg_unit_cost': seed},
    )
    return row


def initialize_inventory_cost(*, product: Product, opening_cost=None) -> InventoryCost:
    """Seed the tenant-wide opening average at product-CREATE time (always
    the `branch=None` row — a brand-new product has no branch history yet).
    No `InventoryCostMovement` row is written — an opening value is not a
    "movement" (same convention D-17 uses for FinancialAccount/Customer/
    Supplier opening balances: stored, never posted).

    Explicitly scoped to `branch=None` in the lookup (Sprint 5 Batch 1) —
    without it, `get_or_create(product=product)` would raise
    `MultipleObjectsReturned` once a product has any branch-scoped
    `InventoryCost` rows alongside its tenant-wide one.
    """
    cost = quantize_cost(opening_cost if opening_cost is not None else product.cost)
    row, created = InventoryCost.objects.get_or_create(
        product=product, branch=None,
        defaults={'tenant_id': product.tenant_id, 'avg_unit_cost': cost},
    )
    return row


@transaction.atomic
def apply_purchase_receipt(
    *, product: Product, qty, unit_cost, source_document_type: str,
    branch=None, source_document_id: Optional[int] = None, actor_user=None,
) -> InventoryCost:
    """Blend a purchase receipt into the average cost.

    Locks `Product` and the `(product, branch)` `InventoryCost` row, computes
    the new average via `moving_average_cost`, syncs the `Product.cost` 2dp
    display mirror, and writes one `InventoryCostMovement` audit row.

    `branch=None` (the default) behaves exactly as before Sprint 5 Batch 1:
    blends against `Product.stock` (read BEFORE the increase — the caller
    applies the stock increase itself, after this call, in the same
    transaction). A real `branch` blends against that branch's own stock
    (`stock_movements.get_branch_stock_balance`) instead, and writes into
    that branch's own `InventoryCost` row.
    """
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    inv_cost = (
        InventoryCost.objects.select_for_update()
        .filter(product=locked_product, branch=branch).first()
    )
    if inv_cost is None:
        inv_cost = get_or_create_inventory_cost(locked_product, branch=branch)
        inv_cost = InventoryCost.objects.select_for_update().get(pk=inv_cost.pk)

    qty = Decimal(str(qty))
    unit_cost = quantize_cost(unit_cost)
    avg_before = inv_cost.avg_unit_cost
    current_stock = (
        stock_svc.get_branch_stock_balance(locked_product, branch)
        if branch is not None else locked_product.stock
    )
    avg_after = moving_average_cost(current_stock, avg_before, qty, unit_cost)

    inv_cost.avg_unit_cost = avg_after
    inv_cost.save(update_fields=['avg_unit_cost', 'updated_at'])
    Product.objects.filter(pk=locked_product.pk).update(cost=quantize_money(avg_after))

    InventoryCostMovement.objects.create(
        tenant=locked_product.tenant, product=locked_product, inventory_cost=inv_cost,
        quantity_before=current_stock, quantity_received=qty,
        unit_cost_received=unit_cost, avg_cost_before=avg_before, avg_cost_after=avg_after,
        source_document_type=source_document_type, source_document_id=source_document_id,
        actor_user=actor_user,
    )
    return inv_cost


@transaction.atomic
def update_cost_from_adjustment(
    *, product: Product, qty, adjustment_cost, source_document_type: str = 'stock_adjustment',
    branch=None, source_document_id: Optional[int] = None, actor_user=None, note: str = '',
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

    `branch=None` (the default) behaves exactly as before Sprint 5 Batch 1.
    A real `branch` blends against that branch's own stock/`InventoryCost`
    row instead — see `apply_purchase_receipt`'s docstring for the same
    scoping rule.

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
    inv_cost = (
        InventoryCost.objects.select_for_update()
        .filter(product=locked_product, branch=branch).first()
    )
    if inv_cost is None:
        inv_cost = get_or_create_inventory_cost(locked_product, branch=branch)
        inv_cost = InventoryCost.objects.select_for_update().get(pk=inv_cost.pk)

    adjustment_cost = quantize_cost(adjustment_cost)
    avg_before = inv_cost.avg_unit_cost
    current_stock = (
        stock_svc.get_branch_stock_balance(locked_product, branch)
        if branch is not None else locked_product.stock
    )
    avg_after = moving_average_cost(current_stock, avg_before, qty, adjustment_cost)

    inv_cost.avg_unit_cost = avg_after
    inv_cost.save(update_fields=['avg_unit_cost', 'updated_at'])
    Product.objects.filter(pk=locked_product.pk).update(cost=quantize_money(avg_after))

    InventoryCostMovement.objects.create(
        tenant=locked_product.tenant, product=locked_product, inventory_cost=inv_cost,
        quantity_before=current_stock, quantity_received=qty,
        unit_cost_received=adjustment_cost, avg_cost_before=avg_before, avg_cost_after=avg_after,
        source_document_type=source_document_type, source_document_id=source_document_id,
        actor_user=actor_user, note=note,
    )
    return inv_cost


def get_cost_for_sale(product: Product, branch=None) -> Decimal:
    """The current average cost, for a sale line to snapshot. Read-only —
    never updates `InventoryCost`; a sale consumes the average, it does not
    change it. `branch=None` reads the tenant-wide row (unchanged pre-
    Sprint-5 behavior); a real `branch` reads that branch's own average,
    falling back through `get_or_create_inventory_cost`'s seed chain if the
    branch has no purchase history yet for this product."""
    return get_or_create_inventory_cost(product, branch=branch).avg_unit_cost


def get_cost_for_return(product: Product, branch=None) -> Decimal:
    """The current average cost, for a return line to snapshot. Read-only,
    identical to `get_cost_for_sale` today — kept as a distinct name because
    a purchase return should eventually be valued at the ORIGINAL purchase
    line's cost snapshot (not the live average, which may have moved since),
    while a sale return uses the current average like a sale does. Neither
    return document exists yet (no PurchaseReturn/SalesReturn model) — this
    function is a placeholder read accessor so that future work slots in
    without touching the costing engine itself."""
    return get_or_create_inventory_cost(product, branch=branch).avg_unit_cost


__all__ = [
    'CostingError', 'quantize_cost', 'quantize_money', 'moving_average_cost',
    'get_or_create_inventory_cost', 'initialize_inventory_cost',
    'apply_purchase_receipt', 'update_cost_from_adjustment',
    'get_cost_for_sale', 'get_cost_for_return',
]
