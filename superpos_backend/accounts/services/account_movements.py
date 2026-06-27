"""Append-only ledger writes + balance reads for `FinancialAccount`.

Implements MASTER_DATA_CONTRACT.md §6 (Universal Movement / Statement
Contracts). All posting code (sales, purchases, customer receipts,
supplier payments, cash drops, expenses, etc.) should land here in Phase
1.5+ — the API surface deliberately exposes only reads.

Sign convention — see `FinancialAccountMovement` docstring:
    * For asset-like accounts:
      cashbox, main_safe, bank, card_settlement, wallet, customer_ar,
      expense, opening_balance, other
      → debit increases balance, credit decreases balance.
    * For liability-like accounts:
      supplier_ap
      → credit increases balance, debit decreases balance.

Adding a new "liability" account_type later is a one-line change in
`_LIABILITY_TYPES` below — every caller stays correct.

Concurrency:
    `_lock_account_row` runs inside an atomic block and takes a row-level
    lock on the FinancialAccount, then reads the latest movement under
    that lock. Two concurrent posts to the same account serialize cleanly
    and the running balance stays monotonic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import FinancialAccount, FinancialAccountMovement


# Account types whose balance INCREASES on credit (liability-like).
_LIABILITY_TYPES = frozenset({
    FinancialAccount.AccountType.SUPPLIER_AP,
})

# Public alias of the model's movement-type enum so callers don't have to
# import the model directly.
MovementType = FinancialAccountMovement.MovementType


class AccountMovementError(Exception):
    """Raised for any service-level rule violation.

    Catch in views to translate to a 400. The DB CHECK constraints catch
    the same issues at the storage layer, but raising early gives callers
    a clean Python exception with a useful message.
    """


@dataclass(frozen=True)
class _PostInput:
    account: FinancialAccount
    debit:   Decimal
    credit:  Decimal


# ── Sign rule ────────────────────────────────────────────────────────────────

def balance_delta(account: FinancialAccount, debit: Decimal, credit: Decimal) -> Decimal:
    """Signed delta applied to `account.balance` for this movement.

    Centralizes the asset-vs-liability rule. Re-used by `get_account_current_balance`
    and by every service-layer writer below.
    """
    if account.account_type in _LIABILITY_TYPES:
        return credit - debit
    return debit - credit


# ── Validation helpers ───────────────────────────────────────────────────────

def _coerce(value) -> Decimal:
    """Coerce numeric input to a 2-place Decimal; reject negatives."""
    d = Decimal(str(value))
    if d < 0:
        raise AccountMovementError('debit/credit must be >= 0')
    return d


def _validate_pair(debit: Decimal, credit: Decimal) -> None:
    if debit > 0 and credit > 0:
        raise AccountMovementError('debit and credit cannot both be positive')
    if debit == 0 and credit == 0:
        raise AccountMovementError('debit and credit cannot both be zero')


def _validate_account_branch(account: FinancialAccount, branch) -> None:
    if branch is None:
        return
    if branch.tenant_id != account.tenant_id:
        raise AccountMovementError(
            'branch and account must belong to the same tenant',
        )


# ── Reads ────────────────────────────────────────────────────────────────────

def get_account_current_balance(account: FinancialAccount) -> Decimal:
    """Return the latest known balance for `account`.

    Reads `balance_after` of the newest movement (ordered by id), falling
    back to `opening_balance` when no movement exists yet. Cheap (single
    indexed lookup) so callers can use it freely in reports.
    """
    latest = (
        FinancialAccountMovement.objects
        .filter(account=account)
        .order_by('-id')
        .values_list('balance_after', flat=True)
        .first()
    )
    if latest is not None:
        return latest
    return account.opening_balance or Decimal('0.00')


def get_account_statement(
    account: FinancialAccount,
    *,
    branch=None,
    movement_type: Optional[str] = None,
    source_document_type: Optional[str] = None,
    source_document_id:   Optional[int] = None,
    occurred_from=None,
    occurred_to=None,
) -> QuerySet[FinancialAccountMovement]:
    """Filtered, tenant-scoped statement for one account.

    Returns a queryset (not a list) so the caller can paginate it. The
    `branch` filter is *additional* — passing it does not lift the
    tenant scope already implied by `account.tenant`.
    """
    qs = FinancialAccountMovement.objects.filter(
        tenant=account.tenant, account=account,
    )
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


# ── Writes ───────────────────────────────────────────────────────────────────

def _lock_and_latest_balance(account_pk: int, opening_balance: Decimal) -> tuple:
    """Take a row-level lock on the account, return (locked_account, latest_balance)."""
    locked = FinancialAccount.objects.select_for_update().get(pk=account_pk)
    latest = (
        FinancialAccountMovement.objects
        .select_for_update()
        .filter(account_id=locked.pk)
        .order_by('-id')
        .values_list('balance_after', flat=True)
        .first()
    )
    if latest is None:
        latest = locked.opening_balance or opening_balance or Decimal('0.00')
    return locked, latest


@transaction.atomic
def record_account_movement(
    *,
    account: FinancialAccount,
    movement_type: str,
    debit=Decimal('0'),
    credit=Decimal('0'),
    branch=None,
    source_document_type: str = '',
    source_document_id: Optional[int] = None,
    actor_user=None,
    terminal_id: Optional[int] = None,
    shift_id:    Optional[int] = None,
    occurred_at=None,
    notes: str = '',
) -> FinancialAccountMovement:
    """Append one movement row to `account` and return it.

    The caller decides the (debit, credit) split; the helpers
    `record_account_debit` / `record_account_credit` are thin sugar around
    this for the common case where only one side is non-zero.

    Validation:
        * exactly one of (debit, credit) > 0
        * both >= 0
        * branch tenant matches account tenant

    Concurrency:
        Runs inside `transaction.atomic`. Takes `select_for_update()` on
        the FinancialAccount row and the latest movement row before
        computing `balance_after` so concurrent writers see a consistent
        snapshot.
    """
    debit  = _coerce(debit)
    credit = _coerce(credit)
    _validate_pair(debit, credit)
    _validate_account_branch(account, branch)

    locked, latest_balance = _lock_and_latest_balance(
        account.pk, account.opening_balance or Decimal('0.00'),
    )
    delta = balance_delta(locked, debit, credit)
    new_balance = latest_balance + delta

    return FinancialAccountMovement.objects.create(
        tenant=locked.tenant,
        branch=branch,
        account=locked,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        movement_type=movement_type,
        debit=debit,
        credit=credit,
        balance_after=new_balance,
        currency=locked.currency,
        actor_user=actor_user,
        terminal_id=terminal_id,
        shift_id=shift_id,
        occurred_at=occurred_at or timezone.now(),
        notes=notes,
    )


def record_account_debit(*, account, amount, movement_type, **kwargs):
    """Sugar: post a debit-only movement."""
    return record_account_movement(
        account=account, debit=amount, credit=Decimal('0'),
        movement_type=movement_type, **kwargs,
    )


def record_account_credit(*, account, amount, movement_type, **kwargs):
    """Sugar: post a credit-only movement."""
    return record_account_movement(
        account=account, debit=Decimal('0'), credit=amount,
        movement_type=movement_type, **kwargs,
    )


__all__ = [
    'AccountMovementError',
    'MovementType',
    'balance_delta',
    'get_account_current_balance',
    'get_account_statement',
    'record_account_movement',
    'record_account_debit',
    'record_account_credit',
]
