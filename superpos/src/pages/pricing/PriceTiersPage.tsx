import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { FormField, FieldError } from '../../components/ui/FormField';
import { priceTiersApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import type { PriceTier } from '../../types/erp';

const TierFormModal: React.FC<{
  initial?: PriceTier;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (name: string) => void;
  onClose: () => void;
}> = ({ initial, busy, error, onSubmit, onClose }) => {
  const [name, setName] = useState(initial?.name ?? '');
  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New price tier'} onClose={onClose}>
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
          hint="Retail, Wholesale, VIP, Distributor — whatever your business calls its pricing levels."
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

export const PriceTiersPage: React.FC = () => {
  const tiersQ = useQuery(() => priceTiersApi.list().then(asResults), []);
  const tiers = tiersQ.data ?? [];

  const [form, setForm] = useState<'create' | 'edit' | null>(null);
  const [selected, setSelected] = useState<PriceTier | null>(null);
  const [deactivating, setDeactivating] = useState<PriceTier | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const submit = async (name: string) => {
    setBusy(true);
    setFormError(null);
    try {
      if (form === 'edit' && selected) {
        await priceTiersApi.update(selected.id, { name });
      } else {
        await priceTiersApi.create({ name });
      }
      setForm(null);
      tiersQ.refetch();
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
      await priceTiersApi.deactivate(deactivating.id);
      setDeactivating(null);
      tiersQ.refetch();
    } catch (err) {
      setActionError(parseApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<PriceTier>[] = [
    { key: 'name', header: 'Name', render: (t) => <span className="font-semibold">{t.name}</span> },
    { key: 'status', header: 'Status', render: (t) => <ActiveBadge active={t.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (t) => (
        <div className="flex justify-end gap-1">
          <button
            onClick={() => { setSelected(t); setFormError(null); setForm('edit'); }}
            className="w-7 h-7 rounded grid place-items-center text-neutral-500 hover:bg-neutral-100 focus-ring"
            aria-label="Edit"
          >
            <Icon name="edit" size={14} />
          </button>
          {t.is_active && (
            <button
              onClick={() => setDeactivating(t)}
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
        title="Price Tiers"
        subtitle="Pricing levels (Retail, Wholesale, …) — set per-unit prices from a product's Units & pricing panel"
        right={
          <Button size="sm" onClick={() => { setFormError(null); setForm('create'); }}>
            <Icon name="plus" size={14} /> New tier
          </Button>
        }
      />
      <div className="p-5 max-w-[900px] w-full mx-auto">
        <DataTable<PriceTier>
          columns={columns}
          rows={tiers}
          rowKey={(t) => t.id}
          loading={tiersQ.loading}
          error={tiersQ.error}
          onRetry={tiersQ.refetch}
          emptyTitle="No price tiers yet"
          emptyHint="Every sale defaults to a product's base retail price until you create tiers and assign per-unit prices."
          emptyAction={
            <Button size="sm" onClick={() => { setFormError(null); setForm('create'); }}>
              <Icon name="plus" size={14} /> New tier
            </Button>
          }
        />
      </div>

      {form && (
        <TierFormModal
          initial={form === 'edit' ? selected ?? undefined : undefined}
          busy={busy}
          error={formError}
          onSubmit={submit}
          onClose={() => setForm(null)}
        />
      )}

      {deactivating && (
        <ConfirmDialog
          title={`Deactivate ${deactivating.name}?`}
          message="Existing per-unit prices under this tier stay on record but the tier can no longer be selected for new sales."
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
