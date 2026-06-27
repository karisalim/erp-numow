"""Idempotency helpers for critical POST endpoints.

Implements API_CONTRACT.md §2 (Idempotency) and DOMAIN.md §6.3 / §26.3.

Usage pattern (Phase 2+ wiring, not done in this slice):

    from pos.services import idempotency

    key = request.headers.get('Idempotency-Key')
    payload = request.data

    found = idempotency.lookup(
        tenant=tenant, key=key, payload=payload,
        method=request.method, path=request.path, user=request.user,
    )
    if found.replay:
        return Response(found.body, status=found.status)
    if found.conflict:
        raise IdempotencyConflict()

    # ... do the real work ...
    response = run_business_logic()

    idempotency.save(
        tenant=tenant, key=key, payload=payload,
        method=request.method, path=request.path, user=request.user,
        response_status=response.status_code, response_body=response.data,
    )
    return response

The helpers are deliberately small and pure-ish so they can be unit-tested
without spinning up a DRF view. Only `lookup` / `save` touch the database.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from pos.models import IdempotencyRecord


class IdempotencyConflict(Exception):
    """Raised when the same key is reused with a *different* payload.

    Callers (views) translate this into HTTP 409 per API_CONTRACT.md §2.
    The exception carries the existing record so the caller can include
    context in the error response if it wants to.
    """

    def __init__(self, existing: IdempotencyRecord):
        self.existing = existing
        super().__init__(
            f'Idempotency-Key {existing.key!r} reused with a different payload',
        )


@dataclass(frozen=True)
class LookupResult:
    """Outcome of `lookup()`.

    Exactly one of `replay` / `conflict` / `proceed` is True. When `replay`
    is True, `status` and `body` hold the stored response snapshot.
    """
    replay: bool = False
    conflict: bool = False
    proceed: bool = False
    record: Optional[IdempotencyRecord] = None
    status: Optional[int] = None
    body: Any = None


def compute_request_hash(payload: Any) -> str:
    """Deterministic SHA-256 of the request payload.

    `payload` is whatever DRF gave us — usually a dict/list. We serialize
    with `sort_keys=True` and `separators=(',', ':')` so two semantically
    identical payloads always hash to the same digest regardless of key
    ordering or whitespace from the client. `default=str` keeps
    Decimal/UUID/datetime serializable without raising.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def lookup(
    *,
    tenant,
    key: str,
    payload: Any,
    method: str,
    path: str,
    user=None,
) -> LookupResult:
    """Inspect the store for `(tenant, key)`.

    Returns:
        LookupResult(proceed=True)  — no prior record; caller should run the work
        LookupResult(replay=True, status=..., body=...) — same payload, replay
        LookupResult(conflict=True, record=...) — different payload, caller raises

    Notes:
        * `tenant` and `key` are mandatory; missing/blank `key` is *also*
          treated as `proceed=True` so callers can decide their own policy
          (e.g. require it via 400 elsewhere) — this helper never invents
          behavior for a missing key.
        * `method` and `path` are stored on first write but are not part of
          the lookup discriminator. The uniqueness contract is per
          (tenant, key); reusing a key against a different endpoint is a
          client-side misuse and yields the same conflict semantics.
        * `user` is informational; tenant scoping (not user scoping) is the
          isolation boundary.
    """
    if not key:
        return LookupResult(proceed=True)

    try:
        existing = IdempotencyRecord.objects.get(tenant=tenant, key=key)
    except IdempotencyRecord.DoesNotExist:
        return LookupResult(proceed=True)

    incoming_hash = compute_request_hash(payload)
    if existing.request_hash == incoming_hash:
        return LookupResult(
            replay=True,
            record=existing,
            status=existing.response_status,
            body=existing.response_body,
        )

    return LookupResult(conflict=True, record=existing)


def save(
    *,
    tenant,
    key: str,
    payload: Any,
    method: str,
    path: str,
    response_status: int,
    response_body: Any,
    user=None,
) -> Optional[IdempotencyRecord]:
    """Persist the response snapshot for `(tenant, key)`.

    Returns the created record, or `None` if `key` is blank (no-op so
    callers can pass through unconditionally without re-checking).

    `response_body` should be a JSON-serializable structure (DRF response
    data). Non-JSON types (Decimal, UUID, datetime) are coerced via the
    same `default=str` rule used by `compute_request_hash` so the snapshot
    is round-trippable.
    """
    if not key:
        return None

    snapshot = json.loads(
        json.dumps(response_body, default=str, ensure_ascii=False),
    )

    record, _created = IdempotencyRecord.objects.update_or_create(
        tenant=tenant,
        key=key,
        defaults={
            'user':            user,
            'method':          method,
            'path':            path,
            'request_hash':    compute_request_hash(payload),
            'response_status': response_status,
            'response_body':   snapshot,
        },
    )
    return record


__all__ = [
    'IdempotencyConflict',
    'LookupResult',
    'compute_request_hash',
    'lookup',
    'save',
]
