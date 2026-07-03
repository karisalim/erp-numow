import React from 'react';
import { DataTable, type Column } from '../ui/DataTable';
import { Badge } from '../ui/Badge';
import { useMoney } from '../../utils/money';
import type { ApiError } from '../../utils/apiError';
import type { LedgerMovement, StatementSummary } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Ledger statement renderer for AR / AP / financial-account statements.
 * Renders the backend summary envelope (opening / totals / closing) above
 * a dense movement table. Data comes straight from the statement
 * endpoints — nothing is recomputed client-side.
 * ──────────────────────────────────────────────────────────────────────────── */

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function movementTypeBadge(type: string): React.ReactNode {
  const t = type.toLowerCase();
  const kind = t.includes('reversal') || t.includes('void') ? 'danger'
    : t.includes('opening') ? 'gray'
    : t.includes('receipt') || t.includes('payment') ? 'success'
    : 'brand';
  return <Badge kind={kind}>{type.replace(/_/g, ' ')}</Badge>;
}

export const StatementTable: React.FC<{
  summary: StatementSummary | null;
  loading?: boolean;
  error?: ApiError | null;
  onRetry?: () => void;
}> = ({ summary, loading, error, onRetry }) => {
  const money = useMoney();

  const columns: Column<LedgerMovement>[] = [
    { key: 'when', header: 'Date', render: (m) => <span className="text-neutral-500 whitespace-nowrap">{fmtDateTime(m.occurred_at)}</span> },
    { key: 'type', header: 'Type', render: (m) => movementTypeBadge(m.movement_type) },
    {
      key: 'source', header: 'Source', render: (m) => (
        <span className="text-neutral-600">
          {m.source_document_type ? `${m.source_document_type}${m.source_document_id ? ` #${m.source_document_id}` : ''}` : '—'}
        </span>
      ),
    },
    { key: 'debit', header: 'Debit', align: 'end', mono: true, render: (m) => (Number(m.debit) ? money(m.debit) : '—') },
    { key: 'credit', header: 'Credit', align: 'end', mono: true, render: (m) => (Number(m.credit) ? money(m.credit) : '—') },
    { key: 'balance', header: 'Balance', align: 'end', mono: true, className: 'font-semibold', render: (m) => money(m.balance_after) },
  ];

  return (
    <div>
      {summary && !loading && !error && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-3">
          {[
            ['Opening', summary.opening_balance],
            ['Total debit', summary.total_debit],
            ['Total credit', summary.total_credit],
            ['Closing', summary.closing_balance],
          ].map(([label, val]) => (
            <div key={label as string} className="bg-neutral-50 border border-neutral-200 rounded-md px-3 py-2">
              <div className="text-[11px] text-neutral-500 font-semibold">{label}</div>
              <div className="text-[14px] font-bold tabular-nums mt-0.5">{money(val as string)}</div>
            </div>
          ))}
        </div>
      )}
      <DataTable<LedgerMovement>
        columns={columns}
        rows={summary?.movements ?? []}
        rowKey={(m) => m.id}
        loading={loading}
        error={error}
        onRetry={onRetry}
        emptyTitle="No movements"
        emptyHint="Ledger entries appear here once documents are posted."
        emptyIcon="doc"
      />
    </div>
  );
};
