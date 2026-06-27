import React from 'react';
import type { Product } from '../../types';
import { initials } from '../../utils/format';
import { useMoney } from '../../utils/money';

interface QuickProductCardProps {
  product: Product;
  onAdd: (product: Product) => void;
}

export const QuickProductCard: React.FC<QuickProductCardProps> = ({ product, onAdd }) => {
  const money = useMoney();
  return (
    <button
      onClick={() => onAdd(product)}
      className="text-start bg-white border border-neutral-200 rounded-lg hover:border-brand-500 hover:shadow-md transition-all p-3 flex flex-col gap-2 focus-ring group"
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
  );
};
