import React, { useMemo, useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Badge } from '../../components/ui/Badge';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { SelectField } from '../../components/ui/FormField';
import { AlertBanner } from '../../components/ui/states';
import { PaymentRouteLabel, routeHint } from '../../components/erp/PaymentRouteLabel';
import { branchesApi, financeApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { accountTypeLabel } from './accountTypes';
import {
  COMPATIBLE_DESTINATIONS,
  type BranchPaymentMethod,
  type BranchPaymentMethodPayload,
  type PaymentMethodType,
} from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Branch payment routing: which payment methods a branch accepts and which
 * financial account each one routes money into. Destination options are
 * filtered by the v3.6 compatibility map (cash → cashbox/main_safe,
 * card → card_settlement, wallet → wallet, credit → customer_ar); the
 * backend revalidates the same rule.
 * ──────────────────────────────────────────────────────────────────────────── */

const RoutingFormModal: React.FC<{
  branchId: number;
  initial?: BranchPaymentMethod;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (payload: BranchPaymentMethodPayload) => void;
  onClose: () => void;
}> = ({ initial, busy, error, onSubmit, onClose }) => {
  const [methodId, setMethodId] = useState<number | ''>(initial?.payment_method ?? '');
  const [accountId, setAccountId] = useState<number | ''>(initial?.destination_account ?? '');
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const methodsQ = useQuery(() => financeApi.listPaymentMethods({ page_size: 100 }), []);
  const accountsQ = useQuery(() => financeApi.listAccounts({ page_size: 200 }), []);

  const methods = (methodsQ.data?.results ?? []).filter((m) => m.is_active);
  const selectedMethod = methods.find((m) => m.id === methodId);

  const compatibleAccounts = useMemo(() => {
    const active = (accountsQ.data?.results ?? []).filter((a) => a.is_active);
    if (!selectedMethod) return active;
    const allowed = COMPATIBLE_DESTINATIONS[selectedMethod.method_type as PaymentMethodType];
    return allowed ? active.filter((a) => allowed.includes(a.account_type)) : active;
  }, [accountsQ.data, selectedMethod]);

  const submit = () => {
    const errs: Record<string, string> = {};
    if (!methodId) errs.payment_method = 'Select a payment method.';
    if (!accountId) errs.destination_account = 'Select a destination account.';
    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({
      payment_method: Number(methodId),
      destination_account: Number(accountId),
      is_default: isDefault,
    });
  };

  const err = (k: string) => localErrors[k] ?? error?.fieldErrors[k];

  return (
    <Modal
      title={initial ? `Edit routing · ${initial.payment_method_name}` : 'Enable payment method for branch'}
      onClose={busy ? () => undefined : onClose}
      maxWidth="max-w-[500px]"
    >
      <div className="p-6 space-y-4">
        {error && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone={error.permissionDenied ? 'warn' : 'danger'}>{error.message}</AlertBanner>
        )}
        <SelectField
          label="Payment method" required value={methodId} error={err('payment_method')}
          disabled={Boolean(initial)}
          onChange={(e) => { setMethodId(e.target.value ? Number(e.target.value) : ''); setAccountId(''); }}
        >
          <option value="">{methodsQ.loading ? 'Loading…' : 'Select method'}</option>
          {methods.map((m) => (
            <option key={m.id} value={m.id}>{m.name} ({m.method_type})</option>
          ))}
        </SelectField>
        {selectedMethod && (
          <div className="flex items-start gap-2 text-[12px] text-neutral-500">
            <PaymentRouteLabel methodType={selectedMethod.method_type as PaymentMethodType} />
            <span>{routeHint(selectedMethod.method_type as PaymentMethodType)}</span>
          </div>
        )}
        <SelectField
          label="Destination account" required value={accountId} error={err('destination_account')}
          onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : '')}
          hint={selectedMethod ? 'Only account types compatible with this method are listed.' : undefined}
        >
          <option value="">{accountsQ.loading ? 'Loading…' : 'Select account'}</option>
          {compatibleAccounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name} ({accountTypeLabel(a.account_type)})</option>
          ))}
        </SelectField>
        {selectedMethod && compatibleAccounts.length === 0 && !accountsQ.loading && (
          <AlertBanner tone="warn">
            No active compatible account exists ({COMPATIBLE_DESTINATIONS[selectedMethod.method_type as PaymentMethodType]?.map(accountTypeLabel).join(' / ')}).
            Create one under the Accounts tab first.
          </AlertBanner>
        )}
        <label className="flex items-center gap-2.5 text-[13.5px] font-medium text-neutral-700">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="w-4 h-4 accent-brand-600"
          />
          Default method for this branch
        </label>
      </div>
      <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save routing'}</Button>
      </div>
    </Modal>
  );
};

export const BranchRoutingTab: React.FC = () => {
  const [branchId, setBranchId] = useState<number | ''>('');
  const [formFor, setFormFor] = useState<BranchPaymentMethod | 'create' | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [deactivateFor, setDeactivateFor] = useState<BranchPaymentMethod | null>(null);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const branchesQ = useQuery(() => branchesApi.list().then(asResults), []);
  const branches = branchesQ.data ?? [];

  // Default to the first branch once loaded.
  const effectiveBranch = branchId || branches[0]?.id || '';

  const listQ = useQuery(
    () => (effectiveBranch ? financeApi.listBranchPaymentMethods(Number(effectiveBranch)) : Promise.resolve([])),
    [effectiveBranch],
  );

  const submitForm = async (payload: BranchPaymentMethodPayload) => {
    if (!effectiveBranch) return;
    setFormBusy(true);
    setFormError(null);
    try {
      if (formFor && formFor !== 'create') {
        await financeApi.updateBranchPaymentMethod(Number(effectiveBranch), formFor.id, {
          destination_account: payload.destination_account,
          is_default: payload.is_default,
        });
      } else {
        await financeApi.createBranchPaymentMethod(Number(effectiveBranch), payload);
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
    if (!deactivateFor || !effectiveBranch) return;
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await financeApi.deactivateBranchPaymentMethod(Number(effectiveBranch), deactivateFor.id);
      setDeactivateFor(null);
      listQ.refetch();
    } catch (err) {
      setDeactivateError(parseApiError(err).message);
    } finally {
      setDeactivateBusy(false);
    }
  };

  const columns: Column<BranchPaymentMethod>[] = [
    {
      key: 'method', header: 'Method',
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-semibold">{r.payment_method_name}</span>
          {r.is_default && <Badge kind="brand">Default</Badge>}
        </div>
      ),
    },
    {
      key: 'route', header: 'Routes to',
      render: (r) => <PaymentRouteLabel methodType={r.payment_method_type} destination={r.destination_account_name} />,
    },
    { key: 'acctType', header: 'Account type', className: 'hidden md:table-cell', render: (r) => <span className="text-neutral-500">{accountTypeLabel(r.destination_account_type)}</span> },
    { key: 'status', header: 'Status', render: (r) => <ActiveBadge active={r.is_active} /> },
    {
      key: 'actions', header: '', align: 'end',
      render: (r) => (
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => { setFormError(null); setFormFor(r); }}>
            <Icon name="edit" size={14} />
          </Button>
          {r.is_active && (
            <Button variant="ghost" size="sm" onClick={() => { setDeactivateError(null); setDeactivateFor(r); }}>
              <Icon name="x" size={14} />
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="flex items-end justify-between gap-3 flex-wrap mb-3">
        <div className="w-full sm:w-72">
          <SelectField
            label="Branch"
            value={effectiveBranch}
            onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
          >
            {branchesQ.loading && <option value="">Loading…</option>}
            {branches.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </SelectField>
        </div>
        <Button size="sm" onClick={() => { setFormError(null); setFormFor('create'); }} disabled={!effectiveBranch}>
          <Icon name="plus" size={14} /> Enable method
        </Button>
      </div>

      <DataTable<BranchPaymentMethod>
        columns={columns}
        rows={listQ.data ?? []}
        rowKey={(r) => r.id}
        loading={listQ.loading || branchesQ.loading}
        error={listQ.error ?? branchesQ.error}
        onRetry={listQ.refetch}
        emptyTitle="No payment routing configured for this branch"
        emptyHint="POS sales on an unconfigured branch skip ledger posting (legacy mode). Enable methods here to activate financial routing."
        emptyIcon="bank"
        emptyAction={
          <Button size="sm" onClick={() => { setFormError(null); setFormFor('create'); }} disabled={!effectiveBranch}>
            <Icon name="plus" size={14} /> Enable method
          </Button>
        }
      />

      {formFor && effectiveBranch && (
        <RoutingFormModal
          branchId={Number(effectiveBranch)}
          initial={formFor === 'create' ? undefined : formFor}
          busy={formBusy}
          error={formError}
          onSubmit={submitForm}
          onClose={() => setFormFor(null)}
        />
      )}

      {deactivateFor && (
        <ConfirmDialog
          title="Disable payment method"
          message={<>Disable <b>{deactivateFor.payment_method_name}</b> for this branch? Cashiers will no longer be offered it at checkout.</>}
          confirmLabel="Disable"
          busy={deactivateBusy}
          error={deactivateError}
          onConfirm={doDeactivate}
          onCancel={() => setDeactivateFor(null)}
        />
      )}
    </>
  );
};
