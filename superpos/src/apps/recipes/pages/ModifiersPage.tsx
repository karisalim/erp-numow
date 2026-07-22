import React, { useState } from 'react';
import { Header } from '../../../components/layout/Header';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { Modal } from '../../../components/ui/Modal';
import { Drawer } from '../../../components/ui/Drawer';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import { DataTable, type Column } from '../../../components/ui/DataTable';
import { ActiveBadge } from '../../../components/ui/StatusBadge';
import { FormField, SelectField, FieldError } from '../../../components/ui/FormField';
import { useQuery } from '../../../hooks/useQuery';
import { useMoney } from '../../../utils/money';
import { formatQty } from '../utils/format';
import {
  modifierGroupsApi, modifierOptionsApi, modifierConsumptionsApi, asResults,
} from '../api';
import { useProductSearch } from '../hooks/useProductSearch';
import { catalogApi } from '../api';
import { parseApiError, type ApiError } from '../../../utils/apiError';
import type { ModifierGroup, ModifierOption, ModifierOptionConsumption, RecipeCatalogProductUnit } from '../types';

/* ── Group form (create) ──────────────────────────────────────────────── */

const GroupFormModal: React.FC<{ busy: boolean; error: ApiError | null; onSubmit: (name: string) => void; onClose: () => void }> = ({
  busy, error, onSubmit, onClose,
}) => {
  const [name, setName] = useState('');
  return (
    <Modal title="New modifier group" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) onSubmit(name.trim()); }} className="p-5 space-y-4">
        <FormField
          label="Name" required autoFocus value={name} onChange={(e) => setName(e.target.value)}
          error={error?.fieldErrors.name} hint="e.g. Extras, Removals, Size options."
        />
        {error && !error.fieldErrors.name && <FieldError error={error.message} />}
        <div className="flex gap-2 pt-1">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" className="flex-1" disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Save'}</Button>
        </div>
      </form>
    </Modal>
  );
};

/* ── Consumption picker (mini product search, reused from IngredientPicker's shape) ── */

const ConsumptionFormPanel: React.FC<{
  onSubmit: (payload: { component_product: number; component_unit: number | null; entered_qty: string }) => void;
  busy: boolean;
  error: ApiError | null;
}> = ({ onSubmit, busy, error }) => {
  const { query, setQuery, results, loading } = useProductSearch();
  const [productId, setProductId] = useState<number | null>(null);
  const [productName, setProductName] = useState('');
  const [units, setUnits] = useState<RecipeCatalogProductUnit[]>([]);
  const [unitId, setUnitId] = useState('');
  const [qty, setQty] = useState('1');

  const pick = async (id: number, name: string) => {
    setProductId(id);
    setProductName(name);
    const u = await catalogApi.listProductUnits(id);
    setUnits(u);
    const base = u.find((x) => x.is_base);
    setUnitId(base ? String(base.id) : (u[0] ? String(u[0].id) : ''));
  };

  return (
    <div className="border border-neutral-200 rounded-md p-3 space-y-3 bg-neutral-50">
      {!productId ? (
        <>
          <FormField label="Search ingredient" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name, SKU, or barcode…" autoFocus />
          {loading && <div className="text-[12px] text-neutral-400">Searching…</div>}
          <div className="max-h-[180px] overflow-y-auto divide-y divide-neutral-100">
            {results.map((p) => (
              <button key={p.id} onClick={() => pick(p.id, p.name)} className="w-full text-start py-1.5 px-1 text-[13px] hover:bg-white rounded focus-ring">
                {p.name}
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold">{productName}</span>
            <Button size="sm" variant="ghost" onClick={() => setProductId(null)}>Change</Button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField
              label="Qty (± — negative removes)" type="number" step="0.001" value={qty}
              onChange={(e) => setQty(e.target.value)}
              error={error?.fieldErrors.entered_qty}
              hint="Positive = adds this much; negative = removes (e.g. No Onion)."
            />
            <SelectField label="Unit" value={unitId} onChange={(e) => setUnitId(e.target.value)}>
              {units.map((u) => <option key={u.id} value={u.id}>{u.unit_name}{u.is_base ? ' (base)' : ''}</option>)}
            </SelectField>
          </div>
          {error && !error.fieldErrors.entered_qty && <FieldError error={error.message} />}
          <Button
            size="sm" disabled={busy || !qty}
            onClick={() => onSubmit({
              component_product: productId,
              component_unit: unitId ? Number(unitId) : null,
              entered_qty: qty,
            })}
          >
            {busy ? 'Saving…' : 'Add consumption'}
          </Button>
        </>
      )}
    </div>
  );
};

/* ── Group detail drawer: options + (per selected option) consumptions ─── */

const ModifierGroupDrawer: React.FC<{ group: ModifierGroup; onClose: () => void }> = ({ group, onClose }) => {
  const money = useMoney();
  const optionsQ = useQuery(() => modifierOptionsApi.list(group.id).then(asResults), [group.id]);
  const options = optionsQ.data ?? [];

  const [addingOption, setAddingOption] = useState(false);
  const [optName, setOptName] = useState('');
  const [optPrice, setOptPrice] = useState('0.00');
  const [optBusy, setOptBusy] = useState(false);
  const [optError, setOptError] = useState<ApiError | null>(null);

  const submitOption = async () => {
    if (!optName.trim()) return;
    setOptBusy(true);
    setOptError(null);
    try {
      await modifierOptionsApi.create(group.id, { name: optName.trim(), price_delta: optPrice || '0.00' });
      setOptName('');
      setOptPrice('0.00');
      setAddingOption(false);
      optionsQ.refetch();
    } catch (err) {
      setOptError(parseApiError(err));
    } finally {
      setOptBusy(false);
    }
  };

  const [selectedOptionId, setSelectedOptionId] = useState<number | null>(null);
  const consumptionsQ = useQuery(
    () => selectedOptionId ? modifierConsumptionsApi.list(selectedOptionId).then(asResults) : Promise.resolve<ModifierOptionConsumption[]>([]),
    [selectedOptionId],
  );
  const [addingConsumption, setAddingConsumption] = useState(false);
  const [consBusy, setConsBusy] = useState(false);
  const [consError, setConsError] = useState<ApiError | null>(null);

  const submitConsumption = async (payload: { component_product: number; component_unit: number | null; entered_qty: string }) => {
    if (!selectedOptionId) return;
    setConsBusy(true);
    setConsError(null);
    try {
      await modifierConsumptionsApi.create(selectedOptionId, payload);
      setAddingConsumption(false);
      consumptionsQ.refetch();
    } catch (err) {
      setConsError(parseApiError(err));
    } finally {
      setConsBusy(false);
    }
  };

  const optionColumns: Column<ModifierOption>[] = [
    {
      key: 'name', header: 'Option',
      render: (o) => (
        <button onClick={() => setSelectedOptionId(o.id)} className="font-semibold text-start hover:underline focus-ring rounded">
          {o.name}
        </button>
      ),
    },
    { key: 'price', header: 'Price delta', align: 'end', mono: true, render: (o) => money(o.price_delta) },
    { key: 'status', header: 'Status', render: (o) => <ActiveBadge active={o.is_active} /> },
  ];

  const consumptionColumns: Column<ModifierOptionConsumption>[] = [
    { key: 'component', header: 'Ingredient', render: (c) => c.component_product_name },
    { key: 'qty', header: 'Qty (entered)', align: 'end', mono: true, render: (c) => formatQty(c.entered_qty) },
    { key: 'qty_base', header: 'Qty (base)', align: 'end', mono: true, render: (c) => formatQty(c.qty_base) },
  ];

  const selectedOption = options.find((o) => o.id === selectedOptionId) ?? null;

  return (
    <Drawer title={group.name} subtitle="Options & consumption formulas" onClose={onClose} widthClassName="max-w-[640px]">
      <div className="space-y-6">
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Options</h3>
            <Button size="sm" variant="secondary" onClick={() => { setOptError(null); setAddingOption((v) => !v); }}>
              <Icon name="plus" size={13} /> Add option
            </Button>
          </div>
          {addingOption && (
            <div className="border border-neutral-200 rounded-md p-3 mb-3 space-y-3 bg-neutral-50">
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Name" value={optName} onChange={(e) => setOptName(e.target.value)} error={optError?.fieldErrors.name} autoFocus />
                <FormField label="Price delta" type="number" step="0.01" value={optPrice} onChange={(e) => setOptPrice(e.target.value)} error={optError?.fieldErrors.price_delta} hint="0 for a free/removal option." />
              </div>
              {optError && !optError.fieldErrors.name && !optError.fieldErrors.price_delta && <FieldError error={optError.message} />}
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setAddingOption(false)} disabled={optBusy}>Cancel</Button>
                <Button size="sm" onClick={submitOption} disabled={optBusy || !optName.trim()}>{optBusy ? 'Saving…' : 'Save'}</Button>
              </div>
            </div>
          )}
          <DataTable<ModifierOption>
            columns={optionColumns}
            rows={options}
            rowKey={(o) => o.id}
            loading={optionsQ.loading}
            error={optionsQ.error}
            onRetry={optionsQ.refetch}
            emptyTitle="No options yet"
            emptyHint="Add an option like 'Extra Cheese' or 'No Onion'."
          />
        </section>

        {selectedOption && (
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">
                Consumption — {selectedOption.name}
              </h3>
              <Button size="sm" variant="secondary" onClick={() => { setConsError(null); setAddingConsumption((v) => !v); }}>
                <Icon name="plus" size={13} /> Add consumption
              </Button>
            </div>
            {addingConsumption && (
              <div className="mb-3">
                <ConsumptionFormPanel onSubmit={submitConsumption} busy={consBusy} error={consError} />
              </div>
            )}
            <DataTable<ModifierOptionConsumption>
              columns={consumptionColumns}
              rows={consumptionsQ.data ?? []}
              rowKey={(c) => c.id}
              loading={consumptionsQ.loading}
              error={consumptionsQ.error}
              onRetry={consumptionsQ.refetch}
              emptyTitle="No consumption formula yet"
              emptyHint="Without one, selecting this option changes price only — it consumes no inventory."
            />
          </section>
        )}
      </div>
    </Drawer>
  );
};

/* ── Page ──────────────────────────────────────────────────────────────── */

/** `/recipes/modifiers` — modifier group catalog: create groups, manage
 * each group's options and their ingredient-consumption formulas. */
export const ModifiersPage: React.FC = () => {
  const groupsQ = useQuery(() => modifierGroupsApi.list().then(asResults), []);
  const groups = groupsQ.data ?? [];

  const [creating, setCreating] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<ApiError | null>(null);
  const [managing, setManaging] = useState<ModifierGroup | null>(null);
  const [deactivating, setDeactivating] = useState<ModifierGroup | null>(null);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const submitGroup = async (name: string) => {
    setCreateBusy(true);
    setCreateError(null);
    try {
      await modifierGroupsApi.create({ name });
      setCreating(false);
      groupsQ.refetch();
    } catch (err) {
      setCreateError(parseApiError(err));
    } finally {
      setCreateBusy(false);
    }
  };

  const confirmDeactivate = async () => {
    if (!deactivating) return;
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await modifierGroupsApi.deactivate(deactivating.id);
      setDeactivating(null);
      groupsQ.refetch();
    } catch (err) {
      setDeactivateError(parseApiError(err).message);
    } finally {
      setDeactivateBusy(false);
    }
  };

  const columns: Column<ModifierGroup>[] = [
    {
      key: 'name', header: 'Name',
      render: (g) => (
        <button onClick={() => setManaging(g)} className="font-semibold text-start hover:underline focus-ring rounded">
          {g.name}
        </button>
      ),
    },
    { key: 'selection', header: 'Selection', render: (g) => g.selection_type === 'single' ? 'Choose one' : 'Choose any' },
    { key: 'status', header: 'Status', render: (g) => <ActiveBadge active={g.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (g) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="secondary" onClick={() => setManaging(g)}>Manage options</Button>
          {g.is_active && (
            <button
              onClick={() => setDeactivating(g)}
              className="w-7 h-7 rounded grid place-items-center text-danger-500 hover:bg-danger-50 focus-ring"
              aria-label="Deactivate"
            >
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Modifiers"
        subtitle="Extras, removals, and size options that change price and ingredient consumption"
        right={
          <Button size="sm" onClick={() => { setCreateError(null); setCreating(true); }}>
            <Icon name="plus" size={14} /> New group
          </Button>
        }
      />
      <div className="p-5 max-w-[900px] w-full mx-auto">
        <DataTable<ModifierGroup>
          columns={columns}
          rows={groups}
          rowKey={(g) => g.id}
          loading={groupsQ.loading}
          error={groupsQ.error}
          onRetry={groupsQ.refetch}
          emptyTitle="No modifier groups yet"
          emptyHint="Create a group like 'Extras', then attach it to products from each product's Recipe page."
        />
      </div>

      {creating && (
        <GroupFormModal busy={createBusy} error={createError} onSubmit={submitGroup} onClose={() => setCreating(false)} />
      )}
      {managing && <ModifierGroupDrawer group={managing} onClose={() => setManaging(null)} />}
      {deactivating && (
        <ConfirmDialog
          title={`Deactivate ${deactivating.name}?`}
          message="Products currently offering this group keep the link, but it can no longer be selected on new sales."
          confirmLabel="Deactivate"
          busy={deactivateBusy}
          error={deactivateError}
          onConfirm={confirmDeactivate}
          onCancel={() => { setDeactivating(null); setDeactivateError(null); }}
        />
      )}
    </div>
  );
};
