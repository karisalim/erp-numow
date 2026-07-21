import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../ui/Icon';

export type RowAction = 'view' | 'edit' | 'history' | 'costHistory' | 'receive' | 'units' | 'delete';

interface Props {
  onSelect: (action: RowAction) => void;
}

/**
 * Per-row "⋮" menu. Self-contained popup that closes on outside-click
 * and on Escape. Positions itself below-and-aligned-right relative to
 * the trigger button.
 */
export const ProductActionsMenu: React.FC<Props> = ({ onSelect }) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const choose = (action: RowAction) => {
    setOpen(false);
    onSelect(action);
  };

  return (
    <div ref={wrapRef} className="relative inline-block text-start">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="w-7 h-7 grid place-items-center rounded text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 focus-ring"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Row actions"
      >
        ⋮
      </button>

      {open && (
        <div
          role="menu"
          className="absolute end-0 mt-1 z-30 w-36 rounded-md border border-neutral-200 bg-white shadow-lg py-1 text-[13px] fade-in"
        >
          <MenuItem onClick={() => choose('view')}    icon="eye">View</MenuItem>
          <MenuItem onClick={() => choose('edit')}    icon="gear">Edit</MenuItem>
          <div className="my-1 border-t border-neutral-100" />
          <MenuItem onClick={() => choose('history')} icon="receipt">Stock movements</MenuItem>
          <MenuItem onClick={() => choose('costHistory')} icon="chart">Cost history</MenuItem>
          <MenuItem onClick={() => choose('receive')} icon="plus">Receive stock</MenuItem>
          <MenuItem onClick={() => choose('units')}   icon="layers">Units & pricing</MenuItem>
          <div className="my-1 border-t border-neutral-100" />
          <MenuItem onClick={() => choose('delete')}  icon="trash" tone="danger">Delete</MenuItem>
        </div>
      )}
    </div>
  );
};

const MenuItem: React.FC<React.PropsWithChildren<{
  onClick: () => void; icon: string; tone?: 'danger';
}>> = ({ onClick, icon, tone, children }) => (
  <button
    type="button"
    role="menuitem"
    onClick={onClick}
    className={`w-full flex items-center gap-2 px-3 py-1.5 text-start hover:bg-neutral-50 focus-ring
      ${tone === 'danger' ? 'text-danger-600 hover:bg-danger-50' : 'text-neutral-700'}`}
  >
    <Icon name={icon} size={14} />
    {children}
  </button>
);
