import React, { useEffect, useState } from 'react';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { SearchField, SelectField, FormField, FieldError } from '../../../components/ui/FormField';
import { LoadingState, EmptyState } from '../../../components/ui/states';
import { useProductSearch } from '../hooks/useProductSearch';
import { catalogApi } from '../api';
import type { RecipeCatalogProduct, RecipeCatalogProductUnit } from '../types';

export interface PickedIngredient {
  component_product: number;
  component_product_name: string;
  component_unit: number | null;
  component_unit_name: string;
  entered_qty: string;
}

/**
 * Two-step picker: search the catalog for a component product, then choose
 * its unit + quantity. Emits a plain `PickedIngredient` — never computes a
 * cost, never validates the quantity beyond "must be a positive number"
 * (the real validation — depth, cycles, tenant scoping, unit compatibility
 * — happens server-side when the line is actually saved).
 */
export const IngredientPicker: React.FC<{
  onAdd: (line: PickedIngredient) => void;
  onClose: () => void;
  excludeProductId?: number;
}> = ({ onAdd, onClose, excludeProductId }) => {
  const { query, setQuery, results, loading } = useProductSearch();
  const [selected, setSelected] = useState<RecipeCatalogProduct | null>(null);
  const [units, setUnits] = useState<RecipeCatalogProductUnit[]>([]);
  const [unitsLoading, setUnitsLoading] = useState(false);
  const [unitId, setUnitId] = useState('');
  const [qty, setQty] = useState('1');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    setUnitsLoading(true);
    catalogApi
      .listProductUnits(selected.id)
      .then((u) => {
        setUnits(u);
        const base = u.find((x) => x.is_base);
        setUnitId(base ? String(base.id) : (u[0] ? String(u[0].id) : ''));
      })
      .finally(() => setUnitsLoading(false));
  }, [selected]);

  const submit = () => {
    if (!selected) return;
    const qtyNum = Number(qty);
    if (!qty || !Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError('Enter a quantity greater than 0.');
      return;
    }
    const unit = units.find((u) => String(u.id) === unitId);
    onAdd({
      component_product: selected.id,
      component_product_name: selected.name,
      component_unit: unit ? unit.id : null,
      component_unit_name: unit ? unit.unit_name : '',
      entered_qty: qty,
    });
  };

  return (
    <Modal title="Add ingredient" onClose={onClose} maxWidth="max-w-[560px]">
      <div className="p-5 space-y-4">
        {!selected ? (
          <>
            <SearchField value={query} onChange={setQuery} placeholder="Search products by name, SKU, or barcode…" autoFocus />
            <div className="max-h-[320px] overflow-y-auto -mx-1 px-1">
              {loading ? (
                <LoadingState label="Searching…" />
              ) : query.trim() && results.length === 0 ? (
                <EmptyState title="No matching products" icon="search" />
              ) : (
                <div className="divide-y divide-neutral-100">
                  {results
                    .filter((p) => p.id !== excludeProductId)
                    .map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setSelected(p)}
                        className="w-full flex items-center justify-between gap-3 py-2.5 px-2 text-start hover:bg-neutral-50 rounded-md focus-ring"
                      >
                        <div className="min-w-0">
                          <div className="text-[13.5px] font-semibold truncate">{p.name}</div>
                          <div className="text-[11.5px] text-neutral-500 truncate">
                            {p.sku || p.barcode || '—'}{p.category_name ? ` · ${p.category_name}` : ''}
                          </div>
                        </div>
                        <Icon name="chevR" size={14} className="text-neutral-400 shrink-0" />
                      </button>
                    ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between bg-neutral-50 border border-neutral-200 rounded-md px-3 py-2.5">
              <div className="min-w-0">
                <div className="text-[13.5px] font-semibold truncate">{selected.name}</div>
                <div className="text-[11.5px] text-neutral-500 truncate">{selected.sku || selected.barcode || '—'}</div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => { setSelected(null); setError(null); }}>
                Change
              </Button>
            </div>
            {unitsLoading ? (
              <LoadingState label="Loading units…" />
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <FormField
                  label="Quantity" type="number" step="0.001" min="0.001" required autoFocus
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                />
                <SelectField
                  label="Unit"
                  value={unitId}
                  onChange={(e) => setUnitId(e.target.value)}
                >
                  {units.length === 0 && <option value="">No units configured</option>}
                  {units.map((u) => (
                    <option key={u.id} value={u.id}>{u.unit_name}{u.is_base ? ' (base)' : ''}</option>
                  ))}
                </SelectField>
              </div>
            )}
            {error && <FieldError error={error} />}
            <div className="flex gap-2 pt-1">
              <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
              <Button className="flex-1" onClick={submit} disabled={unitsLoading}>Add ingredient</Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};
