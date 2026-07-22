import React from 'react';
import { Card, CardBody } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { useMoney } from '../../../utils/money';
import { formatDate } from '../utils/format';
import type { RecipeCatalogProduct } from '../types';
import type { Recipe, RecipeVersion } from '../types';

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div>
    <div className="text-[11px] uppercase tracking-wider font-bold text-neutral-400">{label}</div>
    <div className="text-[14px] font-semibold text-neutral-900 mt-0.5">{value}</div>
  </div>
);

/**
 * Read-only summary of a product + its recipe container + active version —
 * every value comes straight from the backend response, nothing derived.
 */
export const RecipeInfoCard: React.FC<{
  product: RecipeCatalogProduct;
  recipe: Recipe | null;
  activeVersion: RecipeVersion | null;
}> = ({ product, recipe, activeVersion }) => {
  const money = useMoney();
  return (
    <Card>
      <CardBody className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Stat label="Sale price" value={money(product.price)} />
        <Stat label="Category" value={product.category_name || '—'} />
        <Stat
          label="Recipe status"
          value={recipe ? (recipe.is_active ? <Badge kind="success">Active</Badge> : <Badge kind="gray">Inactive</Badge>) : <Badge kind="warn">No recipe yet</Badge>}
        />
        <Stat
          label="Active version"
          value={activeVersion ? `v${activeVersion.version_no} · ${activeVersion.lines.length} ingredients` : '—'}
        />
        {activeVersion && (
          <Stat label="Version created" value={formatDate(activeVersion.created_at)} />
        )}
      </CardBody>
    </Card>
  );
};
