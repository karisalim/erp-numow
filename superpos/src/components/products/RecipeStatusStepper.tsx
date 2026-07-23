import React, { useEffect, useState } from 'react';
import apiClient from '../../api/client';
import { Icon } from '../ui/Icon';

/**
 * The Recipe Workflow status, read directly from the real backend state —
 * never a client-side guess. Mirrors the exact 5 stages the recipe path
 * goes through end to end:
 *
 *   (No Recipe) -> Build Recipe -> Manage Versions -> Activate Version -> POS Ready
 *
 * `pos_ready` only lights up once ALL of these are simultaneously true:
 * a Recipe row exists, it has an ACTIVE `RecipeVersion`, AND the product
 * itself is both sellable (`can_sell`) and visible on the POS catalog
 * (`show_on_pos`) — the same conditions `check_recipe_readiness` /
 * `ProductSerializer` enforce server-side at sale time. A recipe can be
 * fully built and activated yet still not be "POS Ready" if `show_on_pos`
 * is off — this stepper makes that gap visible instead of implying
 * "recipe done = sellable".
 */
type Stage = 'no_recipe' | 'build_recipe' | 'manage_versions' | 'activate_version' | 'pos_ready';

const STAGES: { key: Stage; label: string }[] = [
  { key: 'no_recipe',        label: 'No recipe' },
  { key: 'build_recipe',     label: 'Build recipe' },
  { key: 'manage_versions',  label: 'Manage versions' },
  { key: 'activate_version', label: 'Activate version' },
  { key: 'pos_ready',        label: 'POS ready' },
];

interface RecipeRow { id: number; variant: number | null; active_version_id: number | null; }
interface VersionRow { id: number; status: string; }

function unwrap<T>(data: T[] | { results?: T[] } | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : (data.results ?? []);
}

async function resolveStage(productId: number | string, canSell: boolean, showOnPos: boolean): Promise<{ stage: Stage; blockedReason?: string }> {
  const recipesResp = await apiClient.get(`/products/${productId}/recipes/`);
  const recipes = unwrap<RecipeRow>(recipesResp.data);
  const baseRecipe = recipes.find((r) => r.variant == null) ?? null;

  if (!baseRecipe) return { stage: 'no_recipe' };

  if (baseRecipe.active_version_id == null) {
    const versionsResp = await apiClient.get(`/products/${productId}/recipes/${baseRecipe.id}/versions/`);
    const versions = unwrap<VersionRow>(versionsResp.data);
    return { stage: versions.length > 0 ? 'activate_version' : 'build_recipe' };
  }

  if (!canSell) return { stage: 'activate_version', blockedReason: 'Product type is not sellable — check the product type.' };
  if (!showOnPos) return { stage: 'activate_version', blockedReason: '"Show on POS" is off — turn it on to reach customers.' };
  return { stage: 'pos_ready' };
}

export const RecipeStatusStepper: React.FC<{
  productId: number | string;
  canSell: boolean;
  showOnPos: boolean;
}> = ({ productId, canSell, showOnPos }) => {
  const [stage, setStage] = useState<Stage | null>(null);
  const [blockedReason, setBlockedReason] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    resolveStage(productId, canSell, showOnPos)
      .then((r) => { if (!cancelled) { setStage(r.stage); setBlockedReason(r.blockedReason); } })
      .catch(() => { if (!cancelled) setStage(null); });
    return () => { cancelled = true; };
  }, [productId, canSell, showOnPos]);

  if (stage === null) {
    return <div className="text-[12px] text-neutral-400 py-1">Loading recipe status…</div>;
  }

  const currentIdx = STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="col-span-2 -mt-1 mb-1">
      <div className="flex items-center gap-1 flex-wrap">
        {STAGES.map((s, idx) => {
          const done = idx < currentIdx || (idx === currentIdx && stage === 'pos_ready');
          const current = idx === currentIdx && stage !== 'pos_ready';
          return (
            <React.Fragment key={s.key}>
              {idx > 0 && <span className="w-3 h-px bg-neutral-300 shrink-0" />}
              <span
                className={[
                  'inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap',
                  done ? 'bg-success-50 text-success-600' :
                    current ? 'bg-brand-50 text-brand-600' :
                      'bg-neutral-100 text-neutral-400',
                ].join(' ')}
              >
                {done && <Icon name="check" size={11} />}
                {s.label}
              </span>
            </React.Fragment>
          );
        })}
      </div>
      {blockedReason && (
        <p className="text-[11.5px] text-warn-600 mt-1">{blockedReason}</p>
      )}
    </div>
  );
};
