import type { CartItem, CompletedTransaction, PaymentMethod, Product, TransactionStatus } from '../types';

/* ─────────────────────────────────────────────────────────────────────────────
 * Sale detail response — what `/api/sales/<uuid>/` returns. Shared between
 * SalesPage (reprint) and ReceiptPage (durable fetch by UUID).
 * ──────────────────────────────────────────────────────────────────────────── */
export interface SaleItemDetail {
  id: number;
  product: number | null;
  product_name: string;
  barcode?: string;
  qty: string | number;
  price_each: string | number;
  line_total: string | number;
}

export interface SaleDetail {
  id: number;
  sale_uuid?: string | null;
  cashier_name: string;
  branch_name?: string;
  terminal_name?: string;
  subtotal: string | number;
  tax_amount: string | number;
  total: string | number;
  method: PaymentMethod;
  paid?: string | number;
  change?: string | number;
  status: TransactionStatus;
  offline?: boolean;
  created_at: string;
  item_count: number;
  items: SaleItemDetail[];
}

const toNum = (n: string | number | null | undefined): number =>
  typeof n === 'number' ? n : Number(n ?? 0);

/** Rebuild a receipt-renderable transaction from a sale detail response. */
export function saleDetailToTxn(data: SaleDetail): CompletedTransaction {
  const items: CartItem[] = data.items.map((it, i) => {
    const price = toNum(it.price_each);
    // We don't have the original Product on hand — build a minimal one
    // that satisfies the receipt renderer (name, price, weighted=false).
    const product: Product = {
      id:       it.product ?? `legacy-${it.id}`,
      barcode:  it.barcode ?? '',
      sku:      it.barcode ?? '',
      name:     it.product_name,
      category: null,
      price,
      cost:     0,
      stock:    0,
      reorder:  0,
      color:    '#6B7280',
    };
    return { ...product, lineId: `L${i + 1}`, qty: toNum(it.qty) };
  });

  // Invoice discount is not itemised in the response — derive it from the
  // backend's own totals (subtotal + tax − total) so the receipt matches
  // exactly what was posted.
  const discount = +(toNum(data.subtotal) + toNum(data.tax_amount) - toNum(data.total)).toFixed(2);

  return {
    id:         data.sale_uuid ?? `SALE-${data.id}`,
    sale_uuid:  data.sale_uuid ?? undefined,
    items,
    subtotal:   toNum(data.subtotal),
    tax:        toNum(data.tax_amount),
    tax_amount: toNum(data.tax_amount),
    discount:   discount > 0 ? discount : undefined,
    total:      toNum(data.total),
    method:     data.method,
    paid:       toNum(data.paid ?? data.total),
    change:     toNum(data.change ?? 0),
    ts:         data.created_at ? new Date(data.created_at) : new Date(),
    cashier:    data.cashier_name || '—',
    terminal:   data.terminal_name || '',
    offline:    Boolean(data.offline),
  };
}
