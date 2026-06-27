/**
 * Build an absolute URL for media (e.g. tenant logos) the backend serves.
 *
 * DRF can return either an absolute URL (when the serializer has a request
 * context) or a relative path like `/media/tenant_logos/foo.png`. The latter
 * breaks when the React dev server (port 5173) tries to load it as a same-
 * origin resource. This helper normalises both shapes by prepending the
 * backend base URL whenever the value is not already absolute.
 *
 * The backend host is derived from `VITE_API_URL` (with the trailing `/api`
 * stripped) and falls back to the local dev backend.
 */

const ENV_API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '';
const API_BASE    = ENV_API_URL.replace(/\/api\/?$/, '') || 'http://127.0.0.1:8000';

export function absoluteMediaUrl(url?: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url.startsWith('/') ? '' : '/'}${url}`;
}
