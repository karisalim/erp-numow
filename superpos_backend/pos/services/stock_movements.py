"""Append-only stock-ledger writes + balance reads for `pos.Product`.

Wraps the existing `pos.StockMovement` model (no duplicate table) and the
additive `source_document_*` / `actor_user` columns added in
`pos/migrations/0015`. Future posting code (sales, purchases, open-order
sends, recipe consumption, returns, adjustments, …) should land here so
the running stock balance is always derived from movements, not from the
cached `Product.stock` field.

Sign convention:
    * `quantity` passed to `record_stock_in` / `record_stock_out` is
      **always positive**. Direction is encoded by `movement_type`:
        IN  → PURCHASE_IN, RECEIVE_IN, RETURN_IN
        OUT → SALE_OUT, ADJUSTMENT (when reducing)
    * Stored `StockMovement.qty` is non-negative; callers reading the
      ledger must consult `movement_type` to decide the sign.

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

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from pos.models import Product, StockMovement


class StockMovementError(Exception):
    """Service-level rule violation. Caller translates to a 400 in views."""


# Direction routing. Lets callers pass a friendly `direction='in'/'out'`
# but the real classification is the movement_type the row carries.
_IN_TYPES  = {
    StockMovement.MovementType.PURCHASE_IN,
    StockMovement.MovementType.RECEIVE_IN,
    StockMovement.MovementType.RETURN_IN,
}
_OUT_TYPES = {
    StockMovement.MovementType.SALE_OUT,
    StockMovement.MovementType.ADJUSTMENT,   # ADJUSTMENT can be either; treated as OUT here
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


# ── Writes ───────────────────────────────────────────────────────────────────

@transaction.atomic
def record_stock_in(
    *,
    product: Product,
    quantity,
    movement_type: str = StockMovement.MovementType.RECEIVE_IN,
    branch=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    note: str = '',
) -> StockMovement:
    """Add stock for `product`. Updates the cached `Product.stock` too.

    `movement_type` must be one of PURCHASE_IN / RECEIVE_IN / RETURN_IN —
    the function validates this so a caller can't accidentally log a
    SALE_OUT as an "in" movement.
    """
    if movement_type not in _IN_TYPES:
        raise StockMovementError(
            f'movement_type {movement_type!r} is not an IN movement',
        )
    qty = _coerce_qty(quantity)
    _ensure_branch_tenant(product, branch)

    locked = Product.objects.select_for_update().get(pk=product.pk)
    locked.stock = (locked.stock or Decimal('0')) + qty
    locked.save(update_fields=['stock', 'updated_at'])

    return StockMovement.objects.create(
        tenant=locked.tenant,
        product=locked,
        branch=branch,
        qty=qty,
        movement_type=movement_type,
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
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    note: str = '',
) -> StockMovement:
    """Remove stock for `product`. Stock may go negative — caller (or a
    future posting layer with Negative Stock Control settings) decides
    whether that's allowed."""
    if movement_type not in _OUT_TYPES:
        raise StockMovementError(
            f'movement_type {movement_type!r} is not an OUT movement',
        )
    qty = _coerce_qty(quantity)
    _ensure_branch_tenant(product, branch)

    locked = Product.objects.select_for_update().get(pk=product.pk)
    locked.stock = (locked.stock or Decimal('0')) - qty
    locked.save(update_fields=['stock', 'updated_at'])

    return StockMovement.objects.create(
        tenant=locked.tenant,
        product=locked,
        branch=branch,
        qty=qty,
        movement_type=movement_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        note=note,
    )


# ── Reads ────────────────────────────────────────────────────────────────────

def get_product_stock_balance(product: Product, *, branch=None) -> Decimal:
    """Derive current stock from the StockMovement ledger.

    Sum of in-direction qty minus sum of out-direction qty. Always
    tenant-scoped via `product.tenant`. Pass `branch` for a per-branch
    sub-balance.
    """
    qs = StockMovement.objects.filter(tenant=product.tenant, product=product)
    if branch is not None:
        qs = qs.filter(branch=branch)

    inflow = Decimal('0')
    outflow = Decimal('0')
    for row in qs.values('movement_type', 'qty'):
        if row['movement_type'] in _IN_TYPES:
            inflow += row['qty']
        elif row['movement_type'] in _OUT_TYPES:
            outflow += row['qty']
    return inflow - outflow


def get_product_stock_statement(
    product: Product,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
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
    if occurred_from is not None:
        qs = qs.filter(created_at__gte=occurred_from)
    if occurred_to is not None:
        qs = qs.filter(created_at__lte=occurred_to)
    return qs.order_by('id')


__all__ = [
    'StockMovementError',
    'record_stock_in',
    'record_stock_out',
    'get_product_stock_balance',
    'get_product_stock_statement',
]
