"""Purchase Invoice posting service (Phase 1.5 Slice H).

Posts a real PurchaseInvoice for STOCK-ITEM lines only. One atomic
transaction performs every effect; any failure rolls all of them back:

    1. PurchaseInvoice + PurchaseInvoiceLine document rows.
    2. Per stock line:
         * The AVCO average cost is updated via
           `pos.services.costing.apply_purchase_receipt` (Sprint 3 Batch 2)
           — the moving-average math itself, and its `InventoryCost` /
           `InventoryCostMovement` home, live there now; this module no
           longer inlines the formula. `Product.cost` is kept in sync as a
           2dp display mirror by that call (D-07).
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
      StockMovement quantity + InventoryCost. The purchase's debit side is
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
from pos.services import costing as costing_svc
from pos.services import stock_movements as stock
from pos.services import units as units_svc


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


# Backward-compat re-export — the moving-average formula now lives in
# pos.services.costing (Sprint 3 Batch 2), extracted so it has one
# reusable home instead of being inlined in this posting service. Nothing
# outside this module imported the old inline function directly (checked),
# but keep the name importable here as cheap insurance for any caller this
# audit missed.
moving_average_cost = costing_svc.moving_average_cost


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

        unit_cost = _money(raw['unit_cost'])
        discount  = _money(raw.get('discount_amount', 0))
        tax       = _money(raw.get('tax_amount', 0))

        if unit_cost < 0:
            raise PurchaseInvoiceError('unit_cost must be >= 0')
        if discount < 0 or tax < 0:
            raise PurchaseInvoiceError('discount_amount and tax_amount must be >= 0')

        # Sprint 2 Batch 5a: a unit-aware line (`product_unit` +
        # `entered_qty`) is priced per the unit actually purchased in (a
        # carton, say) — `entered_qty` is what money math (line_subtotal,
        # moving-average cost) uses; `qty` becomes the converted BASE
        # quantity, matching every other stock-writing path (R-B). A legacy
        # line keeps `qty`/`unit_cost` sharing one denomination, unchanged.
        product_unit = raw.get('product_unit')
        entered_qty  = raw.get('entered_qty')
        if product_unit is not None:
            _same_tenant(product_unit, tenant, 'product_unit')
            if product_unit.product_id != product.pk:
                raise PurchaseInvoiceError(
                    'product_unit must belong to the same product as this line')
            if entered_qty is None:
                raise PurchaseInvoiceError('entered_qty is required when product_unit is set')
            entered_qty = _qty(entered_qty)
            if entered_qty <= 0:
                raise PurchaseInvoiceError('entered_qty must be > 0')
            if (
                product_unit.minimum_order_qty is not None
                and entered_qty < product_unit.minimum_order_qty
            ):
                raise PurchaseInvoiceError(
                    f'entered_qty ({entered_qty}) is below minimum_order_qty '
                    f'({product_unit.minimum_order_qty}) for this product unit',
                )
            try:
                qty = units_svc.convert_to_base(
                    product=product, qty=entered_qty, product_unit=product_unit,
                )
            except units_svc.UnitConversionError as exc:
                raise PurchaseInvoiceError(str(exc))

            line_subtotal = (entered_qty * unit_cost).quantize(_CENTS, rounding=ROUND_HALF_UP)
        else:
            if raw.get('qty') is None:
                raise PurchaseInvoiceError('qty must be > 0')
            qty = _qty(raw['qty'])
            if qty <= 0:
                raise PurchaseInvoiceError('qty must be > 0')
            line_subtotal = (qty * unit_cost).quantize(_CENTS, rounding=ROUND_HALF_UP)

        # Cost per BASE unit for the moving-average formula — the real
        # ACQUISITION value divided by the real base quantity received
        # (standard weighted-average COGS math), never a price scaled by
        # `conversion_to_base`. Acquisition value nets out the supplier
        # discount (inventory is valued at what was actually paid for it,
        # matching the same net figure the AP/accounting posting below
        # uses for this line) — but never includes `tax`: this system does
        # not model VAT recovery (no purchase-tax ledger account exists —
        # see `pos/models.py`'s PurchaseInvoiceLine note on tax_amount/
        # tax_total), so tax already wasn't part of the cost basis before
        # this fix and stays that way; only the discount term is new here.
        net_line_value = line_subtotal - discount
        moving_avg_unit_cost = (
            (net_line_value / qty).quantize(_CENTS, rounding=ROUND_HALF_UP)
            if qty > 0 else unit_cost
        )

        line_total = line_subtotal - discount + tax

        warehouse = _resolve_line_warehouse(
            tenant=tenant, branch=branch, line=raw,
        )

        subtotal       += line_subtotal
        discount_total += discount
        tax_total      += tax
        total_amount   += line_total

        prepared.append({
            'product': product, 'warehouse': warehouse, 'line_type': line_type,
            'product_unit': product_unit, 'entered_qty': entered_qty,
            'qty': qty, 'unit_cost': unit_cost,
            'moving_avg_unit_cost': moving_avg_unit_cost,
            'discount_amount': discount,
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
            product_unit=p['product_unit'],
            entered_qty=p['entered_qty'],
            qty=p['qty'],
            unit_cost=p['unit_cost'],
            discount_amount=p['discount_amount'],
            tax_amount=p['tax_amount'],
            line_total=p['line_total'],
            notes=p['notes'],
        )

        # Moving-average cost BEFORE the stock increase — costing.apply_
        # purchase_receipt locks Product + InventoryCost itself and blends
        # `moving_avg_unit_cost` in under that lock. record_stock_in below
        # re-locks the same product row in this same transaction and applies
        # the +qty; Postgres allows re-acquiring a row lock already held in
        # the same transaction, so the "cost computed on pre-increase stock,
        # then stock increases" ordering guarantee is unchanged.
        # `moving_avg_unit_cost` is per-BASE-unit (== `unit_cost` for a
        # legacy line; derived from the real line total ÷ real base qty for
        # a unit-aware line) — the average has always been per-base-unit, so
        # blending anything else in would corrupt it.
        costing_svc.apply_purchase_receipt(
            product=p['product'], qty=p['qty'], unit_cost=p['moving_avg_unit_cost'],
            source_document_type='purchase_invoice', source_document_id=invoice.id,
            actor_user=actor_user,
        )
        locked = Product.objects.select_for_update().get(pk=p['product'].pk)

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
