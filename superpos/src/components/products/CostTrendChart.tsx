import React from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useMoney } from '../../utils/money';
import { Icon } from '../ui/Icon';
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
 * Sprint 4 Batch 7 (+ Batch 10 polish) — average-cost-over-time comparison,
 * inside the Cost History drawer. `movements` must already be chronological
 * (oldest first) — the drawer's own table stays newest-first (an
 * audit-ledger convention), so this component re-sorts rather than
 * assuming order.
 *
 * The "% vs start of period" badge is computed client-side from the first
 * and last point of the loaded series (no backend trend field exists for
 * cost movements — this is a plain, honest first-vs-last comparison over
 * whatever range/quick-filter is currently active, not a period-over-period
 * comparison against a prior window).
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

  const first = points[0].avg_cost;
  const last = points[points.length - 1].avg_cost;
  const pctChange = first !== 0 ? ((last - first) / first) * 100 : null;

  return (
    <div>
      {pctChange !== null && (
        <div className="flex justify-end mb-1">
          <span
            className={`inline-flex items-center gap-1 text-[11.5px] font-semibold px-2 py-0.5 rounded-full ${
              pctChange > 0 ? 'bg-warn-50 text-warn-700' : pctChange < 0 ? 'bg-success-50 text-success-700' : 'bg-neutral-100 text-neutral-600'
            }`}
            title="Change from the first to the last cost movement in the current range"
          >
            {pctChange !== 0 && <Icon name={pctChange > 0 ? 'arrowUp' : 'arrowDn'} size={11} />}
            {pctChange === 0 ? '—' : `${pctChange > 0 ? '+' : ''}${pctChange.toFixed(1)}%`} vs start of period
          </span>
        </div>
      )}
      <div className="h-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="costTrendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.02} />
              </linearGradient>
            </defs>
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
            <Area
              type="monotone"
              dataKey="avg_cost"
              name="Avg cost"
              stroke="#8B5CF6"
              strokeWidth={2}
              fill="url(#costTrendFill)"
              dot={{ r: 3 }}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
