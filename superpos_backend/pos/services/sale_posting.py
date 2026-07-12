"""Sales ledger integration (Phase 1.5 Slice I).

Helpers the Sale create-flow uses to post a completed sale to the financial
and customer ledgers, reusing the existing services:

    * cash / card / wallet → FinancialAccountMovement DEBIT on the
      destination account resolved from BranchPaymentMethod (asset account →
      debit increases; money comes in). Reuses
      `accounts.services.account_movements`.
    * credit → CustomerARMovement DEBIT on the customer (AR asset → debit
      increases what the customer owes). Reuses
      `accounts.services.customer_ar`. Requires a customer.

Routing policy (Release Gate A GA-2 — strict):
    * EVERY completed cash/card/wallet sale must resolve to an active
      `BranchPaymentMethod` route. A missing / inactive / misconfigured route
      raises `SalePostingError`; the caller turns that into a 400 and rolls
      the whole sale back. There is no legacy best-effort skip anymore — the
      `provision_default_payment_routing` management command (the R-F
      replacement for the rejected 0017 backfill migration) provisions default
      routing for every pre-existing branch, so an unrouted branch is always a
      configuration error, never an expected state. Routing is always resolved
      from config, never hardcoded.
    * Credit always posts to Customer AR and always requires a customer,
      regardless of branch payment configuration.

Warehouse resolution mirrors the purchase slice: explicit per-line warehouse
wins; otherwise the branch's default active sales warehouse is used. The
warehouse is recorded for traceability only — there is no per-warehouse stock
balance yet (the on-hand quantity stays on the global `Product.stock`).
"""

from __future__ import annotations

import logging

from accounts.models import BranchPaymentMethod
from accounts.services import account_movements as fa
from accounts.services import customer_ar as ar
from pos.models import BranchWarehouse


logger = logging.getLogger(__name__)


class SalePostingError(Exception):
    """A sale could not be posted to the financial ledger.

    Raised when the chosen method has no active/usable BranchPaymentMethod
    route. The Sale create-flow catches this and returns a 400 so the whole
    sale rolls back — a completed sale must never skip financial posting
    (GA-2 strict routing).

    `code` is a stable machine-readable identifier the API layer surfaces
    alongside the human-readable message (GA-8).
    """

    code = 'payment_routing_missing'


_FINANCE_MOVEMENT_TYPE = {
    'cash':   fa.MovementType.SALES_CASH_IN,
    'card':   fa.MovementType.SALES_CARD_IN,
    'wallet': fa.MovementType.SALES_WALLET_IN,
}


def resolve_sales_warehouse(*, tenant, branch):
    """Branch's default active sales warehouse, or None when unconfigured."""
    if tenant is None or branch is None:
        return None
    link = (
        BranchWarehouse.objects
        .filter(
            tenant=tenant, branch=branch,
            role=BranchWarehouse.Role.SALES,
            is_default=True, is_active=True,
        )
        .select_related('warehouse')
        .first()
    )
    return link.warehouse if link is not None else None


def resolve_branch_payment_method(*, tenant, branch, method):
    """Active BranchPaymentMethod matching this method_type for the branch.

    Prefers the default; falls back to any active one. Returns None when the
    tenant hasn't configured routing for this method (→ posting error).

    Selection is deterministic (GA-6): `-is_default` puts the default first
    and `-id` breaks any remaining tie by newest row, so even bad data (two
    active defaults of the same method_type, which the serializer now
    rejects) resolves to a stable choice instead of DB row order.
    """
    if tenant is None or branch is None:
        return None
    return (
        BranchPaymentMethod.objects
        .filter(
            tenant=tenant, branch=branch, is_active=True,
            payment_method__method_type=method,
        )
        .select_related('destination_account', 'payment_method')
        .order_by('-is_default', '-id')
        .first()
    )


def branch_has_payment_routing(*, tenant, branch):
    """True when the branch has ANY BranchPaymentMethod rows (active or not).

    Gate A note: this no longer gates posting (every sale requires routing
    now); it is kept as a cheap configuration probe for admin/setup UIs.
    """
    if tenant is None or branch is None:
        return False
    return BranchPaymentMethod.objects.filter(tenant=tenant, branch=branch).exists()


def post_sale_ledgers(*, sale, method, customer=None, actor_user=None):
    """Post the financial/AR effect of a completed sale.

    Runs inside the caller's `transaction.atomic` block so a failure here
    rolls back the whole sale. Returns the movement created, or None when
    nothing was posted (zero total only — routing is otherwise mandatory).
    """
    amount = sale.total
    if amount is None or amount <= 0:
        return None

    notes = f'Sale #{sale.id}'

    if method == 'credit':
        # Customer is required for credit — the serializer enforces this; we
        # guard again so a direct service caller can't post AR to nobody.
        if customer is None:
            raise ar.CustomerARError('credit sale requires a customer')
        return ar.record_customer_ar_debit(
            customer=customer,
            amount=amount,
            movement_type=ar.MovementType.SALES_CREDIT,
            branch=sale.branch,
            source_document_type='sale',
            source_document_id=sale.id,
            actor_user=actor_user,
            notes=notes,
        )

    bpm = resolve_branch_payment_method(
        tenant=sale.tenant, branch=sale.branch, method=method,
    )
    if bpm is None:
        # GA-2: no legacy skip. Every completed cash/card/wallet sale must
        # post to the ledger, so a missing/inactive route is always a
        # configuration error — raise and let the caller roll the sale back.
        raise SalePostingError(
            f'No active payment routing is configured for method "{method}" '
            f'on branch {getattr(sale, "branch_id", None)}. Configure an '
            f'active BranchPaymentMethod for this method, or correct the sale.'
        )

    return fa.record_account_debit(
        account=bpm.destination_account,
        amount=amount,
        movement_type=_FINANCE_MOVEMENT_TYPE.get(method, fa.MovementType.OTHER),
        branch=sale.branch,
        source_document_type='sale',
        source_document_id=sale.id,
        actor_user=actor_user,
        notes=notes,
    )


__all__ = [
    'SalePostingError',
    'resolve_sales_warehouse',
    'resolve_branch_payment_method',
    'branch_has_payment_routing',
    'post_sale_ledgers',
]
