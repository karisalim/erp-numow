import React from 'react';

/**
 * In-page header block: title + optional subtitle on the left, actions on
 * the right. Sits inside the scrollable page area (the fixed 64px app
 * Header carries the route title; this one is for page-local context and
 * primary actions).
 */
export const PageHeader: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}> = ({ title, subtitle, actions, className = '' }) => (
  <div className={`flex items-start justify-between gap-4 flex-wrap mb-4 ${className}`}>
    <div className="min-w-0">
      <h1 className="text-[18px] font-bold text-neutral-900 leading-tight">{title}</h1>
      {subtitle && <div className="text-[12.5px] text-neutral-500 mt-0.5">{subtitle}</div>}
    </div>
    {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
  </div>
);
