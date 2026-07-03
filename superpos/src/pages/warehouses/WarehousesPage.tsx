import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Icon } from '../../components/ui/Icon';
import { Tabs } from '../../components/ui/Tabs';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Badge } from '../../components/ui/Badge';
import { Drawer } from '../../components/ui/Drawer';
import { SelectField } from '../../components/ui/FormField';
import { FilterBar, FilterChips } from '../../components/ui/FilterBar';
import { WarehouseStockTable } from '../../components/erp/WarehouseStockTable';
import { warehousesApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import type { Warehouse, WarehouseStockRow } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Warehouses — list of warehouses plus the per-warehouse stock browser
 * (Slice J cached balances). Read-only screens on verified routes:
 *   GET /api/inventory/warehouses/
 *   GET /api/inventory/warehouse-stocks/           (all balances, filterable)
 *   GET /api/inventory/warehouses/{id}/stock/      (one warehouse)
 *   GET /api/products/{id}/warehouse-stocks/       (one product breakdown)
 * ──────────────────────────────────────────────────────────────────────────── */

const PAGE_SIZE = 20;

type StockFilter = 'all' | 'has_stock' | 'negative';

export const WarehousesPage: React.FC = () => {
  const [tab, setTab] = useState<'warehouses' | 'stock'>('warehouses');

  // Stock tab state
  const [warehouseFilter, setWarehouseFilter] = useState<number | ''>('');
  const [stockFilter, setStockFilter] = useState<StockFilter>('all');
  const [stockPage, setStockPage] = useState(1);

  // Product breakdown drawer
  const [breakdownFor, setBreakdownFor] = useState<WarehouseStockRow | null>(null);

  const warehousesQ = useQuery(() => warehousesApi.list({ page_size: 200 }), []);
  const warehouses = warehousesQ.data?.results ?? [];

  const stockQ = useQuery(
    () => {
      if (tab !== 'stock') return Promise.resolve(null);
      const params: Record<string, string | number | undefined> = {
        page: stockPage,
        page_size: PAGE_SIZE,
        warehouse: warehouseFilter || undefined,
      };
      if (stockFilter === 'has_stock') params.has_stock = 'true';
      if (stockFilter === 'negative') params.low_stock = 'true';
      return warehousesApi.stockList(params);
    },
    [tab, stockPage, warehouseFilter, stockFilter],
  );

  const breakdownQ = useQuery(
    () => (breakdownFor ? warehousesApi.productBreakdown(breakdownFor.product).then(asResults) : Promise.resolve(null)),
    [breakdownFor?.product],
  );

  const warehouseColumns: Column<Warehouse>[] = [
    {
      key: 'name', header: 'Warehouse',
      render: (w) => (
        <div>
          <div className="font-semibold">{w.name}</div>
          <div className="text-[11.5px] text-neutral-400 font-mono">{w.code}</div>
        </div>
      ),
    },
    { key: 'type', header: 'Type', render: (w) => <Badge kind="brand">{w.warehouse_type_display}</Badge> },
    { key: 'desc', header: 'Description', className: 'hidden md:table-cell', render: (w) => <span className="text-neutral-500">{w.description || '—'}</span> },
    { key: 'status', header: 'Status', render: (w) => <ActiveBadge active={w.is_active} /> },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Warehouses" subtitle="Per-warehouse stock balances · ledger-driven" />
      <div className="p-5 max-w-[1180px] w-full mx-auto">
        <Tabs
          className="mb-4"
          value={tab}
          onChange={(v) => { setTab(v); setStockPage(1); }}
          options={[
            { value: 'warehouses', label: 'Warehouses' },
            { value: 'stock', label: 'Stock balances' },
          ]}
        />

        {tab === 'warehouses' && (
          <DataTable<Warehouse>
            columns={warehouseColumns}
            rows={warehouses}
            rowKey={(w) => w.id}
            loading={warehousesQ.loading}
            error={warehousesQ.error}
            onRetry={warehousesQ.refetch}
            emptyTitle="No warehouses"
            emptyHint="Warehouses are configured by an administrator (branch default warehouses are created automatically)."
            emptyIcon="archive"
            onRowClick={(w) => { setTab('stock'); setWarehouseFilter(w.id); setStockPage(1); }}
          />
        )}

        {tab === 'stock' && (
          <>
            <FilterBar>
              <div className="w-full sm:w-72">
                <SelectField
                  label="Warehouse"
                  value={warehouseFilter}
                  onChange={(e) => { setWarehouseFilter(e.target.value ? Number(e.target.value) : ''); setStockPage(1); }}
                >
                  <option value="">All warehouses</option>
                  {warehouses.map((w) => (
                    <option key={w.id} value={w.id}>{w.name}</option>
                  ))}
                </SelectField>
              </div>
              <div className="pt-6">
                <FilterChips<StockFilter>
                  value={stockFilter}
                  onChange={(v) => { setStockFilter(v); setStockPage(1); }}
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'has_stock', label: 'With movement' },
                    { value: 'negative', label: 'At/below reorder' },
                  ]}
                />
              </div>
            </FilterBar>

            <WarehouseStockTable
              rows={stockQ.data?.results ?? []}
              loading={stockQ.loading}
              error={stockQ.error}
              onRetry={stockQ.refetch}
              page={stockPage}
              pageSize={PAGE_SIZE}
              count={stockQ.data?.count ?? 0}
              onPage={setStockPage}
              onRowClick={(row) => setBreakdownFor(row)}
            />
            <p className="text-[12px] text-neutral-400 mt-2 flex items-center gap-1.5">
              <Icon name="layers" size={13} /> Click a row to see that product's balance across all warehouses.
            </p>
          </>
        )}
      </div>

      {breakdownFor && (
        <Drawer
          title={breakdownFor.product_name}
          subtitle={`Per-warehouse breakdown${breakdownFor.product_sku ? ` · ${breakdownFor.product_sku}` : ''}`}
          onClose={() => setBreakdownFor(null)}
          widthClassName="max-w-[560px]"
        >
          <WarehouseStockTable
            rows={breakdownQ.data ?? []}
            loading={breakdownQ.loading}
            error={breakdownQ.error}
            onRetry={breakdownQ.refetch}
            showProduct={false}
          />
        </Drawer>
      )}
    </div>
  );
};
