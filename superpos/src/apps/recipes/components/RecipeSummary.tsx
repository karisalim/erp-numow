import React from 'react';
import { Card, CardBody } from '../../../components/ui/Card';
import { Icon } from '../../../components/ui/Icon';

const Tile: React.FC<{ icon: string; label: string; value: React.ReactNode; tone: string }> = ({ icon, label, value, tone }) => (
  <Card>
    <CardBody className="flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg grid place-items-center shrink-0 ${tone}`}>
        <Icon name={icon} size={18} />
      </div>
      <div className="min-w-0">
        <div className="text-[20px] font-bold leading-none">{value}</div>
        <div className="text-[11.5px] text-neutral-500 mt-1">{label}</div>
      </div>
    </CardBody>
  </Card>
);

/**
 * Quick-stat strip at the top of the Recipe Dashboard. Every number here
 * comes from a single already-fetched list response (array length) — pure
 * display aggregation, no cost/margin, no extra requests.
 *
 * Deliberately only 2 tiles, not 4: a per-product "has this product got an
 * active recipe yet" status and a tenant-wide variant count both require
 * either an N+1 request loop (one call per product) or a bulk endpoint
 * that doesn't exist (`/products/{pk}/recipes/` and `/products/{pk}/
 * variants/` are both product-scoped, there is no tenant-wide list of
 * either). Rather than loop per-row to fake those two stats, they're
 * simply not shown — see the Batch 8 Architecture Review's Gaps section.
 */
export const RecipeSummary: React.FC<{
  totalRecipeProducts: number;
  modifierGroupCount: number;
}> = ({ totalRecipeProducts, modifierGroupCount }) => (
  <div className="grid grid-cols-2 gap-3 mb-4 max-w-md">
    <Tile icon="layers" label="Recipe products" value={totalRecipeProducts} tone="bg-brand-50 text-brand-600" />
    <Tile icon="tag" label="Modifier groups" value={modifierGroupCount} tone="bg-success-50 text-success-600" />
  </div>
);
