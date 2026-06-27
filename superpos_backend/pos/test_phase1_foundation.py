"""Phase 1 Foundation Slice tests.

Covers:
    * Shared status enums in pos.domain.statuses — required values exist
    * Idempotency service: same key + same payload → replay
    * Idempotency service: same key + different payload → conflict
    * Idempotency tenant scoping: same key across tenants does not collide

No HTTP layer is exercised here — that wiring is deferred. Existing tests in
pos/tests.py continue to cover the live POS endpoints unchanged.
"""

from django.test import TestCase

from accounts.models import Tenant, User
from pos.domain.statuses import (
    STATUS_REGISTRY,
    ApprovalStatus,
    KitchenTicketStatus,
    OpenOrderLineStatus,
    OpenOrderStatus,
    PaymentStatus,
    PostingStatus,
    ReturnStatus,
    ShiftStatus,
    SyncStatus,
    TableStatus,
)
from pos.models import IdempotencyRecord
from pos.services import idempotency


class StatusEnumContractTests(TestCase):
    """Lock the wire vocabulary so refactors can't silently drop a value.

    Each `expected` set is the contract the v3.6 docs and API_CONTRACT.md
    require. Adding new values later is fine; dropping or renaming one is a
    breaking change to the API surface and the React types.
    """

    def test_registry_exposes_all_ten_status_fields(self):
        expected_fields = {
            'posting_status',
            'payment_status',
            'return_status',
            'approval_status',
            'sync_status',
            'open_order_status',
            'open_order_line_status',
            'table_status',
            'kitchen_ticket_status',
            'shift_status',
        }
        self.assertEqual(set(STATUS_REGISTRY.keys()), expected_fields)

    def test_posting_status_values(self):
        self.assertEqual(
            set(PostingStatus.values),
            {'draft', 'posted', 'cancelled', 'void'},
        )

    def test_payment_status_values(self):
        self.assertEqual(
            set(PaymentStatus.values),
            {'unpaid', 'partially_paid', 'paid', 'n_a'},
        )

    def test_return_status_values(self):
        self.assertEqual(
            set(ReturnStatus.values),
            {'not_returned', 'partially_returned', 'returned'},
        )

    def test_approval_status_values(self):
        self.assertEqual(
            set(ApprovalStatus.values),
            {'not_required', 'pending', 'approved', 'rejected'},
        )

    def test_sync_status_values(self):
        self.assertEqual(
            set(SyncStatus.values),
            {'synced', 'pending_sync', 'sync_failed'},
        )

    def test_open_order_status_values(self):
        # Must include the lifecycle the API_CONTRACT requires for the
        # Pay → SalesInvoice conversion and the request-bill transition.
        self.assertTrue(
            {'draft', 'sent', 'needs_bill', 'paid_clearing', 'paid', 'cancelled'}
            .issubset(set(OpenOrderStatus.values))
        )

    def test_open_order_line_status_values(self):
        # DOMAIN.md §41.6 lifecycle + the two "removed" terminal states.
        self.assertTrue(
            {'draft', 'sent', 'preparing', 'ready', 'served', 'billed', 'voided', 'cancelled'}
            .issubset(set(OpenOrderLineStatus.values))
        )

    def test_table_status_values(self):
        self.assertEqual(
            set(TableStatus.values),
            {
                'available', 'occupied', 'sent_to_kitchen',
                'needs_bill', 'paid_clearing', 'out_of_service',
            },
        )

    def test_kitchen_ticket_status_values(self):
        self.assertEqual(
            set(KitchenTicketStatus.values),
            {
                'queued', 'printed', 'print_failed',
                'preparing', 'ready', 'served', 'voided',
            },
        )

    def test_shift_status_values(self):
        self.assertTrue(
            {'open', 'closed'}.issubset(set(ShiftStatus.values))
        )


class IdempotencyServiceTests(TestCase):
    """Lookup / save semantics from API_CONTRACT.md §2 + DOMAIN.md §6.3."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name='Tenant A')
        cls.tenant_b = Tenant.objects.create(name='Tenant B')
        cls.user_a = User.objects.create_user(
            username='user_a', password='pw', tenant=cls.tenant_a,
        )

    def test_lookup_with_no_record_returns_proceed(self):
        result = idempotency.lookup(
            tenant=self.tenant_a, key='k-1', payload={'x': 1},
            method='POST', path='/api/pos/open-orders/1/lines/',
        )
        self.assertTrue(result.proceed)
        self.assertFalse(result.replay)
        self.assertFalse(result.conflict)

    def test_blank_key_is_proceed_no_op(self):
        result = idempotency.lookup(
            tenant=self.tenant_a, key='', payload={'x': 1},
            method='POST', path='/p/',
        )
        self.assertTrue(result.proceed)

        # save() must also no-op on blank key — callers can pass through.
        out = idempotency.save(
            tenant=self.tenant_a, key='', payload={'x': 1},
            method='POST', path='/p/',
            response_status=201, response_body={'id': 1},
        )
        self.assertIsNone(out)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)

    def test_save_then_replay_with_same_payload(self):
        payload = {'product_id': 12, 'quantity': '2.00', 'notes': 'extra shot'}
        body = {'data': {'id': 701, 'open_order_id': 501}}

        rec = idempotency.save(
            tenant=self.tenant_a, key='req-abc-123', payload=payload,
            method='POST', path='/api/pos/open-orders/501/lines/',
            response_status=201, response_body=body, user=self.user_a,
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.tenant_id, self.tenant_a.id)
        self.assertEqual(rec.user_id, self.user_a.id)
        self.assertEqual(rec.response_status, 201)

        # Reordering keys / whitespace must not change the hash.
        reordered = {'notes': 'extra shot', 'quantity': '2.00', 'product_id': 12}
        result = idempotency.lookup(
            tenant=self.tenant_a, key='req-abc-123', payload=reordered,
            method='POST', path='/api/pos/open-orders/501/lines/',
        )
        self.assertTrue(result.replay)
        self.assertFalse(result.conflict)
        self.assertEqual(result.status, 201)
        self.assertEqual(result.body, body)

    def test_same_key_different_payload_is_conflict(self):
        payload_one = {'product_id': 12, 'quantity': '2.00'}
        payload_two = {'product_id': 12, 'quantity': '3.00'}   # different qty

        idempotency.save(
            tenant=self.tenant_a, key='req-xyz', payload=payload_one,
            method='POST', path='/api/pos/open-orders/501/lines/',
            response_status=201, response_body={'data': {'id': 701}},
        )

        result = idempotency.lookup(
            tenant=self.tenant_a, key='req-xyz', payload=payload_two,
            method='POST', path='/api/pos/open-orders/501/lines/',
        )
        self.assertTrue(result.conflict)
        self.assertFalse(result.replay)
        self.assertIsNotNone(result.record)

    def test_tenant_scoping_isolates_collisions(self):
        """Same opaque key in two tenants must be independent."""
        shared_key = 'shared-key-001'
        payload_a = {'foo': 'tenant_a_payload'}
        payload_b = {'foo': 'tenant_b_payload'}

        idempotency.save(
            tenant=self.tenant_a, key=shared_key, payload=payload_a,
            method='POST', path='/api/pos/shifts/open/',
            response_status=201, response_body={'data': {'id': 1, 'tenant': 'A'}},
        )
        idempotency.save(
            tenant=self.tenant_b, key=shared_key, payload=payload_b,
            method='POST', path='/api/pos/shifts/open/',
            response_status=201, response_body={'data': {'id': 1, 'tenant': 'B'}},
        )

        # Two rows, one per tenant — no collision.
        self.assertEqual(
            IdempotencyRecord.objects.filter(key=shared_key).count(), 2,
        )

        result_a = idempotency.lookup(
            tenant=self.tenant_a, key=shared_key, payload=payload_a,
            method='POST', path='/api/pos/shifts/open/',
        )
        result_b = idempotency.lookup(
            tenant=self.tenant_b, key=shared_key, payload=payload_b,
            method='POST', path='/api/pos/shifts/open/',
        )
        self.assertTrue(result_a.replay)
        self.assertTrue(result_b.replay)
        self.assertEqual(result_a.body['data']['tenant'], 'A')
        self.assertEqual(result_b.body['data']['tenant'], 'B')

        # And a *cross-tenant* lookup with tenant B's payload against tenant
        # A's key still hits tenant A's row → must be a conflict, not a
        # silent replay (because the payload differs).
        cross = idempotency.lookup(
            tenant=self.tenant_a, key=shared_key, payload=payload_b,
            method='POST', path='/api/pos/shifts/open/',
        )
        self.assertTrue(cross.conflict)

    def test_save_is_idempotent_on_same_payload(self):
        """Calling save() twice with same payload updates one row, not two."""
        payload = {'k': 'v'}
        idempotency.save(
            tenant=self.tenant_a, key='dup', payload=payload,
            method='POST', path='/p/',
            response_status=200, response_body={'ok': True},
        )
        idempotency.save(
            tenant=self.tenant_a, key='dup', payload=payload,
            method='POST', path='/p/',
            response_status=200, response_body={'ok': True},
        )
        self.assertEqual(
            IdempotencyRecord.objects.filter(tenant=self.tenant_a, key='dup').count(),
            1,
        )

    def test_compute_request_hash_is_stable_and_order_insensitive(self):
        h1 = idempotency.compute_request_hash({'a': 1, 'b': 2})
        h2 = idempotency.compute_request_hash({'b': 2, 'a': 1})
        h3 = idempotency.compute_request_hash({'a': 1, 'b': 3})
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 64)  # sha256 hex
