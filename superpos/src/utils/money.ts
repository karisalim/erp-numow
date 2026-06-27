import { useAuthStore } from '../store/authStore';

/**
 * Format a numeric amount in the tenant's configured currency.
 *
 * The currency comes from the auth store (`AuthUser.tenant_currency`),
 * falling back to EGP when no tenant is loaded. Returned format is
 * `"<CODE> 0.00"` (e.g. `"EGP 123.45"`).
 */
export function formatMoney(amount: number | string | null | undefined, currency: string): string {
  const num = typeof amount === 'number' ? amount : Number(amount ?? 0);
  return `${currency} ${Number.isFinite(num) ? num.toFixed(2) : '0.00'}`;
}

/** Hook returning a memo-friendly formatter bound to the tenant currency. */
export function useMoney(): (amount: number | string | null | undefined) => string {
  const currency = useAuthStore((s) => s.user?.tenant_currency) || 'EGP';
  return (amount) => formatMoney(amount, currency);
}
