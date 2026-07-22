/**
 * Centralized route-string builders for this feature — so a path shape
 * never gets hand-typed differently in two components. Pure string
 * construction, not a router / not business logic.
 */
export const recipesPaths = {
  root: () => '/recipes',
  new: (productId?: number) => (productId ? `/recipes/new?product_id=${productId}` : '/recipes/new'),
  detail: (productId: number | string) => `/recipes/${productId}`,
  edit: (productId: number | string, variantId?: number | string) =>
    variantId ? `/recipes/${productId}/edit?variant_id=${variantId}` : `/recipes/${productId}/edit`,
  versions: (productId: number | string) => `/recipes/${productId}/versions`,
  modifiers: () => '/recipes/modifiers',
  reports: () => '/recipes/reports',
};
