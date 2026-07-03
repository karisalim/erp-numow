import { useCallback, useEffect, useRef, useState } from 'react';
import { parseApiError, type ApiError } from '../utils/apiError';

/**
 * Minimal fetch-state hook (no react-query dependency): loading / error /
 * data / refetch, with stale-response protection when params change
 * faster than the network answers.
 *
 * `fetcher` must be stable or memoized by the caller (pass deps).
 */
export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => void;
}

export function useQuery<T>(fetcher: () => Promise<T>, deps: React.DependencyList): QueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const seq = useRef(0);

  const run = useCallback(() => {
    const mySeq = ++seq.current;
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => {
        if (seq.current !== mySeq) return; // stale response
        setData(d);
        setLoading(false);
      })
      .catch((err) => {
        if (seq.current !== mySeq) return;
        setError(parseApiError(err));
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
    return () => { seq.current++; }; // invalidate in-flight on unmount/dep change
  }, [run]);

  return { data, loading, error, refetch: run };
}

/** Debounce a fast-changing value (search inputs) before it hits useQuery deps. */
export function useDebounced<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
