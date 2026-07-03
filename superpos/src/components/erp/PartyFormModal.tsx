import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FormField } from '../ui/FormField';
import { AlertBanner } from '../ui/states';
import type { ApiError } from '../../utils/apiError';

/* ─────────────────────────────────────────────────────────────────────────────
 * Create/edit form shared by Customers and Suppliers (same master-data
 * shape; customers additionally have a credit limit). Field names mirror
 * the backend serializers exactly.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface PartyFormValues {
  name: string;
  code: string;
  phone: string;
  email: string;
  tax_number: string;
  credit_limit?: string;
  opening_balance: string;
}

export const PartyFormModal: React.FC<{
  title: string;
  kind: 'customer' | 'supplier';
  initial?: Partial<PartyFormValues>;
  /** Opening balance is only editable at create time (posted ledger afterwards). */
  isEdit?: boolean;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (values: PartyFormValues) => void;
  onClose: () => void;
}> = ({ title, kind, initial, isEdit, busy, error, onSubmit, onClose }) => {
  const [values, setValues] = useState<PartyFormValues>({
    name: initial?.name ?? '',
    code: initial?.code ?? '',
    phone: initial?.phone ?? '',
    email: initial?.email ?? '',
    tax_number: initial?.tax_number ?? '',
    credit_limit: initial?.credit_limit ?? '',
    opening_balance: initial?.opening_balance ?? '',
  });
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const set = (k: keyof PartyFormValues) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [k]: e.target.value }));

  const handleSubmit = () => {
    const errs: Record<string, string> = {};
    if (!values.name.trim()) errs.name = 'Name is required.';
    if (values.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errs.email = 'Enter a valid email address.';
    if (values.credit_limit && Number(values.credit_limit) < 0) errs.credit_limit = 'Cannot be negative.';
    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({ ...values, name: values.name.trim() });
  };

  const err = (k: string) => localErrors[k] ?? error?.fieldErrors[k];

  return (
    <Modal title={title} onClose={busy ? () => undefined : onClose} maxWidth="max-w-[560px]">
      <div className="p-6 space-y-4">
        {error && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone={error.permissionDenied ? 'warn' : 'danger'}>{error.message}</AlertBanner>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField label="Name" required value={values.name} error={err('name')} onChange={set('name')} autoFocus />
          <FormField label="Code" value={values.code} error={err('code')} onChange={set('code')} maxLength={40} hint="Optional short code" />
          <FormField label="Phone" value={values.phone} error={err('phone')} onChange={set('phone')} maxLength={50} />
          <FormField label="Email" type="email" value={values.email} error={err('email')} onChange={set('email')} />
          <FormField label="Tax number" value={values.tax_number} error={err('tax_number')} onChange={set('tax_number')} maxLength={64} />
          {kind === 'customer' && (
            <FormField
              label="Credit limit"
              type="number" min="0" step="0.01" inputMode="decimal"
              value={values.credit_limit}
              error={err('credit_limit')}
              onChange={set('credit_limit')}
              hint="0 = no credit allowed"
            />
          )}
          {!isEdit && (
            <FormField
              label="Opening balance"
              type="number" step="0.01" inputMode="decimal"
              value={values.opening_balance}
              error={err('opening_balance')}
              onChange={set('opening_balance')}
              hint={kind === 'customer' ? 'Existing AR balance owed by the customer' : 'Existing AP balance owed to the supplier'}
            />
          )}
        </div>
      </div>
      <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
      </div>
    </Modal>
  );
};
