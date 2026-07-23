import React from 'react';
import { Badge } from './Badge';
import type { BadgeKind } from '../../types';
import type { ProductTypeValue } from '../../types/erp';

/**
 * Phase 3 (Enterprise UX Polish) — a single, shared vocabulary for the four
 * status concepts that recur across Products/Recipes/POS screens, so a
 * "Recipe product" badge (or "Out of stock", or "Hidden from POS") always
 * looks the same regardless of which screen renders it. Every badge here
 * is a pure function of data already on the record — none of them compute
 * or infer a new business fact; they just render the same field
 * consistently (e.g. `StockStatusBadge` reads `stock`/`reorder`, the exact
 * numbers `ProductsPage`'s filter chips already use).
 */

const PRODUCT_TYPE_TONE: Record<ProductTypeValue, BadgeKind> = {
  stock_item:     'gray',
  resale:         'gray',
  ingredient:     'info',
  packaging:      'info',
  prep_item:      'violet',
  recipe_product: 'violet',
  service:        'brand',
  bundle:         'warn',
  fixed_asset:    'gray',
};

const PRODUCT_TYPE_LABEL: Record<ProductTypeValue, string> = {
  stock_item:     'Stock item',
  resale:         'Resale',
  ingredient:     'Ingredient',
  packaging:      'Packaging',
  prep_item:      'Prep item',
  recipe_product: 'Recipe product',
  service:        'Service',
  bundle:         'Bundle',
  fixed_asset:    'Fixed asset',
};

export const ProductTypeBadge: React.FC<{ productType?: ProductTypeValue | null }> = ({ productType }) => {
  if (!productType) return null;
  return <Badge kind={PRODUCT_TYPE_TONE[productType] ?? 'gray'}>{PRODUCT_TYPE_LABEL[productType] ?? productType}</Badge>;
};

export const StockStatusBadge: React.FC<{ stock: number; reorder: number }> = ({ stock, reorder }) => {
  if (stock <= 0) return <Badge kind="danger">Out of stock</Badge>;
  if (stock <= reorder) return <Badge kind="warn">Low stock</Badge>;
  return <Badge kind="success">In stock</Badge>;
};

export const PosVisibilityBadge: React.FC<{ showOnPos: boolean; canSell: boolean }> = ({ showOnPos, canSell }) => {
  if (!canSell) return <Badge kind="gray">Not sellable</Badge>;
  return showOnPos ? <Badge kind="success">On POS</Badge> : <Badge kind="gray">Hidden from POS</Badge>;
};

export type RecipeWorkflowStage = 'no_recipe' | 'draft' | 'active_not_live' | 'pos_ready';

const RECIPE_STAGE_TONE: Record<RecipeWorkflowStage, BadgeKind> = {
  no_recipe:        'gray',
  draft:            'warn',
  active_not_live:  'info',
  pos_ready:        'success',
};

const RECIPE_STAGE_LABEL: Record<RecipeWorkflowStage, string> = {
  no_recipe:        'No recipe',
  draft:            'Draft',
  active_not_live:  'Active — not on POS',
  pos_ready:        'POS ready',
};

export const RecipeStatusBadge: React.FC<{ stage: RecipeWorkflowStage }> = ({ stage }) => (
  <Badge kind={RECIPE_STAGE_TONE[stage]}>{RECIPE_STAGE_LABEL[stage]}</Badge>
);
