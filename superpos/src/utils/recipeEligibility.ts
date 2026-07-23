import type { Product } from '../types';

/**
 * Sprint 5 Batch 9 (POS integration): mirrors the backend's
 * `recipes.services.costing.is_recipe_eligible()` gate — a product may
 * carry a recipe (`behavior.can_have_recipe`) but Bundle is explicitly
 * excluded from the recipe-sale path (Batch 5 hotfix: a Bundle's own
 * component-explosion logic doesn't exist yet, and conflating it with
 * Recipe/Modifier consumption would silently mis-post stock). Read from
 * the same two server-supplied fields the backend derives its own gate
 * from — never a third, independently-guessed rule.
 */
export function isRecipeEligible(product: Product): boolean {
  return !!product.behavior?.can_have_recipe && product.product_type !== 'bundle';
}
