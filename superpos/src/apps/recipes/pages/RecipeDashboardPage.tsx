import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../../../components/layout/Header';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { Badge } from '../../../components/ui/Badge';
import { DataTable, type Column } from '../../../components/ui/DataTable';
import { ActiveBadge } from '../../../components/ui/StatusBadge';
import { useMoney } from '../../../utils/money';
import { useQuery } from '../../../hooks/useQuery';
import { catalogApi, modifierGroupsApi, asResults } from '../api';
import { isRecipeProduct } from '../services/productEligibility';
import { recipesPaths } from '../services/navigation';
import { RecipeSummary } from '../components/RecipeSummary';
import type { RecipeCatalogProduct } from '../types';

/**
 * `/recipes` — the Recipe app's landing page: quick stats + the list of
 * every RECIPE_PRODUCT-typed product, each row opening its own recipe
 * detail/editor.
 *
 * Backend gap (see module docstring in `api/catalogApi.ts`): `/products/`
 * has no `product_type` filter, so this page fetches a larger page and
 * filters `product_type === 'recipe_product'` client-side for display —
 * narrowing an already-returned field, not recomputing anything.
 */
export const RecipeDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const money = useMoney();

  const productsQ = useQuery(() => catalogApi.listRecipeEligibleProducts(200), []);
  const groupsQ = useQuery(() => modifierGroupsApi.list({ is_active: 'true' }).then(asResults), []);

  const recipeProducts = (productsQ.data ?? []).filter(isRecipeProduct);

  const columns: Column<RecipeCatalogProduct>[] = [
    { key: 'name', header: 'Product', render: (p) => <span className="font-semibold">{p.name}</span> },
    { key: 'type', header: 'Type', render: () => <Badge kind="brand">Recipe</Badge> },
    { key: 'category', header: 'Category', render: (p) => p.category_name || '—' },
    { key: 'price', header: 'Price', align: 'end', mono: true, render: (p) => money(p.price) },
    { key: 'status', header: 'Status', render: (p) => <ActiveBadge active={p.active !== false} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (p) => (
        <div className="flex justify-end">
          <Icon name="chevR" size={14} className="text-neutral-400" />
        </div>
      ),
    },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Recipes"
        subtitle="Recipes, size variants, modifiers, and food-cost reporting"
        right={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => navigate(recipesPaths.modifiers())}>
              <Icon name="tag" size={14} /> Modifiers
            </Button>
            <Button size="sm" variant="secondary" onClick={() => navigate(recipesPaths.reports())}>
              <Icon name="chart" size={14} /> Reports
            </Button>
            <Button size="sm" onClick={() => navigate(recipesPaths.new())}>
              <Icon name="plus" size={14} /> New recipe
            </Button>
          </div>
        }
      />
      <div className="p-5 max-w-[1100px] w-full mx-auto">
        <RecipeSummary
          totalRecipeProducts={recipeProducts.length}
          modifierGroupCount={(groupsQ.data ?? []).length}
        />
        <DataTable<RecipeCatalogProduct>
          columns={columns}
          rows={recipeProducts}
          rowKey={(p) => p.id}
          loading={productsQ.loading}
          error={productsQ.error}
          onRetry={productsQ.refetch}
          onRowClick={(p) => navigate(recipesPaths.detail(p.id))}
          emptyTitle="No recipe products yet"
          emptyHint="Create a product with Type = Recipe on the Products page, then build its recipe here."
          emptyIcon="layers"
        />
      </div>
    </div>
  );
};
