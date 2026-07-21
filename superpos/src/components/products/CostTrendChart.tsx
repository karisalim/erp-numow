import React from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useMoney } from '../../utils/money';
import type { InventoryCostMovement } from '../../types/erp';

interface CostTrendChartProps {
  movements: InventoryCostMovement[];
  loading: boolean;
}

function fmtAxisDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * Sprint 4 Batch 7 — average-cost-over-time comparison, inside the Cost
 * History drawer. `movements` must already be chronological (oldest
 * first) — the drawer's own table stays newest-first (an audit-ledger
 * convention), so this component re-sorts rather than assuming order.
 */
export const CostTrendChart: React.FC<CostTrendChartProps> = ({ movements, loading }) => {
  const money = useMoney();

  if (loading) {
    return <div className="h-[180px] grid place-items-center text-neutral-500 text-[13px]">Loading…</div>;
  }
  if (movements.length < 2) {
    return (
      <div className="h-[180px] grid place-items-center text-neutral-500 text-[13px] text-center px-6">
        Need at least 2 cost movements in this range to plot a trend.
      </div>
    );
  }

  const chronological = [...movements].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  );
  const points = chronological.map((m) => ({ date: m.occurred_at, avg_cost: Number(m.avg_cost_after) }));

  return (
    <div className="h-[180px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtAxisDate}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={false}
            tickLine={false}
            width={64}
            tickFormatter={(v: number) => money(v)}
          />
          <Tooltip
            labelFormatter={(v) => fmtAxisDate(String(v))}
            formatter={(value) => [money(Number(value)), 'Avg cost']}
          />
          <Line type="monotone" dataKey="avg_cost" name="Avg cost" stroke="#8B5CF6" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
