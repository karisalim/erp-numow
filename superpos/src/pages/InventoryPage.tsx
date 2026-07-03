import React, { useEffect, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { fmtDecimal } from '../utils/format';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../components/ui/Icon';
import { GlobalReceiveStockModal } from '../components/inventory/GlobalReceiveStockModal';
import type { BadgeKind } from '../types';

interface StockMovement {
  id: number;
  product: number;
  product_name: string;
  qty: string | number;
  movement_type: string;
  movement_type_display?: string;
  note?: string;
  created_at: string;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

type Toast = { kind: 'success' | 'error'; message: string };

const PAGE_SIZE = 20;

const MOVEMENT_TYPES: { value: string; label: string }[] = [
  { value: '',            label: 'All types'    },
  { value: 'sale_out',    label: 'Sale out'     },
  { value: 'purchase_in', label: 'Purchase in'  },
  { value: 'receive_in',  label: 'Receive in'   },
  { value: 'return_in',   label: 'Return in'    },
  { value: 'adjustment',  label: 'Adjustment'   },
];

const fmtDateTime = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
};

const fmtSignedQty = (q: string | number): string => {
  const n = typeof q === 'number' ? q : Number(q);
  if (!Number.isFinite(n)) return String(q);
  const tidy = fmtDecimal(Math.abs(n));
  return n > 0 ? `+${tidy}` : n < 0 ? `-${tidy}` : tidy;
};

const typeBadge = (type: string): { kind: BadgeKind; label: string } => {
  switch (type) {
    case 'sale_out':    return { kind: 'danger',  label: 'Sale out' };
    case 'purchase_in': return { kind: 'success', label: 'Purchase in' };
    case 'receive_in':  return { kind: 'success', label: 'Receive in' };
    case 'return_in':   return { kind: 'warn',    label: 'Return in' };
    case 'adjustment':  return { kind: 'info',    label: 'Adjustment' };
    default:            return { kind: 'gray',    label: type };
  }
};

export const InventoryPage: React.FC = () => {

  // ── Filter + pagination state ──────────────────────────────────────────
  const [startDate, setStartDate] = useState<string>('');
  const [endDate,   setEndDate]   = useState<string>('');
  const [type,      setType]      = useState<string>('');
  const [page,      setPage]      = useState(1);

  // ── Data state ─────────────────────────────────────────────────────────
  const [movements, setMovements] = useState<StockMovement[]>([]);
  const [total,     setTotal]     = useState(0);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const [receiving, setReceiving] = useState(false);
  const [toast,     setToast]     = useState<Toast | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Reset to page 1 whenever a filter changes.
  useEffect(() => { setPage(1); }, [startDate, endDate, type]);

  /* ─── Fetch movements page ───────────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const params: Record<string, string | number> = {
      page,
      page_size: PAGE_SIZE,
      ordering:  '-created_at',
    };
    if (startDate) params.start_date    = startDate;
    if (endDate)   params.end_date      = endDate;
    if (type)      params.movement_type = type;

    apiClient
      .get<PaginatedResponse<StockMovement> | StockMovement[]>('/stock-movements/', { params })
      .then((res) => {
        if (cancelled) return;
        if (Array.isArray(res.data)) {
          setMovements(res.data);
          setTotal(res.data.length);
        } else {
          setMovements(res.data?.results ?? []);
          setTotal(res.data?.count ?? 0);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        let msg = 'Failed to load stock movements.';
        if (err instanceof AxiosError) {
          if (err.response?.status === 403) msg = 'You do not have permission to view inventory.';
          else if (typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
        }
        setError(msg);
        setMovements([]);
        setTotal(0);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [page, startDate, endDate, type, refreshKey]);

  /* ─── Auto-dismiss toast ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const pageCount    = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstIndex   = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastIndex    = Math.min(page * PAGE_SIZE, total);
  const hasFilters   = !!(startDate || endDate || type);
  const clearFilters = () => {
    setStartDate('');
    setEndDate('');
    setType('');
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Inventory"
        subtitle="Global stock movements ledger"
        right={
          <Button size="sm" onClick={() => setReceiving(true)}>
            <Icon name="plus" size={14} /> Receive stock
          </Button>
        }
      />

      <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
        {toast && (
          <div
            role={toast.kind === 'success' ? 'status' : 'alert'}
            className={`flex items-start gap-2 rounded-md border px-3 py-2.5 text-[13px] ${
              toast.kind === 'success'
                ? 'border-success-600/30 bg-success-50 text-success-700'
                : 'border-danger-500/30 bg-danger-50 text-danger-700'
            }`}
          >
            <Icon name={toast.kind === 'success' ? 'check' : 'alert'} size={16} className="mt-0.5 shrink-0" />
            <span className="flex-1">{toast.message}</span>
            <button onClick={() => setToast(null)} className="shrink-0 hover:opacity-70 focus-ring rounded" aria-label="Dismiss">
              <Icon name="x" size={14} />
            </button>
          </div>
        )}

        {/* Filters */}
        <Card className="p-3 flex items-center gap-3 flex-wrap">
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
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Type</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            >
              {MOVEMENT_TYPES.map((opt) => (
                <option key={opt.value || 'all'} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-[12px] text-neutral-500 hover:text-neutral-800 underline focus-ring"
            >
              Clear filters
            </button>
          )}

          <div className="ms-auto">
            <button
              type="button"
              onClick={() => setRefreshKey((k) => k + 1)}
              className="text-[12px] text-neutral-600 hover:text-neutral-900 inline-flex items-center gap-1 focus-ring rounded"
            >
              <Icon name="sync" size={14} /> Refresh
            </button>
          </div>
        </Card>

        {error && (
          <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            {error}
          </div>
        )}

        <Card className="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div className="px-5 h-14 border-b border-neutral-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-semibold">Stock movements</h2>
              <Badge kind="brand">{total}</Badge>
            </div>
            <div className="text-[12px] text-neutral-500">
              {total > 0 ? <>Showing <b className="text-neutral-700">{firstIndex}–{lastIndex}</b> of {total}</> : '—'}
            </div>
          </div>

          <div className="overflow-auto flex-1">
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">Date</th>
                  <th className="text-start font-semibold">Product</th>
                  <th className="text-start font-semibold">Type</th>
                  <th className="text-end font-semibold">Qty</th>
                  <th className="text-start font-semibold ps-4 pe-4">Note</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-neutral-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                        Loading movements…
                      </span>
                    </td>
                  </tr>
                ) : movements.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-neutral-500">
                      {hasFilters ? 'No movements match the current filters.' : 'No stock movements recorded yet.'}
                    </td>
                  </tr>
                ) : (
                  movements.map((m) => {
                    const b = typeBadge(m.movement_type);
                    const qtyNum = Number(m.qty);
                    return (
                      <tr key={m.id} className="border-t border-neutral-100 hover:bg-neutral-50" style={{ height: 36 }}>
                        <td className="px-4 font-mono text-[12.5px] text-neutral-600">{fmtDateTime(m.created_at)}</td>
                        <td className="font-medium">{m.product_name || `#${m.product}`}</td>
                        <td><Badge kind={b.kind}>{b.label}</Badge></td>
                        <td className={`text-end font-mono tabular-nums font-semibold ${qtyNum < 0 ? 'text-danger-600' : 'text-success-700'}`}>
                          {fmtSignedQty(m.qty)}
                        </td>
                        <td className="ps-4 pe-4 text-neutral-600 truncate max-w-[260px]">{m.note || '—'}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-4 h-12 border-t border-neutral-200 flex items-center justify-between text-[12.5px] text-neutral-500">
            <span>Page {page} of {pageCount}</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={page >= pageCount || loading}
                className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </Card>
      </div>

      {receiving && (
        <GlobalReceiveStockModal
          onClose={() => setReceiving(false)}
          onSuccess={(name, qty) => {
            setReceiving(false);
            setToast({ kind: 'success', message: `Received ${fmtDecimal(qty)} into "${name}".` });
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
};
