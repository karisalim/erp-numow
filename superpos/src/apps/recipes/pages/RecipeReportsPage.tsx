import React, { useMemo, useState } from 'react';
import { Header } from '../../../components/layout/Header';
import { Tabs } from '../../../components/ui/Tabs';
import { DataTable, type Column } from '../../../components/ui/DataTable';
import { Badge } from '../../../components/ui/Badge';
import { Card, CardBody } from '../../../components/ui/Card';
import { Icon } from '../../../components/ui/Icon';
import { useQuery } from '../../../hooks/useQuery';
import { useMoney } from '../../../utils/money';
import { formatPercent, formatQty } from '../utils/format';
import { reportsApi, catalogApi } from '../api';
import type { RecipeProfitabilityRow, IngredientConsumptionRow } from '../types';

const today = () => new Date().toISOString().slice(0, 10);
const startOfMonth = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };

const KpiTile: React.FC<{ icon: string; label: string; value: React.ReactNode; tone: string }> = ({ icon, label, value, tone }) => (
  <Card>
    <CardBody className="flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg grid place-items-center shrink-0 ${tone}`}>
        <Icon name={icon} size={18} />
      </div>
      <div className="min-w-0">
        <div className="text-[18px] font-bold leading-none truncate">{value}</div>
        <div className="text-[11.5px] text-neutral-500 mt-1">{label}</div>
      </div>
    </CardBody>
  </Card>
);

/** A small ranked-list card (Top Recipes / Worst Margin / Most Used
 * Ingredient) — every row is a value already returned by the report
 * endpoint, just re-sorted/sliced client-side for a different view of the
 * SAME data the main table shows. No recomputed cost or margin. */
const RankedListCard: React.FC<{
  title: string; icon: string;
  rows: { key: string | number; label: string; value: string; sub?: string }[];
  emptyHint: string;
}> = ({ title, icon, rows, emptyHint }) => (
  <div className="bg-white border border-neutral-200 rounded-lg shadow-sm">
    <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50">
      <Icon name={icon} size={14} className="text-neutral-500" />
      <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">{title}</h3>
    </div>
    {rows.length === 0 ? (
      <div className="px-3.5 py-6 text-center text-[12.5px] text-neutral-400">{emptyHint}</div>
    ) : (
      <div className="divide-y divide-neutral-100">
        {rows.map((r, i) => (
          <div key={r.key} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="text-[11px] font-bold text-neutral-400 w-4 shrink-0">{i + 1}</span>
              <div className="min-w-0">
                <div className="text-[13px] font-semibold truncate">{r.label}</div>
                {r.sub && <div className="text-[11px] text-neutral-500 truncate">{r.sub}</div>}
              </div>
            </div>
            <span className="text-[13px] font-mono tabular-nums shrink-0">{r.value}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);

/** `/recipes/reports` — Recipe Profitability + Ingredient Consumption,
 * reading Sprint 5 Batch 6's two report endpoints directly. Every number
 * shown is exactly what the backend returned — no re-aggregation, no
 * recomputed margin. The KPI strip and ranked-list cards below are pure
 * client-side SUM/sort/slice over the already-fetched rows (display
 * aggregation, same category as `RecipeSummary.tsx`'s dashboard tiles) —
 * never a recomputed cost or margin value. */
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

  const profitRows = profitabilityQ.data?.results ?? [];
  const consumptionRows = consumptionQ.data?.results ?? [];

  const kpis = useMemo(() => {
    const revenue = profitRows.reduce((s, r) => s + r.revenue, 0);
    const foodCost = profitRows.reduce((s, r) => s + r.food_cost, 0);
    const grossProfit = profitRows.reduce((s, r) => s + r.gross_profit, 0);
    const marginPct = revenue > 0 ? (grossProfit / revenue) * 100 : 0;
    return { revenue, foodCost, grossProfit, marginPct };
  }, [profitRows]);

  const topRecipes = useMemo(
    () => [...profitRows].sort((a, b) => b.gross_profit - a.gross_profit).slice(0, 5)
      .map((r) => ({ key: `${r.product_id}-${r.variant_id ?? 'base'}`, label: r.product_name, sub: r.variant_name || undefined, value: money(r.gross_profit) })),
    [profitRows, money],
  );
  const worstMargin = useMemo(
    () => [...profitRows].sort((a, b) => a.gross_margin_pct - b.gross_margin_pct).slice(0, 5)
      .map((r) => ({ key: `${r.product_id}-${r.variant_id ?? 'base'}`, label: r.product_name, sub: r.variant_name || undefined, value: formatPercent(r.gross_margin_pct) })),
    [profitRows],
  );
  const highestCost = useMemo(
    () => [...profitRows].sort((a, b) => b.food_cost - a.food_cost).slice(0, 5)
      .map((r) => ({ key: `${r.product_id}-${r.variant_id ?? 'base'}`, label: r.product_name, sub: r.variant_name || undefined, value: money(r.food_cost) })),
    [profitRows, money],
  );
  const mostUsedIngredients = useMemo(
    () => [...consumptionRows].sort((a, b) => b.qty_consumed - a.qty_consumed).slice(0, 5)
      .map((r) => ({ key: r.product_id, label: r.product_name, value: formatQty(r.qty_consumed) })),
    [consumptionRows],
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiTile icon="cash" label="Revenue" value={money(kpis.revenue)} tone="bg-brand-50 text-brand-600" />
          <KpiTile icon="box" label="Food cost" value={money(kpis.foodCost)} tone="bg-warn-50 text-warn-600" />
          <KpiTile icon="chart" label="Gross profit" value={money(kpis.grossProfit)} tone="bg-success-50 text-success-600" />
          <KpiTile
            icon="tag" label="Gross margin"
            value={<span className={kpis.marginPct >= 0 ? 'text-success-600' : 'text-danger-600'}>{formatPercent(kpis.marginPct)}</span>}
            tone="bg-violet-50 text-violet-700"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <RankedListCard title="Top recipes (by profit)" icon="chart" rows={topRecipes} emptyHint="No recipe sales in this range yet." />
          <RankedListCard title="Worst margin" icon="alert" rows={worstMargin} emptyHint="No recipe sales in this range yet." />
          <RankedListCard title="Most used ingredient" icon="box" rows={mostUsedIngredients} emptyHint="No ingredient consumption in this range yet." />
        </div>

        {tab === 'profitability' ? (
          <DataTable<RecipeProfitabilityRow>
            columns={profitabilityColumns}
            rows={profitRows}
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
            rows={consumptionRows}
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
