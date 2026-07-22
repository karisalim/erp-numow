import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../../../components/ui/Icon';
import { Badge } from '../../../components/ui/Badge';
import { recipesPaths } from '../services/navigation';

/**
 * Shared title block for every Recipe app page — back-to-list link,
 * product name, a "Recipe / BOM" badge, and an optional variant chip.
 * Purely presentational.
 */
export const RecipeHeader: React.FC<{
  productName: string;
  variantName?: string | null;
  right?: React.ReactNode;
}> = ({ productName, variantName, right }) => {
  const navigate = useNavigate();
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
      <div className="min-w-0">
        <button
          onClick={() => navigate(recipesPaths.root())}
          className="flex items-center gap-1 text-[12px] font-semibold text-neutral-500 hover:text-neutral-700 mb-1.5 focus-ring rounded"
        >
          <Icon name="chevL" size={13} /> All recipes
        </button>
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-[18px] font-bold text-neutral-900 leading-tight truncate">{productName}</h1>
          <Badge kind="brand">Recipe / BOM</Badge>
          {variantName && <Badge kind="violet">{variantName}</Badge>}
        </div>
      </div>
      {right && <div className="flex items-center gap-2 flex-wrap">{right}</div>}
    </div>
  );
};
