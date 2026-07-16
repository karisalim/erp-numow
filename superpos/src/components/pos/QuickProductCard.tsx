import React from 'react';
import type { Product } from '../../types';
import { useMoney } from '../../utils/money';
import { Icon } from '../ui/Icon';
import { productVisual } from '../../utils/categoryVisual';

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
  const { emoji, gradient } = productVisual(product.name, product.category_name ?? product.sales_category_name);
  const outOfStock = !product.weighted && product.stock <= 0;
  const lowStock = !outOfStock && !product.weighted && product.stock > 0 && product.stock <= product.reorder;

  return (
    <div className="relative group">
      <button
        onClick={() => onAdd(product)}
        className="text-start w-full bg-white border border-neutral-200 rounded-xl hover:border-brand-400 hover:shadow-lg hover:-translate-y-0.5 transition-all p-2.5 flex flex-col gap-2 focus-ring overflow-hidden"
        aria-label={`Add ${product.name} to cart`}
      >
        <div className={`relative aspect-square rounded-lg grid place-items-center text-4xl bg-gradient-to-br ${gradient} shadow-inner`}>
          <span className="drop-shadow-sm" aria-hidden>{emoji}</span>
          {outOfStock && (
            <span className="absolute inset-x-0 bottom-1.5 mx-auto w-fit px-2 py-0.5 rounded-full bg-black/70 text-white text-[9px] font-bold uppercase tracking-wide">
              Out of stock
            </span>
          )}
          {lowStock && (
            <span className="absolute top-1.5 end-1.5 w-2.5 h-2.5 rounded-full bg-warn-500 ring-2 ring-white" title="Low stock" />
          )}
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
