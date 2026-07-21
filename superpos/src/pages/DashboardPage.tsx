import React, { useEffect, useMemo, useState } from 'react';
import { AxiosError } from 'axios';
import { dashboardApi, branchesApi, asResults } from '../api/erp';
import { useAuthStore } from '../store/authStore';
import { fmtDecimal } from '../utils/format';
import type { BadgeKind } from '../types';
import type {
  BranchLite, DashboardPaymentMethodSummary, DashboardSummaryResponse, DashboardTrendDay,
} from '../types/erp';
import { MarginCogsChart } from '../components/dashboard/MarginCogsChart';
import { ProductCostHistoryDrawer } from '../components/products/ProductCostHistoryDrawer';

/** Alert-widget specific badge: every row is at or below reorder, so
 *  "In stock" is never appropriate here. */
const lowStockBadge = (stock: number): { kind: BadgeKind; label: string } =>
  stock <= 0
    ? { kind: 'danger', label: 'Out' }
    : { kind: 'warn',   label: 'Low' };
import { useMoney } from '../utils/money';
import { productVisual } from '../utils/categoryVisual';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../components/ui/Icon';

const PAYMENT_COLORS: Record<string, string> = {
  cash:   '#10B981',
  card:   '#3B82F6',
  wallet: '#F59E0B',
};

/* Today in local YYYY-MM-DD (no UTC drift). */
const today = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const fmtRangeLabel = (start: string, end: string): string => {
  if (!start || !end) return 'All time';
  const s = new Date(start + 'T00:00:00');
  const e = new Date(end + 'T00:00:00');
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return `${start} → ${end}`;
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' };
  if (start === end) return s.toLocaleDateString(undefined, opts);
  return `${s.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${e.toLocaleDateString(undefined, opts)}`;
};

export const DashboardPage: React.FC = () => {
  const money = useMoney();
  const branchName = useAuthStore((s) => s.user?.branch_name);

  // Default both ends to today — captured once so a render between the two
  // useState calls can't yield an off-by-a-day window across midnight.
  const [startDate, setStartDate] = useState<string>(() => today());
  const [endDate,   setEndDate]   = useState<string>(() => today());

  // Keep the range chronological. If the user pushes "From" past "To",
  // snap "To" forward; if they pull "To" before "From", snap "From" back.
  const handleStartChange = (next: string) => {
    setStartDate(next);
    if (next && endDate && next > endDate) setEndDate(next);
  };
  const handleEndChange = (next: string) => {
    setEndDate(next);
    if (next && startDate && next < startDate) setStartDate(next);
  };

  const [data,    setData]    = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  /* ─── Branch filter (Sprint 4 Batch 6) ──────────────────────────────────
   * Scoped to Dashboard/sales reporting only — cost data (InventoryCost)
   * stays tenant-wide per D-09, so this never touches the Cost History
   * drawer/export. '' = "All branches" (unfiltered, the default). */
  const [branchId, setBranchId] = useState<number | ''>('');
  const [branches, setBranches] = useState<BranchLite[]>([]);
  useEffect(() => {
    branchesApi.list().then(asResults).then(setBranches).catch(() => setBranches([]));
  }, []);

  /* ─── Fetch summary on date/branch change ───────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    dashboardApi
      .summary({ start_date: startDate, end_date: endDate, branch_id: branchId || undefined })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err: unknown) => {
        if (cancelled) return;
        let msg = 'Failed to load dashboard.';
        if (err instanceof AxiosError) {
          if (err.response?.status === 403) msg = 'You do not have permission to view the dashboard.';
          else if (typeof err.response?.data?.detail === 'string') msg = err.response.data.detail;
        }
        setError(msg);
        setData(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [startDate, endDate, branchId]);

  /* ─── Fetch trend series for the Margin/COGS chart (Sprint 4 Batch 5) ──── */
  const [trendDays,    setTrendDays]    = useState<DashboardTrendDay[]>([]);
  const [trendLoading, setTrendLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setTrendLoading(true);
    dashboardApi
      .trend({ start_date: startDate, end_date: endDate, branch_id: branchId || undefined })
      .then((d) => { if (!cancelled) setTrendDays(d.days); })
      .catch(() => { if (!cancelled) setTrendDays([]); })
      .finally(() => { if (!cancelled) setTrendLoading(false); });
    return () => { cancelled = true; };
  }, [startDate, endDate, branchId]);

  // Sprint 4 Batch 8 — drill-down: click a Top-10 or low-stock row to open
  // the same read-only Cost History drawer used everywhere else (per the
  // owner's confirmed choice, not a new /products/:id route).
  const [costHistoryProduct, setCostHistoryProduct] = useState<{ id: number; name: string } | null>(null);

  const kpis = data?.kpis;
  const paymentMethods = useMemo<DashboardPaymentMethodSummary[]>(() => {
    if (!data?.payment_methods) return [];
    return Object.entries(data.payment_methods)
      .map(([key, v]) => ({ ...v, key } as DashboardPaymentMethodSummary & { key: string }))
      .filter((m) => m.total > 0 || m.count > 0)
      .sort((a, b) => b.total - a.total);
  }, [data]);

  // Selected branch filter takes precedence over the logged-in user's own
  // home branch in the subtitle — they're different concepts once a filter
  // is applied (e.g. an Owner filtering into a branch that isn't their own).
  const filteredBranchName = branchId ? branches.find((b) => b.id === branchId)?.name : undefined;
  const subtitleBranch = filteredBranchName ?? branchName;
  const subtitle = `${fmtRangeLabel(startDate, endDate)}${subtitleBranch ? ` · ${subtitleBranch}` : ''}`;

  /* ─── KPI card definitions, fed by live data ─────────────────────────── */
  // `trend` is deliberately omitted (not zero) on the two costing tiles —
  // the backend hardcodes every *_trend key to 0.0 today (no real trend
  // math exists yet for ANY kpi), and it doesn't even send one for
  // gross_profit/gross_margin_pct at all. Rendering a "0% vs prev" badge
  // there would assert data that doesn't exist; omitting the badge is the
  // honest choice until real trend computation lands.
  const statCards: Array<{ label: string; val: string; trend?: number; color: string; icon: string }> = [
    {
      label: 'Revenue',
      val:   money(kpis?.revenue ?? 0),
      trend: kpis?.revenue_trend ?? 0,
      color: '#3B82F6',
      icon:  'cash',
    },
    {
      label: 'Transactions',
      val:   String(kpis?.transactions ?? 0),
      trend: kpis?.transactions_trend ?? 0,
      color: '#10B981',
      icon:  'receipt',
    },
    {
      label: 'Avg. basket',
      val:   money(kpis?.avg_basket ?? 0),
      trend: kpis?.avg_basket_trend ?? 0,
      color: '#F59E0B',
      icon:  'pos',
    },
    {
      label: 'Items sold',
      val:   fmtDecimal(kpis?.items_sold ?? 0),
      trend: kpis?.items_sold_trend ?? 0,
      color: '#06B6D4',
      icon:  'box',
    },
    {
      label: 'Gross profit',
      val:   money(kpis?.gross_profit ?? 0),
      color: '#8B5CF6',
      icon:  'chart',
    },
    {
      label: 'Gross margin',
      val:   `${(kpis?.gross_margin_pct ?? 0).toFixed(1)}%`,
      color: '#EC4899',
      icon:  'tag',
    },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Dashboard"
        subtitle={subtitle}
        right={
          <>
            {branches.length > 0 && (
              <select
                value={branchId}
                onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
                className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
                aria-label="Branch"
              >
                <option value="">All branches</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            )}
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(e) => handleStartChange(e.target.value)}
                className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
                aria-label="Start date"
              />
              <span className="text-neutral-400">→</span>
              <input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(e) => handleEndChange(e.target.value)}
                className="h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
                aria-label="End date"
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => { const t = today(); setStartDate(t); setEndDate(t); }}
            >
              Today
            </Button>
          </>
        }
      />

      <div className="p-6 space-y-6">
        {error && (
          <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            {error}
          </div>
        )}

        {/* KPI stats */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {statCards.map((s) => (
            <Card key={s.label} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">{s.label}</div>
                  <div className="text-[24px] font-bold tabular-nums mt-1.5 font-mono truncate">
                    {loading ? '…' : s.val}
                  </div>
                  {s.trend !== undefined && (
                    <div className={`text-[12.5px] font-semibold mt-1 flex items-center gap-1 ${s.trend >= 0 ? 'text-success-700' : 'text-danger-600'}`}>
                      <Icon name={s.trend >= 0 ? 'arrowUp' : 'arrowDn'} size={12} />
                      {s.trend === 0 ? '—' : `${s.trend > 0 ? '+' : ''}${s.trend}%`} vs prev
                    </div>
                  )}
                </div>
                <div className="w-9 h-9 rounded-md grid place-items-center shrink-0" style={{ background: `${s.color}1a`, color: s.color }}>
                  <Icon name={s.icon} size={18} />
                </div>
              </div>
            </Card>
          ))}
        </div>

        {/* Margin / COGS trend (Sprint 4 Batch 5) */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-[15px] font-semibold">Revenue, COGS & margin trend</h3>
            <div className="flex items-center gap-4 text-[11.5px] text-neutral-500">
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: '#3B82F6' }} />Net revenue</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: '#F59E0B' }} />COGS</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-0.5 rounded" style={{ background: '#EC4899' }} />Gross margin %</span>
            </div>
          </div>
          <MarginCogsChart days={trendDays} loading={trendLoading} />
        </Card>

        {/* Top products + low stock */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="col-span-2 overflow-hidden">
            <div className="px-5 h-14 border-b border-neutral-200 flex items-center justify-between">
              <h3 className="text-[15px] font-semibold">Top 10 products</h3>
              <span className="text-[12px] text-neutral-500">{fmtRangeLabel(startDate, endDate)}</span>
            </div>
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500">
                <tr>
                  <th className="px-5 py-2.5 text-start font-semibold">#</th>
                  <th className="text-start font-semibold">Product</th>
                  <th className="text-end font-semibold">Units</th>
                  <th className="text-end font-semibold">Revenue</th>
                  <th className="text-end font-semibold">Gross profit</th>
                  <th className="px-5 text-end font-semibold">Margin %</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-neutral-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                        Loading…
                      </span>
                    </td>
                  </tr>
                ) : !data || data.top_products.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-neutral-500">No sales in this range.</td>
                  </tr>
                ) : (
                  data.top_products.map((p, i) => (
                    <tr
                      key={p.id}
                      className="border-t border-neutral-100 hover:bg-neutral-50 cursor-pointer"
                      role="button"
                      tabIndex={0}
                      onClick={() => setCostHistoryProduct({ id: p.id, name: p.name })}
                      onKeyDown={(e) => { if (e.key === 'Enter') setCostHistoryProduct({ id: p.id, name: p.name }); }}
                    >
                      <td className="px-5 py-2.5 text-neutral-400 font-mono w-10">{i + 1}</td>
                      <td className="py-2.5 font-medium">{p.name}</td>
                      <td className="text-end font-mono tabular-nums">{fmtDecimal(p.units_sold)}</td>
                      <td className="text-end font-mono tabular-nums">{money(p.revenue)}</td>
                      <td className="text-end font-mono tabular-nums">{money(p.gross_profit)}</td>
                      <td className="px-5 py-2.5 text-end font-mono tabular-nums">{p.gross_margin_pct.toFixed(1)}%</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </Card>

          <Card className="overflow-hidden flex flex-col">
            <div className="px-5 h-14 border-b border-neutral-200 flex items-center justify-between">
              <h3 className="text-[15px] font-semibold flex items-center gap-2">
                <Icon name="alert" size={16} className="text-warn-600" /> Low stock alerts
              </h3>
              <Badge kind="warn">{data?.low_stock_count ?? 0}</Badge>
            </div>
            <div className="flex-1 divide-y divide-neutral-100 max-h-[420px] overflow-auto">
              {loading ? (
                <div className="px-5 py-10 text-center text-neutral-500 text-[13px]">Loading…</div>
              ) : !data || data.low_stock.length === 0 ? (
                <div className="px-5 py-10 text-center text-neutral-500 text-[13px]">
                  All products above reorder point. 🎉
                </div>
              ) : (
                data.low_stock.map((p) => {
                  const b = lowStockBadge(Number(p.stock));
                  return (
                    <div
                      key={p.id}
                      className="px-5 py-3 flex items-center gap-3 hover:bg-neutral-50 cursor-pointer"
                      role="button"
                      tabIndex={0}
                      onClick={() => setCostHistoryProduct({ id: p.id, name: p.name })}
                      onKeyDown={(e) => { if (e.key === 'Enter') setCostHistoryProduct({ id: p.id, name: p.name }); }}
                    >
                      <div
                        className={`w-8 h-8 rounded-md grid place-items-center text-[13px] shrink-0 bg-gradient-to-br ${productVisual(p.name).gradient}`}
                      >
                        <span aria-hidden>{productVisual(p.name).emoji}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-semibold truncate">{p.name}</div>
                        <div className="text-[11.5px] text-neutral-500">
                          <span className="font-mono">{fmtDecimal(p.stock)}</span>/{fmtDecimal(p.reorder_point)} · reorder point
                        </div>
                      </div>
                      <Badge kind={b.kind}>{b.label}</Badge>
                    </div>
                  );
                })
              )}
            </div>
          </Card>
        </div>

        {/* Payment methods */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="p-5 col-span-2">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold">Payment methods</h3>
              <span className="text-[12px] text-neutral-500">{money(kpis?.revenue ?? 0)} total</span>
            </div>
            {loading ? (
              <div className="py-6 text-center text-neutral-500 text-[13px]">Loading…</div>
            ) : paymentMethods.length === 0 ? (
              <div className="py-6 text-center text-neutral-500 text-[13px]">No payments in this range.</div>
            ) : (
              paymentMethods.map((m) => {
                const key = (m as DashboardPaymentMethodSummary & { key: string }).key;
                const color = PAYMENT_COLORS[key] || '#6B7280';
                return (
                  <div key={key} className="mb-3 last:mb-0">
                    <div className="flex justify-between text-[13px] mb-1">
                      <span className="font-medium capitalize">{m.label || key}</span>
                      <span className="font-mono tabular-nums text-neutral-600">
                        {money(m.total)} <span className="text-neutral-400">· {m.pct}%</span>
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-neutral-100 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${Math.min(100, m.pct)}%`, background: color }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </Card>
        </div>
      </div>

      {costHistoryProduct && (
        <ProductCostHistoryDrawer
          product={costHistoryProduct}
          onClose={() => setCostHistoryProduct(null)}
        />
      )}
    </div>
  );
};
