import React, { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Header } from '../../../components/layout/Header';
import { LoadingState, ErrorState, EmptyState } from '../../../components/ui/states';
import { RecipeHeader } from '../components/RecipeHeader';
import { VersionSelector } from '../components/VersionSelector';
import { IngredientTable } from '../components/IngredientTable';
import { useQuery } from '../../../hooks/useQuery';
import { useRecipeVersions } from '../hooks/useRecipeVersions';
import { recipesApi, recipeVersionsApi, catalogApi, asResults } from '../api';

/** `/recipes/:id/versions` — full version history for one product's base
 * recipe: every DRAFT/ACTIVE/ARCHIVED version, with the ability to inspect
 * any of them and activate a non-active one. */
export const RecipeVersionsPage: React.FC = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const productId = Number(id);
  const variantId = searchParams.get('variant_id') ? Number(searchParams.get('variant_id')) : null;

  const productQ = useQuery(() => catalogApi.getProduct(productId), [productId]);
  const recipesQ = useQuery(() => recipesApi.list(productId).then(asResults), [productId]);
  const recipe = (recipesQ.data ?? []).find((r) => (r.variant ?? null) === variantId) ?? null;

  const versionsQ = useRecipeVersions(productId, recipe?.id ?? null);
  const versions = versionsQ.data ?? [];

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activating, setActivating] = useState(false);
  const selected = versions.find((v) => v.id === selectedId) ?? versions[0] ?? null;

  const activate = async (versionId: number) => {
    if (!recipe) return;
    setActivating(true);
    try {
      await recipeVersionsApi.activate(productId, recipe.id, versionId);
      recipesQ.refetch();
      versionsQ.refetch();
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Version history" />
      <div className="p-5 max-w-[900px] w-full mx-auto space-y-4">
        <RecipeHeader productName={productQ.data?.name ?? '…'} />
        {versionsQ.loading ? (
          <LoadingState label="Loading versions…" />
        ) : versionsQ.error ? (
          <ErrorState message={versionsQ.error.message} onRetry={versionsQ.refetch} />
        ) : versions.length === 0 ? (
          <EmptyState title="No versions yet" hint="This recipe has no saved versions yet." icon="clock" />
        ) : (
          <>
            <VersionSelector
              versions={versions}
              selectedId={selected?.id ?? null}
              onSelect={setSelectedId}
              onActivate={activate}
              activating={activating}
            />
            {selected && <IngredientTable lines={selected.lines} />}
          </>
        )}
      </div>
    </div>
  );
};
