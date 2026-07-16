import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import { posApi } from '../api/pos';
import { priceTiersApi, asResults } from '../api/erp';
import { previewUnitPrice } from '../utils/pricing';
import { productVisual } from '../utils/categoryVisual';
import { usePosStore } from '../store/posStore';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import { useMoney } from '../utils/money';
import { useDebounced } from '../hooks/useQuery';
import type { Product, CompletedTransaction } from '../types';
import type { PriceTier } from '../types/erp';
import { Header } from '../components/layout/Header';
import { OfflineBanner } from '../components/layout/OfflineBanner';
import { BarcodeInput } from '../components/pos/BarcodeInput';
import { QuickProductCard } from '../components/pos/QuickProductCard';
import { CartLine } from '../components/pos/CartLine';
import { PaymentModal } from '../components/pos/PaymentModal';
import { CustomerSelectModal } from '../components/pos/CustomerSelectModal';
import { DiscountModal } from '../components/pos/DiscountModal';
import { UnitPickerModal } from '../components/pos/UnitPickerModal';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Icon } from '../components/ui/Icon';
import { SearchField } from '../components/ui/FormField';
import type { SaleItemPayload } from '../api/pos';

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
    customer, discountType, discountValue, priceTierId,
    addItem, removeItem, updateQty, clearCart,
    setBarcode, setPaymentMode, setError, setReceiptTxn,
    setCustomer, setDiscount, setPriceTier,
  } = usePosStore();

  const online = useAppStore((s) => s.online);

  const [editing, setEditing]             = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('All');
  const [customerModal, setCustomerModal] = useState(false);
  const [discountModal, setDiscountModal] = useState(false);
  const [unitPickerProduct, setUnitPickerProduct] = useState<Product | null>(null);

  // ── Server-driven Quick Grid + Categories (always show_on_pos=true) ────
  const [quickGrid, setQuickGrid]   = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>(['All']);
  const [gridLoading, setGridLoading] = useState(false);

  // ── Product search (server-side, replaces the quick grid while active) ─
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounced(search, 300);
  const [searchResults, setSearchResults] = useState<Product[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // ── Price tiers ──────────────────────────────────────────────────────
  const [priceTiers, setPriceTiers] = useState<PriceTier[]>([]);

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

  /* ─── Initial fetch: 8 POS-visible products + categories + price tiers ── */
  useEffect(() => {
    let cancelled = false;
    setGridLoading(true);
    Promise.all([
      posApi.listPosProducts(),
      posApi.listCategories(),
      priceTiersApi.list({ is_active: 'true' }),
    ])
      .then(([allProducts, allCats, tiers]) => {
        if (cancelled) return;
        setQuickGrid(allProducts.slice(0, 8));
        setCategories(['All', ...allCats.map(c => c.name)]);
        setPriceTiers(asResults(tiers));
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

  /* ─── Product search: server-side, replaces the grid while a query is set ── */
  useEffect(() => {
    if (!debouncedSearch.trim()) {
      setSearchResults([]);
      return;
    }
    let cancelled = false;
    setSearchLoading(true);
    posApi.listPosProducts({ search: debouncedSearch.trim() })
      .then((results) => { if (!cancelled) setSearchResults(results.slice(0, 24)); })
      .catch((err) => { handle401(err); if (!cancelled) setSearchResults([]); })
      .finally(() => { if (!cancelled) setSearchLoading(false); });
    return () => { cancelled = true; };
  }, [debouncedSearch]);

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
  // Mirror the backend discount rule exactly: percent applies to the
  // pre-tax subtotal; fixed subtracts from the invoice total.
  const discountAmount = useMemo(() => {
    if (discountType === 'percent') return (subtotal * discountValue) / 100;
    if (discountType === 'fixed') return discountValue;
    return 0;
  }, [discountType, discountValue, subtotal]);
  const total = Math.max(0, subtotal + tax - discountAmount);

  /* ─── Keyboard shortcuts: F2 discount, F8 payment ─────────────────────── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'F2') {
        e.preventDefault();
        if (cart.length > 0) setDiscountModal(true);
      } else if (e.key === 'F8') {
        e.preventDefault();
        if (cart.length > 0) setPaymentMode('choose');
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [cart.length, setPaymentMode]);

  /* ─── Quick grid filter (client-side over the fetched 8, search off) ──── */
  const filteredGrid = useMemo(() => {
    if (activeCategory === 'All') return quickGrid;
    return quickGrid.filter(p => (p.category_name ?? p.category) === activeCategory);
  }, [quickGrid, activeCategory]);

  const isSearching = debouncedSearch.trim().length > 0;
  const displayedGrid = isSearching ? searchResults : filteredGrid;

  /* ─── Barcode submit: /products/scan/ handles weight-encoded + unit
   *     resolution server-side (single source of truth — no client-side
   *     duplication of the scale-barcode decode or scan precedence rules). */
  const submitBarcode = useCallback(async (raw: string) => {
    const code = raw.trim();
    if (!code) return;
    setError(null);
    setBarcodeLoading(true);

    try {
      const result = await posApi.scanBarcode(code);

      if (result.type === 'weight_encoded') {
        const qty = Number(result.quantity);
        if (qty <= 0) {
          setError('Invalid weight. Rescan.');
          return;
        }
        addItem(result.product, qty);
        setScanInfo(`Added ${result.product.name} (${qty.toFixed(3)} kg) — ${money(Number(result.line_total))}`);
        setBarcode('');
        return;
      }

      // type === 'barcode'
      const { product, product_unit } = result;
      if (product_unit && !product_unit.is_base) {
        const displayPrice = await previewUnitPrice(
          Number(product.id), product_unit.id, priceTierId, Number(product.price),
        );
        addItem(product, 1, {
          productUnitId: product_unit.id,
          unitLabel: product_unit.unit_name,
          displayPrice,
        });
        setScanInfo(`Added ${product.name} (${product_unit.unit_name}) — ${money(displayPrice)}`);
      } else {
        addItem(product);
        setScanInfo(`Added ${product.name}`);
      }
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
  }, [addItem, money, priceTierId, setBarcode, setError]);

  /* ─── Idempotency key: one per checkout attempt ───────────────────────── */
  // Generated lazily on the first submit of a cart and reused on retries, so
  // a double-click or a retried request after a network hiccup can never
  // create two sales. Cleared only after the backend confirms success.
  const idemKeyRef = useRef<string | null>(null);

  /* ─── Sale completion: POST /sales/ with the cart ─────────────────────── */
  // Third arg (client-computed change) is ignored — the backend recomputes it.
  const completeSale = async (method: 'cash' | 'card' | 'wallet' | 'credit', paid: number, _change: number) => {
    void _change;
    if (saleLoading) return;
    setSaleError(null);

    const items: SaleItemPayload[] = cart.map(c => {
      const productId = typeof c.id === 'number' ? c.id : Number(c.id);
      // Unit-aware line: send product_unit + entered_qty, server derives
      // qty/price_each — never send price_each ourselves for these.
      if (c.productUnitId) {
        return { product: productId, product_unit: c.productUnitId, entered_qty: c.qty };
      }
      // Legacy base-unit shape, unchanged.
      return { product: productId, qty: c.qty, price_each: Number(Number(c.price).toFixed(2)) };
    });

    const body: Record<string, unknown> = {
      method,
      paid: Number(Number(paid).toFixed(2)),
      items,
    };
    if (customer) body.customer = customer.id;
    if (priceTierId != null) body.price_tier = priceTierId;
    if (discountType && discountValue > 0) {
      body.discount_type = discountType;
      body.discount_value = Number(discountValue.toFixed(2));
    }

    if (!idemKeyRef.current) idemKeyRef.current = crypto.randomUUID();

    setSaleLoading(true);
    try {
      const data = await posApi.createSale(body as never, idemKeyRef.current);
      idemKeyRef.current = null;

      // Invoice discount from the backend's own numbers, so the receipt
      // matches the posted document exactly.
      const backendDiscount = +(Number(data.subtotal) + Number(data.tax_amount) - Number(data.total)).toFixed(2);

      const txn: CompletedTransaction = {
        id:         data.sale_uuid ?? `SALE-${data.id}`,
        sale_uuid:  data.sale_uuid,
        items:      cart,
        subtotal:   Number(data.subtotal),
        tax:        Number(data.tax_amount),
        tax_amount: Number(data.tax_amount),
        discount:   backendDiscount > 0 ? backendDiscount : undefined,
        total:      Number(data.total),
        method:     data.method,
        paid:       Number(data.paid),
        change:     Number(data.change),
        ts:         data.created_at ? new Date(data.created_at) : new Date(),
        cashier:    data.cashier_name || user?.name || 'Cashier',
        terminal:   data.terminal_name || user?.terminal_name || 'POS-01',
        customer_name: customer?.name,
        offline:    false,
      };

      // Close payment modal immediately so the user sees the warning toast.
      setPaymentMode(null);

      // Durable receipt URL — a refresh on the receipt page refetches the
      // sale by UUID instead of losing the transaction.
      const receiptPath = data.sale_uuid ? `/receipt/${data.sale_uuid}` : '/receipt';

      const apiWarnings = Array.isArray(data.warnings) ? data.warnings : [];
      if (apiWarnings.length > 0) {
        setWarnings(apiWarnings);
        // Hold for ~2.5s so the cashier reads the oversell notice before the receipt.
        setTimeout(() => {
          setReceiptTxn(txn);
          clearCart();
          setWarnings([]);
          navigate(receiptPath);
        }, 2500);
      } else {
        setReceiptTxn(txn);
        clearCart();
        navigate(receiptPath);
      }
    } catch (err) {
      if (handle401(err)) return;

      let msg = 'Failed to complete the sale. Please try again.';
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        const errObj = data?.error as { code?: string; detail?: string } | undefined;
        if (err.response?.status === 409 && errObj?.code === 'IDEMPOTENCY_CONFLICT') {
          // Same key, different payload — the original submit very likely
          // succeeded but its response was lost. Don't blind-retry.
          msg = 'This sale may have already been recorded. Check the Sales screen before retrying.';
        } else if (typeof data?.payment === 'string' || Array.isArray(data?.payment)) {
          // Ledger routing/config failure — the sale was rolled back.
          const text = Array.isArray(data.payment) ? String(data.payment[0]) : String(data.payment);
          msg = `Payment routing error — the sale was NOT recorded: ${text} ` +
            'A manager can fix this under Finance → Branch routing.';
        } else if (Array.isArray(data?.code) ? data.code[0] === 'credit_limit_exceeded' : data?.code === 'credit_limit_exceeded') {
          const detail = Array.isArray(data?.customer) ? String(data.customer[0]) : 'Credit limit exceeded.';
          msg = `${detail} The sale was not recorded.`;
        } else if (typeof data?.detail === 'string') {
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
      />
      {!online && <OfflineBanner />}

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 p-5 min-h-0 bg-neutral-100 overflow-y-auto lg:overflow-hidden">
        {/* LEFT — Scan + Search + Quick grid */}
        <section className="lg:col-span-7 flex flex-col gap-5 min-h-0">
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
          </div>

          <div className="flex items-center gap-3">
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder="Search products by name, barcode or SKU…"
              className="flex-1"
            />
            {priceTiers.length > 0 && (
              <select
                value={priceTierId ?? ''}
                onChange={(e) => setPriceTier(e.target.value ? Number(e.target.value) : null)}
                className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[13.5px] focus-ring shrink-0"
                aria-label="Price tier"
                title="Price tier applied to unit-aware lines"
              >
                <option value="">Retail (default)</option>
                {priceTiers.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            )}
          </div>

          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">
                {isSearching ? `Search results${searchLoading ? '…' : ` (${searchResults.length})`}` : 'Quick select'}
              </h3>
              {!isSearching && (
                <div className="flex gap-1.5 text-[12px] flex-wrap justify-end max-w-[65%]">
                  {categories.map((c) => {
                    const active = activeCategory === c;
                    const { emoji, gradient } = c === 'All'
                      ? { emoji: '🗂️', gradient: 'from-neutral-700 to-neutral-900' }
                      : productVisual(c, c);
                    return (
                      <button
                        key={c}
                        onClick={() => setActiveCategory(c)}
                        className={`px-3 py-1.5 rounded-full font-semibold inline-flex items-center gap-1.5 focus-ring transition-all
                          ${active
                            ? `bg-gradient-to-br ${gradient} text-white shadow-sm`
                            : 'bg-white border border-neutral-200 text-neutral-600 hover:border-neutral-300 hover:bg-neutral-50'
                          }`}
                      >
                        <span aria-hidden>{emoji}</span>
                        {c}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {(isSearching ? searchLoading : gridLoading) ? (
              <div className="flex-1 grid place-items-center text-neutral-500 text-[13px]">
                <span className="inline-flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                  {isSearching ? 'Searching…' : 'Loading quick grid…'}
                </span>
              </div>
            ) : displayedGrid.length === 0 ? (
              <div className="flex-1 grid place-items-center text-[13px] text-neutral-500">
                {isSearching
                  ? `No products match "${debouncedSearch}".`
                  : quickGrid.length === 0
                    ? 'No products available.'
                    : 'No products in this category.'}
              </div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 xl:grid-cols-5 gap-3 overflow-auto pr-1 pb-1">
                {displayedGrid.map(p => (
                  <QuickProductCard
                    key={String(p.id)}
                    product={p}
                    onAdd={(prod: Product) => addItem(prod)}
                    onPickUnit={(prod: Product) => setUnitPickerProduct(prod)}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        {/* RIGHT — Cart */}
        <aside className="lg:col-span-5 flex flex-col min-h-0">
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

            {/* Customer + discount controls */}
            <div className="px-5 py-2.5 border-b border-neutral-200 flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setCustomerModal(true)}
                className={`h-8 px-3 rounded-md border text-[12.5px] font-semibold inline-flex items-center gap-1.5 focus-ring
                  ${customer
                    ? 'bg-brand-50 border-brand-500/40 text-brand-700'
                    : 'bg-white border-neutral-300 text-neutral-600 hover:bg-neutral-50'}`}
              >
                <Icon name="user" size={14} />
                {customer ? customer.name : 'Customer: Walk-in'}
              </button>
              {customer && (
                <button
                  onClick={() => setCustomer(null)}
                  aria-label="Clear customer"
                  className="w-7 h-7 grid place-items-center rounded-md text-neutral-400 hover:bg-neutral-100 focus-ring"
                >
                  <Icon name="x" size={13} />
                </button>
              )}
              <button
                onClick={() => cart.length > 0 && setDiscountModal(true)}
                disabled={cart.length === 0}
                className={`h-8 px-3 rounded-md border text-[12.5px] font-semibold inline-flex items-center gap-1.5 focus-ring disabled:opacity-40
                  ${discountType
                    ? 'bg-warn-50 border-warn-500/40 text-warn-700'
                    : 'bg-white border-neutral-300 text-neutral-600 hover:bg-neutral-50'}`}
              >
                <Icon name="tag" size={14} />
                {discountType
                  ? discountType === 'percent' ? `Discount ${discountValue}%` : `Discount ${money(discountValue)}`
                  : 'Discount'}
                <kbd className="ms-1 px-1 rounded border border-current/30 text-[10px] font-mono">F2</kbd>
              </button>
            </div>

            <div className="flex-1 overflow-auto min-h-0">
              {cart.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-8 py-12">
                  <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-50 to-violet-50 grid place-items-center text-4xl mb-3 shadow-inner">
                    <span aria-hidden>🛒</span>
                  </div>
                  <div className="text-[15px] font-semibold text-neutral-700">Cart is empty</div>
                  <div className="text-[13px] text-neutral-500 mt-1 max-w-[260px]">
                    Scan a barcode, search, or tap a product on the left to start a new transaction.
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
                  <span className="text-neutral-600">
                    Discount{discountType === 'percent' ? ` (${discountValue}%)` : ''}
                  </span>
                  {discountAmount > 0 ? (
                    <span className="font-mono tabular-nums text-warn-700">−{money(discountAmount)}</span>
                  ) : (
                    <span className="font-mono tabular-nums text-neutral-400">—</span>
                  )}
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
          customer={customer}
          onComplete={completeSale}
          onSelectCustomer={() => { setPaymentMode(null); setCustomerModal(true); }}
          online={online}
        />
      )}

      {customerModal && (
        <CustomerSelectModal
          current={customer}
          onSelect={setCustomer}
          onClose={() => setCustomerModal(false)}
        />
      )}

      {discountModal && (
        <DiscountModal
          subtotal={subtotal}
          currentType={discountType}
          currentValue={discountValue}
          onApply={setDiscount}
          onClose={() => setDiscountModal(false)}
        />
      )}

      {unitPickerProduct && (
        <UnitPickerModal
          product={unitPickerProduct}
          priceTierId={priceTierId}
          onClose={() => setUnitPickerProduct(null)}
          onConfirm={(qty, unit) => {
            addItem(unitPickerProduct, qty, unit);
            setUnitPickerProduct(null);
          }}
        />
      )}
    </div>
  );
};
