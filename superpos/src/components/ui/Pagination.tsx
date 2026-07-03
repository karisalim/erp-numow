import React from 'react';
import { Icon } from './Icon';

/**
 * Server-side pagination footer for DRF page-number pagination.
 * Renders nothing when there is only one page.
 */
export const Pagination: React.FC<{
  page: number;
  pageSize: number;
  count: number;
  onPage: (page: number) => void;
  className?: string;
}> = ({ page, pageSize, count, onPage, className = '' }) => {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(count, page * pageSize);
  return (
    <div className={`flex items-center justify-between px-4 py-2.5 border-t border-neutral-200 text-[12.5px] text-neutral-500 ${className}`}>
      <span className="tabular-nums">
        {from}–{to} of {count}
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
          className="w-8 h-8 grid place-items-center rounded-md border border-neutral-300 bg-white disabled:opacity-40 hover:bg-neutral-50 focus-ring"
        >
          <Icon name="chevL" size={15} className="rtl:rotate-180" />
        </button>
        <span className="px-2 font-semibold text-neutral-700 tabular-nums">
          {page} / {pages}
        </span>
        <button
          onClick={() => onPage(page + 1)}
          disabled={page >= pages}
          aria-label="Next page"
          className="w-8 h-8 grid place-items-center rounded-md border border-neutral-300 bg-white disabled:opacity-40 hover:bg-neutral-50 focus-ring"
        >
          <Icon name="chevR" size={15} className="rtl:rotate-180" />
        </button>
      </div>
    </div>
  );
};
