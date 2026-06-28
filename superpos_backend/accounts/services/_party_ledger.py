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
from django.db.models import Sum
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
    actor_user=None,
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
    if actor_user is not None:
        qs = qs.filter(actor_user=actor_user)
    if occurred_from is not None:
        qs = qs.filter(occurred_at__gte=occurred_from)
    if occurred_to is not None:
        qs = qs.filter(occurred_at__lte=occurred_to)
    return qs.order_by('id')


def opening_balance_for_window(*, first_row, fallback, party_qs, occurred_from):
    """Compute the opening balance for a statement window.

    Mirrors `account_movements._opening_balance_for_window` so AR/AP/finance
    statements all use identical logic. Preference:
        1. `first_row.balance_before` (post-hardening rows store this)
        2. `balance_after` of the latest row *before* the window
        3. `fallback` (party.opening_balance)
    """
    if first_row is not None and first_row.balance_before is not None:
        return first_row.balance_before
    if occurred_from is not None:
        prior = (
            party_qs
            .filter(occurred_at__lt=occurred_from)
            .order_by('-id')
            .values_list('balance_after', flat=True)
            .first()
        )
        if prior is not None:
            return prior
    return fallback


def statement_summary(
    *,
    qs,
    party,
    opening_balance: Decimal,
    asset: bool,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    actor_user=None,
    occurred_from=None,
    occurred_to=None,
):
    """Generic statement-summary builder for party ledgers.

    `qs` is the already-filtered movement queryset, `opening_balance` is
    the resolved start-of-window balance, and `asset` flips the
    `net_change` sign rule (True for AR, False for AP).
    """
    last_row = qs.order_by('id').last()
    closing_balance = (
        last_row.balance_after if last_row is not None else opening_balance
    )

    totals = qs.aggregate(
        total_debit=Sum('debit'),
        total_credit=Sum('credit'),
    )
    total_debit  = totals['total_debit']  or Decimal('0.00')
    total_credit = totals['total_credit'] or Decimal('0.00')
    net_change = (
        (total_debit - total_credit) if asset
        else (total_credit - total_debit)
    )

    return {
        'opening_balance': opening_balance,
        'total_debit':     total_debit,
        'total_credit':    total_credit,
        'net_change':      net_change,
        'closing_balance': closing_balance,
        'date_from':       occurred_from,
        'date_to':         occurred_to,
        'filters': {
            'branch':               branch.id if branch is not None else None,
            'movement_type':        movement_type,
            'source_document_type': source_document_type,
            'source_document_id':   source_document_id,
            'actor_user':           actor_user.id if actor_user is not None else None,
        },
        'movements':       qs,
    }


def now():
    return timezone.now()
