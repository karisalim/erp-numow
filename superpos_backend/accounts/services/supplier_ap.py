"""Supplier AP ledger writes + balance reads.

Implements MASTER_DATA_CONTRACT.md §6.3 (SupplierAPMovement) and
DOMAIN.md §12.2 (Supplier AP Rule). Supplier AP is liability-like:

    credit → increases supplier balance (we owe more)
    debit  → decreases supplier balance (we paid or returned)

`opening_balance` from the Supplier master record is treated as the
starting balance for the very first movement.

This slice does NOT create supplier-payment or purchase-invoice
documents. It only records movement rows. Callers (the future posting
engine) supply `source_document_type` / `source_document_id`.

Concurrency: same `transaction.atomic` + `select_for_update` pattern as
customer_ar.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import QuerySet

from accounts.models import Supplier, SupplierAPMovement
from accounts.services import _party_ledger as _l


# Public alias of the model's movement-type enum.
MovementType = SupplierAPMovement.MovementType


class SupplierAPError(_l.PartyLedgerError):
    """Service-level AP rule violation."""


# ── Reads ────────────────────────────────────────────────────────────────────

def get_supplier_balance(supplier: Supplier) -> Decimal:
    latest = (
        SupplierAPMovement.objects
        .filter(supplier=supplier)
        .order_by('-id')
        .values_list('balance_after', flat=True)
        .first()
    )
    if latest is not None:
        return latest
    return supplier.opening_balance or Decimal('0.00')


def get_supplier_statement(
    supplier: Supplier,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    actor_user=None,
    occurred_from=None,
    occurred_to=None,
) -> QuerySet[SupplierAPMovement]:
    qs = SupplierAPMovement.objects.filter(
        tenant=supplier.tenant, supplier=supplier,
    )
    return _l.filter_statement(
        qs,
        branch=branch,
        movement_type=movement_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )


def get_supplier_statement_summary(
    supplier: Supplier,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    actor_user=None,
    occurred_from=None,
    occurred_to=None,
) -> dict:
    """Statement metadata + rows for one supplier (AP, liability-like)."""
    qs = get_supplier_statement(
        supplier,
        branch=branch,
        movement_type=movement_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )
    first_row = qs.first()
    party_qs = SupplierAPMovement.objects.filter(
        tenant=supplier.tenant, supplier=supplier,
    )
    opening_balance = _l.opening_balance_for_window(
        first_row=first_row,
        fallback=supplier.opening_balance or Decimal('0.00'),
        party_qs=party_qs,
        occurred_from=occurred_from,
    )
    return _l.statement_summary(
        qs=qs,
        party=supplier,
        opening_balance=opening_balance,
        asset=False,
        branch=branch,
        movement_type=movement_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        actor_user=actor_user,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )


# ── Writes ───────────────────────────────────────────────────────────────────

@transaction.atomic
def record_supplier_ap_movement(
    *,
    supplier: Supplier,
    movement_type: str,
    debit=Decimal('0'),
    credit=Decimal('0'),
    branch=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    occurred_at=None,
    notes: str = '',
) -> SupplierAPMovement:
    try:
        debit  = _l.coerce_amount(debit)
        credit = _l.coerce_amount(credit)
        _l.validate_pair(debit, credit)
        _l.validate_branch_tenant(supplier, branch)
    except _l.PartyLedgerError as exc:
        raise SupplierAPError(str(exc)) from exc

    locked_supplier, latest_balance = _l.lock_and_latest_balance(
        party_model=Supplier,
        party_pk=supplier.pk,
        movement_model=SupplierAPMovement,
        party_field='supplier_id',
    )
    # First-ever movement: `latest_balance` is `supplier.opening_balance`
    # (resolved by `_l.lock_and_latest_balance`). Subsequent movements:
    # `latest_balance` is the previous row's `balance_after`. Either way,
    # it is the right `balance_before` for the row about to be written.
    balance_before = latest_balance
    new_balance    = balance_before + _l.liability_delta(debit, credit)

    # AP rows inherit tenant currency — see customer_ar.py for the
    # rationale. Per-supplier currency lands in a future slice.
    currency = (locked_supplier.tenant.currency or '') if locked_supplier.tenant_id else ''

    return SupplierAPMovement.objects.create(
        tenant=locked_supplier.tenant,
        branch=branch,
        supplier=locked_supplier,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        movement_type=movement_type,
        debit=debit,
        credit=credit,
        balance_before=balance_before,
        balance_after=new_balance,
        currency=currency,
        actor_user=actor_user,
        occurred_at=occurred_at or _l.now(),
        notes=notes,
    )


def record_supplier_ap_debit(*, supplier, amount, movement_type, **kwargs):
    """Sugar: post a debit-only movement (we paid / returned)."""
    return record_supplier_ap_movement(
        supplier=supplier, debit=amount, credit=Decimal('0'),
        movement_type=movement_type, **kwargs,
    )


def record_supplier_ap_credit(*, supplier, amount, movement_type, **kwargs):
    """Sugar: post a credit-only movement (we owe more)."""
    return record_supplier_ap_movement(
        supplier=supplier, debit=Decimal('0'), credit=amount,
        movement_type=movement_type, **kwargs,
    )


__all__ = [
    'SupplierAPError',
    'MovementType',
    'get_supplier_balance',
    'get_supplier_statement',
    'get_supplier_statement_summary',
    'record_supplier_ap_movement',
    'record_supplier_ap_debit',
    'record_supplier_ap_credit',
]
