import React, { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { useMoney } from '../../utils/money';

/**
 * "Derived / average cost" for a Recipe product (Batch 8 architectural-
 * improvement pass): a Recipe product has no `Product.cost` of its own
 * (`requires_cost=False` in the behavior matrix) — its cost is whatever
 * its recipe's ingredients currently roll up to. Rather than hiding the
 * Cost section entirely for this type (the old behavior), this shows the
 * real, live, server-computed total from the same
 * `.../versions/{id}/cost-preview/` endpoint the Recipe Editor's
 * `CostPreview` uses — always read-only, never editable here.
 */
interface RecipeRow { id: number; variant: number | null; active_version_id: number | null; }

function unwrap<T>(data: T[] | { results?: T[] } | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : (data.results ?? []);
}

type State = 'loading' | 'no_recipe' | 'ready' | 'error';

export const DerivedCostField: React.FC<{ productId: number | string }> = ({ productId }) => {
  const money = useMoney();
  const [state, setState] = useState<State>('loading');
  const [total, setTotal] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    (async () => {
      try {
        const recipesResp = await apiClient.get(`/products/${productId}/recipes/`);
        const recipes = unwrap<RecipeRow>(recipesResp.data);
        const base = recipes.find((r) => r.variant == null) ?? null;
        if (!base || base.active_version_id == null) {
          if (!cancelled) setState('no_recipe');
          return;
        }
        const preview = await apiClient.get(
          `/products/${productId}/recipes/${base.id}/versions/${base.active_version_id}/cost-preview/`,
        );
        if (!cancelled) {
          setTotal(Number(preview.data.total_cost));
          setState('ready');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    })();
    return () => { cancelled = true; };
  }, [productId]);

  return (
    <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700">
      <span>Derived cost</span>
      <div className="h-10 px-3 rounded-md border border-neutral-200 bg-neutral-50 text-[14px] flex items-center text-neutral-700">
        {state === 'loading' && <span className="text-neutral-400">Computing…</span>}
        {state === 'no_recipe' && <span className="text-neutral-400">No active recipe yet</span>}
        {state === 'error' && <span className="text-neutral-400">Unavailable</span>}
        {state === 'ready' && total !== null && <span className="font-mono">{money(total)}</span>}
      </div>
      <span className="text-[12px] font-normal text-neutral-500">
        Live roll-up from the active recipe's ingredient costs — never entered manually.
      </span>
    </label>
  );
};
