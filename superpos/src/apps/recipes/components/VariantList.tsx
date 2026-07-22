import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { Badge } from '../../../components/ui/Badge';
import { FormField, FieldError } from '../../../components/ui/FormField';
import { EmptyState, LoadingState } from '../../../components/ui/states';
import { useMoney } from '../../../utils/money';
import { useQuery } from '../../../hooks/useQuery';
import { variantsApi, asResults } from '../api';
import { recipesPaths } from '../services/navigation';
import { parseApiError, type ApiError } from '../../../utils/apiError';

/**
 * Size/option variants of a product (Large/Small, …) — each one owns its
 * OWN independent recipe, not a multiplier of the base. Listing + creating
 * variants here; each row links into the Recipe Editor scoped to that
 * variant (`?variant_id=`).
 */
export const VariantList: React.FC<{ productId: number }> = ({ productId }) => {
  const money = useMoney();
  const variantsQ = useQuery(() => variantsApi.list(productId).then(asResults), [productId]);
  const variants = variantsQ.data ?? [];

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submit = async () => {
    if (!name.trim() || !price) return;
    setBusy(true);
    setError(null);
    try {
      await variantsApi.create(productId, { name: name.trim(), price });
      setName('');
      setPrice('');
      setAdding(false);
      variantsQ.refetch();
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-sm">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Size variants</h3>
        <Button size="sm" variant="secondary" onClick={() => setAdding((v) => !v)}>
          <Icon name="plus" size={13} /> Add variant
        </Button>
      </div>
      <div className="p-3.5 space-y-3">
        {adding && (
          <div className="border border-neutral-200 rounded-md p-3 space-y-2 bg-neutral-50">
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Name" placeholder="Large" value={name} onChange={(e) => setName(e.target.value)} error={error?.fieldErrors.name} autoFocus />
              <FormField label="Price" type="number" step="0.01" min="0" value={price} onChange={(e) => setPrice(e.target.value)} error={error?.fieldErrors.price} />
            </div>
            {error && !error.fieldErrors.name && !error.fieldErrors.price && <FieldError error={error.message} />}
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setAdding(false)} disabled={busy}>Cancel</Button>
              <Button size="sm" onClick={submit} disabled={busy || !name.trim() || !price}>{busy ? 'Saving…' : 'Save'}</Button>
            </div>
          </div>
        )}
        {variantsQ.loading ? (
          <LoadingState label="Loading variants…" />
        ) : variants.length === 0 ? (
          <EmptyState
            title="No size variants"
            hint="This product sells at one size with one recipe. Add a variant (e.g. Large) to give it its own independent recipe and price."
            icon="layers"
          />
        ) : (
          <div className="divide-y divide-neutral-100">
            {variants.map((v) => (
              <Link
                key={v.id}
                to={recipesPaths.edit(productId, v.id)}
                className="flex items-center justify-between gap-3 px-1 py-2.5 hover:bg-neutral-50 rounded-md focus-ring"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[13.5px] font-semibold truncate">{v.name}</span>
                  {!v.is_active && <Badge kind="gray">Inactive</Badge>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[13px] font-mono tabular-nums text-neutral-600">{money(v.price)}</span>
                  <Icon name="chevR" size={14} className="text-neutral-400" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
