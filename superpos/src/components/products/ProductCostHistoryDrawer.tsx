import React, { useState } from 'react';
import { Drawer } from '../ui/Drawer';
import { Icon } from '../ui/Icon';
import { DataTable, type Column } from '../ui/DataTable';
import { inventoryCostApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { fmtDecimal } from '../../utils/format';
import type { Product } from '../../types';
import type { InventoryCostMovement } from '../../types/erp';

const PAGE_SIZE = 20;

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface ProductCostHistoryDrawerProps {
  product: Product;
  onClose: () => void;
}

/**
 * Read-only audit trail for a product's moving-average cost — every row is
 * written exclusively by the backend costing service (purchase receipts,
 * positive stock-count adjustments with a unit cost entered). Nothing here
 * is ever editable; there is currently no way to correct a wrong average
 * without also increasing recorded stock, so this view is history only.
 */
export const ProductCostHistoryDrawer: React.FC<ProductCostHistoryDrawerProps> = ({ product, onClose }) => {
  const money = useMoney();
  const productId = Number(product.id);
  const [page, setPage] = useState(1);

  const movementsQ = useQuery(
    () => inventoryCostApi.listMovements(productId, { page, page_size: PAGE_SIZE }),
    [productId, page],
  );

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
      <DataTable<InventoryCostMovement>
        columns={columns}
        rows={movementsQ.data?.results ?? []}
        rowKey={(m) => m.id}
        loading={movementsQ.loading}
        error={movementsQ.error}
        onRetry={movementsQ.refetch}
        emptyTitle="No cost movements yet"
        emptyHint="This product's average cost only changes on purchase receipts or positive stock-count adjustments with a unit cost entered — it hasn't moved since this product was created."
        emptyIcon="chart"
        page={page}
        pageSize={PAGE_SIZE}
        count={movementsQ.data?.count ?? 0}
        onPage={setPage}
      />
    </Drawer>
  );
};
