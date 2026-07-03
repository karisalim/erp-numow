import React from 'react';
import { DataTable, type Column } from '../ui/DataTable';
import { Badge } from '../ui/Badge';
import { fmtDecimal } from '../../utils/format';
import type { ApiError } from '../../utils/apiError';
import type { WarehouseStockRow } from '../../types/erp';

/**
 * Per-warehouse stock balance table (Slice J cached WarehouseStock rows).
 * Negative quantities get a distinct danger state — never shown as
 * ordinary "low" stock.
 */
export function qtyBadge(quantity: string): React.ReactNode {
  const q = Number(quantity);
  if (q < 0) return <Badge kind="danger">Negative</Badge>;
  if (q === 0) return <Badge kind="gray">Empty</Badge>;
  return <Badge kind="success">In stock</Badge>;
}

export const WarehouseStockTable: React.FC<{
  rows: WarehouseStockRow[];
  loading?: boolean;
  error?: ApiError | null;
  onRetry?: () => void;
  /** Hide the warehouse column when the table is already warehouse-scoped. */
  showWarehouse?: boolean;
  /** Hide the product column when product-scoped. */
  showProduct?: boolean;
  page?: number;
  pageSize?: number;
  count?: number;
  onPage?: (page: number) => void;
  onRowClick?: (row: WarehouseStockRow) => void;
}> = ({ rows, loading, error, onRetry, showWarehouse = true, showProduct = true, page, pageSize, count, onPage, onRowClick }) => {
  const columns: Column<WarehouseStockRow>[] = [];

  if (showProduct) {
    columns.push({
      key: 'product',
      header: 'Product',
      render: (r) => (
        <div>
          <div className="font-semibold">{r.product_name}</div>
          {r.product_sku && <div className="text-[11.5px] text-neutral-400 font-mono">{r.product_sku}</div>}
        </div>
      ),
    });
  }
  if (showWarehouse) {
    columns.push({
      key: 'warehouse',
      header: 'Warehouse',
      render: (r) => (
        <span className="text-neutral-600">
          {r.warehouse_name}
          {r.warehouse_code && <span className="text-neutral-400 font-mono text-[11.5px]"> · {r.warehouse_code}</span>}
        </span>
      ),
    });
  }
  columns.push(
    {
      key: 'qty',
      header: 'On hand',
      align: 'end',
      mono: true,
      className: 'font-semibold',
      render: (r) => (
        <span className={Number(r.quantity) < 0 ? 'text-danger-600' : ''}>{fmtDecimal(r.quantity)}</span>
      ),
    },
    { key: 'status', header: 'Status', render: (r) => qtyBadge(r.quantity) },
  );

  return (
    <DataTable<WarehouseStockRow>
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      loading={loading}
      error={error}
      onRetry={onRetry}
      emptyTitle="No stock balances"
      emptyHint="Balances appear after purchases or stock movements are posted per warehouse."
      emptyIcon="layers"
      page={page}
      pageSize={pageSize}
      count={count}
      onPage={onPage}
      onRowClick={onRowClick}
    />
  );
};
