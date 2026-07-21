import React, { useState } from 'react';
import { AxiosError } from 'axios';
import { Link } from 'react-router-dom';
import { Drawer } from '../ui/Drawer';
import { Icon } from '../ui/Icon';
import { Button } from '../ui/Button';
import { DataTable, type Column } from '../ui/DataTable';
import { CostTrendChart } from './CostTrendChart';
import { inventoryCostApi } from '../../api/erp';
import apiClient from '../../api/client';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { fmtDecimal } from '../../utils/format';
import { productVisual } from '../../utils/categoryVisual';
import type { InventoryCostMovement } from '../../types/erp';
import type { Product } from '../../types';

const CHART_PAGE_SIZE = 500; // Sprint 4 Batch 3's documented ceiling — a chart
// covering an extreme date range for a very high-volume product could still
// exceed this and get truncated; narrowing the date range is the mitigation,
// not building aggregation/downsampling infra nobody has asked for yet.

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

/** Friendly label for `source_document_type` — falls back to a title-cased
 * version of the raw value for anything not explicitly named, so a future
 * write path never renders as a blank cell. */
const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  purchase_invoice:  'Purchase',
  stock_adjustment:  'Stock adjustment',
  csv_import:        'CSV import',
};
function movementTypeLabel(sourceType: string): string {
  if (!sourceType) return '—';
  return MOVEMENT_TYPE_LABELS[sourceType] || sourceType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* Local YYYY-MM-DD (no UTC drift), mirrors DashboardPage's own `today()`. */
function toLocalISODate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

type QuickRangeKey = 'all' | '7d' | '30d' | '90d' | 'month' | 'year' | 'custom';

const QUICK_RANGES: Array<{ key: QuickRangeKey; label: string }> = [
  { key: 'all',    label: 'All' },
  { key: '7d',     label: '7D' },
  { key: '30d',    label: '30D' },
  { key: '90d',    label: '90D' },
  { key: 'month',  label: 'This Month' },
  { key: 'year',   label: 'This Year' },
  { key: 'custom', label: 'Custom' },
];

function quickRangeDates(key: QuickRangeKey): { start: string; end: string } {
  const now = new Date();
  const end = toLocalISODate(now);
  const daysAgo = (n: number) => {
    const d = new Date(now);
    d.setDate(d.getDate() - n);
    return toLocalISODate(d);
  };
  switch (key) {
    case '7d':    return { start: daysAgo(6),  end };
    case '30d':   return { start: daysAgo(29), end };
    case '90d':   return { start: daysAgo(89), end };
    case 'month': return { start: toLocalISODate(new Date(now.getFullYear(), now.getMonth(), 1)), end };
    case 'year':  return { start: toLocalISODate(new Date(now.getFullYear(), 0, 1)), end };
    default:      return { start: '', end: '' };
  }
}

interface ProductCostHistoryDrawerProps {
  /* Sprint 4 Batch 8 — widened from the full `Product` type to just the
   * two fields this drawer actually reads, so Dashboard drill-down (which
   * only has a `DashboardTopProduct`/`DashboardLowStockEntry` row, not a
   * full Product) can open it without fabricating dummy field values. The
   * drawer fetches the full Product itself (Batch 10) for the summary
   * header, so every caller gets full fidelity regardless of what it had
   * on hand when it opened the drawer. */
  product: { id: number | string; name: string };
  onClose: () => void;
}

/**
 * Read-only audit trail for a product's moving-average cost — every row is
 * written exclusively by the backend costing service (purchase receipts,
 * positive stock-count adjustments with a unit cost entered). Nothing here
 * is ever editable; there is currently no way to correct a wrong average
 * without also increasing recorded stock, so this view is history only.
 *
 * Sprint 4 Batch 7 added: a date-range filter, a trend chart, and CSV/
 * Excel/PDF export. Batch 10 added: a product-summary header, quick-range
 * chips, an area chart with a start-of-period trend badge, Movement
 * Type/User columns, clickable Purchase-invoice source links, sortable
 * columns, and a page-size selector. No branch/warehouse filter exists
 * here — cost data stays tenant-wide per D-09, there is nothing to filter
 * by; Warehouse/Supplier columns are likewise not shown — neither is
 * tracked on `InventoryCostMovement` today (D-09 keeps cost dimension-free,
 * and supplier would need an extra join per row this drawer doesn't do).
 */
export const ProductCostHistoryDrawer: React.FC<ProductCostHistoryDrawerProps> = ({ product, onClose }) => {
  const money = useMoney();
  const productId = Number(product.id);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [quickRange, setQuickRange] = useState<QuickRangeKey>('all');
  const [startDate, setStartDate] = useState('');
  const [endDate,   setEndDate]   = useState('');
  const dateParams = startDate && endDate ? { start_date: startDate, end_date: endDate } : {};

  const selectQuickRange = (key: QuickRangeKey) => {
    setQuickRange(key);
    setPage(1);
    if (key === 'custom') return; // keep whatever dates are already set, let the inputs show
    const { start, end } = quickRangeDates(key);
    setStartDate(start);
    setEndDate(end);
  };

  const [ordering, setOrdering] = useState('-occurred_at');
  const toggleSort = (field: string) => {
    setOrdering((cur) => (cur === field ? `-${field}` : cur === `-${field}` ? field : field));
    setPage(1);
  };
  const sortIcon = (field: string) =>
    ordering === field ? 'arrowUp' : ordering === `-${field}` ? 'arrowDn' : null;

  const movementsQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page, page_size: pageSize, ordering, ...dateParams }),
    [productId, page, pageSize, ordering, startDate, endDate],
  );

  const chartQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page_size: CHART_PAGE_SIZE, ...dateParams }),
    [productId, startDate, endDate],
  );

  // Product summary header (Batch 10) — fetched directly so every caller
  // (Products page, Dashboard Top-10/low-stock rows) gets the same full
  // header regardless of what fields it happened to have on hand.
  const productQ = useQuery(
    () => apiClient.get<Product>(`/products/${productId}/`).then((r) => r.data),
    [productId],
  );

  // Latest cost movement overall (unfiltered) — used only for the "Last
  // cost update" timestamp, since Product.updated_at also bumps on
  // unrelated field edits (name, category, …) and would be misleading here.
  const latestMovementQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page: 1, page_size: 1 }),
    [productId],
  );
  const lastCostUpdateAt = latestMovementQ.data?.results?.[0]?.occurred_at;

  const [exportingFormat, setExportingFormat] = useState<'csv' | 'xlsx' | 'pdf' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const onExport = async (fmt: 'csv' | 'xlsx' | 'pdf') => {
    if (exportingFormat) return;
    setExportingFormat(fmt);
    setExportError(null);
    try {
      const res = await inventoryCostApi.exportMovements(productId, fmt, dateParams);
      const contentType = { csv: 'text/csv;charset=utf-8', xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', pdf: 'application/pdf' }[fmt];
      const blob = new Blob([res.data], { type: contentType });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      const tag  = startDate && endDate ? `-${startDate}_${endDate}` : '';
      a.download = `cost-history-${product.name.toLowerCase().replace(/\s+/g, '-')}${tag}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      let msg = `Failed to export ${fmt.toUpperCase()}.`;
      if (err instanceof AxiosError && typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
      setExportError(msg);
    } finally {
      setExportingFormat(null);
    }
  };

  const sortableHeader = (label: string, field: string) => (
    <button
      type="button"
      onClick={() => toggleSort(field)}
      className="inline-flex items-center gap-1 hover:text-neutral-700 focus-ring rounded"
    >
      {label}
      {sortIcon(field) && <Icon name={sortIcon(field) as string} size={11} />}
    </button>
  );

  const columns: Column<InventoryCostMovement>[] = [
    { key: 'when', header: sortableHeader('Date', 'occurred_at'), render: (m) => <span className="text-neutral-500 whitespace-nowrap">{fmtDateTime(m.occurred_at)}</span> },
    {
      key: 'type', header: 'Movement type',
      render: (m) => <span className="text-neutral-600">{movementTypeLabel(m.source_document_type)}</span>,
    },
    {
      key: 'source', header: 'Source',
      render: (m) => {
        if (!m.source_document_type) return <span className="text-neutral-600">—</span>;
        const label = `${m.source_document_type}${m.source_document_id ? ` #${m.source_document_id}` : ''}`;
        if (m.source_document_type === 'purchase_invoice' && m.source_document_id) {
          return (
            <Link
              to={`/purchases/${m.source_document_id}`}
              className="text-brand-600 hover:text-brand-700 underline"
              onClick={(e) => e.stopPropagation()}
            >
              {label}
            </Link>
          );
        }
        return <span className="text-neutral-600">{label}</span>;
      },
    },
    { key: 'user', header: 'User', render: (m) => <span className="text-neutral-600">{m.actor_user_username || '—'}</span> },
    { key: 'qty', header: sortableHeader('Qty received', 'quantity_received'), align: 'end', mono: true, render: (m) => m.quantity_received != null ? fmtDecimal(m.quantity_received) : '—' },
    { key: 'unit_cost', header: 'Unit cost received', align: 'end', mono: true, render: (m) => m.unit_cost_received != null ? money(m.unit_cost_received) : '—' },
    {
      key: 'delta', header: sortableHeader('Avg cost (before → after)', 'avg_cost_after'), align: 'end', mono: true,
      render: (m) => {
        const before = Number(m.avg_cost_before);
        const after = Number(m.avg_cost_after);
        const tone = after > before ? 'text-warn-700 font-semibold' : after < before ? 'text-success-700 font-semibold' : '';
        return (
          <span className="inline-flex items-center gap-1">
            {money(m.avg_cost_before)}
            <Icon name="chevR" size={11} className="text-neutral-400" />
            <span className={tone}>{money(m.avg_cost_after)}</span>
          </span>
        );
      },
    },
    { key: 'note', header: 'Note', render: (m) => m.note || '—' },
  ];

  const visual = productVisual(product.name);
  const p = productQ.data;

  return (
    <Drawer
      title="Cost history"
      subtitle={product.name}
      onClose={onClose}
      widthClassName="max-w-[1200px]"
    >
      {/* Product summary header (Batch 10) */}
      <div className="flex items-center gap-3 pb-4 mb-4 border-b border-neutral-200">
        <div className={`w-11 h-11 rounded-lg grid place-items-center text-[18px] shrink-0 bg-gradient-to-br ${visual.gradient}`}>
          <span aria-hidden>{visual.emoji}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-bold truncate">{product.name}</div>
          <div className="text-[12px] text-neutral-500">{p?.sku ? `SKU ${p.sku}` : ' '}</div>
        </div>
        <div className="hidden sm:flex items-center gap-5">
          <div className="text-end">
            <div className="text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">Current avg cost</div>
            <div className="text-[15px] font-bold font-mono tabular-nums">{p ? money(p.cost) : '…'}</div>
          </div>
          <div className="text-end">
            <div className="text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">Current stock</div>
            <div className="text-[15px] font-bold font-mono tabular-nums">{p ? fmtDecimal(p.stock) : '…'}</div>
          </div>
          <div className="text-end">
            <div className="text-[10.5px] uppercase tracking-wider text-neutral-500 font-semibold">Last cost update</div>
            <div className="text-[13px] font-semibold whitespace-nowrap">{lastCostUpdateAt ? fmtDateTime(lastCostUpdateAt) : '—'}</div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {QUICK_RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              onClick={() => selectQuickRange(r.key)}
              className={`h-8 px-3 rounded-full text-[12.5px] font-semibold border focus-ring ${
                quickRange === r.key
                  ? 'bg-brand-500 border-brand-500 text-white'
                  : 'bg-white border-neutral-300 text-neutral-600 hover:bg-neutral-50'
              }`}
            >
              {r.label}
            </button>
          ))}
          {quickRange === 'custom' && (
            <div className="flex items-center gap-2 ms-1">
              <input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(e) => { setStartDate(e.target.value); setPage(1); }}
                className="h-8 px-2 rounded-md border border-neutral-300 bg-white text-[12.5px] focus-ring"
                aria-label="Start date"
              />
              <span className="text-neutral-400 text-[12.5px]">→</span>
              <input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(e) => { setEndDate(e.target.value); setPage(1); }}
                className="h-8 px-2 rounded-md border border-neutral-300 bg-white text-[12.5px] focus-ring"
                aria-label="End date"
              />
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11.5px] text-neutral-500 mr-0.5">Export:</span>
          {(['csv', 'xlsx', 'pdf'] as const).map((fmt) => (
            <Button
              key={fmt}
              variant="secondary"
              size="sm"
              disabled={exportingFormat !== null}
              onClick={() => onExport(fmt)}
            >
              {exportingFormat === fmt ? '…' : fmt.toUpperCase()}
            </Button>
          ))}
        </div>
      </div>
      {exportError && (
        <div role="alert" className="mt-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2 text-[12.5px] text-danger-700">
          {exportError}
        </div>
      )}

      <div className="pt-4">
        <div className="text-[12.5px] font-semibold text-neutral-600 mb-1">Average cost over time</div>
        <CostTrendChart movements={chartQ.data?.results ?? []} loading={chartQ.loading} />
      </div>

      <div className="pt-4">
        <DataTable<InventoryCostMovement>
          columns={columns}
          rows={movementsQ.data?.results ?? []}
          rowKey={(m) => m.id}
          loading={movementsQ.loading}
          error={movementsQ.error}
          onRetry={movementsQ.refetch}
          emptyTitle="No cost movements yet"
          emptyHint={
            startDate || endDate
              ? 'No cost movements in this date range — try widening it.'
              : "This product's average cost only changes on purchase receipts or positive stock-count adjustments with a unit cost entered — it hasn't moved since this product was created."
          }
          emptyIcon="chart"
          emptyAction={
            !startDate && !endDate ? (
              <Link to="/purchases/new">
                <Button size="sm">
                  <Icon name="plus" size={14} /> Create purchase
                </Button>
              </Link>
            ) : undefined
          }
          page={page}
          pageSize={pageSize}
          count={movementsQ.data?.count ?? 0}
          onPage={setPage}
        />
        <div className="flex items-center justify-end gap-2 mt-2">
          <span className="text-[12px] text-neutral-500">Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="h-7 px-2 rounded-md border border-neutral-300 bg-white text-[12.5px] focus-ring"
            aria-label="Rows per page"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>
    </Drawer>
  );
};
