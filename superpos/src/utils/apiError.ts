import { AxiosError } from 'axios';

/**
 * Normalised shape for DRF error responses so pages can render a single
 * message banner plus per-field validation errors without re-parsing axios
 * errors everywhere.
 */
export interface ApiError {
  status: number | null;
  /** Human-readable top-level message. */
  message: string;
  /** field name → first error string (DRF serializer errors). */
  fieldErrors: Record<string, string>;
  /** True when the backend denied the action (401/403). */
  permissionDenied: boolean;
  /** Backend machine code when present (e.g. IDEMPOTENCY_CONFLICT). */
  code?: string;
}

function firstString(v: unknown): string | null {
  if (typeof v === 'string') return v;
  if (Array.isArray(v) && v.length > 0 && typeof v[0] === 'string') return v[0];
  return null;
}

export function parseApiError(err: unknown, fallback = 'Request failed. Please try again.'): ApiError {
  const out: ApiError = { status: null, message: fallback, fieldErrors: {}, permissionDenied: false };

  if (!(err instanceof AxiosError)) return out;

  out.status = err.response?.status ?? null;
  out.permissionDenied = out.status === 403 || out.status === 401;

  if (err.code === 'ERR_NETWORK') {
    out.message = 'Cannot reach the server. Check your connection.';
    return out;
  }

  const data = err.response?.data;
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.code === 'string') out.code = obj.code;

    const detail = firstString(obj.detail);
    const nonField = firstString(obj.non_field_errors);
    let topMessage = detail ?? nonField ?? null;

    for (const [key, value] of Object.entries(obj)) {
      if (key === 'detail' || key === 'non_field_errors' || key === 'code') continue;
      const msg = firstString(value);
      if (msg) {
        out.fieldErrors[key] = msg;
      } else if (value && typeof value === 'object' && !Array.isArray(value)) {
        // Nested serializer errors (e.g. lines: [{qty: [...]}]) — flatten one level.
        const nested = firstString(Object.values(value as Record<string, unknown>)[0]);
        if (nested) out.fieldErrors[key] = nested;
      }
    }

    if (!topMessage) {
      const firstField = Object.entries(out.fieldErrors)[0];
      if (firstField) topMessage = `${firstField[0]}: ${firstField[1]}`;
    }
    if (topMessage) out.message = topMessage;
  }

  if (out.permissionDenied && out.message === fallback) {
    out.message = 'You do not have permission to perform this action.';
  }
  return out;
}
