import React from 'react';
import type { CartItem } from '../../types';
import { useMoney } from '../../utils/money';
import { Icon } from '../ui/Icon';
import { productVisual } from '../../utils/categoryVisual';

interface CartLineProps {
  item: CartItem;
  onQty: (lineId: string, delta: number) => void;
  onRemove: (lineId: string) => void;
  editing: string | null;
  setEditing: (id: string | null) => void;
  flash: boolean;
}

export const CartLine: React.FC<CartLineProps> = ({
  item,
  onQty,
  onRemove,
  editing,
  setEditing,
  flash,
}) => {
  const money = useMoney();
  const { emoji, gradient } = productVisual(item.name, item.category_name ?? item.sales_category_name);
  return (
  <div
    className={`row-zebra group flex items-center gap-3 px-4 py-2.5 border-b border-neutral-100 ${flash ? 'scan-flash' : ''}`}
  >
    <div
      className={`w-9 h-9 rounded-md grid place-items-center text-[16px] shrink-0 bg-gradient-to-br ${gradient}`}
    >
      <span aria-hidden>{emoji}</span>
    </div>

    <div className="flex-1 min-w-0">
      <div className="text-[13.5px] font-semibold truncate">
        {item.name}
        {item.unitLabel && (
          <span className="ms-1.5 text-[10.5px] font-semibold text-brand-700 bg-brand-50 border border-brand-500/30 rounded px-1.5 py-0.5 align-middle">
            {item.unitLabel}
          </span>
        )}
        {item.variantName && (
          <span className="ms-1.5 text-[10.5px] font-semibold text-violet-700 bg-violet-50 border border-violet-500/30 rounded px-1.5 py-0.5 align-middle">
            {item.variantName}
          </span>
        )}
      </div>
      {item.modifiers && item.modifiers.length > 0 && (
        <div className="text-[11px] text-neutral-500 truncate">
          + {item.modifiers.map((m) => m.name).join(', ')}
        </div>
      )}
      <div className="text-[11.5px] text-neutral-500 flex items-center gap-2">
        {item.barcode && <span className="font-mono">{item.barcode}</span>}
        {item.barcode && <span>·</span>}
        <span>
          {money(item.price)}
          {item.weighted ? '/kg' : item.unitLabel ? ` / ${item.unitLabel}` : ''}
        </span>
      </div>
    </div>

    {editing === item.lineId ? (
      <div className="flex items-center gap-1 bg-neutral-100 rounded-md p-1">
        <button
          onClick={() => onQty(item.lineId, -1)}
          className="w-7 h-7 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
          aria-label="Decrease quantity"
        >
          <Icon name="minus" size={14} />
        </button>
        <span className="w-14 text-center font-mono text-[14px] font-semibold tabular-nums">
          {item.weighted ? item.qty.toFixed(3) + 'kg' : item.qty}
        </span>
        <button
          onClick={() => onQty(item.lineId, +1)}
          className="w-7 h-7 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
          aria-label="Increase quantity"
        >
          <Icon name="plus" size={14} />
        </button>
        <button
          onClick={() => onRemove(item.lineId)}
          className="w-7 h-7 rounded grid place-items-center text-danger-600 hover:bg-danger-50 focus-ring"
          aria-label="Remove item"
        >
          <Icon name="trash" size={14} />
        </button>
        <button
          onClick={() => setEditing(null)}
          className="w-7 h-7 rounded grid place-items-center text-neutral-500 hover:bg-neutral-200 focus-ring"
          aria-label="Confirm"
        >
          <Icon name="check" size={14} />
        </button>
      </div>
    ) : item.weighted ? (
      <button
        onClick={() => setEditing(item.lineId)}
        className="text-end font-mono text-[12px] leading-tight hover:bg-brand-50 px-2 py-1 rounded focus-ring"
      >
        <div className="text-brand-700 font-semibold">{item.qty.toFixed(3)} kg</div>
        <div className="text-neutral-500">× {money(item.price)}/kg</div>
      </button>
    ) : (
      <button
        onClick={() => setEditing(item.lineId)}
        className="text-[13px] font-mono text-neutral-600 hover:text-brand-600 hover:bg-brand-50 px-2 py-1 rounded focus-ring"
      >
        ×{item.qty}{item.unitLabel ? ` ${item.unitLabel}` : ''}
      </button>
    )}

    <div className="w-20 text-end font-mono font-semibold text-[14px] tabular-nums">
      {money(item.qty * item.price)}
    </div>
  </div>
  );
};
