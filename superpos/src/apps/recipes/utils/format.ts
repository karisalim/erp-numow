/**
 * Pure display formatting only — no cost, margin, or quantity MATH lives
 * here. Every number these functions format is already computed server-
 * side; this file just decides how many decimals / what separator to show.
 */

/** `qty_base` (a Decimal(14,4) string) trimmed to a readable quantity —
 * display only, the value itself is never recomputed. */
export function formatQty(value: string | number | null | undefined, unitLabel?: string): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return '—';
  // Trim trailing zeros but keep up to 3 decimals — matches this codebase's
  // existing qty-display convention (WarehousesPage, PurchaseCreatePage).
  const text = num % 1 === 0 ? num.toFixed(0) : num.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  return unitLabel ? `${text} ${unitLabel}` : text;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}
