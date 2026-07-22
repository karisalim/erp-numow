import type { RecipeCatalogProduct } from '../types';

/**
 * Reads the server-computed `product_type` field to decide whether a
 * product belongs in the Recipe app — does not derive or guess eligibility
 * itself. Mirrors the backend's own `ProductType.RECIPE_PRODUCT` value
 * (`pos/services/product_types.py`) and the `is_recipe_eligible()` check
 * `SaleSerializer` uses — kept as a single named check here so no
 * component hardcodes the raw string `'recipe_product'` more than once.
 */
export function isRecipeProduct(product: Pick<RecipeCatalogProduct, 'product_type'>): boolean {
  return product.product_type === 'recipe_product';
}
