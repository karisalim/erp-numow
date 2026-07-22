import React, { useState } from 'react';
import { Header } from '../../../components/layout/Header';
import { Tabs } from '../../../components/ui/Tabs';
import { DataTable, type Column } from '../../../components/ui/DataTable';
import { Badge } from '../../../components/ui/Badge';
import { useQuery } from '../../../hooks/useQuery';
import { useMoney } from '../../../utils/money';
import { formatPercent, formatQty } from '../utils/format';
import { reportsApi, catalogApi } from '../api';
import type { RecipeProfitabilityRow, IngredientConsumptionRow } from '../types';

const today = () => new Date().toISOString().slice(0, 10);
const startOfMonth = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };

/** `/recipes/reports` — Recipe Profitability + Ingredient Consumption,
 * reading Sprint 5 Batch 6's two report endpoints directly. Every number
 * shown is exactly what the backend returned — no re-aggregation, no
 * recomputed margin. */
export const RecipeReportsPage: React.FC = () => {
  const money = useMoney();
  const [tab, setTab] = useState<'profitability' | 'consumption'>('profitability');
  const [startDate, setStartDate] = useState(startOfMonth());
  const [endDate, setEndDate] = useState(today());
  const [branchId, setBranchId] = useState<number | ''>('');

  const branchesQ = useQuery(() => catalogApi.listBranches(), []);

  const profitabilityQ = useQuery(
    () => reportsApi.recipeProfitability({ start_date: startDate, end_date: endDate, branch_id: branchId || undefined, ordering: '-revenue' }),
    [startDate, endDate, branchId],
  );
  const consumptionQ = useQuery(
    () => reportsApi.ingredientConsumption({ start_date: startDate, end_date: endDate, branch_id: branchId || undefined, ordering: '-cost_consumed' }),
    [startDate, endDate, branchId],
  );

  const profitabilityColumns: Column<RecipeProfitabilityRow>[] = [
    {
      key: 'product', header: 'Product',
      render: (r) => (
        <div>
          <div className="font-semibold">{r.product_name}</div>
          {r.variant_name && <Badge kind="violet">{r.variant_name}</Badge>}
        </div>
      ),
    },
    { key: 'units', header: 'Units sold', align: 'end', mono: true, render: (r) => formatQty(r.units_sold) },
    { key: 'revenue', header: 'Revenue', align: 'end', mono: true, render: (r) => money(r.revenue) },
    { key: 'food_cost', header: 'Food cost', align: 'end', mono: true, render: (r) => money(r.food_cost) },
    { key: 'food_cost_pct', header: 'Food cost %', align: 'end', mono: true, render: (r) => formatPercent(r.food_cost_pct) },
    { key: 'gross_profit', header: 'Gross profit', align: 'end', mono: true, render: (r) => money(r.gross_profit) },
    {
      key: 'margin', header: 'Margin', align: 'end',
      render: (r) => (
        <span className={r.gross_margin_pct >= 0 ? 'text-success-600 font-semibold' : 'text-danger-600 font-semibold'}>
          {formatPercent(r.gross_margin_pct)}
        </span>
      ),
    },
  ];

  const consumptionColumns: Column<IngredientConsumptionRow>[] = [
    { key: 'product', header: 'Ingredient', render: (r) => <span className="font-semibold">{r.product_name}</span> },
    { key: 'qty', header: 'Qty consumed', align: 'end', mono: true, render: (r) => formatQty(r.qty_consumed) },
    { key: 'cost', header: 'Cost consumed', align: 'end', mono: true, render: (r) => money(r.cost_consumed) },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Recipe reports" subtitle="Food-cost profitability and ingredient consumption" />
      <div className="p-5 max-w-[1100px] w-full mx-auto space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <Tabs
            options={[
              { value: 'profitability', label: 'Recipe Profitability' },
              { value: 'consumption', label: 'Ingredient Consumption' },
            ]}
            value={tab}
            onChange={setTab}
          />
          <div className="flex items-center gap-2 ms-auto">
            <select
              value={branchId}
              onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
              className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
            >
              <option value="">All branches</option>
              {(branchesQ.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <input
              type="date" value={startDate} max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
            />
            <span className="text-neutral-400 text-[12px]">to</span>
            <input
              type="date" value={endDate} min={startDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
            />
          </div>
        </div>

        {tab === 'profitability' ? (
          <DataTable<RecipeProfitabilityRow>
            columns={profitabilityColumns}
            rows={profitabilityQ.data?.results ?? []}
            rowKey={(r) => `${r.product_id}-${r.variant_id ?? 'base'}`}
            loading={profitabilityQ.loading}
            error={profitabilityQ.error}
            onRetry={profitabilityQ.refetch}
            emptyTitle="No recipe sales in this range"
            emptyHint="Sell a recipe product within the selected dates to see food cost and margin here."
            emptyIcon="chart"
          />
        ) : (
          <DataTable<IngredientConsumptionRow>
            columns={consumptionColumns}
            rows={consumptionQ.data?.results ?? []}
            rowKey={(r) => r.product_id}
            loading={consumptionQ.loading}
            error={consumptionQ.error}
            onRetry={consumptionQ.refetch}
            emptyTitle="No ingredient consumption in this range"
            emptyHint="Ingredients consumed via recipe sales in the selected dates will appear here."
            emptyIcon="box"
          />
        )}
      </div>
    </div>
  );
};
