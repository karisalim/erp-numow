import React, { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Badge } from '../../components/ui/Badge';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Modal } from '../../components/ui/Modal';
import { Drawer } from '../../components/ui/Drawer';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { FormField, SelectField } from '../../components/ui/FormField';
import { AlertBanner, LoadingState, QueryErrorState } from '../../components/ui/states';
import { BalanceCard } from '../../components/erp/BalanceCard';
import { StatementTable } from '../../components/erp/StatementTable';
import { financeApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import { ACCOUNT_TYPES, accountTypeBadge, accountTypeLabel } from './accountTypes';
import type { AccountType, FinancialAccount, FinancialAccountPayload } from '../../types/erp';

const PAGE_SIZE = 20;

/* ── Create / edit form ─────────────────────────────────────────────────── */

const AccountFormModal: React.FC<{
  initial?: FinancialAccount;
  busy: boolean;
  error: ApiError | null;
  onSubmit: (payload: FinancialAccountPayload) => void;
  onClose: () => void;
}> = ({ initial, busy, error, onSubmit, onClose }) => {
  const [name, setName] = useState(initial?.name ?? '');
  const [code, setCode] = useState(initial?.code ?? '');
  const [accountType, setAccountType] = useState<AccountType | ''>(initial?.account_type ?? '');
  const [openingBalance, setOpeningBalance] = useState(initial?.opening_balance ?? '');
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const submit = () => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name is required.';
    if (!accountType) errs.account_type = 'Select an account type.';
    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;
    const payload: FinancialAccountPayload = {
      name: name.trim(),
      code,
      account_type: accountType as AccountType,
    };
    if (!initial && openingBalance) payload.opening_balance = openingBalance;
    onSubmit(payload);
  };

  const err = (k: string) => localErrors[k] ?? error?.fieldErrors[k];

  return (
    <Modal title={initial ? `Edit ${initial.name}` : 'New financial account'} onClose={busy ? () => undefined : onClose} maxWidth="max-w-[480px]">
      <div className="p-6 space-y-4">
        {error && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone={error.permissionDenied ? 'warn' : 'danger'}>{error.message}</AlertBanner>
        )}
        <FormField label="Name" required value={name} error={err('name')} onChange={(e) => setName(e.target.value)} autoFocus />
        <FormField label="Code" value={code} error={err('code')} onChange={(e) => setCode(e.target.value)} maxLength={40} hint="Optional short code" />
        <SelectField
          label="Account type" required value={accountType} error={err('account_type')}
          onChange={(e) => setAccountType(e.target.value as AccountType | '')}
          disabled={Boolean(initial)}
          hint={initial ? 'Type cannot change once movements reference the account.' : undefined}
        >
          <option value="">Select type</option>
          {(Object.keys(ACCOUNT_TYPES) as AccountType[]).map((t) => (
            <option key={t} value={t}>{ACCOUNT_TYPES[t].label}</option>
          ))}
        </SelectField>
        {!initial && (
          <FormField
            label="Opening balance" type="number" step="0.01" inputMode="decimal"
            value={openingBalance} error={err('opening_balance')}
            onChange={(e) => setOpeningBalance(e.target.value)}
          />
        )}
      </div>
      <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
      </div>
    </Modal>
  );
};

/* ── Account detail drawer: balance + movements ─────────────────────────── */

const AccountDrawer: React.FC<{
  account: FinancialAccount;
  onClose: () => void;
  onEdit: () => void;
  onChanged: () => void;
}> = ({ account, onClose, onEdit, onChanged }) => {
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const balanceQ = useQuery(() => financeApi.accountBalance(account.id), [account.id]);
  const statementQ = useQuery(() => financeApi.accountStatement(account.id), [account.id]);

  const doDeactivate = async () => {
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await financeApi.deactivateAccount(account.id);
      setConfirmDeactivate(false);
      onChanged();
      onClose();
    } catch (err) {
      setDeactivateError(parseApiError(err).message);
    } finally {
      setDeactivateBusy(false);
    }
  };

  return (
    <Drawer
      title={account.name}
      subtitle={<span><Badge kind={accountTypeBadge(account.account_type)}>{accountTypeLabel(account.account_type)}</Badge> <ActiveBadge active={account.is_active} /></span>}
      onClose={onClose}
      widthClassName="max-w-[680px]"
      footer={
        <>
          {account.is_active && (
            <Button variant="secondary" onClick={() => setConfirmDeactivate(true)}>Deactivate</Button>
          )}
          <Button variant="secondary" onClick={onEdit}><Icon name="edit" size={14} /> Edit</Button>
        </>
      }
    >
      <div className="space-y-4">
        {balanceQ.loading ? (
          <LoadingState label="Loading balance…" />
        ) : balanceQ.error ? (
          <QueryErrorState error={balanceQ.error} onRetry={balanceQ.refetch} />
        ) : balanceQ.data && (
          <BalanceCard
            label="Current balance"
            balance={balanceQ.data.balance}
            openingBalance={balanceQ.data.opening_balance}
          />
        )}
        <StatementTable
          summary={statementQ.data}
          loading={statementQ.loading}
          error={statementQ.error}
          onRetry={statementQ.refetch}
        />
      </div>

      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate account"
          message={<>Deactivate <b>{account.name}</b>? Its history stays intact but new documents can no longer route money to it.</>}
          confirmLabel="Deactivate"
          busy={deactivateBusy}
          error={deactivateError}
          onConfirm={doDeactivate}
          onCancel={() => setConfirmDeactivate(false)}
        />
      )}
    </Drawer>
  );
};

/* ── Tab ────────────────────────────────────────────────────────────────── */

export const AccountsTab: React.FC = () => {
  const money = useMoney();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<FinancialAccount | null>(null);
  const [formOpen, setFormOpen] = useState<'create' | 'edit' | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const listQ = useQuery(() => financeApi.listAccounts({ page, page_size: PAGE_SIZE }), [page]);

  const submitForm = async (payload: FinancialAccountPayload) => {
    setFormBusy(true);
    setFormError(null);
    try {
      if (formOpen === 'edit' && selected) {
        const updated = await financeApi.updateAccount(selected.id, { name: payload.name, code: payload.code });
        setSelected(updated);
      } else {
        await financeApi.createAccount(payload);
      }
      setFormOpen(null);
      listQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setFormBusy(false);
    }
  };

  const columns: Column<FinancialAccount>[] = [
    {
      key: 'name', header: 'Account',
      render: (a) => (
        <div>
          <div className="font-semibold">{a.name}</div>
          {a.code && <div className="text-[11.5px] text-neutral-400 font-mono">{a.code}</div>}
        </div>
      ),
    },
    { key: 'type', header: 'Type', render: (a) => <Badge kind={accountTypeBadge(a.account_type)}>{accountTypeLabel(a.account_type)}</Badge> },
    { key: 'currency', header: 'Currency', className: 'hidden md:table-cell', render: (a) => <span className="text-neutral-500">{a.currency || '—'}</span> },
    { key: 'opening', header: 'Opening', align: 'end', mono: true, render: (a) => money(a.opening_balance) },
    { key: 'status', header: 'Status', render: (a) => <ActiveBadge active={a.is_active} /> },
    { key: 'chev', header: '', render: () => <Icon name="chevR" size={15} className="text-neutral-300 rtl:rotate-180" /> },
  ];

  return (
    <>
      <div className="flex justify-end mb-3">
        <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
          <Icon name="plus" size={14} /> New account
        </Button>
      </div>
      <DataTable<FinancialAccount>
        columns={columns}
        rows={listQ.data?.results ?? []}
        rowKey={(a) => a.id}
        loading={listQ.loading}
        error={listQ.error}
        onRetry={listQ.refetch}
        emptyTitle="No financial accounts"
        emptyHint="Create a cashbox, card settlement, and wallet account so payment methods can route money."
        emptyIcon="bank"
        emptyAction={
          <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
            <Icon name="plus" size={14} /> New account
          </Button>
        }
        onRowClick={(a) => setSelected(a)}
        page={page}
        pageSize={PAGE_SIZE}
        count={listQ.data?.count ?? 0}
        onPage={setPage}
      />

      {selected && formOpen !== 'edit' && (
        <AccountDrawer
          account={selected}
          onClose={() => setSelected(null)}
          onEdit={() => { setFormError(null); setFormOpen('edit'); }}
          onChanged={() => listQ.refetch()}
        />
      )}

      {formOpen && (
        <AccountFormModal
          initial={formOpen === 'edit' ? selected ?? undefined : undefined}
          busy={formBusy}
          error={formError}
          onSubmit={submitForm}
          onClose={() => setFormOpen(null)}
        />
      )}
    </>
  );
};
