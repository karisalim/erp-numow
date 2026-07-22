import React, { useEffect, useMemo, useState } from 'react';
import { Button } from '../../../components/ui/Button';
import { LoadingState, ErrorState, AlertBanner } from '../../../components/ui/states';
import { useQuery } from '../../../hooks/useQuery';
import { recipesApi, recipeVersionsApi, catalogApi, asResults } from '../api';
import { useRecipeVersions } from '../hooks/useRecipeVersions';
import { useRecipesStore } from '../store/recipesStore';
import { parseApiError, type ApiError } from '../../../utils/apiError';
import { RecipeInfoCard } from './RecipeInfoCard';
import { IngredientTable } from './IngredientTable';
import { CostPreview } from './CostPreview';
import { ModifierPanel } from './ModifierPanel';
import { VariantList } from './VariantList';
import { VersionSelector } from './VersionSelector';
import type { RecipeVersion } from '../types';

/**
 * The Recipe Editor's actual UI — deliberately a standalone, reusable
 * component (not a page) so it can be embedded either as the Recipe app's
 * own routed editor (`/recipes/:id/edit`) OR, later, directly inside the
 * main Product Form when `product_type === 'recipe_product'`, without any
 * rewrite. It owns no route-level chrome (no page header) — the caller
 * decides how it's framed.
 *
 * All business logic (cost, validation, depth/cycle checks, unit
 * conversion) happens server-side. This component only assembles the
 * request bodies the backend already documents and renders whatever comes
 * back — see `CostPreview` for the one place this is most tempting to
 * fake, and why it deliberately doesn't.
 */
export const RecipeProductForm: React.FC<{
  productId: number;
  variantId?: number | null;
  /** When true, drops straight into draft-editing mode on first load
   * (used by the `/recipes/:id/edit` route so following that link starts
   * editing immediately instead of requiring a second click). */
  autoEdit?: boolean;
  onSaved?: (version: RecipeVersion) => void;
}> = ({ productId, variantId = null, autoEdit, onSaved }) => {
  const productQ = useQuery(() => catalogApi.getProduct(productId), [productId]);
  const recipesQ = useQuery(() => recipesApi.list(productId).then(asResults), [productId]);

  const recipe = useMemo(
    () => (recipesQ.data ?? []).find((r) => (r.variant ?? null) === variantId) ?? null,
    [recipesQ.data, variantId],
  );

  const versionsQ = useRecipeVersions(productId, recipe?.id ?? null);
  const versions = versionsQ.data ?? [];
  const activeVersion = versions.find((v) => v.id === recipe?.active_version_id) ?? null;

  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  useEffect(() => {
    if (activeVersion && selectedVersionId === null) setSelectedVersionId(activeVersion.id);
  }, [activeVersion, selectedVersionId]);
  const selectedVersion = versions.find((v) => v.id === selectedVersionId) ?? activeVersion;

  const draftProductId = useRecipesStore((s) => s.draftProductId);
  const draftLines = useRecipesStore((s) => s.draftLines);
  const startDraft = useRecipesStore((s) => s.startDraft);
  const addDraftLine = useRecipesStore((s) => s.addDraftLine);
  const updateDraftLine = useRecipesStore((s) => s.updateDraftLine);
  const removeDraftLine = useRecipesStore((s) => s.removeDraftLine);
  const clearDraft = useRecipesStore((s) => s.clearDraft);

  const [mode, setMode] = useState<'view' | 'draft'>('view');
  const [saving, setSaving] = useState(false);
  const [activating, setActivating] = useState(false);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [justCreatedVersion, setJustCreatedVersion] = useState<RecipeVersion | null>(null);

  const isDraftingThis = mode === 'draft' && draftProductId === productId;

  const beginDraft = (seedFrom?: RecipeVersion | null) => {
    startDraft(productId, variantId);
    if (seedFrom) {
      for (const line of seedFrom.lines) {
        addDraftLine({
          component_product: line.component_product,
          component_product_name: line.component_product_name,
          component_unit: line.component_unit,
          component_unit_name: line.component_unit_name,
          entered_qty: line.entered_qty,
        });
      }
    }
    setJustCreatedVersion(null);
    setSaveError(null);
    setMode('draft');
  };

  const [autoEditTriggered, setAutoEditTriggered] = useState(false);
  useEffect(() => {
    if (!autoEdit || autoEditTriggered) return;
    // Wait for the recipe list + (if any) version list to resolve before
    // deciding what to seed the draft from — avoids a flash of an empty
    // draft immediately overwritten once the real active version loads.
    if (recipesQ.loading || (recipe && versionsQ.loading)) return;
    setAutoEditTriggered(true);
    beginDraft(activeVersion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoEdit, autoEditTriggered, recipesQ.loading, recipe, versionsQ.loading, activeVersion]);

  const cancelDraft = () => {
    clearDraft();
    setMode('view');
    setSaveError(null);
  };

  const save = async () => {
    if (draftLines.length === 0) {
      setSaveError({ status: null, message: 'Add at least one ingredient before saving.', fieldErrors: {}, permissionDenied: false });
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      let recipeId = recipe?.id;
      if (!recipeId) {
        const created = await recipesApi.create(productId, { variant: variantId });
        recipeId = created.id;
        recipesQ.refetch();
      }
      const version = await recipeVersionsApi.create(productId, recipeId, {
        lines: draftLines.map((l) => ({
          component_product: l.component_product,
          component_unit: l.component_unit,
          entered_qty: l.entered_qty,
        })),
      });
      clearDraft();
      setMode('view');
      setJustCreatedVersion(version);
      setSelectedVersionId(version.id);
      versionsQ.refetch();
      onSaved?.(version);
    } catch (err) {
      setSaveError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const activate = async (versionId: number) => {
    if (!recipe) return;
    setActivating(true);
    try {
      await recipeVersionsApi.activate(productId, recipe.id, versionId);
      recipesQ.refetch();
      versionsQ.refetch();
      setJustCreatedVersion(null);
    } finally {
      setActivating(false);
    }
  };

  if (productQ.loading) return <LoadingState label="Loading recipe…" />;
  if (productQ.error) return <ErrorState message={productQ.error.message} onRetry={productQ.refetch} />;
  if (!productQ.data) return null;

  return (
    <div className="space-y-4">
      <RecipeInfoCard product={productQ.data} recipe={recipe} activeVersion={activeVersion} />

      {justCreatedVersion && (
        <AlertBanner tone="success" title={`Draft v${justCreatedVersion.version_no} saved`}>
          This version isn't live yet — activate it below to make it the one used at sale time.
          <div className="mt-2">
            <Button size="sm" disabled={activating} onClick={() => activate(justCreatedVersion.id)}>
              {activating ? 'Activating…' : 'Activate this version'}
            </Button>
          </div>
        </AlertBanner>
      )}

      {versions.length > 0 && (
        <VersionSelector
          versions={versions}
          selectedId={selectedVersion?.id ?? null}
          onSelect={(id) => { setSelectedVersionId(id); setJustCreatedVersion(null); }}
          onActivate={activate}
          activating={activating}
        />
      )}

      {isDraftingThis ? (
        <>
          <IngredientTable
            lines={draftLines}
            editable
            productId={productId}
            onAdd={addDraftLine}
            onQtyChange={(idx, value) => {
              const line = draftLines[idx];
              if (line) updateDraftLine(line.draftKey, { entered_qty: value });
            }}
            onRemove={(idx) => {
              const line = draftLines[idx];
              if (line) removeDraftLine(line.draftKey);
            }}
          />
          {saveError && <AlertBanner tone="danger">{saveError.message}</AlertBanner>}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={cancelDraft} disabled={saving}>Cancel</Button>
            <Button onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save as new draft version'}</Button>
          </div>
        </>
      ) : (
        <>
          <IngredientTable lines={selectedVersion?.lines ?? []} />
          <div className="flex gap-2">
            <Button onClick={() => beginDraft(selectedVersion)}>
              {recipe ? 'New version' : 'Create recipe'}
            </Button>
          </div>
        </>
      )}

      <CostPreview productId={productId} />

      {variantId === null && (
        <>
          <VariantList productId={productId} />
          <ModifierPanel productId={productId} />
        </>
      )}
    </div>
  );
};
