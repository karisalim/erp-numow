import React from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Header } from '../../../components/layout/Header';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { ErrorState } from '../../../components/ui/states';
import { RecipeHeader } from '../components/RecipeHeader';
import { RecipeProductForm } from '../components/RecipeProductForm';
import { catalogApi } from '../api';
import { useQuery } from '../../../hooks/useQuery';
import { recipesPaths } from '../services/navigation';

/** `/recipes/:id` — read-first detail view for one product's recipe(s). */
export const RecipeDetailPage: React.FC = () => {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const productId = Number(id);
  const variantId = searchParams.get('variant_id') ? Number(searchParams.get('variant_id')) : null;

  const productQ = useQuery(() => catalogApi.getProduct(productId), [productId]);

  if (!Number.isFinite(productId)) {
    return <ErrorState message="Invalid product id." />;
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Recipe detail" />
      <div className="p-5 max-w-[900px] w-full mx-auto">
        <RecipeHeader
          productName={productQ.data?.name ?? '…'}
          variantName={null}
          right={
            <Button size="sm" variant="secondary" onClick={() => navigate(recipesPaths.versions(productId))}>
              <Icon name="clock" size={14} /> Version history
            </Button>
          }
        />
        <RecipeProductForm productId={productId} variantId={variantId} />
      </div>
    </div>
  );
};
