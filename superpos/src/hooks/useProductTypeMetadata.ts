import { useEffect, useState } from 'react';
import { productTypesApi } from '../api/erp';
import type { ProductTypeMetadata } from '../types/erp';

/**
 * Session-wide cache for `GET /catalog/product-types/` — the single source
 * of truth for product-type behavior + required fields (Batch 8
 * architectural-improvement pass). This is static reference data: it only
 * changes when a developer adds a new `ProductType` to the backend, never
 * per-tenant or per-request, so every `ProductFormModal`/Recipe screen that
 * opens during a session shares one fetch instead of re-requesting it.
 */
let cache: ProductTypeMetadata[] | null = null;
let inflight: Promise<ProductTypeMetadata[]> | null = null;

function load(): Promise<ProductTypeMetadata[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = productTypesApi.list()
      .then((data) => { cache = data; inflight = null; return data; })
      .catch((err) => { inflight = null; throw err; });
  }
  return inflight;
}

export interface ProductTypeMetadataState {
  data: ProductTypeMetadata[] | null;
  loading: boolean;
  error: unknown;
}

/** Read the cached (or freshly-fetched-once) product-type metadata list. */
export function useProductTypeMetadata(): ProductTypeMetadataState {
  const [data, setData] = useState<ProductTypeMetadata[] | null>(cache);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (cache) { setData(cache); return; }
    let cancelled = false;
    load()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => { if (!cancelled) setError(err); });
    return () => { cancelled = true; };
  }, []);

  return { data, loading: data === null && error === null, error };
}

/** Find one type's metadata row, or `undefined` before the list has loaded
 * / for a value the backend doesn't recognize. */
export function findTypeMetadata(
  list: ProductTypeMetadata[] | null,
  value: string,
): ProductTypeMetadata | undefined {
  return list?.find((row) => row.value === value);
}
