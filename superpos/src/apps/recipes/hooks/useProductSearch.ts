import { useState } from 'react';
import { useQuery, useDebounced } from '../../../hooks/useQuery';
import { catalogApi } from '../api';
import type { RecipeCatalogProduct } from '../types';

/**
 * Debounced product-name/barcode/sku search for the Ingredient Picker —
 * thin composition of the shared `useDebounced`/`useQuery` hooks over
 * `catalogApi.searchProducts`. No filtering/business logic here beyond
 * "don't fire a request on every keystroke."
 */
export function useProductSearch() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounced(query, 300);

  const searchQ = useQuery(
    () =>
      debouncedQuery.trim()
        ? catalogApi.searchProducts({ search: debouncedQuery.trim(), page_size: 20 })
        : Promise.resolve<RecipeCatalogProduct[]>([]),
    [debouncedQuery],
  );

  return { query, setQuery, results: searchQ.data ?? [], loading: searchQ.loading, error: searchQ.error };
}
