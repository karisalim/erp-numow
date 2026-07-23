import React from 'react';
import { Link } from 'react-router-dom';
import { AlertBanner, LoadingState, ErrorState } from '../../../components/ui/states';
import { useQuery } from '../../../hooks/useQuery';
import { useMoney } from '../../../utils/money';
import { recipeVersionsApi } from '../api';
import { recipesPaths } from '../services/navigation';
import type { RecipeCostPreview } from '../types';

/**
 * Server-computed, branch-scoped live cost for a saved (draft or active)
 * recipe version — powered by `GET .../versions/{id}/cost-preview/`
 * (Batch 8 architectural-improvement pass), which reuses the exact same
 * `compute_recipe_cost` roll-up the backend already runs at sale time.
 * Nothing is computed here: every number rendered is read straight off
 * the response. Recomputing this in React (qty_base × some client-known
 * unit cost) would mean re-implementing the branch-scoped AVCO lookup
 * client-side — this is precisely the endpoint that was missing to avoid
 * that, replacing the earlier documented placeholder.
 */
export const CostPreview: React.FC<{
  productId?: number;
  recipeId?: number | null;
  versionId?: number | null;
  branchId?: number;
}> = ({ productId, recipeId, versionId, branchId }) => {
  const money = useMoney();
  const canPreview = !!(productId && recipeId && versionId);

  // The fetcher itself must guard on `canPreview` (not just the render
  // branch below) — `useQuery`'s effect fires on every dependency change
  // regardless of what the component chooses to render, so an unguarded
  // fetcher would call the API with literal `undefined` ids the moment
  // this mounts before a version is ever saved.
  const previewQ = useQuery<RecipeCostPreview | null>(
    () => (canPreview
      ? recipeVersionsApi.costPreview(productId!, recipeId!, versionId!, branchId)
      : Promise.resolve(null)),
    [productId, recipeId, versionId, branchId],
  );

  if (!canPreview) {
    return (
      <AlertBanner tone="info" title="Cost preview isn't available yet">
        Save this recipe as a version first — once it exists, its live
        ingredient cost is computed here automatically.
      </AlertBanner>
    );
  }

  if (previewQ.loading) return <LoadingState label="Computing recipe cost…" />;
  if (previewQ.error) return <ErrorState message={previewQ.error.message} onRetry={previewQ.refetch} />;
  if (!previewQ.data) return null;

  const preview = previewQ.data;

  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">
          Derived cost
        </h3>
        <div className="text-[18px] font-bold">{money(Number(preview.total_cost))}</div>
      </div>
      <div className="divide-y divide-neutral-100">
        {preview.lines.map((line) => (
          <div key={line.component_product} className="flex items-center justify-between py-1.5 text-[12.5px]">
            <span className="text-neutral-700">{line.component_name}</span>
            <span className="font-mono text-neutral-500">{money(Number(line.line_cost))}</span>
          </div>
        ))}
      </div>
      <p className="text-[11.5px] text-neutral-400 mt-2">
        Computed live from each ingredient's current cost — recalculates
        automatically the next time an ingredient's price changes. Once
        this recipe has sales, see{' '}
        {productId && (
          <Link to={recipesPaths.reports()} className="underline font-semibold">
            Recipe Reports → Profitability
          </Link>
        )}{' '}
        for real, sale-time-frozen food cost and margin.
      </p>
    </div>
  );
};
