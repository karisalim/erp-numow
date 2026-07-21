import React from 'react';
import {
  Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useMoney } from '../../utils/money';
import type { DashboardTrendDay } from '../../types/erp';

interface MarginCogsChartProps {
  days: DashboardTrendDay[];
  loading: boolean;
}

const fmtAxisDate = (iso: string): string => {
  const d = new Date(iso + 'T00:00:00');
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

/**
 * Sprint 4 Batch 5 — first chart in the codebase. Bars compare net revenue
 * vs. COGS per day; the line (right axis, 0-100%) tracks gross margin —
 * the two figures the owner explicitly asked to see charted together.
 */
export const MarginCogsChart: React.FC<MarginCogsChartProps> = ({ days, loading }) => {
  const money = useMoney();

  if (loading) {
    return <div className="h-[280px] grid place-items-center text-neutral-500 text-[13px]">Loading…</div>;
  }
  if (days.length === 0 || days.every((d) => d.net_revenue === 0 && d.cogs === 0)) {
    return (
      <div className="h-[280px] grid place-items-center text-neutral-500 text-[13px]">
        No sales in this range.
      </div>
    );
  }

  return (
    <div className="h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={days} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtAxisDate}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickLine={false}
          />
          <YAxis
            yAxisId="money"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(v: number) => money(v)}
          />
          <YAxis
            yAxisId="pct"
            orientation="right"
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            axisLine={false}
            tickLine={false}
            width={40}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            labelFormatter={(v) => fmtAxisDate(String(v))}
            formatter={(value, name) =>
              name === 'Gross margin' ? [`${Number(value).toFixed(1)}%`, name] : [money(Number(value)), name]
            }
          />
          <Bar yAxisId="money" dataKey="net_revenue" name="Net revenue" fill="#3B82F6" radius={[3, 3, 0, 0]} maxBarSize={22} />
          <Bar yAxisId="money" dataKey="cogs" name="COGS" fill="#F59E0B" radius={[3, 3, 0, 0]} maxBarSize={22} />
          <Line
            yAxisId="pct"
            type="monotone"
            dataKey="gross_margin_pct"
            name="Gross margin"
            stroke="#EC4899"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
