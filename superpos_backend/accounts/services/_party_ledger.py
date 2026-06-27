"""Private helpers shared by customer_ar.py and supplier_ap.py.

Both AR (asset) and AP (liability) ledgers share identical validation,
locking, and balance-arithmetic semantics — only the sign rule differs.
Centralising that here keeps the public service modules thin and any
future ledger (employee advances, partner equity, …) trivially correct
by parameterizing direction.

The leading underscore in the filename signals: do **not** import from
this module outside `accounts.services.*`. Use the public service APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Type

from django.db import models, transaction
from django.utils import timezone


class PartyLedgerError(Exception):
    """Service-level rule violation. Translate to 400 in views."""


# ── Coercion + validation ────────────────────────────────────────────────────

def coerce_amount(value) -> Decimal:
    """Coerce numeric input to a Decimal; reject negatives."""
    d = Decimal(str(value))
    if d < 0:
        raise PartyLedgerError('debit/credit must be >= 0')
    return d


def validate_pair(debit: Decimal, credit: Decimal) -> None:
    if debit > 0 and credit > 0:
        raise PartyLedgerError('debit and credit cannot both be positive')
    if debit == 0 and credit == 0:
        raise PartyLedgerError('debit and credit cannot both be zero')


def validate_branch_tenant(party, branch) -> None:
    if branch is None:
        return
    if branch.tenant_id != party.tenant_id:
        raise PartyLedgerError(
            'branch and party must belong to the same tenant',
        )


# ── Sign rule ────────────────────────────────────────────────────────────────

def asset_delta(debit: Decimal, credit: Decimal) -> Decimal:
    """For asset-like party ledgers (Customer AR): debit ↑, credit ↓."""
    return debit - credit


def liability_delta(debit: Decimal, credit: Decimal) -> Decimal:
    """For liability-like party ledgers (Supplier AP): credit ↑, debit ↓."""
    return credit - debit


# ── Balance + locking ────────────────────────────────────────────────────────

def lock_and_latest_balance(
    *,
    party_model: Type[models.Model],
    party_pk: int,
    movement_model: Type[models.Model],
    party_field: str,
    opening_attr: str = 'opening_balance',
):
    """Take a row-level lock on the party + latest movement.

    Returns `(locked_party, latest_balance_or_opening)`.

    Held inside `transaction.atomic()` by the caller. Two concurrent
    writers to the same party serialize cleanly via the lock so the
    running balance stays monotonic.
    """
    locked = party_model.objects.select_for_update().get(pk=party_pk)
    latest = (
        movement_model.objects
        .select_for_update()
        .filter(**{party_field: locked.pk})
        .order_by('-id')
        .values_list('balance_after', flat=True)
        .first()
    )
    if latest is None:
        latest = getattr(locked, opening_attr, None) or Decimal('0.00')
    return locked, latest


# ── Generic statement filter ─────────────────────────────────────────────────

def filter_statement(
    qs,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    occurred_from=None,
    occurred_to=None,
):
    """Apply the standard set of filters to a movement queryset."""
    if branch is not None:
        qs = qs.filter(branch=branch)
    if movement_type:
        qs = qs.filter(movement_type=movement_type)
    if source_document_type:
        qs = qs.filter(source_document_type=source_document_type)
    if source_document_id is not None:
        qs = qs.filter(source_document_id=source_document_id)
    if occurred_from is not None:
        qs = qs.filter(occurred_at__gte=occurred_from)
    if occurred_to is not None:
        qs = qs.filter(occurred_at__lte=occurred_to)
    return qs.order_by('id')


def now():
    return timezone.now()
