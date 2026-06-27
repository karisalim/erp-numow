"""Shared document/operational status enums for SuperPOS v3.6.

These are the canonical status vocabularies referenced across the v3.6 PRD,
FLOW, DOMAIN, and API contracts. They are defined here once so future models,
serializers, services, and tests can import a single source of truth instead
of redeclaring magic strings.

Phase 1 slice scope: *defining* the enums only. No model on this branch yet
references them — that wiring lands with the table-service / open-order /
shift / kitchen-ticket models in Phase 2+. Listing them centrally now keeps
later additive migrations contract-aligned.

Each class is a `django.db.models.TextChoices` so it can be dropped into a
`models.CharField(choices=...)` without translation, and the raw values are
stable wire strings (snake_case, lowercase) matching API_CONTRACT.md and
DOMAIN.md §5.2 (Five-Status Model) plus §41 (Table Service).
"""

from django.db import models


# ── §5.2 Five-Status Document Model ──────────────────────────────────────────

class PostingStatus(models.TextChoices):
    """Lifecycle of a business document's posted state.

    DOMAIN.md §5.2 / §5.3 / §5.5 / §5.6.
    """
    DRAFT     = 'draft',     'Draft'
    POSTED    = 'posted',    'Posted'
    CANCELLED = 'cancelled', 'Cancelled'
    VOID      = 'void',      'Void'


class PaymentStatus(models.TextChoices):
    """Payment fulfillment status for a posted document. DOMAIN.md §5.2."""
    UNPAID         = 'unpaid',         'Unpaid'
    PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
    PAID           = 'paid',           'Paid'
    NOT_APPLICABLE = 'n_a',            'N/A'


class ReturnStatus(models.TextChoices):
    """Return fulfillment status for a posted document. DOMAIN.md §5.2."""
    NOT_RETURNED       = 'not_returned',       'Not Returned'
    PARTIALLY_RETURNED = 'partially_returned', 'Partially Returned'
    RETURNED           = 'returned',           'Returned'


class ApprovalStatus(models.TextChoices):
    """Manager approval gate state. DOMAIN.md §5.2 / §3.3."""
    NOT_REQUIRED = 'not_required', 'Not Required'
    PENDING      = 'pending',      'Pending'
    APPROVED     = 'approved',     'Approved'
    REJECTED     = 'rejected',     'Rejected'


class SyncStatus(models.TextChoices):
    """Offline-sync lifecycle. DOMAIN.md §5.2 / §26.2 / §26.3."""
    SYNCED       = 'synced',       'Synced'
    PENDING_SYNC = 'pending_sync', 'Pending Sync'
    SYNC_FAILED  = 'sync_failed',  'Sync Failed'


# ── §41 Table Service / Open Orders ──────────────────────────────────────────

class OpenOrderStatus(models.TextChoices):
    """OpenOrder lifecycle. API_CONTRACT.md §3.1 / DOMAIN.md §41.6.

    `paid_clearing` is the table-side post-payment state used until the table
    is explicitly cleared back to `available` (API_CONTRACT.md §3.17).
    """
    DRAFT           = 'draft',           'Draft'
    SENT            = 'sent',            'Sent'
    NEEDS_BILL      = 'needs_bill',      'Needs Bill'
    PAID_CLEARING   = 'paid_clearing',   'Paid / Clearing'
    PAID            = 'paid',            'Paid'
    CANCELLED       = 'cancelled',       'Cancelled'


class OpenOrderLineStatus(models.TextChoices):
    """Per-line lifecycle inside an OpenOrder. DOMAIN.md §41.6 / §41.7."""
    DRAFT             = 'draft',             'Draft'
    SENT              = 'sent',              'Sent'
    PREPARED_PENDING  = 'prepared_pending',  'Prepared / Pending'
    PREPARING         = 'preparing',         'Preparing'
    READY             = 'ready',             'Ready'
    SERVED            = 'served',            'Served'
    BILLED            = 'billed',            'Billed'
    VOIDED            = 'voided',            'Voided'
    CANCELLED         = 'cancelled',         'Cancelled'


class TableStatus(models.TextChoices):
    """DiningTable status. API_CONTRACT.md §3.1 business rule."""
    AVAILABLE       = 'available',       'Available'
    OCCUPIED        = 'occupied',        'Occupied'
    SENT_TO_KITCHEN = 'sent_to_kitchen', 'Sent to Kitchen'
    NEEDS_BILL      = 'needs_bill',      'Needs Bill'
    PAID_CLEARING   = 'paid_clearing',   'Paid / Clearing'
    OUT_OF_SERVICE  = 'out_of_service',  'Out of Service'


class KitchenTicketStatus(models.TextChoices):
    """KitchenTicket status. API_CONTRACT.md §3.15."""
    QUEUED       = 'queued',       'Queued'
    PRINTED      = 'printed',      'Printed'
    PRINT_FAILED = 'print_failed', 'Print Failed'
    PREPARING    = 'preparing',    'Preparing'
    READY        = 'ready',        'Ready'
    SERVED       = 'served',       'Served'
    VOIDED       = 'voided',       'Voided'


# ── §14 Shift ────────────────────────────────────────────────────────────────

class ShiftStatus(models.TextChoices):
    """Shift lifecycle. DOMAIN.md §14, API_CONTRACT.md §3.10 / §3.11."""
    OPEN          = 'open',          'Open'
    CLOSED        = 'closed',        'Closed'
    FORCE_CLOSED  = 'force_closed',  'Force Closed'
    RECONCILING   = 'reconciling',   'Reconciling'


# ── Public registry ──────────────────────────────────────────────────────────

#: Maps the public status-field name used in API contracts (and in
#: `superpos/src/types/index.ts`) to the corresponding TextChoices class.
#: Useful for tests, OpenAPI schema introspection, and validation helpers.
STATUS_REGISTRY = {
    'posting_status':         PostingStatus,
    'payment_status':         PaymentStatus,
    'return_status':          ReturnStatus,
    'approval_status':        ApprovalStatus,
    'sync_status':            SyncStatus,
    'open_order_status':      OpenOrderStatus,
    'open_order_line_status': OpenOrderLineStatus,
    'table_status':           TableStatus,
    'kitchen_ticket_status':  KitchenTicketStatus,
    'shift_status':           ShiftStatus,
}


__all__ = [
    'PostingStatus',
    'PaymentStatus',
    'ReturnStatus',
    'ApprovalStatus',
    'SyncStatus',
    'OpenOrderStatus',
    'OpenOrderLineStatus',
    'TableStatus',
    'KitchenTicketStatus',
    'ShiftStatus',
    'STATUS_REGISTRY',
]
