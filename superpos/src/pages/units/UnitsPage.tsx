import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Tabs } from '../../components/ui/Tabs';
import { FormField, SelectField, FieldError } from '../../components/ui/FormField';
import { unitsApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import type { Unit, UnitGroup, StandardUnitCode } from '../../types/erp';

type TabValue = 'groups' | 'units';

/* ── Unit Group form ─────────────────────────────────────────────────────── */

const GroupFormModal: React.FC<{
  initial?: UnitGroup;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (name: string) => void;
  onClose: () => void;
}> = ({ initial, busy, error, onSubmit, onClose }) => {
  const [name, setName] = useState(initial?.name ?? '');
  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New unit group'} onClose={onClose}>
      <form
        onSubmit={(e) => { e.preventDefault(); if (name.trim()) onSubmit(name.trim()); }}
        className="p-5 space-y-4"
      >
        <FormField
          label="Name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={error?.fieldErrors.name}
          hint="A measurement family, e.g. Mass, Volume, Count, Packaging."
        />
        {error && !error.fieldErrors.name && <FieldError error={error.message} />}
        <div className="flex gap-2 pt-1">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" className="flex-1" disabled={busy || !name.trim()}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

/* ── Unit form ────────────────────────────────────────────────────────────── */

interface UnitFormValues {
  unit_group: number | '';
  name: string;
  symbol: string;
  standard_code: string;
  factor_to_base: string;
  allow_decimal: boolean;
}

const UnitFormModal: React.FC<{
  initial?: Unit;
  groups: UnitGroup[];
  standardCodes: StandardUnitCode[];
  busy: boolean;
  error: ApiError | null;
  onSubmit: (values: UnitFormValues) => void;
  onClose: () => void;
}> = ({ initial, groups, standardCodes, busy, error, onSubmit, onClose }) => {
  const [values, setValues] = useState<UnitFormValues>({
    unit_group: initial?.unit_group ?? (groups[0]?.id ?? ''),
    name: initial?.name ?? '',
    symbol: initial?.symbol ?? '',
    standard_code: initial?.standard_code ?? '',
    factor_to_base: initial?.factor_to_base ?? '1',
    allow_decimal: initial?.allow_decimal ?? true,
  });
  const set = <K extends keyof UnitFormValues>(k: K, v: UnitFormValues[K]) =>
    setValues((s) => ({ ...s, [k]: v }));

  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New unit'} onClose={onClose}>
      <form
        onSubmit={(e) => { e.preventDefault(); if (values.name.trim() && values.unit_group) onSubmit(values); }}
        className="p-5 space-y-4"
      >
        <SelectField
          label="Unit group"
          required
          value={values.unit_group}
          onChange={(e) => set('unit_group', Number(e.target.value))}
          error={error?.fieldErrors.unit_group}
        >
          {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </SelectField>
        <div className="grid grid-cols-2 gap-3">
          <FormField
            label="Name"
            required
            autoFocus
            value={values.name}
            onChange={(e) => set('name', e.target.value)}
            error={error?.fieldErrors.name}
            hint="Free-text label your staff picks — e.g. Carton, Kilogram."
          />
          <FormField
            label="Symbol"
            value={values.symbol}
            onChange={(e) => set('symbol', e.target.value)}
            error={error?.fieldErrors.symbol}
            placeholder="kg, L, ct…"
          />
        </div>
        <SelectField
          label="Standard code (optional)"
          hint="UN/CEFACT Rec 20 — purely optional, for future e-invoice compatibility. Leave blank if unsure."
          value={values.standard_code}
          onChange={(e) => set('standard_code', e.target.value)}
          error={error?.fieldErrors.standard_code}
        >
          <option value="">— none —</option>
          {standardCodes.map((c) => (
            <option key={c.code} value={c.code}>{c.label} ({c.code})</option>
          ))}
        </SelectField>
        <div className="grid grid-cols-2 gap-3">
          <FormField
            label="Factor to base"
            type="number"
            step="0.000001"
            min="0.000001"
            value={values.factor_to_base}
            onChange={(e) => set('factor_to_base', e.target.value)}
            error={error?.fieldErrors.factor_to_base}
            hint="Converts to the group's base unit (e.g. kg → 1000 g)."
          />
          <label className="flex items-center gap-2 mt-6 h-10">
            <input
              type="checkbox"
              checked={values.allow_decimal}
              onChange={(e) => set('allow_decimal', e.target.checked)}
              className="w-4 h-4 accent-brand-600"
            />
            <span className="text-[13.5px]">Allow decimal quantities</span>
          </label>
        </div>
        {error && !Object.keys(error.fieldErrors).length && <FieldError error={error.message} />}
        <div className="flex gap-2 pt-1">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" className="flex-1" disabled={busy || !values.name.trim() || !values.unit_group}>
            {busy ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

/* ── Page ─────────────────────────────────────────────────────────────────── */

export const UnitsPage: React.FC = () => {
  const [tab, setTab] = useState<TabValue>('groups');

  const groupsQ = useQuery(() => unitsApi.listGroups().then(asResults), []);
  const unitsQ  = useQuery(() => unitsApi.list().then(asResults), []);
  const codesQ  = useQuery(() => unitsApi.standardCodes(), []);

  const [groupForm, setGroupForm] = useState<'create' | 'edit' | null>(null);
  const [unitForm, setUnitForm]   = useState<'create' | 'edit' | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<UnitGroup | null>(null);
  const [selectedUnit, setSelectedUnit]   = useState<Unit | null>(null);
  const [deactivating, setDeactivating] = useState<{ kind: 'group' | 'unit'; id: number; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const groups = groupsQ.data ?? [];
  const units = unitsQ.data ?? [];
  const codes = codesQ.data ?? [];

  const submitGroup = async (name: string) => {
    setBusy(true);
    setFormError(null);
    try {
      if (groupForm === 'edit' && selectedGroup) {
        await unitsApi.updateGroup(selectedGroup.id, { name });
      } else {
        await unitsApi.createGroup({ name });
      }
      setGroupForm(null);
      groupsQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const submitUnit = async (values: UnitFormValues) => {
    if (!values.unit_group) return;
    setBusy(true);
    setFormError(null);
    const payload = {
      unit_group: Number(values.unit_group),
      name: values.name,
      symbol: values.symbol,
      standard_code: values.standard_code,
      factor_to_base: values.factor_to_base,
      allow_decimal: values.allow_decimal,
    };
    try {
      if (unitForm === 'edit' && selectedUnit) {
        await unitsApi.update(selectedUnit.id, payload);
      } else {
        await unitsApi.create(payload);
      }
      setUnitForm(null);
      unitsQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmDeactivate = async () => {
    if (!deactivating) return;
    setBusy(true);
    setActionError(null);
    try {
      if (deactivating.kind === 'group') {
        await unitsApi.deactivateGroup(deactivating.id);
        groupsQ.refetch();
      } else {
        await unitsApi.deactivate(deactivating.id);
        unitsQ.refetch();
      }
      setDeactivating(null);
    } catch (err) {
      setActionError(parseApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const groupColumns: Column<UnitGroup>[] = [
    { key: 'name', header: 'Name', render: (g) => <span className="font-semibold">{g.name}</span> },
    { key: 'status', header: 'Status', render: (g) => <ActiveBadge active={g.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (g) => (
        <div className="flex justify-end gap-1">
          <button
            onClick={() => { setSelectedGroup(g); setFormError(null); setGroupForm('edit'); }}
            className="w-7 h-7 rounded grid place-items-center text-neutral-500 hover:bg-neutral-100 focus-ring"
            aria-label="Edit"
          >
            <Icon name="edit" size={14} />
          </button>
          {g.is_active && (
            <button
              onClick={() => setDeactivating({ kind: 'group', id: g.id, name: g.name })}
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

  const unitColumns: Column<Unit>[] = [
    {
      key: 'name', header: 'Unit',
      render: (u) => (
        <div>
          <div className="font-semibold">{u.name}{u.symbol && <span className="text-neutral-400 font-normal"> ({u.symbol})</span>}</div>
          <div className="text-[11.5px] text-neutral-400">{u.unit_group_name}</div>
        </div>
      ),
    },
    {
      key: 'standard_code', header: 'Standard code',
      render: (u) => u.standard_code
        ? <span className="font-mono text-[12px]">{u.standard_code_display} ({u.standard_code})</span>
        : <span className="text-neutral-400">—</span>,
    },
    { key: 'factor', header: 'Factor to base', align: 'end', mono: true, render: (u) => u.factor_to_base },
    { key: 'decimal', header: 'Decimals', render: (u) => u.allow_decimal ? 'Allowed' : 'Whole only' },
    { key: 'status', header: 'Status', render: (u) => <ActiveBadge active={u.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (u) => (
        <div className="flex justify-end gap-1">
          <button
            onClick={() => { setSelectedUnit(u); setFormError(null); setUnitForm('edit'); }}
            className="w-7 h-7 rounded grid place-items-center text-neutral-500 hover:bg-neutral-100 focus-ring"
            aria-label="Edit"
          >
            <Icon name="edit" size={14} />
          </button>
          {u.is_active && (
            <button
              onClick={() => setDeactivating({ kind: 'unit', id: u.id, name: u.name })}
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
        title="Units"
        subtitle="Measurement families and the units built from them — carton, kg, box, …"
        right={
          tab === 'groups' ? (
            <Button size="sm" onClick={() => { setFormError(null); setGroupForm('create'); }}>
              <Icon name="plus" size={14} /> New group
            </Button>
          ) : (
            <Button size="sm" disabled={groups.length === 0} onClick={() => { setFormError(null); setUnitForm('create'); }}>
              <Icon name="plus" size={14} /> New unit
            </Button>
          )
        }
      />
      <div className="p-5 max-w-[1180px] w-full mx-auto space-y-4">
        <Tabs
          value={tab}
          onChange={setTab}
          options={[
            { value: 'groups', label: 'Unit groups' },
            { value: 'units', label: 'Units' },
          ]}
        />

        {tab === 'groups' ? (
          <DataTable<UnitGroup>
            columns={groupColumns}
            rows={groups}
            rowKey={(g) => g.id}
            loading={groupsQ.loading}
            error={groupsQ.error}
            onRetry={groupsQ.refetch}
            emptyTitle="No unit groups yet"
            emptyHint="Create a group (e.g. Mass, Volume, Packaging) before adding units."
          />
        ) : (
          <>
            {groups.length === 0 && !groupsQ.loading && (
              <div className="text-[13px] text-neutral-500 bg-neutral-50 border border-neutral-200 rounded-md px-3 py-2">
                Create a unit group first — units belong to a group.
              </div>
            )}
            <DataTable<Unit>
              columns={unitColumns}
              rows={units}
              rowKey={(u) => u.id}
              loading={unitsQ.loading}
              error={unitsQ.error}
              onRetry={unitsQ.refetch}
              emptyTitle="No units yet"
              emptyHint="Existing free-text unit names on products keep working with no unit assigned — this is purely additive."
            />
          </>
        )}
      </div>

      {groupForm && (
        <GroupFormModal
          initial={groupForm === 'edit' ? selectedGroup ?? undefined : undefined}
          busy={busy}
          error={formError}
          onSubmit={submitGroup}
          onClose={() => setGroupForm(null)}
        />
      )}

      {unitForm && (
        <UnitFormModal
          initial={unitForm === 'edit' ? selectedUnit ?? undefined : undefined}
          groups={groups.filter((g) => g.is_active)}
          standardCodes={codes}
          busy={busy}
          error={formError}
          onSubmit={submitUnit}
          onClose={() => setUnitForm(null)}
        />
      )}

      {deactivating && (
        <ConfirmDialog
          title={`Deactivate ${deactivating.name}?`}
          message="It stays visible on historical records but can no longer be selected on new ones."
          confirmLabel="Deactivate"
          busy={busy}
          error={actionError}
          onConfirm={confirmDeactivate}
          onCancel={() => { setDeactivating(null); setActionError(null); }}
        />
      )}
    </div>
  );
};
