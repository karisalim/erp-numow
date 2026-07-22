"""Append-only stock-ledger writes + balance reads for `pos.Product`.

Wraps the existing `pos.StockMovement` model (no duplicate table) and the
additive `source_document_*` / `actor_user` / `quantity_before` /
`quantity_after` columns added in `pos/migrations/0015` + `0016`. Future
posting code (sales, purchases, open-order sends, recipe consumption,
returns, adjustments, …) should land here so the running stock balance
is always derived from movements, not from the cached `Product.stock`
field.

Sign convention:
    * `quantity` passed to `record_stock_in` / `record_stock_out` is
      **always positive**. Direction is encoded by `movement_type`:
        IN  → PURCHASE_IN, RECEIVE_IN, RETURN_IN, ADJUSTMENT (when used in)
        OUT → SALE_OUT, ADJUSTMENT (when used out)
    * Stored `StockMovement.qty` is non-negative when written through this
      service. The legacy serializer-create path may still store negative
      `qty` for SALE_OUT rows; `quantity_in` / `quantity_out` derivations
      use `abs(qty)` to stay safe.

Running ledger (hardening slice):
    Every new movement carries `quantity_before` (the stock level
    immediately before this movement) and `quantity_after`
    (quantity_before + signed delta). The chain is tenant-scoped: the
    first movement starts from the current `Product.stock` baseline,
    subsequent movements chain off the previous row's `quantity_after`.
    Legacy rows without `quantity_after` are tolerated by reads — the
    chain just skips them when computing the next `quantity_before`.

Concurrency:
    `record_stock_*` uses `Product.deduct_stock`-style atomicity via
    `select_for_update()` on the product row so two checkouts can't pass
    a stock check at once. Out-direction does **not** raise on negative
    stock here — that decision belongs to the future posting engine and
    its tenant-level Negative Stock Control settings (DOMAIN.md §15.2).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import models as db_models, transaction
from django.db.models import QuerySet, Sum

from pos.models import BranchWarehouse, Product, StockMovement, WarehouseStock


class StockMovementError(Exception):
    """Service-level rule violation. Caller translates to a 400 in views."""


# Direction routing. Lets callers pass a friendly `direction='in'/'out'`
# but the real classification is the movement_type the row carries.
# Legacy `ADJUSTMENT` lives in both sets (unchanged, pre-hotfix behavior —
# see the model docstring for why it isn't retroactively reclassified).
# `ADJUSTMENT_IN`/`ADJUSTMENT_OUT` (Hotfix Pack) are each in exactly one
# set — no ambiguity for anything written going forward.
_IN_TYPES  = {
    StockMovement.MovementType.PURCHASE_IN,
    StockMovement.MovementType.RECEIVE_IN,
    StockMovement.MovementType.RETURN_IN,
    StockMovement.MovementType.ADJUSTMENT,
    StockMovement.MovementType.ADJUSTMENT_IN,
}
_OUT_TYPES = {
    StockMovement.MovementType.SALE_OUT,
    StockMovement.MovementType.ADJUSTMENT,
    StockMovement.MovementType.ADJUSTMENT_OUT,
}


def _coerce_qty(qty) -> Decimal:
    d = Decimal(str(qty))
    if d <= 0:
        raise StockMovementError('quantity must be > 0')
    return d


def _ensure_branch_tenant(product: Product, branch) -> None:
    if branch is None:
        return
    if branch.tenant_id != product.tenant_id:
        raise StockMovementError(
            'branch and product must belong to the same tenant',
        )


def _ensure_warehouse_tenant(product: Product, warehouse) -> None:
    if warehouse is None:
        return
    if warehouse.tenant_id != product.tenant_id:
        raise StockMovementError(
            'warehouse and product must belong to the same tenant',
        )


def apply_warehouse_delta(*, product: Product, warehouse, delta) -> Optional[WarehouseStock]:
    """Adjust the cached per-warehouse balance for `product` by `delta`.

    No-op (returns None) when `warehouse` is None — legacy / unconfigured
    callers keep the global-only behavior, preserving the invariant
    `Σ WarehouseStock(product) + unassigned == Product.stock`.

    Locks the `WarehouseStock` row (`select_for_update`) so two concurrent
    movements on the same (product, warehouse) can't lose an update. **Never
    touches `Product.stock`** — the caller already updates that exactly once,
    so there is no double counting. Must run inside a transaction (all callers
    already open one).
    """
    if warehouse is None:
        return None
    _ensure_warehouse_tenant(product, warehouse)

    row, _created = (
        WarehouseStock.objects
        .select_for_update()
        .get_or_create(
            tenant=product.tenant, product=product, warehouse=warehouse,
            defaults={'quantity': Decimal('0')},
        )
    )
    row.quantity = (row.quantity or Decimal('0')) + Decimal(str(delta))
    row.save(update_fields=['quantity', 'updated_at'])
    return row


def get_branch_stock_balance(product: Product, branch) -> Decimal:
    """Sum of `WarehouseStock.quantity` across every warehouse actively
    linked to `branch` (any role) for `product` (Sprint 5 Batch 1) — the
    branch-level stock figure the branch-scoped AVCO blend
    (`pos.services.costing`) uses as its `current_stock` input, now that
    D-09 tracks average cost per branch while quantity stays per warehouse.
    Defaults to zero for a branch with no stock history yet for this
    product — a brand-new branch correctly starts from zero, not an error.
    """
    warehouse_ids = (
        BranchWarehouse.objects
        .filter(tenant=product.tenant, branch=branch, is_active=True)
        .values_list('warehouse_id', flat=True)
        .distinct()
    )
    total = (
        WarehouseStock.objects
        .filter(product=product, warehouse_id__in=warehouse_ids)
        .aggregate(total=Sum('quantity'))['total']
    )
    return total or Decimal('0')


def _latest_quantity_after(product: Product) -> Optional[Decimal]:
    """Last `quantity_after` seen for this tenant/product, or None.

    Tenant-wide chain (ignores branch) so the running ledger stays
    consistent with `Product.stock` — which is a global field today. Per-
    branch running totals are reported via the statement summary, but the
    canonical `quantity_before` chain is global to match the source of
    truth in the schema.
    """
    return (
        StockMovement.objects
        .filter(
            tenant=product.tenant, product=product,
            quantity_after__isnull=False,
        )
        .order_by('-id')
        .values_list('quantity_after', flat=True)
        .first()
    )


# ── Writes ───────────────────────────────────────────────────────────────────

@transaction.atomic
def record_stock_in(
    *,
    product: Product,
    quantity,
    movement_type: str = StockMovement.MovementType.RECEIVE_IN,
    branch=None,
    warehouse=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    note: str = '',
) -> StockMovement:
    """Add stock for `product`. Updates the cached `Product.stock` too.

    `movement_type` must be one of PURCHASE_IN / RECEIVE_IN / RETURN_IN /
    ADJUSTMENT — the function validates this so a caller can't accidentally
    log a SALE_OUT as an "in" movement.

    The row stores `quantity_before` (stock at the moment of the lock,
    falling back to `Product.stock` for the very first ledger-tracked
    movement) and `quantity_after` (quantity_before + qty).
    """
    if movement_type not in _IN_TYPES:
        raise StockMovementError(
            f'movement_type {movement_type!r} is not an IN movement',
        )
    qty = _coerce_qty(quantity)
    _ensure_branch_tenant(product, branch)
    _ensure_warehouse_tenant(product, warehouse)

    locked = Product.objects.select_for_update().get(pk=product.pk)

    # `quantity_before` chains off the prior ledger row when one exists,
    # otherwise we anchor to the current Product.stock (the existing
    # source of truth — see module docstring). This keeps legacy and
    # new posts consistent without touching legacy data.
    prior_after = _latest_quantity_after(locked)
    quantity_before = prior_after if prior_after is not None else (
        locked.stock or Decimal('0')
    )
    quantity_after  = quantity_before + qty

    locked.stock = (locked.stock or Decimal('0')) + qty
    locked.save(update_fields=['stock', 'updated_at'])

    # Mirror the increase into the cached per-warehouse balance (no-op when
    # warehouse is None → legacy global-only behavior).
    apply_warehouse_delta(product=locked, warehouse=warehouse, delta=qty)

    return StockMovement.objects.create(
        tenant=locked.tenant,
        product=locked,
        branch=branch,
        warehouse=warehouse,
        qty=qty,
        movement_type=movement_type,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        note=note,
    )


@transaction.atomic
def record_stock_out(
    *,
    product: Product,
    quantity,
    movement_type: str = StockMovement.MovementType.SALE_OUT,
    branch=None,
    warehouse=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    note: str = '',
) -> StockMovement:
    """Remove stock for `product`. Stock may go negative — caller (or a
    future posting layer with Negative Stock Control settings) decides
    whether that's allowed.

    Row stores `quantity_before` and `quantity_after` exactly like
    `record_stock_in` (see its docstring). The delta is subtracted.
    """
    if movement_type not in _OUT_TYPES:
        raise StockMovementError(
            f'movement_type {movement_type!r} is not an OUT movement',
        )
    qty = _coerce_qty(quantity)
    _ensure_branch_tenant(product, branch)
    _ensure_warehouse_tenant(product, warehouse)

    locked = Product.objects.select_for_update().get(pk=product.pk)

    prior_after = _latest_quantity_after(locked)
    quantity_before = prior_after if prior_after is not None else (
        locked.stock or Decimal('0')
    )
    quantity_after  = quantity_before - qty

    locked.stock = (locked.stock or Decimal('0')) - qty
    locked.save(update_fields=['stock', 'updated_at'])

    # Mirror the decrease into the cached per-warehouse balance (no-op when
    # warehouse is None → legacy global-only behavior).
    apply_warehouse_delta(product=locked, warehouse=warehouse, delta=-qty)

    return StockMovement.objects.create(
        tenant=locked.tenant,
        product=locked,
        branch=branch,
        warehouse=warehouse,
        qty=qty,
        movement_type=movement_type,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        note=note,
    )


# ── Reads ────────────────────────────────────────────────────────────────────

def get_product_stock_balance(product: Product, *, branch=None, warehouse=None) -> Decimal:
    """Derive current stock from the StockMovement ledger.

    Sum of in-direction qty minus sum of out-direction qty (uses `abs`
    so legacy negative-qty SALE_OUT rows still subtract correctly).
    Always tenant-scoped via `product.tenant`. Pass `branch` for a
    per-branch sub-balance, or `warehouse` for a per-warehouse sub-balance
    (the movement-derived counterpart of the cached `WarehouseStock`, used
    for reconciliation/verification).
    """
    qs = StockMovement.objects.filter(tenant=product.tenant, product=product)
    if branch is not None:
        qs = qs.filter(branch=branch)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)

    inflow = Decimal('0')
    outflow = Decimal('0')
    for row in qs.values('movement_type', 'qty'):
        magnitude = abs(row['qty'] or Decimal('0'))
        # ADJUSTMENT lives in both sets; routing here treats it as OUT
        # to match the historical `get_product_stock_balance` behavior.
        if row['movement_type'] in _OUT_TYPES:
            outflow += magnitude
        elif row['movement_type'] in _IN_TYPES:
            inflow += magnitude
    return inflow - outflow


def get_product_stock_statement(
    product: Product,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    actor_user=None,
    occurred_from=None,
    occurred_to=None,
) -> QuerySet[StockMovement]:
    """Filtered, tenant-scoped statement for one product.

    Returns a queryset (not a list) so the view can paginate. The
    `created_at` field is used as the time axis since `StockMovement` has
    no separate `occurred_at` field today.
    """
    qs = StockMovement.objects.filter(tenant=product.tenant, product=product)
    if branch is not None:
        qs = qs.filter(branch=branch)
    if movement_type:
        qs = qs.filter(movement_type=movement_type)
    if source_document_type:
        qs = qs.filter(source_document_type=source_document_type)
    if source_document_id is not None:
        qs = qs.filter(source_document_id=source_document_id)
    if actor_user is not None:
        qs = qs.filter(actor_user=actor_user)
    if occurred_from is not None:
        qs = qs.filter(created_at__gte=occurred_from)
    if occurred_to is not None:
        qs = qs.filter(created_at__lte=occurred_to)
    return qs.order_by('id')


def _row_magnitudes(qs):
    """Compute (total_in, total_out) for a stock movement queryset.

    Uses `abs(qty)` so legacy negative-qty SALE_OUT rows still count
    on the right side. Done in Python (not SQL) so the `_IN_TYPES` /
    `_OUT_TYPES` Python sets stay the single source of truth.
    """
    total_in  = Decimal('0')
    total_out = Decimal('0')
    for row in qs.values('movement_type', 'qty'):
        magnitude = abs(row['qty'] or Decimal('0'))
        if row['movement_type'] in _OUT_TYPES:
            total_out += magnitude
        elif row['movement_type'] in _IN_TYPES:
            total_in += magnitude
    return total_in, total_out


def get_product_stock_statement_summary(
    product: Product,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    actor_user=None,
    occurred_from=None,
    occurred_to=None,
) -> dict:
    """Statement metadata + rows for one product.

    Returns a dict with:
        opening_quantity  — quantity_before of the first row in the
                            filtered window. Falls back to "quantity_after
                            of the latest row strictly before the window"
                            when the first row predates the hardening
                            (`quantity_before IS NULL`); falls back further
                            to 0 when no historical data exists.
        total_in          — Σ magnitudes of IN rows in the window
        total_out         — Σ magnitudes of OUT rows in the window
        net_change        — total_in - total_out
        closing_quantity  — quantity_after of the last row, or
                            opening_quantity when the window is empty
        date_from / date_to / filters — echo of the input
        movements         — the underlying queryset (caller serializes it)
    """
    qs = get_product_stock_statement(
        product,
        branch=branch,
        movement_type=movement_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )
    first_row = qs.first()
    last_row  = qs.order_by('id').last()

    opening_quantity = _resolve_opening_quantity(
        product=product, branch=branch,
        first_row=first_row, occurred_from=occurred_from,
    )
    total_in, total_out = _row_magnitudes(qs)
    net_change       = total_in - total_out

    if last_row is not None and last_row.quantity_after is not None:
        closing_quantity = last_row.quantity_after
    else:
        # No hardened row in the window — closing == opening + net_change
        # so the math still reconciles even if individual rows are legacy.
        closing_quantity = opening_quantity + net_change

    return {
        'opening_quantity': opening_quantity,
        'total_in':         total_in,
        'total_out':        total_out,
        'net_change':       net_change,
        'closing_quantity': closing_quantity,
        'date_from':        occurred_from,
        'date_to':          occurred_to,
        'filters': {
            'branch':               branch.id if branch is not None else None,
            'movement_type':        movement_type,
            'source_document_type': source_document_type,
            'source_document_id':   source_document_id,
            'actor_user':           actor_user.id if actor_user is not None else None,
            'product':              product.id,
        },
        'movements':        qs,
    }


def _resolve_opening_quantity(*, product, branch, first_row, occurred_from):
    """Pick the right opening quantity for a stock statement window.

    Order of preference:
        1. `first_row.quantity_before` (hardened rows store this directly)
        2. `quantity_after` of the latest hardened row strictly before
           the window
        3. Sum-based fallback (in - out) of all rows before the window
        4. 0 — no historical data
    """
    if first_row is not None and first_row.quantity_before is not None:
        return first_row.quantity_before

    prior_qs = StockMovement.objects.filter(
        tenant=product.tenant, product=product,
    )
    if branch is not None:
        prior_qs = prior_qs.filter(branch=branch)
    if occurred_from is not None:
        prior_qs = prior_qs.filter(created_at__lt=occurred_from)
    if first_row is not None and occurred_from is None:
        prior_qs = prior_qs.filter(id__lt=first_row.id)

    prior_hardened = (
        prior_qs.filter(quantity_after__isnull=False)
        .order_by('-id')
        .values_list('quantity_after', flat=True)
        .first()
    )
    if prior_hardened is not None:
        return prior_hardened

    # Final fallback: sum magnitudes of *all* prior rows so the
    # statement totals still chain coherently for legacy-only data.
    total_in, total_out = _row_magnitudes(prior_qs)
    return total_in - total_out


__all__ = [
    'StockMovementError',
    'apply_warehouse_delta',
    'record_stock_in',
    'record_stock_out',
    'get_product_stock_balance',
    'get_product_stock_statement',
    'get_product_stock_statement_summary',
]
