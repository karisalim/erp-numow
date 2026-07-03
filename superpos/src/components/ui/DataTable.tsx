import React from 'react';
import { LoadingState, EmptyState, QueryErrorState } from './states';
import { Pagination } from './Pagination';
import type { ApiError } from '../../utils/apiError';

/* ─────────────────────────────────────────────────────────────────────────────
 * Generic dense data table in the prototype `.tbl` style:
 * uppercase 11px headers on n50, 13.5px cells, row hover, right-aligned
 * numeric columns. Owns loading / empty / error / pagination so pages
 * don't re-implement them.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  /** Right-align (numbers/amounts). */
  align?: 'start' | 'end';
  /** Monospaced tabular numbers. */
  mono?: boolean;
  className?: string;
  render: (row: T) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  loading?: boolean;
  error?: ApiError | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  emptyIcon?: string;
  emptyAction?: React.ReactNode;
  onRowClick?: (row: T) => void;
  /** Server pagination (optional). */
  page?: number;
  pageSize?: number;
  count?: number;
  onPage?: (page: number) => void;
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  emptyTitle = 'No records',
  emptyHint,
  emptyIcon,
  emptyAction,
  onRowClick,
  page,
  pageSize,
  count,
  onPage,
  className = '',
}: DataTableProps<T>) {
  let body: React.ReactNode = null;

  if (loading) {
    body = <LoadingState />;
  } else if (error) {
    body = <QueryErrorState error={error} onRetry={onRetry} />;
  } else if (rows.length === 0) {
    body = <EmptyState title={emptyTitle} hint={emptyHint} icon={emptyIcon} action={emptyAction} />;
  }

  return (
    <div className={`bg-white border border-neutral-200 rounded-lg shadow-sm overflow-hidden ${className}`}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse min-w-[560px]">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`text-start text-[11px] tracking-wider uppercase text-neutral-500 font-bold px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50 whitespace-nowrap
                    ${c.align === 'end' ? 'text-end' : ''} ${c.className ?? ''}`}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          {!body && (
            <tbody>
              {rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => { if (e.key === 'Enter') onRowClick(row); }
                      : undefined
                  }
                  className={`group ${onRowClick ? 'cursor-pointer focus-ring' : ''}`}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`px-3.5 py-2.5 border-b border-neutral-100 text-[13.5px] group-hover:bg-neutral-50
                        ${c.align === 'end' ? 'text-end' : ''}
                        ${c.mono ? 'font-mono tabular-nums' : ''} ${c.className ?? ''}`}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          )}
        </table>
      </div>
      {body}
      {!body && page !== undefined && pageSize !== undefined && count !== undefined && onPage && (
        <Pagination page={page} pageSize={pageSize} count={count} onPage={onPage} />
      )}
    </div>
  );
}
