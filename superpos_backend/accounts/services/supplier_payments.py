"""Supplier payment posting service.

Mirror of `customer_receipts.py` for the AP side. Implements
MASTER_DATA_CONTRACT.md §10 (Supplier settlements). A supplier payment is
the *event* in which we pay down (some or all of) an outstanding AP
balance with a supplier. Creating one atomically produces:

    1. A SupplierPayment header row (audit trail / document).
    2. A SupplierAPMovement debit row against the supplier (AP ↓).
    3. A FinancialAccountMovement credit row against the source account
       (cashbox / bank / wallet balance ↓).

All three writes happen inside a single `transaction.atomic` block. If
any one fails, nothing is persisted ("no partial posting").

Compatibility:
    * Source account must be cashbox / main_safe / bank / wallet —
      paying a supplier *out of* a card_settlement (acquirer holding
      account) doesn't model a real-world flow; that money first
      settles to a bank account, and the bank then pays the supplier.
    * Credit-type payment methods are rejected — "paying a supplier on
      credit" means increasing AP, not settling it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounts.models import (
    Branch,
    FinancialAccount,
    PaymentMethod,
    Supplier,
    SupplierPayment,
)
from accounts.services import account_movements as fa
from accounts.services import supplier_ap as ap


class SupplierPaymentError(Exception):
    """Service-level rule violation. Views translate to HTTP 400."""


# Source account types that may *fund* a supplier payment, keyed by the
# payment method's type. Cash methods leave a cashbox; card methods leave
# a card settlement account (rare — usually a refund-to-card scenario);
# wallet methods leave a wallet account.
_METHOD_TO_SRC_ACCOUNT_TYPES = {
    PaymentMethod.MethodType.CASH:   {
        FinancialAccount.AccountType.CASHBOX,
        FinancialAccount.AccountType.MAIN_SAFE,
        FinancialAccount.AccountType.BANK,
    },
    PaymentMethod.MethodType.CARD:   {FinancialAccount.AccountType.BANK},
    PaymentMethod.MethodType.WALLET: {FinancialAccount.AccountType.WALLET},
}


def _validate_inputs(
    *,
    tenant,
    branch: Optional[Branch],
    supplier: Supplier,
    payment_method: PaymentMethod,
    source_account: FinancialAccount,
    amount: Decimal,
) -> None:
    """Reject any cross-tenant / cross-branch / type-mismatched input."""
    if amount is None:
        raise SupplierPaymentError('amount is required')

    try:
        amount_dec = Decimal(str(amount))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise SupplierPaymentError(f'invalid amount: {amount!r}') from exc
    if amount_dec <= 0:
        raise SupplierPaymentError('amount must be > 0')

    if supplier.tenant_id != tenant.id:
        raise SupplierPaymentError('supplier must belong to the caller\'s tenant')
    if payment_method.tenant_id != tenant.id:
        raise SupplierPaymentError('payment_method must belong to the caller\'s tenant')
    if source_account.tenant_id != tenant.id:
        raise SupplierPaymentError('source_account must belong to the caller\'s tenant')

    if branch is not None and branch.tenant_id != tenant.id:
        raise SupplierPaymentError('branch must belong to the caller\'s tenant')

    if (
        branch is not None
        and source_account.branch_id is not None
        and source_account.branch_id != branch.id
    ):
        raise SupplierPaymentError(
            'source_account branch does not match the payment branch',
        )

    if not source_account.is_active:
        raise SupplierPaymentError('source_account is inactive')
    if not payment_method.is_active:
        raise SupplierPaymentError('payment_method is inactive')

    if payment_method.method_type == PaymentMethod.MethodType.CREDIT:
        raise SupplierPaymentError(
            'credit payment method cannot be used for a supplier payment '
            '(would increase AP, not settle it)',
        )

    allowed = _METHOD_TO_SRC_ACCOUNT_TYPES.get(payment_method.method_type)
    if allowed and source_account.account_type not in allowed:
        raise SupplierPaymentError(
            f'method_type={payment_method.method_type!r} cannot fund from '
            f'account_type={source_account.account_type!r}; allowed: '
            f'{sorted(allowed)}',
        )


@transaction.atomic
def create_supplier_payment(
    *,
    tenant,
    branch: Optional[Branch],
    supplier: Supplier,
    payment_method: PaymentMethod,
    source_account: FinancialAccount,
    amount,
    reference: str = '',
    notes: str = '',
    actor_user=None,
    occurred_at=None,
) -> SupplierPayment:
    """Post one supplier payment + the two ledger rows atomically.

    Returns the persisted SupplierPayment. Raises SupplierPaymentError for
    rule violations; underlying ledger errors are wrapped so callers only
    need to catch one type. On any exception, the surrounding
    `transaction.atomic` rolls back every write.
    """
    _validate_inputs(
        tenant=tenant, branch=branch, supplier=supplier,
        payment_method=payment_method, source_account=source_account,
        amount=amount,
    )

    amount_dec = Decimal(str(amount))
    when = occurred_at or timezone.now()

    payment = SupplierPayment.objects.create(
        tenant=tenant,
        branch=branch,
        supplier=supplier,
        payment_method=payment_method,
        source_account=source_account,
        amount=amount_dec,
        reference=reference,
        notes=notes,
        status=SupplierPayment.Status.POSTED,
        posted_at=when,
        actor_user=actor_user,
    )

    try:
        ap.record_supplier_ap_debit(
            supplier=supplier,
            amount=amount_dec,
            movement_type=ap.MovementType.SUPPLIER_PAYMENT,
            branch=branch,
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=notes or '',
        )
    except ap.SupplierAPError as exc:
        raise SupplierPaymentError(f'AP posting failed: {exc}') from exc

    try:
        fa.record_account_credit(
            account=source_account,
            amount=amount_dec,
            movement_type=fa.MovementType.SUPPLIER_PAYMENT_OUT,
            branch=branch,
            source_document_type='SupplierPayment',
            source_document_id=payment.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=notes or '',
        )
    except fa.AccountMovementError as exc:
        raise SupplierPaymentError(f'Finance posting failed: {exc}') from exc

    return payment


__all__ = [
    'SupplierPaymentError',
    'create_supplier_payment',
]
