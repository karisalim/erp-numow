import React from 'react';
import type { Product } from '../../types';
import { initials } from '../../utils/format';
import { useMoney } from '../../utils/money';
import { Icon } from '../ui/Icon';

interface QuickProductCardProps {
  product: Product;
  onAdd: (product: Product) => void;
  /** Optional secondary action — opens the unit picker (carton/box/…) for
   * this product instead of adding it at its base unit. Omit to hide the
   * affordance (e.g. contexts where Sprint 2 units aren't relevant). */
  onPickUnit?: (product: Product) => void;
}

export const QuickProductCard: React.FC<QuickProductCardProps> = ({ product, onAdd, onPickUnit }) => {
  const money = useMoney();
  return (
    <div className="relative group">
      <button
        onClick={() => onAdd(product)}
        className="text-start w-full bg-white border border-neutral-200 rounded-lg hover:border-brand-500 hover:shadow-md transition-all p-3 flex flex-col gap-2 focus-ring"
        aria-label={`Add ${product.name} to cart`}
      >
        <div
          className="aspect-square rounded-md grid place-items-center text-white font-bold text-xl"
          style={{ background: product.color }}
        >
          {initials(product.name)}
        </div>
        <div className="min-h-[36px]">
          <div className="text-[13px] font-semibold leading-tight line-clamp-2">{product.name}</div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[14px] font-bold tabular-nums">{money(product.price)}</span>
          <span className="text-[11px] text-neutral-500">{product.stock}{product.weighted ? 'kg' : ' pcs'}</span>
        </div>
      </button>
      {onPickUnit && (
        <button
          onClick={(e) => { e.stopPropagation(); onPickUnit(product); }}
          className="absolute top-1.5 end-1.5 w-6 h-6 rounded-md bg-white/90 border border-neutral-200 grid place-items-center text-neutral-500 opacity-0 group-hover:opacity-100 hover:border-brand-500 hover:text-brand-600 focus-ring transition-opacity"
          aria-label={`Choose unit for ${product.name}`}
          title="Choose unit (carton, box, …)"
        >
          <Icon name="layers" size={13} />
        </button>
      )}
    </div>
  );
};
