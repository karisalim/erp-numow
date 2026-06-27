"""Customer AR ledger writes + balance reads.

Implements MASTER_DATA_CONTRACT.md §6.3 (CustomerARMovement) and
DOMAIN.md §12.1 (Customer AR Rule). Customer AR is asset-like:

    debit  → increases customer balance (customer owes more)
    credit → decreases customer balance (customer paid or settled)

`opening_balance` from the Customer master record is treated as the
starting balance for the very first movement — the service reads it
when no prior movement exists.

This slice does NOT create receipt or sales-invoice documents. It only
records movement rows. Callers (the future posting engine) supply
`source_document_type` / `source_document_id` so the row can be
traced back to whatever caused it.

Concurrency: each write is wrapped in `transaction.atomic` + row-level
locks on the Customer and the latest movement, so two concurrent
posts to the same customer serialize cleanly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import QuerySet

from accounts.models import Customer, CustomerARMovement
from accounts.services import _party_ledger as _l


# Public alias of the model's movement-type enum.
MovementType = CustomerARMovement.MovementType


# Re-export the shared exception so callers don't reach into the private module.
class CustomerARError(_l.PartyLedgerError):
    """Service-level AR rule violation."""


# ── Reads ────────────────────────────────────────────────────────────────────

def get_customer_balance(customer: Customer) -> Decimal:
    """Latest known balance for `customer`.

    Reads `balance_after` of the newest movement (by id), falling back to
    `customer.opening_balance` when no movement exists yet.
    """
    latest = (
        CustomerARMovement.objects
        .filter(customer=customer)
        .order_by('-id')
        .values_list('balance_after', flat=True)
        .first()
    )
    if latest is not None:
        return latest
    return customer.opening_balance or Decimal('0.00')


def get_customer_statement(
    customer: Customer,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    occurred_from=None,
    occurred_to=None,
) -> QuerySet[CustomerARMovement]:
    """Filtered, tenant-scoped statement for one customer."""
    qs = CustomerARMovement.objects.filter(
        tenant=customer.tenant, customer=customer,
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
def record_customer_ar_movement(
    *,
    customer: Customer,
    movement_type: str,
    debit=Decimal('0'),
    credit=Decimal('0'),
    branch=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    occurred_at=None,
    notes: str = '',
) -> CustomerARMovement:
    """Append one movement row to `customer` and return it.

    Validates: amounts non-negative, exactly one side > 0, branch tenant
    matches customer tenant. Uses `select_for_update` on Customer + the
    latest CustomerARMovement row so concurrent writes don't race.
    """
    try:
        debit  = _l.coerce_amount(debit)
        credit = _l.coerce_amount(credit)
        _l.validate_pair(debit, credit)
        _l.validate_branch_tenant(customer, branch)
    except _l.PartyLedgerError as exc:
        # Re-raise under the public AR exception for clean catch-by-type.
        raise CustomerARError(str(exc)) from exc

    locked_customer, latest_balance = _l.lock_and_latest_balance(
        party_model=Customer,
        party_pk=customer.pk,
        movement_model=CustomerARMovement,
        party_field='customer_id',
    )
    new_balance = latest_balance + _l.asset_delta(debit, credit)

    return CustomerARMovement.objects.create(
        tenant=locked_customer.tenant,
        branch=branch,
        customer=locked_customer,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        movement_type=movement_type,
        debit=debit,
        credit=credit,
        balance_after=new_balance,
        currency='',  # No per-customer currency yet — tenant-wide default later.
        actor_user=actor_user,
        occurred_at=occurred_at or _l.now(),
        notes=notes,
    )


def record_customer_ar_debit(*, customer, amount, movement_type, **kwargs):
    """Sugar: post a debit-only movement (customer owes more)."""
    return record_customer_ar_movement(
        customer=customer, debit=amount, credit=Decimal('0'),
        movement_type=movement_type, **kwargs,
    )


def record_customer_ar_credit(*, customer, amount, movement_type, **kwargs):
    """Sugar: post a credit-only movement (customer paid / settled)."""
    return record_customer_ar_movement(
        customer=customer, debit=Decimal('0'), credit=amount,
        movement_type=movement_type, **kwargs,
    )


__all__ = [
    'CustomerARError',
    'MovementType',
    'get_customer_balance',
    'get_customer_statement',
    'record_customer_ar_movement',
    'record_customer_ar_debit',
    'record_customer_ar_credit',
]
