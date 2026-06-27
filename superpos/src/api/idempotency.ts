/**
 * Idempotency-Key helpers for critical POST requests.
 *
 * Backend contract: `pos/services/idempotency.py` + API_CONTRACT.md §2.
 * Server-side wiring is deferred (Phase 2+), but the client helper is safe
 * to land now because:
 *   - it doesn't change any existing request behavior unless callers opt in
 *   - it lets us encode the key-generation rule in one place from day one
 *     (avoids divergence between POS, Sales, and future Table-Service code)
 *
 * Usage (no existing call site is migrated in this slice):
 *
 *     import apiClient from '@/api/client';
 *     import { generateIdempotencyKey, withIdempotencyHeaders } from '@/api/idempotency';
 *
 *     const key = generateIdempotencyKey();
 *     await apiClient.post('/pos/open-orders/501/lines/', body, withIdempotencyHeaders(key));
 *
 * The same `key` must be retried verbatim on offline-sync replay so the
 * backend recognises the duplicate and replays the original response.
 */

/**
 * Generate a fresh idempotency key. Prefers the platform's
 * `crypto.randomUUID()` (available in all modern browsers and Node 19+);
 * falls back to a sufficiently-random string for legacy environments.
 *
 * The key is opaque to the backend — only its uniqueness per (tenant, key)
 * matters. Don't include sensitive data in it.
 */
export function generateIdempotencyKey(): string {
  const cryptoObj: Crypto | undefined =
    typeof globalThis !== 'undefined' ? (globalThis as { crypto?: Crypto }).crypto : undefined;

  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') {
    return cryptoObj.randomUUID();
  }

  // Fallback: timestamp + 16 hex chars of randomness. Not cryptographically
  // strong, but more than enough entropy for an idempotency token.
  const rand = Math.random().toString(16).slice(2).padEnd(16, '0').slice(0, 16);
  return `idem-${Date.now().toString(16)}-${rand}`;
}

/**
 * Build an axios-compatible config fragment carrying the `Idempotency-Key`
 * header. Designed to be spread into an existing per-call config or used as
 * the third argument to `apiClient.post(url, body, withIdempotencyHeaders(key))`.
 *
 * `extra` is merged shallowly so callers can still pass `signal`, `params`,
 * etc. without losing the header.
 */
export function withIdempotencyHeaders(
  key: string,
  extra: { headers?: Record<string, string> } & Record<string, unknown> = {},
): { headers: Record<string, string> } & Record<string, unknown> {
  const { headers: extraHeaders, ...rest } = extra;
  return {
    ...rest,
    headers: {
      ...(extraHeaders ?? {}),
      'Idempotency-Key': key,
    },
  };
}
