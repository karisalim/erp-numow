import React, { useState } from 'react';
import { AxiosError } from 'axios';
import { Drawer } from '../ui/Drawer';
import { Icon } from '../ui/Icon';
import { Button } from '../ui/Button';
import { DataTable, type Column } from '../ui/DataTable';
import { CostTrendChart } from './CostTrendChart';
import { inventoryCostApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { fmtDecimal } from '../../utils/format';
import type { InventoryCostMovement } from '../../types/erp';

const PAGE_SIZE = 20;
const CHART_PAGE_SIZE = 500; // Sprint 4 Batch 3's documented ceiling — a chart
// covering an extreme date range for a very high-volume product could still
// exceed this and get truncated; narrowing the date range is the mitigation,
// not building aggregation/downsampling infra nobody has asked for yet.

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface ProductCostHistoryDrawerProps {
  /* Sprint 4 Batch 8 — widened from the full `Product` type to just the
   * two fields this drawer actually reads, so Dashboard drill-down (which
   * only has a `DashboardTopProduct`/`DashboardLowStockEntry` row, not a
   * full Product) can open it without fabricating dummy field values. */
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
 * Sprint 4 Batch 7 added: an optional date-range filter (narrows both the
 * table and the trend chart together), a trend chart of the average cost
 * over time, and CSV/Excel/PDF export of the currently filtered set. No
 * branch/warehouse filter exists here — cost data stays tenant-wide per
 * D-09, there is nothing to filter by.
 */
export const ProductCostHistoryDrawer: React.FC<ProductCostHistoryDrawerProps> = ({ product, onClose }) => {
  const money = useMoney();
  const productId = Number(product.id);
  const [page, setPage] = useState(1);

  const [startDate, setStartDate] = useState('');
  const [endDate,   setEndDate]   = useState('');
  const dateParams = startDate && endDate ? { start_date: startDate, end_date: endDate } : {};

  const movementsQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page, page_size: PAGE_SIZE, ...dateParams }),
    [productId, page, startDate, endDate],
  );

  const chartQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page_size: CHART_PAGE_SIZE, ...dateParams }),
    [productId, startDate, endDate],
  );

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

  const columns: Column<InventoryCostMovement>[] = [
    { key: 'when', header: 'Date', render: (m) => <span className="text-neutral-500 whitespace-nowrap">{fmtDateTime(m.occurred_at)}</span> },
    {
      key: 'source', header: 'Source',
      render: (m) => (
        <span className="text-neutral-600">
          {m.source_document_type ? `${m.source_document_type}${m.source_document_id ? ` #${m.source_document_id}` : ''}` : '—'}
        </span>
      ),
    },
    { key: 'qty', header: 'Qty received', align: 'end', mono: true, render: (m) => m.quantity_received != null ? fmtDecimal(m.quantity_received) : '—' },
    { key: 'unit_cost', header: 'Unit cost received', align: 'end', mono: true, render: (m) => m.unit_cost_received != null ? money(m.unit_cost_received) : '—' },
    {
      key: 'delta', header: 'Avg cost (before → after)', align: 'end', mono: true,
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

  return (
    <Drawer
      title="Cost history"
      subtitle={product.name}
      onClose={onClose}
      widthClassName="max-w-[920px]"
    >
      <div className="px-5 pt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
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
          {(startDate || endDate) && (
            <button
              type="button"
              onClick={() => { setStartDate(''); setEndDate(''); setPage(1); }}
              className="text-[12px] text-neutral-500 hover:text-neutral-700 underline"
            >
              Clear
            </button>
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
        <div role="alert" className="mx-5 mt-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2 text-[12.5px] text-danger-700">
          {exportError}
        </div>
      )}

      <div className="px-5 pt-4">
        <div className="text-[12.5px] font-semibold text-neutral-600 mb-1">Average cost over time</div>
        <CostTrendChart movements={chartQ.data?.results ?? []} loading={chartQ.loading} />
      </div>

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
        page={page}
        pageSize={PAGE_SIZE}
        count={movementsQ.data?.count ?? 0}
        onPage={setPage}
      />
    </Drawer>
  );
};
