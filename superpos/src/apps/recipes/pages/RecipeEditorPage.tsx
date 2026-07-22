import React, { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Header } from '../../../components/layout/Header';
import { SearchField } from '../../../components/ui/FormField';
import { LoadingState, EmptyState } from '../../../components/ui/states';
import { Icon } from '../../../components/ui/Icon';
import { RecipeHeader } from '../components/RecipeHeader';
import { RecipeProductForm } from '../components/RecipeProductForm';
import { useProductSearch } from '../hooks/useProductSearch';
import { catalogApi } from '../api';
import { useQuery } from '../../../hooks/useQuery';
import { isRecipeProduct } from '../services/productEligibility';
import { recipesPaths } from '../services/navigation';

/** `/recipes/new` — pick a Recipe-typed product to build a recipe for, when
 * not already deep-linked with `?product_id=`. */
const ProductPickerForNewRecipe: React.FC = () => {
  const navigate = useNavigate();
  const { query, setQuery, results, loading } = useProductSearch();
  const recipeResults = results.filter(isRecipeProduct);

  return (
    <div className="p-5 max-w-[560px] w-full mx-auto">
      <RecipeHeader productName="New recipe" />
      <div className="bg-white border border-neutral-200 rounded-lg shadow-sm p-4">
        <p className="text-[13px] text-neutral-500 mb-3">
          Search for a product with Type = Recipe to build its recipe. Products
          are typed on the main Products page.
        </p>
        <SearchField value={query} onChange={setQuery} placeholder="Search recipe products…" autoFocus />
        <div className="mt-3 max-h-[360px] overflow-y-auto">
          {loading ? (
            <LoadingState label="Searching…" />
          ) : query.trim() && recipeResults.length === 0 ? (
            <EmptyState title="No matching recipe products" icon="search" />
          ) : (
            <div className="divide-y divide-neutral-100">
              {recipeResults.map((p) => (
                <button
                  key={p.id}
                  onClick={() => navigate(recipesPaths.edit(p.id))}
                  className="w-full flex items-center justify-between gap-3 py-2.5 px-1 text-start hover:bg-neutral-50 rounded-md focus-ring"
                >
                  <div className="text-[13.5px] font-semibold">{p.name}</div>
                  <Icon name="chevR" size={14} className="text-neutral-400" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/** `/recipes/:id/edit` and `/recipes/new?product_id=` — the routed Recipe
 * Editor. Thin page chrome around `RecipeProductForm`, which owns all the
 * actual editing behavior (and is the piece meant to be reused later
 * inside the main Product Form). */
export const RecipeEditorPage: React.FC = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [savedNotice, setSavedNotice] = useState(false);

  const productIdParam = id ?? searchParams.get('product_id');
  const productId = productIdParam ? Number(productIdParam) : null;
  const variantId = searchParams.get('variant_id') ? Number(searchParams.get('variant_id')) : null;

  if (!productId || !Number.isFinite(productId)) {
    return (
      <div className="flex-1 flex flex-col min-h-0 overflow-auto">
        <Header title="New recipe" />
        <ProductPickerForNewRecipe />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Edit recipe" />
      <div className="p-5 max-w-[900px] w-full mx-auto">
        <ProductEditorHeaderAndForm productId={productId} variantId={variantId} savedNotice={savedNotice} onSaved={() => setSavedNotice(true)} />
      </div>
    </div>
  );
};

const ProductEditorHeaderAndForm: React.FC<{
  productId: number;
  variantId: number | null;
  savedNotice: boolean;
  onSaved: () => void;
}> = ({ productId, variantId, onSaved }) => {
  const productQ = useQuery(() => catalogApi.getProduct(productId), [productId]);
  return (
    <>
      <RecipeHeader productName={productQ.data?.name ?? '…'} />
      <RecipeProductForm productId={productId} variantId={variantId} autoEdit onSaved={onSaved} />
    </>
  );
};
