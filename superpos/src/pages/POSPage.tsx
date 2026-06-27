import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { usePosStore } from '../store/posStore';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import { parseScaleBarcode } from '../utils/barcode';
import { useMoney } from '../utils/money';
import type { Product, CompletedTransaction } from '../types';
import { Header } from '../components/layout/Header';
import { OfflineBanner } from '../components/layout/OfflineBanner';
import { BarcodeInput } from '../components/pos/BarcodeInput';
import { QuickProductCard } from '../components/pos/QuickProductCard';
import { CartLine } from '../components/pos/CartLine';
import { PaymentModal } from '../components/pos/PaymentModal';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Icon } from '../components/ui/Icon';

interface CategoryDto { id: number; name: string; }
interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
interface SaleResponseDto {
  id: number;
  sale_uuid?: string;
  cashier_name?: string;
  branch_name?: string;
  terminal_name?: string;
  subtotal: string | number;
  tax_amount: string | number;
  total: string | number;
  paid: string | number;
  change: string | number;
  method: 'cash' | 'card' | 'wallet';
  offline?: boolean;
  status: string;
  created_at?: string;
  warnings?: string[];
}

/** Unwrap a paginated DRF list response (or accept a bare array). */
function unwrapList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  const obj = payload as PaginatedResponse<T> | undefined;
  return obj?.results ?? [];
}

/** If the API returns 401, kick the session immediately. */
function handle401(err: unknown): boolean {
  if (err instanceof AxiosError && err.response?.status === 401) {
    useAuthStore.getState().logout();
    return true;
  }
  return false;
}

export const POSPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useAuthStore(s => s.user);
  const money = useMoney();

  const {
    cart, barcode, paymentMode, flashId, error,
    addItem, removeItem, updateQty, clearCart,
    setBarcode, setPaymentMode, setError, setReceiptTxn,
  } = usePosStore();

  const { online, pendingSync, setOnline, incrementPendingSync } = useAppStore();

  const [editing, setEditing]             = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('All');

  // ── Server-driven Quick Grid + Categories ───────────────────────────────
  const [quickGrid, setQuickGrid]   = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>(['All']);
  const [gridLoading, setGridLoading] = useState(false);

  // ── In-flight indicators for barcode lookup + sale submission ──────────
  const [barcodeLoading, setBarcodeLoading] = useState(false);
  const [saleLoading,    setSaleLoading]    = useState(false);

  // ── Sale-completion feedback ────────────────────────────────────────────
  const [saleError, setSaleError] = useState<string | null>(null);
  const [warnings,  setWarnings]  = useState<string[]>([]);
  // ── Scan-success toast (mirrors the error slot in the Listening header) ──
  const [scanInfo,  setScanInfo]  = useState<string | null>(null);

  useEffect(() => {
    if (!scanInfo) return;
    const t = setTimeout(() => setScanInfo(null), 2500);
    return () => clearTimeout(t);
  }, [scanInfo]);

  /* ─── Initial fetch: 8 products + categories ──────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setGridLoading(true);
    Promise.all([
      apiClient.get<PaginatedResponse<Product> | Product[]>('/products/', { params: { active: 'true' } }),
      apiClient.get<PaginatedResponse<CategoryDto> | CategoryDto[]>('/categories/'),
    ])
      .then(([prodRes, catRes]) => {
        if (cancelled) return;
        const allProducts = unwrapList<Product>(prodRes.data);
        const allCats     = unwrapList<CategoryDto>(catRes.data);
        setQuickGrid(allProducts.slice(0, 8));
        setCategories(['All', ...allCats.map(c => c.name)]);
      })
      .catch((err) => {
        handle401(err);
        if (cancelled) return;
        // Per spec: degrade gracefully — empty arrays, page still renders.
        setQuickGrid([]);
        setCategories(['All']);
      })
      .finally(() => { if (!cancelled) setGridLoading(false); });

    return () => { cancelled = true; };
  }, []);

  /* ─── Auto-dismiss saleError after 5s ─────────────────────────────────── */
  useEffect(() => {
    if (!saleError) return;
    const t = setTimeout(() => setSaleError(null), 5000);
    return () => clearTimeout(t);
  }, [saleError]);

  /* ─── Totals (local preview — backend recomputes authoritative values) ── */
  const subtotal = useMemo(() => cart.reduce((s, x) => s + x.qty * Number(x.price), 0), [cart]);
  const tax      = useMemo(
    () => cart.reduce((s, x) => s + x.qty * Number(x.price) * Number(x.tax ?? x.tax_rate ?? 0), 0),
    [cart],
  );
  const total = subtotal + tax;

  /* ─── Quick grid filter (client-side over the fetched 8) ──────────────── */
  const filteredGrid = useMemo(() => {
    if (activeCategory === 'All') return quickGrid;
    return quickGrid.filter(p => (p.category_name ?? p.category) === activeCategory);
  }, [quickGrid, activeCategory]);

  /* ─── Barcode submit: weight-barcode short-circuit, then regular lookup ─ */
  const submitBarcode = useCallback(async (raw: string) => {
    const code = raw.trim();
    if (!code) return;
    setError(null);
    setBarcodeLoading(true);

    try {
      // 1. EAN-13 weight barcode (`<prefix>` + 5-digit PLU + 5-digit weight + check)?
      //    Prefix comes from tenant settings; defaults to "21".
      const scale = parseScaleBarcode(code, user?.tenant_scale_barcode_prefix);
      if (scale) {
        // Weight=0 means the customer pressed "PRINT" before placing the
        // item on the platform. Don't add a 0kg line — ask for a rescan.
        if (scale.weightKg <= 0) {
          setError('Invalid weight. Rescan.');
          return;
        }

        try {
          // Resolve the PLU to a Product via the server-side filter. Limit to
          // weighted catalog entries so a stray non-weighted match can't be
          // added as a kg line. unique_together(tenant, plu) guarantees ≤1
          // result; we still pick the first defensively.
          const lookup = await apiClient.get<PaginatedResponse<Product> | Product[]>(
            '/products/', { params: { plu: scale.plu, weighted: 'true' } },
          );
          const matches = unwrapList<Product>(lookup.data);
          const prod = matches[0];

          if (!prod) {
            setError(`PLU ${scale.plu} not found in catalog.`);
            return;
          }

          if (!prod.weighted) {
            setError(`${prod.name} is not a weighted item.`);
            return;
          }

          addItem(prod, scale.weightKg);
          const lineTotal = scale.weightKg * Number(prod.price);
          setScanInfo(
            `Added ${prod.name} (${scale.weightKg.toFixed(3)} kg) — ${money(lineTotal)}`,
          );
          setBarcode('');
          return;
        } catch (err) {
          if (handle401(err)) return;
          // Treat lookup failures as a hard scale-flow error — the regular
          // barcode path would just hit the same 404 since this isn't a
          // standard product code.
          setError('Scale lookup failed. Try again.');
          return;
        }
      }

      // 2. Regular barcode lookup.
      const res = await apiClient.get<Product>(`/products/barcode/${code}/`);
      addItem(res.data);
      setBarcode('');
    } catch (err) {
      if (handle401(err)) return;
      if (err instanceof AxiosError && err.response?.status === 404) {
        setError(`No product found for "${code}"`);
      } else {
        setError('Lookup failed. Try again.');
      }
    } finally {
      setBarcodeLoading(false);
    }
  }, [addItem, money, setBarcode, setError, user?.tenant_scale_barcode_prefix]);

  /* ─── Sale completion: POST /sales/ with the cart ─────────────────────── */
  // Third arg (client-computed change) is ignored — the backend recomputes it.
  const completeSale = async (method: 'cash' | 'card' | 'wallet', paid: number, _change: number) => {
    void _change;
    if (saleLoading) return;
    setSaleError(null);

    const items = cart.map(c => ({
      product:    typeof c.id === 'number' ? c.id : Number(c.id),
      qty:        c.qty,
      price_each: Number(Number(c.price).toFixed(2)),
    }));

    const body: Record<string, unknown> = {
      method,
      paid: Number(Number(paid).toFixed(2)),
      items,
    };
    if (!online) body.offline = true;

    setSaleLoading(true);
    try {
      const { data } = await apiClient.post<SaleResponseDto>('/sales/', body);

      if (!online) incrementPendingSync();

      const txn: CompletedTransaction = {
        id:         data.sale_uuid ?? `SALE-${data.id}`,
        sale_uuid:  data.sale_uuid,
        items:      cart,
        subtotal:   Number(data.subtotal),
        tax:        Number(data.tax_amount),
        tax_amount: Number(data.tax_amount),
        total:      Number(data.total),
        method:     data.method,
        paid:       Number(data.paid),
        change:     Number(data.change),
        ts:         data.created_at ? new Date(data.created_at) : new Date(),
        cashier:    data.cashier_name || user?.name || 'Cashier',
        terminal:   data.terminal_name || user?.terminal_name || 'POS-01',
        offline:    Boolean(data.offline ?? !online),
      };

      // Close payment modal immediately so the user sees the warning toast.
      setPaymentMode(null);

      const apiWarnings = Array.isArray(data.warnings) ? data.warnings : [];
      if (apiWarnings.length > 0) {
        setWarnings(apiWarnings);
        // Hold for ~2.5s so the cashier reads the oversell notice before the receipt.
        setTimeout(() => {
          setReceiptTxn(txn);
          clearCart();
          setWarnings([]);
          navigate('/receipt');
        }, 2500);
      } else {
        setReceiptTxn(txn);
        clearCart();
        navigate('/receipt');
      }
    } catch (err) {
      if (handle401(err)) return;

      let msg = 'Failed to complete the sale. Please try again.';
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        if (typeof data?.detail === 'string') {
          msg = data.detail;
        } else if (data && typeof data === 'object') {
          // DRF field-level errors → flatten the first one for display.
          const first = Object.entries(data)[0];
          if (first) {
            const [field, value] = first;
            const text = Array.isArray(value) ? String(value[0]) : String(value);
            msg = field === 'non_field_errors' ? text : `${field}: ${text}`;
          }
        } else if (err.response?.status === 403) {
          msg = 'You do not have permission to complete sales.';
        } else if (err.response?.status === 500) {
          msg = 'Server error. The sale was not recorded. Please retry.';
        }
      }
      setSaleError(msg);
      // Per spec: don't open receipt, don't clear the cart, keep the payment modal closed
      // so the cashier can review the banner and click Proceed again.
      setPaymentMode(null);
    } finally {
      setSaleLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <Header
        title="Point of Sale"
        subtitle={`${user?.tenant_name || 'Supermarket'} · ${user?.branch_name || 'Main Branch'} · ${user?.terminal_name || 'POS-01'}`}
        online={online}
        pendingSync={pendingSync}
        right={
          <Button variant="ghost" size="sm" onClick={() => setOnline(o => !o)}>
            <Icon name={online ? 'wifi' : 'wifiOff'} size={14} />
            Toggle {online ? 'offline' : 'online'}
          </Button>
        }
      />
      {!online && <OfflineBanner pending={pendingSync} />}

      <div className="flex-1 grid grid-cols-12 gap-5 p-5 min-h-0 bg-neutral-100">
        {/* LEFT — Scan + Quick grid */}
        <section className="col-span-7 flex flex-col gap-5 min-h-0">
          {/* Sale-level banners */}
          {saleError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700"
            >
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <span className="flex-1">{saleError}</span>
              <button
                type="button"
                onClick={() => setSaleError(null)}
                className="shrink-0 hover:opacity-70 focus-ring rounded"
                aria-label="Dismiss"
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          )}
          {warnings.length > 0 && (
            <div
              role="status"
              className="flex items-start gap-2 rounded-md border border-warn-600/40 bg-warn-50 px-3 py-2.5 text-[13px] text-warn-700"
            >
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="font-semibold mb-0.5">Sale completed with {warnings.length} warning{warnings.length === 1 ? '' : 's'}:</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-2">
                Barcode Scanner <span className="text-neutral-400 normal-case font-medium">· always focused</span>
                {barcodeLoading && (
                  <span className="inline-flex items-center gap-1 normal-case font-medium text-brand-600">
                    <span className="w-3 h-3 border-2 border-brand-300 border-t-brand-600 rounded-full spin" />
                    Looking up…
                  </span>
                )}
              </label>
              {error ? (
                <span className="text-[12px] font-semibold text-danger-600 fade-in flex items-center gap-1">
                  <Icon name="alert" size={12} /> {error}
                </span>
              ) : scanInfo ? (
                <span className="text-[12px] font-semibold text-success-700 fade-in flex items-center gap-1">
                  <Icon name="check" size={12} /> {scanInfo}
                </span>
              ) : (
                <span className="text-[12px] text-neutral-500 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success-500 animate-pulse" /> Listening
                </span>
              )}
            </div>
            <BarcodeInput
              value={barcode}
              setValue={setBarcode}
              onSubmit={submitBarcode}
              error={!!error}
            />
            <div className="flex items-center gap-2 mt-2 text-[12px] text-neutral-500">
              <span>Try:</span>
              {['5410188006353', '8480000200013', '2100041015002', '9999999999'].map(b => (
                <button
                  key={b}
                  onClick={() => { setBarcode(b); submitBarcode(b); }}
                  disabled={barcodeLoading}
                  className="font-mono text-[11.5px] px-2 py-1 rounded border border-neutral-300 bg-white hover:border-brand-500 hover:text-brand-700 focus-ring disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Quick select</h3>
              <div className="flex gap-1 text-[12px] flex-wrap justify-end max-w-[60%]">
                {categories.map((c) => (
                  <button
                    key={c}
                    onClick={() => setActiveCategory(c)}
                    className={`px-2.5 py-1 rounded-md font-medium focus-ring
                      ${activeCategory === c
                        ? 'bg-neutral-900 text-white'
                        : 'text-neutral-600 hover:bg-neutral-200'
                      }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>

            {gridLoading ? (
              <div className="flex-1 grid place-items-center text-neutral-500 text-[13px]">
                <span className="inline-flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                  Loading quick grid…
                </span>
              </div>
            ) : filteredGrid.length === 0 ? (
              <div className="flex-1 grid place-items-center text-[13px] text-neutral-500">
                {quickGrid.length === 0
                  ? 'No products available.'
                  : 'No products in this category.'}
              </div>
            ) : (
              <div className="grid grid-cols-4 gap-3 overflow-auto pr-1 pb-1">
                {filteredGrid.map(p => (
                  <QuickProductCard key={String(p.id)} product={p} onAdd={(prod: Product) => addItem(prod)} />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* RIGHT — Cart */}
        <aside className="col-span-5 flex flex-col min-h-0">
          <Card className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className="px-5 h-14 border-b border-neutral-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-[15px] font-semibold">Current Sale</h2>
                <Badge kind="brand">{cart.length} {cart.length === 1 ? 'item' : 'items'}</Badge>
              </div>
              {cart.length > 0 && (
                <button
                  onClick={clearCart}
                  className="text-[12px] font-semibold text-danger-600 hover:underline flex items-center gap-1 focus-ring"
                >
                  <Icon name="trash" size={14} /> Clear cart
                </button>
              )}
            </div>

            <div className="flex-1 overflow-auto min-h-0">
              {cart.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-8 py-12">
                  <div className="w-16 h-16 rounded-full bg-neutral-100 grid place-items-center text-neutral-400 mb-3">
                    <Icon name="barcode" size={28} />
                  </div>
                  <div className="text-[15px] font-semibold text-neutral-700">Cart is empty</div>
                  <div className="text-[13px] text-neutral-500 mt-1 max-w-[260px]">
                    Scan a barcode or tap a product on the left to start a new transaction.
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-[11.5px] text-neutral-500">
                    <kbd className="px-2 py-0.5 rounded border border-neutral-300 bg-neutral-50 font-mono">F2</kbd>
                    <span>discount</span>
                    <kbd className="px-2 py-0.5 rounded border border-neutral-300 bg-neutral-50 font-mono">F8</kbd>
                    <span>payment</span>
                  </div>
                </div>
              ) : (
                cart.map(item => (
                  <CartLine
                    key={item.lineId}
                    item={item}
                    onQty={updateQty}
                    onRemove={removeItem}
                    editing={editing}
                    setEditing={setEditing}
                    flash={flashId === item.lineId}
                  />
                ))
              )}
            </div>

            {/* Totals */}
            <div className="border-t border-neutral-200 bg-neutral-50">
              <div className="px-5 py-3 space-y-1 text-[13.5px]">
                <div className="flex justify-between">
                  <span className="text-neutral-600">Subtotal</span>
                  <span className="font-mono tabular-nums">{money(subtotal)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-600">VAT</span>
                  <span className="font-mono tabular-nums">{money(tax)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-600">Discount</span>
                  <span className="font-mono tabular-nums text-neutral-400">—</span>
                </div>
              </div>
              <div className="px-5 py-3 border-t border-neutral-200 flex items-center justify-between">
                <span className="text-[13px] font-semibold uppercase tracking-wider text-neutral-500">Total</span>
                <span className="font-mono text-[28px] font-bold tabular-nums">{money(total)}</span>
              </div>
              <div className="px-4 pb-4">
                <Button
                  size="xl"
                  className="w-full text-[15px]"
                  disabled={cart.length === 0 || saleLoading}
                  onClick={() => setPaymentMode('choose')}
                >
                  {saleLoading ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full spin" />
                      Submitting sale…
                    </>
                  ) : (
                    <>Proceed to Payment <Icon name="chevR" size={18} /></>
                  )}
                </Button>
              </div>
            </div>
          </Card>
        </aside>
      </div>

      {paymentMode && (
        <PaymentModal
          mode={paymentMode}
          setMode={setPaymentMode}
          total={total}
          onComplete={completeSale}
          online={online}
        />
      )}
    </div>
  );
};
