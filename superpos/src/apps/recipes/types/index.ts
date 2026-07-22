/* ─────────────────────────────────────────────────────────────────────────────
 * Recipes / BOM / Modifiers feature — types.
 *
 * Every interface here mirrors a Sprint 5 backend serializer field-for-field
 * (superpos_backend/recipes/serializers.py). Decimals arrive as strings on
 * the wire, exactly like the rest of this codebase's ERP types — keep them
 * as strings in state, format only for display via ../utils/format.
 * ──────────────────────────────────────────────────────────────────────────── */

/* ── Product Variants (Sprint 5 Batch 2) ─────────────────────────────────── */

export interface ProductVariant {
  id: number;
  name: string;
  sku: string;
  plu: string;
  price: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductVariantPayload {
  name: string;
  sku?: string;
  plu?: string;
  price: string;
  sort_order?: number;
}

/* ── Recipes / Versions / Lines (Sprint 5 Batch 3) ───────────────────────── */

export interface Recipe {
  id: number;
  variant: number | null;
  variant_name: string;
  active_version_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RecipePayload {
  variant?: number | null;
}

export type RecipeVersionStatus = 'draft' | 'active' | 'archived';

export interface RecipeLine {
  id: number;
  component_product: number;
  component_product_name: string;
  component_unit: number | null;
  component_unit_name: string;
  entered_qty: string;
  qty_base: string;
  sort_order: number;
  is_active: boolean;
}

/** Body shape for one line when creating a new RecipeVersion — no `id`,
 * `qty_base` is always server-computed, never sent. */
export interface RecipeLineInput {
  component_product: number;
  component_unit?: number | null;
  entered_qty: string;
  sort_order?: number;
}

export interface RecipeVersion {
  id: number;
  version_no: number;
  status: RecipeVersionStatus;
  status_display: string;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  lines: RecipeLine[];
}

export interface RecipeVersionPayload {
  lines: RecipeLineInput[];
}

/* ── Modifiers (Sprint 5 Batch 4) ─────────────────────────────────────────── */

export type ModifierSelectionType = 'single' | 'multiple';

export interface ModifierGroup {
  id: number;
  name: string;
  selection_type: ModifierSelectionType;
  min_select: number | null;
  max_select: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModifierGroupPayload {
  name: string;
  selection_type?: ModifierSelectionType;
  min_select?: number | null;
  max_select?: number | null;
}

export interface ModifierOption {
  id: number;
  name: string;
  price_delta: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModifierOptionPayload {
  name: string;
  price_delta?: string;
  sort_order?: number;
}

export interface ProductModifierGroup {
  id: number;
  modifier_group: number;
  modifier_group_name: string;
  sort_order: number;
}

export interface ProductModifierGroupPayload {
  modifier_group: number;
  sort_order?: number;
}

export interface ModifierOptionConsumption {
  id: number;
  variant: number | null;
  variant_name: string;
  component_product: number;
  component_product_name: string;
  component_unit: number | null;
  entered_qty: string;
  qty_base: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModifierOptionConsumptionPayload {
  variant?: number | null;
  component_product: number;
  component_unit?: number | null;
  entered_qty: string;
}

/* ── Reports (Sprint 5 Batch 6) ──────────────────────────────────────────── */

export interface RecipeProfitabilityRow {
  product_id: number;
  product_name: string;
  variant_id: number | null;
  variant_name: string;
  units_sold: number;
  revenue: number;
  food_cost: number;
  gross_profit: number;
  gross_margin_pct: number;
  food_cost_pct: number;
}

export interface IngredientConsumptionRow {
  product_id: number;
  product_name: string;
  qty_consumed: number;
  cost_consumed: number;
}

export interface ReportRange {
  start_date: string;
  end_date: string;
}

export interface RecipeProfitabilityResponse {
  range: ReportRange;
  results: RecipeProfitabilityRow[];
}

export interface IngredientConsumptionResponse {
  range: ReportRange;
  results: IngredientConsumptionRow[];
}

export type RecipeProfitabilityOrdering =
  | 'revenue' | '-revenue' | 'units_sold' | '-units_sold'
  | 'gross_profit' | '-gross_profit' | 'gross_margin_pct' | '-gross_margin_pct'
  | 'food_cost_pct' | '-food_cost_pct';

export type IngredientConsumptionOrdering =
  | 'qty_consumed' | '-qty_consumed' | 'cost_consumed' | '-cost_consumed';

/* ── Lightweight product shape for the catalog / ingredient picker ──────── */

/** Only the fields the recipe app actually reads off `/products/` — not the
 * full `Product` type from the main app, to keep this feature's dependency
 * surface small and explicit. */
export interface RecipeCatalogProduct {
  id: number;
  name: string;
  sku: string;
  barcode: string;
  product_type?: string;
  product_type_display?: string;
  price: number | string;
  cost: number | string;
  stock: number | string;
  category_name?: string;
  active?: boolean;
}

/** Only the fields needed to populate a unit dropdown for a chosen
 * ingredient — mirrors `ProductUnit` from the shared ERP types. */
export interface RecipeCatalogProductUnit {
  id: number;
  unit: number;
  unit_name: string;
  is_base: boolean;
  conversion_to_base: string;
}

export interface BranchLite {
  id: number;
  name: string;
}
