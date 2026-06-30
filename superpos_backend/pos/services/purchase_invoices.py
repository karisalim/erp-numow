"""Purchase Invoice posting service (Phase 1.5 Slice H).

Posts a real PurchaseInvoice for STOCK-ITEM lines only. One atomic
transaction performs every effect; any failure rolls all of them back:

    1. PurchaseInvoice + PurchaseInvoiceLine document rows.
    2. Per stock line:
         * Product.cost updated to the weighted moving-average cost
           (FLOW_v3_6 §7.1 formula) using the stock/cost BEFORE the
           increase. `Product.cost` is used as the moving-average field
           because ProductUnit.avg_cost does not exist yet (out of scope).
         * StockMovement PURCHASE_IN via `pos.services.stock_movements`,
           warehouse-aware, linked by source_document_type='purchase_invoice'.
    3. If paid_amount > 0: FinancialAccountMovement CREDIT on the source
       account (asset → balance decreases; cash/bank leaves). Reuses
       `accounts.services.account_movements`.
    4. If credit_amount > 0: SupplierAPMovement CREDIT (liability → balance
       increases; we owe the supplier more). Reuses
       `accounts.services.supplier_ap`.

Accounting scope notes (intentional for this slice):
    * No Inventory GL FinancialAccountMovement — inventory is tracked by
      StockMovement quantity + Product.cost. The purchase's debit side is
      stock value, not a GL row. Full double-entry inventory is a later slice.
    * tax_amount / tax_total are stored but NOT posted to any tax ledger —
      v3.6 leaves purchase-tax accounting undefined.
    * Only line_type='stock_item' is accepted; other types raise.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounts.services import account_movements as fa
from accounts.services import supplier_ap as ap
from pos.models import (
    BranchWarehouse, Product, PurchaseInvoice, PurchaseInvoiceLine, Warehouse,
)
from pos.services import stock_movements as stock


_CENTS = Decimal('0.01')


class PurchaseInvoiceError(Exception):
    """Service-level rule violation. The serializer/view turns this into a 400."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _qty(value) -> Decimal:
    return Decimal(str(value))


def _same_tenant(obj, tenant, label: str) -> None:
    if obj is not None and obj.tenant_id != tenant.id:
        raise PurchaseInvoiceError(f'{label} must belong to the same tenant')


def moving_average_cost(current_stock, current_cost, qty, unit_cost) -> Decimal:
    """Weighted moving-average cost after receiving `qty` at `unit_cost`.

    new_cost = (current_stock × current_cost + qty × unit_cost)
               ÷ (current_stock + qty)

    Falls back to `unit_cost` when the resulting denominator is <= 0 (e.g.
    the product was oversold to a negative balance) so we never divide by
    zero or carry a nonsensical average.
    """
    current_stock = Decimal(str(current_stock or 0))
    current_cost  = Decimal(str(current_cost or 0))
    qty           = Decimal(str(qty))
    unit_cost     = Decimal(str(unit_cost))

    denom = current_stock + qty
    if denom <= 0:
        return unit_cost.quantize(_CENTS, rounding=ROUND_HALF_UP)
    new_cost = (current_stock * current_cost + qty * unit_cost) / denom
    return new_cost.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _resolve_line_warehouse(*, tenant, branch, line: dict) -> Warehouse:
    """Return the warehouse a stock line lands in.

    Uses the explicit `warehouse` when supplied (tenant-checked), otherwise
    resolves the branch's default active BranchWarehouse with
    role=purchase_receiving. Raises when neither is available.
    """
    warehouse = line.get('warehouse')
    if warehouse is not None:
        _same_tenant(warehouse, tenant, 'warehouse')
        return warehouse

    link = (
        BranchWarehouse.objects
        .filter(
            tenant=tenant, branch=branch,
            role=BranchWarehouse.Role.PURCHASE_RECEIVING,
            is_default=True, is_active=True,
        )
        .select_related('warehouse')
        .first()
    )
    if link is None or link.warehouse_id is None:
        raise PurchaseInvoiceError(
            'no warehouse provided and no default purchase_receiving '
            'warehouse is configured for this branch',
        )
    return link.warehouse


# ── Posting ───────────────────────────────────────────────────────────────────

@transaction.atomic
def post_purchase_invoice(
    *,
    tenant,
    branch,
    supplier,
    lines,
    payment_method=None,
    source_account=None,
    paid_amount=Decimal('0'),
    reference: str = '',
    notes: str = '',
    actor_user=None,
    occurred_at=None,
) -> PurchaseInvoice:
    """Create and post a stock-item PurchaseInvoice. Returns the invoice.

    `lines` is a list of dicts: product, qty, unit_cost, line_type, and
    optional warehouse / discount_amount / tax_amount / notes.
    """
    if not lines:
        raise PurchaseInvoiceError('at least one line is required')

    # ── Tenant ownership (defensive; serializer scopes querysets too) ──
    _same_tenant(branch, tenant, 'branch')
    _same_tenant(supplier, tenant, 'supplier')
    _same_tenant(payment_method, tenant, 'payment_method')
    _same_tenant(source_account, tenant, 'source_account')

    when = occurred_at or timezone.now()

    # ── Validate lines + compute totals ──
    subtotal = discount_total = tax_total = total_amount = Decimal('0.00')
    prepared = []
    for raw in lines:
        line_type = raw.get('line_type') or PurchaseInvoiceLine.LineType.STOCK_ITEM
        if line_type != PurchaseInvoiceLine.LineType.STOCK_ITEM:
            raise PurchaseInvoiceError(
                f"line_type '{line_type}' is out of scope in this slice "
                f"(only 'stock_item' is accepted)",
            )

        product = raw.get('product')
        if product is None:
            raise PurchaseInvoiceError('stock_item line requires a product')
        _same_tenant(product, tenant, 'product')

        qty       = _qty(raw['qty'])
        unit_cost = _money(raw['unit_cost'])
        discount  = _money(raw.get('discount_amount', 0))
        tax       = _money(raw.get('tax_amount', 0))

        if qty <= 0:
            raise PurchaseInvoiceError('qty must be > 0')
        if unit_cost < 0:
            raise PurchaseInvoiceError('unit_cost must be >= 0')
        if discount < 0 or tax < 0:
            raise PurchaseInvoiceError('discount_amount and tax_amount must be >= 0')

        line_subtotal = (qty * unit_cost).quantize(_CENTS, rounding=ROUND_HALF_UP)
        line_total    = line_subtotal - discount + tax

        warehouse = _resolve_line_warehouse(
            tenant=tenant, branch=branch, line=raw,
        )

        subtotal       += line_subtotal
        discount_total += discount
        tax_total      += tax
        total_amount   += line_total

        prepared.append({
            'product': product, 'warehouse': warehouse, 'line_type': line_type,
            'qty': qty, 'unit_cost': unit_cost, 'discount_amount': discount,
            'tax_amount': tax, 'line_total': line_total,
            'notes': raw.get('notes', '') or '',
        })

    paid = _money(paid_amount)
    if paid < 0:
        raise PurchaseInvoiceError('paid_amount must be >= 0')
    if paid > total_amount:
        raise PurchaseInvoiceError('paid_amount cannot exceed total_amount')
    if paid > 0 and source_account is None:
        raise PurchaseInvoiceError('source_account is required when paid_amount > 0')

    credit_amount = total_amount - paid

    if paid <= 0:
        payment_status = PurchaseInvoice.PaymentStatus.UNPAID
    elif paid >= total_amount:
        payment_status = PurchaseInvoice.PaymentStatus.PAID
    else:
        payment_status = PurchaseInvoice.PaymentStatus.PARTIALLY_PAID

    # ── Document header ──
    invoice = PurchaseInvoice.objects.create(
        tenant=tenant,
        branch=branch,
        supplier=supplier,
        reference=reference or '',
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total_amount=total_amount,
        paid_amount=paid,
        credit_amount=credit_amount,
        payment_method=payment_method,
        source_account=source_account,
        posting_status=PurchaseInvoice.PostingStatus.POSTED,
        payment_status=payment_status,
        posted_at=when,
        actor_user=actor_user,
        notes=notes or '',
    )

    # ── Lines + stock effects ──
    for p in prepared:
        PurchaseInvoiceLine.objects.create(
            tenant=tenant,
            purchase_invoice=invoice,
            product=p['product'],
            warehouse=p['warehouse'],
            line_type=p['line_type'],
            qty=p['qty'],
            unit_cost=p['unit_cost'],
            discount_amount=p['discount_amount'],
            tax_amount=p['tax_amount'],
            line_total=p['line_total'],
            notes=p['notes'],
        )

        # Moving-average cost BEFORE the stock increase, under a row lock so a
        # concurrent purchase/sale can't race the valuation. record_stock_in
        # re-locks the same row in this transaction and applies the +qty.
        locked = Product.objects.select_for_update().get(pk=p['product'].pk)
        new_cost = moving_average_cost(
            locked.stock, locked.cost, p['qty'], p['unit_cost'],
        )
        Product.objects.filter(pk=locked.pk).update(cost=new_cost)

        stock.record_stock_in(
            product=locked,
            quantity=p['qty'],
            movement_type=stock.StockMovement.MovementType.PURCHASE_IN,
            branch=branch,
            warehouse=p['warehouse'],
            source_document_type='purchase_invoice',
            source_document_id=invoice.id,
            actor_user=actor_user,
            note=f'Purchase invoice #{invoice.id}',
        )

    # ── Finance effect: paid amount leaves the source cash/bank account ──
    if paid > 0:
        fa.record_account_credit(
            account=source_account,
            amount=paid,
            movement_type=fa.MovementType.PURCHASE_OUT,
            branch=branch,
            source_document_type='purchase_invoice',
            source_document_id=invoice.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=reference or '',
        )

    # ── AP effect: unpaid amount increases what we owe the supplier ──
    if credit_amount > 0:
        ap.record_supplier_ap_credit(
            supplier=supplier,
            amount=credit_amount,
            movement_type=ap.MovementType.PURCHASE_CREDIT,
            branch=branch,
            source_document_type='purchase_invoice',
            source_document_id=invoice.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=reference or '',
        )

    return invoice


__all__ = [
    'PurchaseInvoiceError',
    'moving_average_cost',
    'post_purchase_invoice',
]
