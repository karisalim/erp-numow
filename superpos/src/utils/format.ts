export const fmt = (n: number | string | null | undefined): string => {
  const num = typeof n === 'number' ? n : Number(n ?? 0);
  return '€' + (Number.isFinite(num) ? num.toFixed(2) : '0.00');
};

export const fmtDate = (d: Date): string =>
  d.toLocaleDateString() + ' ' + d.toLocaleTimeString();

export const initials = (name: string): string =>
  name
    .split(' ')
    .map(w => w[0])
    .slice(0, 2)
    .join('');

export const stockLabel = (stock: number, reorder: number): { label: string; kind: 'success' | 'warn' | 'danger' } => {
  if (stock === 0) return { label: 'Out', kind: 'danger' };
  if (stock < reorder) return { label: 'Low', kind: 'warn' };
  return { label: 'In stock', kind: 'success' };
};

export const methodIcon = (method: string): string => {
  if (method === 'cash') return 'cash';
  if (method === 'card') return 'card';
  return 'wallet';
};

/**
 * Pretty-print a decimal qty (stock, kg, etc.) without trailing zeros.
 * `30.000` → `"30"`, `0.500` → `"0.5"`, `1.230` → `"1.23"`.
 */
export const fmtDecimal = (n: number | string | null | undefined): string => {
  const num = typeof n === 'number' ? n : Number(n ?? 0);
  if (!Number.isFinite(num)) return '0';
  if (Number.isInteger(num)) return num.toString();
  return num.toFixed(3).replace(/\.?0+$/, '');
};
