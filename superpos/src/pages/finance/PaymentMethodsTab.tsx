import React, { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Badge } from '../../components/ui/Badge';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { FormField, SelectField } from '../../components/ui/FormField';
import { AlertBanner } from '../../components/ui/states';
import { PaymentRouteLabel } from '../../components/erp/PaymentRouteLabel';
import { financeApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import type { PaymentMethodPayload, PaymentMethodRecord, PaymentMethodType } from '../../types/erp';

const PAGE_SIZE = 20;

const METHOD_TYPES: { value: PaymentMethodType; label: string }[] = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card / Visa' },
  { value: 'wallet', label: 'Wallet' },
  { value: 'credit', label: 'Credit (customer pays later)' },
  { value: 'custom', label: 'Custom' },
];

const MethodFormModal: React.FC<{
  initial?: PaymentMethodRecord;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (payload: PaymentMethodPayload) => void;
  onClose: () => void;
}> = ({ initial, busy, error, onSubmit, onClose }) => {
  const [name, setName] = useState(initial?.name ?? '');
  const [methodType, setMethodType] = useState<PaymentMethodType | ''>(initial?.method_type ?? '');
  const [providerName, setProviderName] = useState(initial?.provider_name ?? '');
  const [requiresCustomer, setRequiresCustomer] = useState(initial?.requires_customer ?? false);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const submit = () => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name is required.';
    if (!methodType) errs.method_type = 'Select a method type.';
    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({
      name: name.trim(),
      method_type: methodType as PaymentMethodType,
      provider_name: providerName.trim(),
      requires_customer: methodType === 'credit' ? true : requiresCustomer,
    });
  };

  const err = (k: string) => localErrors[k] ?? error?.fieldErrors[k];

  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New payment method'} onClose={busy ? () => undefined : onClose} maxWidth="max-w-[480px]">
      <div className="p-6 space-y-4">
        {error && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone={error.permissionDenied ? 'warn' : 'danger'}>{error.message}</AlertBanner>
        )}
        <FormField label="Name" required value={name} error={err('name')} onChange={(e) => setName(e.target.value)} autoFocus />
        <SelectField
          label="Method type" required value={methodType} error={err('method_type')}
          onChange={(e) => setMethodType(e.target.value as PaymentMethodType | '')}
        >
          <option value="">Select type</option>
          {METHOD_TYPES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </SelectField>
        {methodType && <PaymentRouteLabel methodType={methodType as PaymentMethodType} />}
        <FormField
          label="Provider" value={providerName} error={err('provider_name')} maxLength={80}
          onChange={(e) => setProviderName(e.target.value)}
          hint="Optional — e.g. Visa, Vodafone Cash, InstaPay"
        />
        <label className="flex items-center gap-2.5 text-[13.5px] font-medium text-neutral-700">
          <input
            type="checkbox"
            checked={methodType === 'credit' ? true : requiresCustomer}
            disabled={methodType === 'credit'}
            onChange={(e) => setRequiresCustomer(e.target.checked)}
            className="w-4 h-4 accent-brand-600"
          />
          Requires a selected customer
          {methodType === 'credit' && <span className="text-[11.5px] text-neutral-400">(always required for credit)</span>}
        </label>
      </div>
      <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
      </div>
    </Modal>
  );
};

export const PaymentMethodsTab: React.FC = () => {
  const [page, setPage] = useState(1);
  const [formFor, setFormFor] = useState<PaymentMethodRecord | 'create' | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [deactivateFor, setDeactivateFor] = useState<PaymentMethodRecord | null>(null);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const listQ = useQuery(() => financeApi.listPaymentMethods({ page, page_size: PAGE_SIZE }), [page]);

  const submitForm = async (payload: PaymentMethodPayload) => {
    setFormBusy(true);
    setFormError(null);
    try {
      if (formFor && formFor !== 'create') {
        await financeApi.updatePaymentMethod(formFor.id, payload);
      } else {
        await financeApi.createPaymentMethod(payload);
      }
      setFormFor(null);
      listQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setFormBusy(false);
    }
  };

  const doDeactivate = async () => {
    if (!deactivateFor) return;
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await financeApi.deactivatePaymentMethod(deactivateFor.id);
      setDeactivateFor(null);
      listQ.refetch();
    } catch (err) {
      setDeactivateError(parseApiError(err).message);
    } finally {
      setDeactivateBusy(false);
    }
  };

  const columns: Column<PaymentMethodRecord>[] = [
    { key: 'name', header: 'Method', render: (m) => <span className="font-semibold">{m.name}</span> },
    { key: 'route', header: 'Routes to', render: (m) => <PaymentRouteLabel methodType={m.method_type} /> },
    { key: 'provider', header: 'Provider', className: 'hidden md:table-cell', render: (m) => <span className="text-neutral-500">{m.provider_name || '—'}</span> },
    {
      key: 'customer', header: 'Customer',
      render: (m) => (m.requires_customer ? <Badge kind="warn">Required</Badge> : <span className="text-neutral-400 text-[12.5px]">Optional</span>),
    },
    { key: 'status', header: 'Status', render: (m) => <ActiveBadge active={m.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (m) => (
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => { setFormError(null); setFormFor(m); }}>
            <Icon name="edit" size={14} />
          </Button>
          {m.is_active && (
            <Button variant="ghost" size="sm" onClick={() => { setDeactivateError(null); setDeactivateFor(m); }}>
              <Icon name="x" size={14} />
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="flex justify-end mb-3">
        <Button size="sm" onClick={() => { setFormError(null); setFormFor('create'); }}>
          <Icon name="plus" size={14} /> New method
        </Button>
      </div>
      <DataTable<PaymentMethodRecord>
        columns={columns}
        rows={listQ.data?.results ?? []}
        rowKey={(m) => m.id}
        loading={listQ.loading}
        error={listQ.error}
        onRetry={listQ.refetch}
        emptyTitle="No payment methods"
        emptyHint="Create Cash / Card / Wallet / Credit methods, then route them per branch under Branch routing."
        emptyIcon="card"
        page={page}
        pageSize={PAGE_SIZE}
        count={listQ.data?.count ?? 0}
        onPage={setPage}
      />

      {formFor && (
        <MethodFormModal
          initial={formFor === 'create' ? undefined : formFor}
          busy={formBusy}
          error={formError}
          onSubmit={submitForm}
          onClose={() => setFormFor(null)}
        />
      )}

      {deactivateFor && (
        <ConfirmDialog
          title="Deactivate payment method"
          message={<>Deactivate <b>{deactivateFor.name}</b>? It will no longer be offered at checkout in any branch.</>}
          confirmLabel="Deactivate"
          busy={deactivateBusy}
          error={deactivateError}
          onConfirm={doDeactivate}
          onCancel={() => setDeactivateFor(null)}
        />
      )}
    </>
  );
};
