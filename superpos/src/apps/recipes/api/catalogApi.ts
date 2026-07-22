/**
 * Thin wrappers around pre-existing, non-Sprint-5 endpoints that the recipe
 * app needs to integrate with (the product catalog for the Ingredient
 * Picker, a product's own unit conversions for the unit dropdown, and the
 * branch list for report filters). These are read-only reuses of already-
 * shipped Sprint 1/2 endpoints — no new backend surface, no business logic.
 *
 * Known gap: `GET /products/` has no `product_type` filter param
 * (`pos/filters.py#ProductFilter` — fields are `category, active, weighted,
 * plu, show_on_pos` only). The Recipe List page therefore fetches a larger
 * page and filters `product_type === 'recipe_product'` client-side for
 * *display* purposes only (narrowing an already-server-returned field, not
 * recomputing anything) — documented in the Batch 8 Architecture Review as
 * a backend gap, not silently worked around.
 */
import apiClient from '../../../api/client';
import type { Paginated } from '../../../types/erp';
import type { RecipeCatalogProduct, RecipeCatalogProductUnit, BranchLite } from '../types';

export const catalogApi = {
  /** Search the product catalog (name/barcode/sku) — used by the
   * IngredientPicker and the "pick a product to build a recipe for" step. */
  searchProducts: (params: { search?: string; page_size?: number; active?: boolean }) =>
    apiClient
      .get<Paginated<RecipeCatalogProduct> | RecipeCatalogProduct[]>('/products/', {
        params: { ...params, active: params.active ?? true },
      })
      .then(r => (Array.isArray(r.data) ? r.data : r.data.results)),

  /** A larger, unfiltered-by-type page for the Recipe List/Dashboard —
   * see the module docstring's gap note. */
  listRecipeEligibleProducts: (pageSize = 100) =>
    apiClient
      .get<Paginated<RecipeCatalogProduct> | RecipeCatalogProduct[]>('/products/', {
        params: { page_size: pageSize, active: true },
      })
      .then(r => (Array.isArray(r.data) ? r.data : r.data.results)),

  getProduct: (productId: number) =>
    apiClient.get<RecipeCatalogProduct>(`/products/${productId}/`).then(r => r.data),

  /** A chosen ingredient's own unit conversions, for the per-line unit
   * dropdown (mirrors `productUnitsApi.list` in the main app's api/erp.ts,
   * duplicated here so this feature has no cross-app import). */
  listProductUnits: (productId: number) =>
    apiClient
      .get<Paginated<RecipeCatalogProductUnit> | RecipeCatalogProductUnit[]>(`/products/${productId}/units/`)
      .then(r => (Array.isArray(r.data) ? r.data : r.data.results)),

  /** Branch list for report filters (mirrors `branchesApi.list` in the main
   * app — same legacy `/accounts/branches/` endpoint every other branch
   * filter in this codebase already uses, e.g. the Dashboard's branch
   * selector). */
  listBranches: () =>
    apiClient.get<BranchLite[] | Paginated<BranchLite>>('/accounts/branches/').then(
      r => (Array.isArray(r.data) ? r.data : r.data.results),
    ),
};
