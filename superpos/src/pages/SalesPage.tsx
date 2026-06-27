import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import { usePosStore } from '../store/posStore';
import { methodIcon } from '../utils/format';
import type {
  BadgeKind, CartItem, CompletedTransaction, PaymentMethod, Product, TransactionStatus,
} from '../types';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../components/ui/Icon';

/* ─────────────────────────────────────────────────────────────────────────────
 * Sale row — what we actually render in the table. Matches SaleListSerializer.
 * ──────────────────────────────────────────────────────────────────────────── */
interface SaleRow {
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
  status: TransactionStatus;
  offline?: boolean;
  created_at: string;
  item_count: number;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

const statusBadge = (s: TransactionStatus): { kind: BadgeKind; label: string } => {
  const lc = String(s).toLowerCase();
  if (lc === 'completed') return { kind: 'success', label: 'Completed' };
  if (lc === 'voided')    return { kind: 'danger',  label: 'Voided' };
  return                         { kind: 'warn',    label: 'Refunded' };
};

/* Today as YYYY-MM-DD in local time (no UTC drift). */
const today = (): string => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const shortId = (r: SaleRow): string =>
  r.sale_uuid ? r.sale_uuid.slice(-8).toUpperCase() : `SALE-${r.id}`;

const toNum = (n: string | number | null | undefined): number =>
  typeof n === 'number' ? n : Number(n ?? 0);

const fmtDateTime = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Sale detail response — what `/api/sales/<uuid>/` returns. Includes items.
 * ──────────────────────────────────────────────────────────────────────────── */
interface SaleItemDetail {
  id: number;
  product: number | null;
  product_name: string;
  barcode?: string;
  qty: string | number;
  price_each: string | number;
  line_total: string | number;
}

interface SaleDetail extends SaleRow {
  items: SaleItemDetail[];
  change?: string | number;
}

const extractDetail = (err: unknown, fallback: string): string => {
  if (err instanceof AxiosError) {
    const data = err.response?.data as Record<string, unknown> | undefined;
    if (typeof data?.detail === 'string') return data.detail;
  }
  return fallback;
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Transaction detail modal — wired for Void + Reprint.
 * ──────────────────────────────────────────────────────────────────────────── */
interface TxnModalProps {
  row: SaleRow;
  currency: string;
  canVoid: boolean;
  onClose: () => void;
  onVoided: (updated: SaleRow) => void;
  onToast: (kind: 'success' | 'error', msg: string) => void;
}

const TxnDetailModal: React.FC<TxnModalProps> = ({
  row, currency, canVoid, onClose, onVoided, onToast,
}) => {
  const navigate    = useNavigate();
  const setReceiptTxn = usePosStore((s) => s.setReceiptTxn);

  const [voiding,     setVoiding]     = useState(false);
  const [reprinting,  setReprinting]  = useState(false);
  const [localStatus, setLocalStatus] = useState<TransactionStatus>(row.status);

  const isVoided = String(localStatus).toLowerCase() === 'voided';
  const b = statusBadge(localStatus);
  const saleKey  = row.sale_uuid || String(row.id);

  const handleVoid = async () => {
    if (voiding || isVoided) return;
    if (!window.confirm('Are you sure you want to void this transaction?')) return;
    setVoiding(true);
    try {
      const { data } = await apiClient.post<SaleDetail>(`/sales/${saleKey}/void/`);
      const updated: SaleRow = { ...row, status: data.status };
      setLocalStatus(data.status);
      onToast('success', `Transaction ${shortId(row)} voided.`);
      onVoided(updated);
      onClose();
    } catch (err) {
      onToast('error', extractDetail(err, 'Failed to void the transaction.'));
    } finally {
      setVoiding(false);
    }
  };

  const handleReprint = async () => {
    if (reprinting) return;
    setReprinting(true);
    try {
      const { data } = await apiClient.get<SaleDetail>(`/sales/${saleKey}/`);

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

      const txn: CompletedTransaction = {
        id:         data.sale_uuid ?? `SALE-${data.id}`,
        sale_uuid:  data.sale_uuid ?? undefined,
        items,
        subtotal:   toNum(data.subtotal),
        tax:        toNum(data.tax_amount),
        tax_amount: toNum(data.tax_amount),
        total:      toNum(data.total),
        method:     data.method,
        paid:       toNum(data.paid ?? data.total),
        change:     toNum(data.change ?? 0),
        ts:         data.created_at ? new Date(data.created_at) : new Date(),
        cashier:    data.cashier_name || '—',
        terminal:   data.terminal_name || '',
        offline:    Boolean(data.offline),
      };
      setReceiptTxn(txn);
      navigate('/receipt');
    } catch (err) {
      onToast('error', extractDetail(err, 'Failed to load receipt.'));
    } finally {
      setReprinting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1100] bg-black/50 backdrop-blur-sm grid place-items-center p-6 fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-xl shadow-lg w-full max-w-[680px] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-6 h-14 border-b border-neutral-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[16px] font-semibold">Transaction {shortId(row)}</h2>
            <Badge kind={b.kind}>{b.label}</Badge>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 grid place-items-center rounded-md hover:bg-neutral-100 text-neutral-500 focus-ring"
          >
            <Icon name="x" size={18} />
          </button>
        </div>
        <div className="p-6 overflow-auto grid grid-cols-5 gap-5">
          <div className="col-span-3 receipt bg-neutral-50 border border-neutral-200 rounded-md p-5">
            <div className="text-center">
              <div className="font-bold">{row.branch_name || 'Sale receipt'}</div>
              <div className="text-[11px]">{row.terminal_name || ''}</div>
            </div>
            <div className="dashed" />
            <div className="text-[12px]">
              <div className="flex justify-between"><span>{fmtDateTime(row.created_at)}</span><span>{shortId(row)}</span></div>
              <div className="flex justify-between">
                <span>Cashier: {row.cashier_name || '—'}</span>
                <span>{row.terminal_name || ''}</span>
              </div>
            </div>
            <div className="dashed" />
            <div className="flex justify-between font-bold">
              <span>TOTAL</span><span>{currency} {toNum(row.total).toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span>Paid ({row.method.toUpperCase()})</span>
              <span>{toNum(row.paid ?? row.total).toFixed(2)}</span>
            </div>
          </div>
          <div className="col-span-2 flex flex-col gap-3">
            <Card className="p-4">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">Payment</div>
              <div className="flex items-center gap-2">
                <Icon name={methodIcon(row.method)} size={20} className="text-brand-600" />
                <span className="capitalize font-semibold">{row.method}</span>
              </div>
              <div className="mt-3 space-y-1 text-[13px]">
                <div className="flex justify-between"><span className="text-neutral-500">Items</span><span className="font-mono">{row.item_count}</span></div>
                <div className="flex justify-between"><span className="text-neutral-500">Subtotal</span><span className="font-mono">{toNum(row.subtotal).toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="text-neutral-500">VAT</span><span className="font-mono">{toNum(row.tax_amount).toFixed(2)}</span></div>
                <div className="flex justify-between font-semibold pt-1 border-t mt-1">
                  <span>Total</span>
                  <span className="font-mono">{currency} {toNum(row.total).toFixed(2)}</span>
                </div>
              </div>
            </Card>
            <Button
              variant="secondary"
              size="md"
              onClick={handleReprint}
              disabled={reprinting}
            >
              {reprinting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-neutral-300 border-t-brand-600 rounded-full spin" />
                  Loading…
                </>
              ) : (
                <><Icon name="printer" size={16} /> Reprint receipt</>
              )}
            </Button>
            {canVoid && (
              <Button
                variant="danger"
                size="md"
                onClick={handleVoid}
                disabled={voiding || isVoided || String(localStatus).toLowerCase() !== 'completed'}
              >
                {voiding ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                    Voiding…
                  </>
                ) : (
                  <><Icon name="x" size={16} /> {isVoided ? 'Voided' : 'Void transaction'}</>
                )}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
 * SalesPage
 * ──────────────────────────────────────────────────────────────────────────── */
export const SalesPage: React.FC = () => {
  const { online, pendingSync } = useAppStore();
  const currency  = useAuthStore((s) => s.user?.tenant_currency) || 'EGP';
  const role      = useAuthStore((s) => s.user?.role);
  const isCashier = role === 'Cashier';

  // Default range = today only.
  const [startDate, setStartDate] = useState<string>(today());
  const [endDate,   setEndDate]   = useState<string>(today());

  const [q,        setQ]        = useState('');
  const [method,   setMethod]   = useState('All');
  const [cashier,  setCashier]  = useState('All');

  const [sales,    setSales]    = useState<SaleRow[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [open,     setOpen]     = useState<SaleRow | null>(null);
  const [exporting, setExporting] = useState(false);
  const [toast,    setToast]    = useState<{ kind: 'success' | 'error'; msg: string } | null>(null);

  // Managers/Owners/Admins can void any sale; Cashiers may only void their own.
  const canVoid = role !== undefined;  // any authenticated role above no-role

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /* ─── Fetch sales whenever the date filters change ────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const params: Record<string, string> = {};
    if (startDate) params.start_date = startDate;
    if (endDate)   params.end_date   = endDate;
    // Server caps page size at 20 by default; ask for a larger page for the table.
    params.page_size = '100';

    apiClient.get<PaginatedResponse<SaleRow> | SaleRow[]>('/sales/', { params })
      .then((res) => {
        if (cancelled) return;
        const rows = Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        setSales(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        let msg = 'Failed to load sales.';
        if (err instanceof AxiosError && typeof err.response?.data?.detail === 'string') {
          msg = err.response.data.detail;
        }
        setError(msg);
        setSales([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [startDate, endDate]);

  /* ─── Local refinement: method, cashier, free-text search ─────────────── */
  const filtered = useMemo(() => sales.filter((t) =>
    (method === 'All' || t.method === method.toLowerCase()) &&
    (cashier === 'All' || t.cashier_name === cashier) &&
    (!q || shortId(t).toLowerCase().includes(q.toLowerCase()) || t.cashier_name.toLowerCase().includes(q.toLowerCase()))
  ), [sales, method, cashier, q]);

  /* Unique cashier names from the fetched window — feeds the cashier filter. */
  const cashierOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of sales) if (s.cashier_name) set.add(s.cashier_name);
    return ['All', ...Array.from(set).sort()];
  }, [sales]);

  /* ─── KPI tiles — derived from the currently fetched window ───────────── */
  const stats = useMemo(() => {
    const completed = sales.filter((s) => String(s.status).toLowerCase() === 'completed');
    const totalRev   = completed.reduce((sum, s) => sum + toNum(s.total), 0);
    const txnCount   = completed.length;
    const avgTxn     = txnCount ? totalRev / txnCount : 0;
    const itemsSold  = completed.reduce((sum, s) => sum + (s.item_count || 0), 0);

    const fmtMoney = (n: number) => `${currency} ${n.toFixed(2)}`;

    return [
      { l: 'Revenue (range)',  v: fmtMoney(totalRev), s: `${txnCount} transactions` },
      { l: 'Transactions',     v: String(txnCount),   s: `${itemsSold} items sold` },
      { l: 'Avg transaction',  v: fmtMoney(avgTxn),   s: `over ${txnCount || 0} sales` },
      { l: 'Voided / refunded', v: String(sales.length - completed.length), s: 'in current range' },
    ];
  }, [sales, currency]);

  /* ─── CSV export — fetch as authenticated blob, trigger a download ────── */
  const onExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const params: Record<string, string> = {};
      if (startDate) params.start_date = startDate;
      if (endDate)   params.end_date   = endDate;

      const res = await apiClient.get('/sales/export/', {
        params,
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      const tag  = (startDate && endDate) ? `_${startDate}_${endDate}` : '';
      a.download = `sales_export${tag}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      let msg = 'Failed to export CSV.';
      if (err instanceof AxiosError && typeof err.response?.data?.detail === 'string') {
        msg = err.response.data.detail;
      }
      setError(msg);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Sales"
        subtitle="Transaction history · all branches"
        online={online}
        pendingSync={pendingSync}
        right={
          <>
            <Button variant="secondary" size="sm" onClick={onExport} disabled={exporting}>
              {exporting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-neutral-300 border-t-brand-600 rounded-full spin" />
                  Exporting…
                </>
              ) : (
                <>Export CSV</>
              )}
            </Button>
            <Button size="sm">Daily report</Button>
          </>
        }
      />
      <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
        <div className="grid grid-cols-4 gap-4">
          {stats.map((s) => (
            <Card key={s.l} className="p-5">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">{s.l}</div>
              <div className="text-[24px] font-bold tabular-nums mt-1.5 font-mono">{s.v}</div>
              <div className="text-[12.5px] text-neutral-500 mt-1">{s.s}</div>
            </Card>
          ))}
        </div>

        {/* Filters */}
        <Card className="p-3 flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">From</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
            />
            <span className="text-neutral-400">→</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
            />
            <button
              type="button"
              onClick={() => { setStartDate(''); setEndDate(''); }}
              className="text-[12px] text-neutral-500 hover:text-neutral-800 underline focus-ring"
            >
              All time
            </button>
          </div>
          <select value={method} onChange={(e) => setMethod(e.target.value)} className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring">
            <option>All</option><option>Cash</option><option>Card</option><option>Wallet</option>
          </select>
          {!isCashier && (
            <select value={cashier} onChange={(e) => setCashier(e.target.value)} className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring">
              {cashierOptions.map((c) => <option key={c}>{c}</option>)}
            </select>
          )}
          <div className="relative flex-1 min-w-[220px]">
            <Icon name="search" size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by ID or cashier…"
              className="w-full h-10 ps-9 pe-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            />
          </div>
        </Card>

        {error && (
          <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            {error}
          </div>
        )}

        {/* Table */}
        <Card className="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div className="overflow-auto flex-1">
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">ID</th>
                  <th className="text-start font-semibold">Date & Time</th>
                  {!isCashier && <th className="text-start font-semibold">Cashier</th>}
                  <th className="text-end font-semibold">Items</th>
                  <th className="text-start font-semibold ps-4">Method</th>
                  <th className="text-end font-semibold">Total</th>
                  <th className="px-4 text-start font-semibold">Status</th>
                  <th className="px-4 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={isCashier ? 7 : 8} className="px-4 py-10 text-center text-neutral-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                        Loading sales…
                      </span>
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={isCashier ? 7 : 8} className="px-4 py-10 text-center text-neutral-500">
                      No sales match the current filters.
                    </td>
                  </tr>
                ) : (
                  filtered.map((t) => {
                    const b = statusBadge(t.status);
                    return (
                      <tr
                        key={t.id}
                        onClick={() => setOpen(t)}
                        className="border-t border-neutral-100 hover:bg-neutral-50 cursor-pointer"
                        style={{ height: 36 }}
                      >
                        <td className="px-4 font-mono text-[12.5px] font-semibold text-brand-700">{shortId(t)}</td>
                        <td className="font-mono text-[12.5px] text-neutral-600">{fmtDateTime(t.created_at)}</td>
                        {!isCashier && <td className="font-medium">{t.cashier_name || '—'}</td>}
                        <td className="text-end font-mono tabular-nums">{t.item_count}</td>
                        <td className="ps-4">
                          <span className="inline-flex items-center gap-1.5 capitalize">
                            <Icon name={methodIcon(t.method)} size={14} className="text-neutral-500" />
                            {t.method}
                          </span>
                        </td>
                        <td className="text-end font-mono tabular-nums font-semibold">
                          {currency} {toNum(t.total).toFixed(2)}
                        </td>
                        <td className="px-4"><Badge kind={b.kind}>{b.label}</Badge></td>
                        <td className="px-4 text-end">
                          <button className="w-7 h-7 grid place-items-center rounded text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 focus-ring">⋮</button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="px-4 h-12 border-t border-neutral-200 flex items-center justify-between text-[12.5px] text-neutral-500">
            <span>Showing <b className="text-neutral-700">{filtered.length}</b> of {sales.length}</span>
            <div className="flex items-center gap-1">
              <button className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring" disabled>Previous</button>
              <span className="px-2">Page 1 of 1</span>
              <button className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring" disabled>Next</button>
            </div>
          </div>
        </Card>
      </div>
      {toast && (
        <div
          role={toast.kind === 'success' ? 'status' : 'alert'}
          className={`fixed bottom-6 right-6 z-[1200] rounded-md border px-3 py-2.5 text-[13px] shadow-md flex items-start gap-2 fade-in ${
            toast.kind === 'success'
              ? 'border-success-500/30 bg-success-50 text-success-700'
              : 'border-danger-500/30 bg-danger-50 text-danger-700'
          }`}
        >
          <Icon name={toast.kind === 'success' ? 'check' : 'alert'} size={16} className="mt-0.5 shrink-0" />
          <span className="flex-1">{toast.msg}</span>
          <button onClick={() => setToast(null)} className="shrink-0 hover:opacity-70 focus-ring rounded" aria-label="Dismiss">
            <Icon name="x" size={14} />
          </button>
        </div>
      )}
      {open && (
        <TxnDetailModal
          row={open}
          currency={currency}
          canVoid={canVoid}
          onClose={() => setOpen(null)}
          onVoided={(updated) => {
            setSales((rows) => rows.map((r) => (r.id === updated.id ? { ...r, status: updated.status } : r)));
          }}
          onToast={(kind, msg) => setToast({ kind, msg })}
        />
      )}
    </div>
  );
};
