import React, { useEffect } from 'react';
import { Icon } from './Icon';

/**
 * Side drawer (end-anchored, RTL-aware) for detail views: customer /
 * supplier profiles, movement previews. Prototype modal visual language —
 * white panel, soft shadow, 64px header.
 */
export const Drawer: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  widthClassName?: string;
}> = ({ title, subtitle, onClose, children, footer, widthClassName = 'max-w-[520px]' }) => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[1100] bg-black/40 backdrop-blur-[1px] flex justify-end fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`h-full w-full ${widthClassName} bg-white shadow-lg flex flex-col`}
      >
        <div className="h-16 px-5 border-b border-neutral-200 flex items-center justify-between shrink-0">
          <div className="min-w-0">
            <div className="text-[16px] font-bold truncate">{title}</div>
            {subtitle && <div className="text-[12px] text-neutral-500 truncate">{subtitle}</div>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-9 h-9 grid place-items-center rounded-md hover:bg-neutral-100 text-neutral-500 focus-ring"
          >
            <Icon name="x" size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="px-5 py-3.5 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
