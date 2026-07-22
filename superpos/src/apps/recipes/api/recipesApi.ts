/**
 * Typed API layer for ProductVariant / Recipe / RecipeVersion (Sprint 5
 * Batches 2-3). Every function maps 1:1 onto a verified backend route
 * (superpos_backend/recipes/urls.py) — nothing here invents an endpoint,
 * a field, or a computed value. `qty_base` and every cost-shaped field are
 * always read back from the server response, never computed here.
 */
import apiClient from '../../../api/client';
import type { Paginated } from '../../../types/erp';
import type {
  ProductVariant, ProductVariantPayload,
  Recipe, RecipePayload,
  RecipeVersion, RecipeVersionPayload,
} from '../types';

export type ListParams = Record<string, string | number | boolean | undefined>;

/** Unwrap endpoints that may return either a bare array or a DRF page —
 * same helper as the main app's `api/erp.ts#asResults`, duplicated here so
 * this feature has zero import dependency on the rest of the app's api
 * layer (only on the shared `apiClient`/`types/erp` primitives). */
export function asResults<T>(data: T[] | Paginated<T>): T[] {
  return Array.isArray(data) ? data : data.results;
}

/* ── Product Variants ─────────────────────────────────────────────────────
 * /products/{product_pk}/variants/... */

export const variantsApi = {
  list: (productId: number) =>
    apiClient.get<Paginated<ProductVariant> | ProductVariant[]>(`/products/${productId}/variants/`).then(r => r.data),
  create: (productId: number, payload: ProductVariantPayload) =>
    apiClient.post<ProductVariant>(`/products/${productId}/variants/`, payload).then(r => r.data),
  get: (productId: number, variantId: number) =>
    apiClient.get<ProductVariant>(`/products/${productId}/variants/${variantId}/`).then(r => r.data),
  update: (productId: number, variantId: number, payload: Partial<ProductVariantPayload>) =>
    apiClient.patch<ProductVariant>(`/products/${productId}/variants/${variantId}/`, payload).then(r => r.data),
  deactivate: (productId: number, variantId: number) =>
    apiClient.post<ProductVariant>(`/products/${productId}/variants/${variantId}/deactivate/`).then(r => r.data),
};

/* ── Recipes ───────────────────────────────────────────────────────────────
 * /products/{product_pk}/recipes/... */

export const recipesApi = {
  /** `variantId` filters to one variant's recipe; omit for the base
   * (variant=null) recipe's own list entry alongside every variant's. */
  list: (productId: number, params?: { variant_id?: number }) =>
    apiClient
      .get<Paginated<Recipe> | Recipe[]>(`/products/${productId}/recipes/`, { params })
      .then(r => r.data),
  create: (productId: number, payload: RecipePayload) =>
    apiClient.post<Recipe>(`/products/${productId}/recipes/`, payload).then(r => r.data),
  get: (productId: number, recipeId: number) =>
    apiClient.get<Recipe>(`/products/${productId}/recipes/${recipeId}/`).then(r => r.data),
  update: (productId: number, recipeId: number, payload: Partial<RecipePayload> & { is_active?: boolean }) =>
    apiClient.patch<Recipe>(`/products/${productId}/recipes/${recipeId}/`, payload).then(r => r.data),
};

/* ── Recipe Versions ───────────────────────────────────────────────────────
 * /products/{product_pk}/recipes/{recipe_pk}/versions/...
 *
 * There is no "edit an existing version's lines" endpoint — a version's
 * lines are immutable once created (RecipeVersionDetailView is GET-only).
 * The only way to change a recipe's composition is to POST a brand-new
 * DRAFT version, then call `activate` to promote it (archiving whatever
 * was previously active). This mirrors the backend exactly — the frontend
 * does not simulate an in-place edit that doesn't exist. */

export const recipeVersionsApi = {
  list: (productId: number, recipeId: number) =>
    apiClient
      .get<Paginated<RecipeVersion> | RecipeVersion[]>(
        `/products/${productId}/recipes/${recipeId}/versions/`,
      )
      .then(r => r.data),
  create: (productId: number, recipeId: number, payload: RecipeVersionPayload) =>
    apiClient
      .post<RecipeVersion>(`/products/${productId}/recipes/${recipeId}/versions/`, payload)
      .then(r => r.data),
  get: (productId: number, recipeId: number, versionId: number) =>
    apiClient
      .get<RecipeVersion>(`/products/${productId}/recipes/${recipeId}/versions/${versionId}/`)
      .then(r => r.data),
  activate: (productId: number, recipeId: number, versionId: number) =>
    apiClient
      .post<RecipeVersion>(`/products/${productId}/recipes/${recipeId}/versions/${versionId}/activate/`)
      .then(r => r.data),
};
