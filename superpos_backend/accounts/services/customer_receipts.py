"""Customer receipt posting service.

Implements MASTER_DATA_CONTRACT.md §10 (Customer settlements). A customer
receipt is the *event* in which a customer pays down (some or all of)
their outstanding AR balance. Creating one atomically produces:

    1. A CustomerReceipt header row (audit trail / document).
    2. A CustomerARMovement credit row (customer balance ↓).
    3. A FinancialAccountMovement debit row against the destination
       account (cashbox / bank / wallet / card_settlement balance ↑).

All three writes happen inside a single `transaction.atomic` block. If any
one fails — DB CHECK violation, balance lock race, validation error —
nothing is persisted. This is the "no partial posting" rule from the
Slice G goal.

This module is the ONLY supported way to create a CustomerReceipt
document. Views call into it; tests call into it. Bypassing it (writing
the model directly) skips the ledger postings and creates an orphaned
document.

Compatibility matrix (which destination accounts are allowed for each
payment method type) mirrors `accounts.serializers._METHOD_TO_DEST_ACCOUNT_TYPES`
but is enforced here too — the service is the last line of defense and
the test layer exercises it directly without round-tripping through the
serializer.

Credit-type payment methods are rejected: paying down an AR balance by
*increasing* AR is incoherent (it'd be the same as not paying). Callers
that want to refund or settle an over-payment use a separate
`overpayment_refund` / `write_off` flow (later slices).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounts.models import (
    Branch,
    Customer,
    CustomerReceipt,
    FinancialAccount,
    PaymentMethod,
)
from accounts.services import account_movements as fa
from accounts.services import customer_ar as ar


class CustomerReceiptError(Exception):
    """Service-level rule violation. Views translate to HTTP 400."""


# Destination account types that may receive a customer payment, keyed by
# the payment method's type. `custom` accepts anything (tenants who model
# unusual flows opt into their own routing).
_METHOD_TO_DEST_ACCOUNT_TYPES = {
    PaymentMethod.MethodType.CASH:   {FinancialAccount.AccountType.CASHBOX},
    PaymentMethod.MethodType.CARD:   {FinancialAccount.AccountType.CARD_SETTLEMENT},
    PaymentMethod.MethodType.WALLET: {FinancialAccount.AccountType.WALLET},
}


def _validate_inputs(
    *,
    tenant,
    branch: Optional[Branch],
    customer: Customer,
    payment_method: PaymentMethod,
    destination_account: FinancialAccount,
    amount: Decimal,
) -> None:
    """Reject any cross-tenant / cross-branch / type-mismatched input.

    Runs before the atomic block opens so we never spend a DB row-lock
    on input that was always going to fail.
    """
    if amount is None:
        raise CustomerReceiptError('amount is required')

    try:
        amount_dec = Decimal(str(amount))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise CustomerReceiptError(f'invalid amount: {amount!r}') from exc
    if amount_dec <= 0:
        raise CustomerReceiptError('amount must be > 0')

    if customer.tenant_id != tenant.id:
        raise CustomerReceiptError('customer must belong to the caller\'s tenant')
    if payment_method.tenant_id != tenant.id:
        raise CustomerReceiptError('payment_method must belong to the caller\'s tenant')
    if destination_account.tenant_id != tenant.id:
        raise CustomerReceiptError('destination_account must belong to the caller\'s tenant')

    if branch is not None and branch.tenant_id != tenant.id:
        raise CustomerReceiptError('branch must belong to the caller\'s tenant')

    # A branch-scoped destination_account must match the receipt's branch
    # if one was supplied. Tenant-wide accounts (branch_id IS NULL on the
    # account) can land any branch's receipts.
    if (
        branch is not None
        and destination_account.branch_id is not None
        and destination_account.branch_id != branch.id
    ):
        raise CustomerReceiptError(
            'destination_account branch does not match the receipt branch',
        )

    if not destination_account.is_active:
        raise CustomerReceiptError('destination_account is inactive')
    if not payment_method.is_active:
        raise CustomerReceiptError('payment_method is inactive')

    if payment_method.method_type == PaymentMethod.MethodType.CREDIT:
        raise CustomerReceiptError(
            'credit payment method cannot be used for a customer receipt '
            '(would increase AR, not settle it)',
        )

    allowed = _METHOD_TO_DEST_ACCOUNT_TYPES.get(payment_method.method_type)
    # `custom` (and any unknown type) → no destination-type restriction.
    if allowed and destination_account.account_type not in allowed:
        raise CustomerReceiptError(
            f'method_type={payment_method.method_type!r} cannot route to '
            f'account_type={destination_account.account_type!r}; allowed: '
            f'{sorted(allowed)}',
        )


@transaction.atomic
def create_customer_receipt(
    *,
    tenant,
    branch: Optional[Branch],
    customer: Customer,
    payment_method: PaymentMethod,
    destination_account: FinancialAccount,
    amount,
    reference: str = '',
    notes: str = '',
    actor_user=None,
    occurred_at=None,
) -> CustomerReceipt:
    """Post one customer receipt + the two ledger rows atomically.

    Returns the persisted CustomerReceipt. Raises CustomerReceiptError for
    rule violations, and re-raises any underlying service errors
    (CustomerARError / AccountMovementError) wrapped in
    CustomerReceiptError so callers only need to catch one type.

    On exception, the surrounding `transaction.atomic` rolls back every
    write — the document, the AR row, and the financial account row all
    disappear together.
    """
    _validate_inputs(
        tenant=tenant, branch=branch, customer=customer,
        payment_method=payment_method, destination_account=destination_account,
        amount=amount,
    )

    amount_dec = Decimal(str(amount))
    when = occurred_at or timezone.now()

    receipt = CustomerReceipt.objects.create(
        tenant=tenant,
        branch=branch,
        customer=customer,
        payment_method=payment_method,
        destination_account=destination_account,
        amount=amount_dec,
        reference=reference,
        notes=notes,
        status=CustomerReceipt.Status.POSTED,
        posted_at=when,
        actor_user=actor_user,
    )

    try:
        ar.record_customer_ar_credit(
            customer=customer,
            amount=amount_dec,
            movement_type=ar.MovementType.CUSTOMER_RECEIPT,
            branch=branch,
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=notes or '',
        )
    except ar.CustomerARError as exc:
        raise CustomerReceiptError(f'AR posting failed: {exc}') from exc

    try:
        fa.record_account_debit(
            account=destination_account,
            amount=amount_dec,
            movement_type=fa.MovementType.CUSTOMER_RECEIPT_IN,
            branch=branch,
            source_document_type='CustomerReceipt',
            source_document_id=receipt.id,
            actor_user=actor_user,
            occurred_at=when,
            notes=notes or '',
        )
    except fa.AccountMovementError as exc:
        raise CustomerReceiptError(f'Finance posting failed: {exc}') from exc

    return receipt


__all__ = [
    'CustomerReceiptError',
    'create_customer_receipt',
]
