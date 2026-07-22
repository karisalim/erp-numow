import React from 'react';
import { Link } from 'react-router-dom';
import { AlertBanner } from '../../../components/ui/states';
import { recipesPaths } from '../services/navigation';

/**
 * KNOWN BACKEND GAP (documented, not worked around): there is no endpoint
 * that computes a recipe's total cost before it's actually sold.
 * `RecipeVersionSerializer`'s response has no cost field, and
 * `recipes.services.costing.compute_recipe_cost()` is only ever called
 * internally by `SaleSerializer` at the moment of sale — it is not exposed
 * over the API. Recomputing it here (qty_base × some client-known unit
 * cost) would mean re-implementing the branch-scoped AVCO lookup in
 * React, which is exactly what this batch's brief prohibits ("لا تنشئ
 * Business Logic داخل React" / "أي Cost... يأتي من الـ Backend فقط").
 *
 * So this component does not show a number. It explains why, and links to
 * the one place a real, server-computed food cost DOES exist once the
 * recipe has actual sales: the Recipe Profitability report.
 */
export const CostPreview: React.FC<{ productId?: number }> = ({ productId }) => (
  <AlertBanner tone="info" title="Cost preview isn't available yet">
    This recipe's cost isn't calculated until it's actually sold — the
    backend prices each sale using the live, branch-scoped average
    ingredient cost at that moment (not a value stored on the recipe
    itself), so a "preview" number here would just be a guess.
    {productId && (
      <>
        {' '}Once this recipe has sales,{' '}
        <Link to={recipesPaths.reports()} className="underline font-semibold">
          Recipe Reports → Profitability
        </Link>{' '}
        will show its real food cost and margin.
      </>
    )}
  </AlertBanner>
);
