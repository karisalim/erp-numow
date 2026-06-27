export interface ScaleBarcodeResult {
  plu: string;
  weightKg: number;
}

export const DEFAULT_SCALE_PREFIX = '21';

/**
 * Sanitize a tenant-configured scale prefix. We only accept 1–4 digit prefixes
 * (Digi defaults to "21", some German chains use "20", etc.); anything else
 * falls back to `21` so the parser stays predictable.
 */
function safePrefix(raw: string | null | undefined): string {
  const p = (raw ?? '').trim();
  if (!p) return DEFAULT_SCALE_PREFIX;
  if (!/^\d{1,4}$/.test(p)) return DEFAULT_SCALE_PREFIX;
  return p;
}

/**
 * Parse an EAN-13 weight barcode emitted by Digi-style scale label printers.
 *
 * Format: `<prefix>` + `XXXXX` (PLU) + `YYYYY` (weight in grams) + 1 check digit.
 * With the default 2-digit prefix "21": `2100041015002` → PLU "00041", 1.500 kg.
 *
 * Returns `null` when the code is not a strict 13-char EAN-13 weight form so
 * the caller can fall back to a regular barcode lookup. We deliberately do NOT
 * substitute a default weight here — the caller decides whether a zero-weight
 * scan is an error.
 */
export function parseScaleBarcode(code: string, prefix?: string | null): ScaleBarcodeResult | null {
  const p = safePrefix(prefix);
  if (code.length !== 13 || !code.startsWith(p)) return null;
  if (!/^\d{13}$/.test(code)) return null;
  // The PLU + weight payload still occupies positions 2..12 — when the prefix
  // is longer than 2 it eats into the PLU window, so we slice from `p.length`
  // and keep the remaining 5/5 split intact only for the common 2-char case.
  const payload = code.slice(p.length, 12);
  if (payload.length !== 10) return null;
  const plu = payload.slice(0, 5);
  const grams = parseInt(payload.slice(5, 10), 10);
  if (!Number.isFinite(grams)) return null;
  return { plu, weightKg: +(grams / 1000).toFixed(3) };
}

export function isScaleBarcode(code: string, prefix?: string | null): boolean {
  const p = safePrefix(prefix);
  return code.length === 13 && code.startsWith(p) && /^\d{13}$/.test(code);
}
