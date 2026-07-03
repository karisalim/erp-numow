import React from 'react';
import { Icon } from './Icon';
import { Button } from './Button';
import type { ApiError } from '../../utils/apiError';

/* ─────────────────────────────────────────────────────────────────────────────
 * Shared async-UI states: loading / empty / error / permission-denied,
 * plus the persistent AlertBanner. Visual language follows the approved
 * prototype (soft cards, muted neutrals, compact type).
 * ──────────────────────────────────────────────────────────────────────────── */

export const LoadingState: React.FC<{ label?: string; className?: string }> = ({
  label = 'Loading…',
  className = '',
}) => (
  <div className={`flex flex-col items-center justify-center gap-3 py-14 text-neutral-400 ${className}`} role="status">
    <span className="w-7 h-7 rounded-full border-2 border-neutral-200 border-t-brand-500 animate-spin" />
    <span className="text-[13px] font-medium">{label}</span>
  </div>
);

export const EmptyState: React.FC<{
  title: string;
  hint?: string;
  icon?: string;
  action?: React.ReactNode;
  className?: string;
}> = ({ title, hint, icon = 'box', action, className = '' }) => (
  <div className={`flex flex-col items-center justify-center gap-2 py-14 text-center ${className}`}>
    <span className="text-neutral-300"><Icon name={icon} size={34} /></span>
    <div className="text-[14px] font-semibold text-neutral-600">{title}</div>
    {hint && <div className="text-[12.5px] text-neutral-400 max-w-sm">{hint}</div>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

export const ErrorState: React.FC<{
  message?: string;
  onRetry?: () => void;
  className?: string;
}> = ({ message = 'Something went wrong loading this data.', onRetry, className = '' }) => (
  <div className={`flex flex-col items-center justify-center gap-2 py-14 text-center ${className}`}>
    <span className="text-danger-500"><Icon name="alert" size={30} /></span>
    <div className="text-[14px] font-semibold text-neutral-700">Failed to load</div>
    <div className="text-[12.5px] text-neutral-500 max-w-md">{message}</div>
    {onRetry && (
      <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
        <Icon name="sync" size={14} /> Retry
      </Button>
    )}
  </div>
);

export const PermissionDeniedState: React.FC<{ message?: string; className?: string }> = ({
  message = 'You do not have permission to view this page. Contact a manager if you believe this is a mistake.',
  className = '',
}) => (
  <div className={`flex flex-col items-center justify-center gap-2 py-14 text-center ${className}`}>
    <span className="text-warn-500"><Icon name="lock" size={30} /></span>
    <div className="text-[14px] font-semibold text-neutral-700">Access denied</div>
    <div className="text-[12.5px] text-neutral-500 max-w-md">{message}</div>
  </div>
);

/**
 * Route the right state for a query result: permission errors render the
 * denied state, everything else the generic error state.
 */
export const QueryErrorState: React.FC<{ error: ApiError; onRetry?: () => void; className?: string }> = ({
  error,
  onRetry,
  className,
}) =>
  error.permissionDenied
    ? <PermissionDeniedState message={error.message} className={className} />
    : <ErrorState message={error.message} onRetry={onRetry} className={className} />;

/* ── AlertBanner — persistent inline alert (not a toast) ────────────────── */

export type AlertTone = 'info' | 'warn' | 'danger' | 'success';

const toneClasses: Record<AlertTone, string> = {
  info:    'bg-info-50 text-info-700 border-info-500/30',
  warn:    'bg-warn-50 text-warn-700 border-warn-500/30',
  danger:  'bg-danger-50 text-danger-700 border-danger-500/30',
  success: 'bg-success-50 text-success-700 border-success-500/30',
};

export const AlertBanner: React.FC<{
  tone?: AlertTone;
  title?: string;
  children: React.ReactNode;
  className?: string;
  onDismiss?: () => void;
}> = ({ tone = 'info', title, children, className = '', onDismiss }) => (
  <div className={`flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border text-[12.5px] ${toneClasses[tone]} ${className}`} role="alert">
    <span className="mt-0.5 shrink-0"><Icon name="alert" size={15} /></span>
    <div className="min-w-0 flex-1">
      {title && <div className="font-bold">{title}</div>}
      <div>{children}</div>
    </div>
    {onDismiss && (
      <button onClick={onDismiss} aria-label="Dismiss" className="shrink-0 opacity-70 hover:opacity-100">
        <Icon name="x" size={14} />
      </button>
    )}
  </div>
);
