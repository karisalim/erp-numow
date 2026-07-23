import React from 'react';
import { LoadingState, EmptyState, QueryErrorState } from './states';
import { Pagination } from './Pagination';
import { Icon } from './Icon';
import type { ApiError } from '../../utils/apiError';

/* ─────────────────────────────────────────────────────────────────────────────
 * Generic dense data table in the prototype `.tbl` style:
 * uppercase 11px headers on n50, 13.5px cells, row hover, right-aligned
 * numeric columns. Owns loading / empty / error / pagination so pages
 * don't re-implement them.
 *
 * Phase 3 (Enterprise UX Polish, item 8): two opt-in, additive capabilities
 * — column sorting (`sortable` on a column + `sort`/`onSort` on the table)
 * and a sticky header (`stickyHeader`). Both default to the previous,
 * unchanged behavior, so every existing call site across the app keeps
 * rendering exactly as before unless it explicitly opts in.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  /** Right-align (numbers/amounts). */
  align?: 'start' | 'end';
  /** Monospaced tabular numbers. */
  mono?: boolean;
  className?: string;
  /** Clickable header that toggles `onSort(key)` — only rendered as
   * clickable when the table is also given `sort`/`onSort`. */
  sortable?: boolean;
  render: (row: T) => React.ReactNode;
}

export interface SortState {
  key: string;
  dir: 'asc' | 'desc';
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
  /** Current sort + toggle handler — omit both to leave headers static
   * (existing behavior). Sort direction/logic is the caller's — this
   * component only renders the indicator and forwards the click. */
  sort?: SortState;
  onSort?: (key: string) => void;
  /** Keep the header row visible while the table body scrolls — opt-in
   * since it requires a bounded scroll container the caller controls. */
  stickyHeader?: boolean;
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
  sort,
  onSort,
  stickyHeader,
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
              {columns.map((c) => {
                const isSortable = !!(c.sortable && onSort);
                const isSorted = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    aria-sort={isSorted ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                    className={`text-start text-[11px] tracking-wider uppercase text-neutral-500 font-bold px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50 whitespace-nowrap
                      ${stickyHeader ? 'sticky top-0 z-10' : ''}
                      ${c.align === 'end' ? 'text-end' : ''} ${c.className ?? ''}`}
                  >
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => onSort!(c.key)}
                        className={`inline-flex items-center gap-1 focus-ring rounded hover:text-neutral-800 transition-colors
                          ${c.align === 'end' ? 'flex-row-reverse' : ''}`}
                      >
                        {c.header}
                        <Icon
                          name={isSorted ? (sort!.dir === 'asc' ? 'arrowUp' : 'arrowDn') : 'arrowDn'}
                          size={11}
                          className={isSorted ? 'text-brand-500' : 'text-neutral-300'}
                        />
                      </button>
                    ) : c.header}
                  </th>
                );
              })}
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
