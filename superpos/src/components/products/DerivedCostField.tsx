import React, { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { useMoney } from '../../utils/money';

/**
 * "Derived / average cost" for a Recipe product (Batch 8 architectural-
 * improvement pass; breakdown added in the Phase 3 Enterprise UX pass —
 * item 7): a Recipe product has no `Product.cost` of its own
 * (`requires_cost=False` in the behavior matrix) — its cost is whatever
 * its recipe's ingredients currently roll up to. Rather than hiding the
 * Cost section entirely for this type (the old behavior) or showing one
 * opaque total, this reads the same `.../versions/{id}/cost-preview/`
 * response the Recipe Editor's `CostPreview` uses — total AND the
 * per-ingredient line list — and renders both, always read-only.
 */
interface RecipeRow { id: number; variant: number | null; active_version_id: number | null; }
interface CostPreviewLine { component_product: number; component_name: string; line_cost: string; }
interface CostPreviewResponse { total_cost: string; lines: CostPreviewLine[]; }

function unwrap<T>(data: T[] | { results?: T[] } | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : (data.results ?? []);
}

type State = 'loading' | 'no_recipe' | 'ready' | 'error';

export const DerivedCostField: React.FC<{ productId: number | string }> = ({ productId }) => {
  const money = useMoney();
  const [state, setState] = useState<State>('loading');
  const [preview, setPreview] = useState<CostPreviewResponse | null>(null);
  const [expanded, setExpanded] = useState(false);

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
        const resp = await apiClient.get<CostPreviewResponse>(
          `/products/${productId}/recipes/${base.id}/versions/${base.active_version_id}/cost-preview/`,
        );
        if (!cancelled) {
          setPreview(resp.data);
          setState('ready');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    })();
    return () => { cancelled = true; };
  }, [productId]);

  return (
    <div className="col-span-2">
      <div className="text-[12.5px] font-semibold text-neutral-700 mb-1.5">Derived cost</div>
      <div className="rounded-md border border-neutral-200 bg-neutral-50">
        <div className="h-10 px-3 flex items-center justify-between">
          <span className="text-[14px] text-neutral-700">
            {state === 'loading' && <span className="text-neutral-400">Computing…</span>}
            {state === 'no_recipe' && <span className="text-neutral-400">No active recipe yet</span>}
            {state === 'error' && <span className="text-neutral-400">Unavailable</span>}
            {state === 'ready' && preview && <span className="font-mono font-semibold">{money(Number(preview.total_cost))}</span>}
          </span>
          {state === 'ready' && preview && preview.lines.length > 0 && (
            <button
              type="button" onClick={() => setExpanded((v) => !v)}
              className="text-[11.5px] font-semibold text-brand-600 hover:underline"
            >
              {expanded ? 'Hide breakdown' : `Breakdown (${preview.lines.length})`}
            </button>
          )}
        </div>
        {expanded && state === 'ready' && preview && (
          <div className="border-t border-neutral-200 px-3 py-2 divide-y divide-neutral-100">
            {preview.lines.map((line) => (
              <div key={line.component_product} className="flex items-center justify-between py-1 text-[12px]">
                <span className="text-neutral-600">{line.component_name}</span>
                <span className="font-mono text-neutral-500">{money(Number(line.line_cost))}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <span className="text-[12px] font-normal text-neutral-500">
        Live roll-up from the active recipe's ingredient costs — never entered manually.
      </span>
    </div>
  );
};
