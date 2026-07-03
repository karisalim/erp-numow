import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

// Single env-driven API base shared with utils/media.ts (VITE_API_URL).
// Falls back to the local dev backend so `npm run dev` keeps working
// without a .env file.
const ENV_API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '';
const API_URL = ENV_API_URL.replace(/\/$/, '') || 'http://127.0.0.1:8000/api';

const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

/* ─────────────────────────────────────────────────────────────────────────────
 * Request interceptor — attach Bearer token from localStorage.
 * ──────────────────────────────────────────────────────────────────────────── */
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

/* ─────────────────────────────────────────────────────────────────────────────
 * Response interceptor — on 401, try to refresh the access token once and
 * retry the original request. If refresh fails, clear tokens and emit a
 * global "auth-expired" event so the auth store can react (e.g. redirect
 * to /login).
 *
 * Concurrent 401s share a single refresh promise so we don't spawn
 * multiple refresh calls in parallel.
 * ──────────────────────────────────────────────────────────────────────────── */
type Retriable = InternalAxiosRequestConfig & { _retry?: boolean };
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  const refresh = localStorage.getItem('refresh');
  if (!refresh) throw new Error('No refresh token');

  refreshPromise = axios
    .post(`${API_URL}/auth/token/refresh/`, { refresh })
    .then((r) => {
      const access = r.data.access as string;
      localStorage.setItem('access', access);
      // SimpleJWT rotates refresh tokens — store the new one if returned.
      if (r.data.refresh) localStorage.setItem('refresh', r.data.refresh);
      return access;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as Retriable | undefined;

    // ── Subscription / activation block from SubscriptionCheckMiddleware ──
    if (error.response?.status === 403) {
      const data = error.response.data as { code?: string } | undefined;
      if (data?.code === 'SUBSCRIPTION_EXPIRED') {
        // Tell the auth store to swap the app shell for the block screen.
        // The event listener lives in authStore so we stay free of cyclic
        // imports here.
        window.dispatchEvent(new Event('superpos:subscription-blocked'));
        return Promise.reject(error);
      }
    }

    if (!original || error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    // Don't try to refresh while authenticating — that's a real credential failure.
    const url = original.url ?? '';
    if (url.includes('/auth/login/') || url.includes('/auth/token/refresh/')) {
      return Promise.reject(error);
    }

    try {
      original._retry = true;
      const newToken = await refreshAccessToken();
      original.headers.Authorization = `Bearer ${newToken}`;
      return apiClient.request(original);
    } catch {
      // Refresh failed — session is dead.
      localStorage.removeItem('access');
      localStorage.removeItem('refresh');
      localStorage.removeItem('user');
      window.dispatchEvent(new Event('superpos:auth-expired'));
      return Promise.reject(error);
    }
  },
);

export default apiClient;
