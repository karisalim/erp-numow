import { AxiosError } from 'axios';
import { create } from 'zustand';
import apiClient from '../api/client';
import type { AuthUser, UserRole } from '../types';

interface AuthState {
  user: AuthUser | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
  subscriptionBlocked: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  updateUser: (patch: Partial<AuthUser>) => void;
  setSubscriptionBlocked: (blocked: boolean) => void;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Backend → AuthUser adapter
 * /api/auth/login/ returns { access, refresh, user: <UserSerializer> }
 * ──────────────────────────────────────────────────────────────────────────── */
interface BackendUser {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  role: UserRole;
  is_active?: boolean;
  tenant?: number | null;
  tenant_name?: string;
  tenant_phone?: string | null;
  tenant_address?: string | null;
  tenant_logo?: string | null;
  tenant_vat_number?: string | null;
  tenant_receipt_footer?: string | null;
  tenant_currency?: string | null;
  tenant_language?: string | null;
  tenant_show_tax_on_receipt?: boolean | null;
  tenant_scale_barcode_prefix?: string | null;
  branch?: number | null;
  branch_name?: string;
  terminal?: number | null;
  terminal_name?: string;
}

function computeInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '??';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function adaptUser(u: BackendUser): AuthUser {
  const fullName = u.full_name || `${u.first_name ?? ''} ${u.last_name ?? ''}`.trim();
  const displayName = fullName || u.username;
  return {
    id: u.id,
    username: u.username,
    email: u.email,
    first_name: u.first_name ?? '',
    last_name: u.last_name ?? '',
    full_name: fullName,
    role: u.role,
    is_active: u.is_active ?? true,
    tenant: u.tenant ?? null,
    tenant_name: u.tenant_name ?? '',
    tenant_phone: u.tenant_phone ?? '',
    tenant_address: u.tenant_address ?? '',
    tenant_logo: u.tenant_logo ?? '',
    tenant_vat_number: u.tenant_vat_number ?? '',
    tenant_receipt_footer: u.tenant_receipt_footer ?? '',
    tenant_currency: u.tenant_currency ?? 'EGP',
    tenant_language: u.tenant_language ?? 'en',
    tenant_show_tax_on_receipt: u.tenant_show_tax_on_receipt ?? true,
    tenant_scale_barcode_prefix: u.tenant_scale_barcode_prefix ?? '21',
    branch: u.branch ?? null,
    branch_name: u.branch_name ?? '',
    terminal: u.terminal ?? null,
    terminal_name: u.terminal_name ?? '',
    name: displayName,
    initials: computeInitials(displayName),
  };
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Hydrate from localStorage so a page refresh doesn't kick the user out.
 * The client-side interceptor will refresh the access token if it has expired.
 * ──────────────────────────────────────────────────────────────────────────── */
function hydrate(): { user: AuthUser | null; isAuthenticated: boolean } {
  try {
    const raw = localStorage.getItem('user');
    const access = localStorage.getItem('access');
    if (!raw || !access) return { user: null, isAuthenticated: false };
    const user = JSON.parse(raw) as AuthUser;
    return { user, isAuthenticated: true };
  } catch {
    return { user: null, isAuthenticated: false };
  }
}

function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data as Record<string, unknown> | undefined;
    if (data) {
      if (typeof data.detail === 'string') return data.detail;
      // SimpleJWT returns { detail: "No active account found..." } on bad creds.
      // Some custom validators may return { non_field_errors: [...] }.
      const nonField = data.non_field_errors;
      if (Array.isArray(nonField) && nonField.length > 0 && typeof nonField[0] === 'string') {
        return nonField[0];
      }
    }
    if (err.response?.status === 401) return 'Invalid username or password.';
    if (err.code === 'ERR_NETWORK') return 'Cannot reach the server. Check your connection.';
    return err.message || 'Login failed.';
  }
  return 'Unexpected error. Please try again.';
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Zustand store
 * ──────────────────────────────────────────────────────────────────────────── */
const initial = hydrate();

export const useAuthStore = create<AuthState>((set) => ({
  user: initial.user,
  isAuthenticated: initial.isAuthenticated,
  loading: false,
  error: null,
  subscriptionBlocked: false,

  login: async (username: string, password: string) => {
    set({ loading: true, error: null });
    try {
      const { data } = await apiClient.post('/auth/login/', {
        username: username.trim(),
        password,
      });

      const access = data.access as string;
      const refresh = data.refresh as string;
      const user = adaptUser(data.user as BackendUser);

      localStorage.setItem('access', access);
      localStorage.setItem('refresh', refresh);
      localStorage.setItem('user', JSON.stringify(user));

      // Successful login = fresh session = clear any prior block flag.
      set({ user, isAuthenticated: true, loading: false, error: null, subscriptionBlocked: false });
    } catch (err) {
      const message = extractErrorMessage(err);
      set({ loading: false, error: message, user: null, isAuthenticated: false });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem('access');
    localStorage.removeItem('refresh');
    localStorage.removeItem('user');
    set({ user: null, isAuthenticated: false, error: null, subscriptionBlocked: false });
  },

  clearError: () => set({ error: null }),

  updateUser: (patch: Partial<AuthUser>) => {
    set((state) => {
      if (!state.user) return state;
      const next = { ...state.user, ...patch };
      try { localStorage.setItem('user', JSON.stringify(next)); } catch { /* quota / private mode */ }
      return { user: next };
    });
  },

  setSubscriptionBlocked: (blocked: boolean) => set({ subscriptionBlocked: blocked }),
}));

/* ─────────────────────────────────────────────────────────────────────────────
 * Listen for the global "auth-expired" event dispatched by the API client
 * when a token refresh fails (session truly dead). Triggering logout here
 * keeps the auth state consistent with localStorage no matter who detected
 * the expiry.
 * ──────────────────────────────────────────────────────────────────────────── */
if (typeof window !== 'undefined') {
  window.addEventListener('superpos:auth-expired', () => {
    useAuthStore.getState().logout();
  });
  // 403 with code=SUBSCRIPTION_EXPIRED → swap the app shell for the block
  // screen. We keep the tokens around so the user can read the message; a
  // login by another tenant is still possible from the support link.
  window.addEventListener('superpos:subscription-blocked', () => {
    useAuthStore.getState().setSubscriptionBlocked(true);
  });
}
