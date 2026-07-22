import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { Badge } from '../../../components/ui/Badge';
import { SelectField, FieldError } from '../../../components/ui/FormField';
import { EmptyState, LoadingState } from '../../../components/ui/states';
import { useQuery } from '../../../hooks/useQuery';
import { productModifierGroupsApi, modifierGroupsApi, asResults } from '../api';
import { recipesPaths } from '../services/navigation';
import { parseApiError, type ApiError } from '../../../utils/apiError';

/**
 * Which `ModifierGroup`s (Extras, Removals, …) this product offers —
 * attach/detach only; editing a group's own options/price-deltas/
 * consumption formulas happens on the dedicated Modifiers page
 * (`/recipes/modifiers`), not here.
 */
export const ModifierPanel: React.FC<{ productId: number }> = ({ productId }) => {
  const linksQ = useQuery(() => productModifierGroupsApi.list(productId).then(asResults), [productId]);
  const allGroupsQ = useQuery(() => modifierGroupsApi.list({ is_active: 'true' }).then(asResults), []);

  const [attaching, setAttaching] = useState(false);
  const [groupId, setGroupId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const links = linksQ.data ?? [];
  const attachedIds = new Set(links.map((l) => l.modifier_group));
  const available = (allGroupsQ.data ?? []).filter((g) => !attachedIds.has(g.id));

  const attach = async () => {
    if (!groupId) return;
    setBusy(true);
    setError(null);
    try {
      await productModifierGroupsApi.attach(productId, { modifier_group: Number(groupId) });
      setGroupId('');
      setAttaching(false);
      linksQ.refetch();
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const detach = async (linkId: number) => {
    setBusy(true);
    try {
      await productModifierGroupsApi.detach(productId, linkId);
      linksQ.refetch();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-sm">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Modifier groups</h3>
        <Button size="sm" variant="secondary" onClick={() => setAttaching((v) => !v)}>
          <Icon name="plus" size={13} /> Attach group
        </Button>
      </div>
      <div className="p-3.5 space-y-3">
        {attaching && (
          <div className="border border-neutral-200 rounded-md p-3 space-y-2 bg-neutral-50">
            <SelectField
              label="Modifier group"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              error={error?.fieldErrors.modifier_group}
            >
              <option value="">Select…</option>
              {available.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </SelectField>
            {available.length === 0 && (
              <div className="text-[11.5px] text-neutral-500">
                No unattached groups — <Link to={recipesPaths.modifiers()} className="underline">create one</Link> first.
              </div>
            )}
            {error && !error.fieldErrors.modifier_group && <FieldError error={error.message} />}
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setAttaching(false)} disabled={busy}>Cancel</Button>
              <Button size="sm" onClick={attach} disabled={busy || !groupId}>{busy ? 'Attaching…' : 'Attach'}</Button>
            </div>
          </div>
        )}
        {linksQ.loading ? (
          <LoadingState label="Loading modifier groups…" />
        ) : links.length === 0 ? (
          <EmptyState title="No modifier groups attached" hint="Attach a group like 'Extras' or 'Size options' to offer it on this product." icon="tag" />
        ) : (
          <div className="flex flex-wrap gap-2">
            {links.map((l) => (
              <span key={l.id} className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-md bg-neutral-100">
                <Badge kind="violet">{l.modifier_group_name}</Badge>
                <button
                  onClick={() => detach(l.id)}
                  disabled={busy}
                  aria-label={`Detach ${l.modifier_group_name}`}
                  className="w-5 h-5 grid place-items-center rounded hover:bg-neutral-200 text-neutral-500 focus-ring"
                >
                  <Icon name="x" size={11} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
