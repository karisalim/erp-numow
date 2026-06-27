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
    new_balance = latest_balance + _l.liability_delta(debit, credit)

    return SupplierAPMovement.objects.create(
        tenant=locked_supplier.tenant,
        branch=branch,
        supplier=locked_supplier,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        movement_type=movement_type,
        debit=debit,
        credit=credit,
        balance_after=new_balance,
        currency='',
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
    'record_supplier_ap_movement',
    'record_supplier_ap_debit',
    'record_supplier_ap_credit',
]
