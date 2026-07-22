import { useQuery } from '../../../hooks/useQuery';
import { recipeVersionsApi, asResults } from '../api';

/** All versions of one recipe, newest first (matches the backend's own
 * `ordering = ['-version_no']`) — used by VersionSelector and the standalone
 * Recipe Version Manager page. */
export function useRecipeVersions(productId: number | null, recipeId: number | null) {
  return useQuery(
    () =>
      productId && recipeId
        ? recipeVersionsApi.list(productId, recipeId).then(asResults)
        : Promise.resolve([]),
    [productId, recipeId],
  );
}
