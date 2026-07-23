import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';
import { Icon } from '../ui/Icon';
import { RecipeStatusBadge, type RecipeWorkflowStage } from '../ui/StatusBadges';

/**
 * Phase 3 (Enterprise UX Polish) — the Recipe Workflow as a real workflow
 * card (not a passive status pill), matching the exact 3-branch spec:
 *
 *   No Recipe        -> "Build Recipe"
 *   Draft             -> "Continue Editing" + "Manage Versions"
 *   Active            -> "Open Recipe" + "Version History" + POS-ready badge
 *
 * State is read directly from the real backend (Recipe + RecipeVersion
 * rows) — never guessed or cached across renders. Route strings are
 * duplicated (not imported from `apps/recipes`) on purpose: this is a
 * `components/products/` file in the main app, and every other cross-app
 * touchpoint in this codebase (`apps/recipes/api/catalogApi.ts`) already
 * establishes "duplicate a few small strings, never reach into the other
 * app's internals" as the boundary rule.
 */
interface RecipeRow { id: number; variant: number | null; active_version_id: number | null; }
interface VersionRow { id: number; status: string; }

function unwrap<T>(data: T[] | { results?: T[] } | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : (data.results ?? []);
}

interface ResolvedState {
  recipeId: number | null;
  activeVersionId: number | null;
  hasDraftVersions: boolean;
}

async function resolve(productId: number | string): Promise<ResolvedState> {
  const recipesResp = await apiClient.get(`/products/${productId}/recipes/`);
  const recipes = unwrap<RecipeRow>(recipesResp.data);
  const baseRecipe = recipes.find((r) => r.variant == null) ?? null;

  if (!baseRecipe) return { recipeId: null, activeVersionId: null, hasDraftVersions: false };

  if (baseRecipe.active_version_id != null) {
    return { recipeId: baseRecipe.id, activeVersionId: baseRecipe.active_version_id, hasDraftVersions: true };
  }

  const versionsResp = await apiClient.get(`/products/${productId}/recipes/${baseRecipe.id}/versions/`);
  const versions = unwrap<VersionRow>(versionsResp.data);
  return { recipeId: baseRecipe.id, activeVersionId: null, hasDraftVersions: versions.length > 0 };
}

export const RecipeWorkflowCard: React.FC<{
  productId: number | string;
  canSell: boolean;
  showOnPos: boolean;
}> = ({ productId, canSell, showOnPos }) => {
  const navigate = useNavigate();
  const [state, setState] = useState<ResolvedState | null>(null);

  useEffect(() => {
    let cancelled = false;
    resolve(productId).then((r) => { if (!cancelled) setState(r); }).catch(() => { if (!cancelled) setState(null); });
    return () => { cancelled = true; };
  }, [productId]);

  if (state === null) {
    return (
      <div className="col-span-2 -mt-1 mb-1 flex items-center gap-2 text-[12px] text-neutral-400 py-2">
        <span className="w-3 h-3 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
        Loading recipe status…
      </div>
    );
  }

  let stage: RecipeWorkflowStage;
  let blockedReason: string | undefined;
  if (!state.recipeId) {
    stage = 'no_recipe';
  } else if (state.activeVersionId == null) {
    stage = 'draft';
  } else if (!canSell) {
    stage = 'active_not_live';
    blockedReason = 'Product type is not sellable — check the product type.';
  } else if (!showOnPos) {
    stage = 'active_not_live';
    blockedReason = '"Show on POS" is off — turn it on to reach customers.';
  } else {
    stage = 'pos_ready';
  }

  const editPath = `/recipes/${productId}/edit`;
  const versionsPath = `/recipes/${productId}/versions`;
  const detailPath = `/recipes/${productId}`;

  return (
    <div className="col-span-2 -mt-1 mb-1 bg-neutral-50 border border-neutral-200 rounded-lg p-3.5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-violet-50 text-violet-600 grid place-items-center shrink-0">
            <Icon name="layers" size={16} />
          </div>
          <div>
            <div className="text-[13px] font-semibold text-neutral-800">Recipe workflow</div>
            <RecipeStatusBadge stage={stage} />
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {stage === 'no_recipe' && (
            <WorkflowButton icon="layers" onClick={() => navigate(editPath)}>
              Build Recipe
            </WorkflowButton>
          )}

          {stage === 'draft' && (
            <>
              <WorkflowButton icon="edit" onClick={() => navigate(editPath)}>
                Continue Editing
              </WorkflowButton>
              <WorkflowButton icon="clock" variant="secondary" onClick={() => navigate(versionsPath)}>
                Manage Versions
              </WorkflowButton>
            </>
          )}

          {(stage === 'active_not_live' || stage === 'pos_ready') && (
            <>
              <WorkflowButton icon="doc" variant="secondary" onClick={() => navigate(detailPath)}>
                Open Recipe
              </WorkflowButton>
              <WorkflowButton icon="clock" variant="secondary" onClick={() => navigate(versionsPath)}>
                Version History
              </WorkflowButton>
            </>
          )}
        </div>
      </div>
      {blockedReason && (
        <p className="text-[11.5px] text-warn-600 mt-2">{blockedReason}</p>
      )}
    </div>
  );
};

const WorkflowButton: React.FC<React.PropsWithChildren<{
  icon: string; onClick: () => void; variant?: 'primary' | 'secondary';
}>> = ({ icon, onClick, variant = 'primary', children }) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      'h-8 px-3 rounded-md text-[12.5px] font-semibold inline-flex items-center gap-1.5 focus-ring transition-colors',
      variant === 'primary'
        ? 'bg-brand-500 text-white hover:bg-brand-600'
        : 'bg-white border border-neutral-300 text-neutral-700 hover:bg-neutral-100',
    ].join(' ')}
  >
    <Icon name={icon} size={13} />
    {children}
  </button>
);
