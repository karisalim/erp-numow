import React, { useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Tabs } from '../../components/ui/Tabs';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { AlertBanner, LoadingState, QueryErrorState } from '../../components/ui/states';
import { BalanceCard } from '../../components/erp/BalanceCard';
import { StatementTable } from '../../components/erp/StatementTable';
import { SettlementFormModal, type SettlementSubmit } from '../../components/erp/SettlementFormModal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { customersApi, settlementsApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import type { Customer } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Customer detail drawer: overview (contact + AR balance), statement tab,
 * receipt recording, deactivate. Balances/statements come from the
 * backend ledger endpoints (Manager+; a 403 shows the denied state).
 * ──────────────────────────────────────────────────────────────────────────── */

export const CustomerDrawer: React.FC<{
  customer: Customer;
  onClose: () => void;
  onEdit: () => void;
  onChanged: () => void;   // refresh list after deactivate / receipt
}> = ({ customer, onClose, onEdit, onChanged }) => {
  const money = useMoney();
  const [tab, setTab] = useState<'overview' | 'statement'>('overview');
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [receiptBusy, setReceiptBusy] = useState(false);
  const [receiptError, setReceiptError] = useState<ApiError | null>(null);
  const [receiptDone, setReceiptDone] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const balanceQ = useQuery(() => customersApi.balance(customer.id), [customer.id, refreshKey]);
  const statementQ = useQuery(() => customersApi.statement(customer.id), [customer.id, refreshKey]);

  const submitReceipt = async (data: SettlementSubmit) => {
    setReceiptBusy(true);
    setReceiptError(null);
    try {
      const created = await settlementsApi.createCustomerReceipt({
        customer: customer.id,
        payment_method: data.payment_method,
        destination_account: data.account,
        amount: data.amount,
        reference: data.reference || undefined,
        notes: data.notes || undefined,
      });
      setReceiptOpen(false);
      setReceiptDone(`Receipt #${created.id} posted — ${money(created.amount)} received into ${created.destination_account_name}.`);
      setRefreshKey((k) => k + 1);  // refresh balance + statement
      onChanged();
    } catch (err) {
      setReceiptError(parseApiError(err));
    } finally {
      setReceiptBusy(false);
    }
  };

  const doDeactivate = async () => {
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await customersApi.deactivate(customer.id);
      setConfirmDeactivate(false);
      onChanged();
      onClose();
    } catch (err) {
      setDeactivateError(parseApiError(err).message);
    } finally {
      setDeactivateBusy(false);
    }
  };

  const overviewRow = (label: string, value: React.ReactNode) => (
    <div className="flex justify-between gap-4 py-2 border-b border-neutral-100 text-[13px]">
      <span className="text-neutral-500">{label}</span>
      <span className="font-medium text-end">{value || '—'}</span>
    </div>
  );

  return (
    <Drawer
      title={customer.name}
      subtitle={<span>Customer{customer.code ? ` · ${customer.code}` : ''} <ActiveBadge active={customer.is_active} /></span>}
      onClose={onClose}
      widthClassName="max-w-[640px]"
      footer={
        <>
          {customer.is_active && (
            <Button variant="secondary" onClick={() => setConfirmDeactivate(true)}>Deactivate</Button>
          )}
          <Button variant="secondary" onClick={onEdit}><Icon name="edit" size={14} /> Edit</Button>
          <Button onClick={() => { setReceiptDone(null); setReceiptOpen(true); }}>
            <Icon name="cash" size={15} /> Record receipt
          </Button>
        </>
      }
    >
      {receiptDone && (
        <AlertBanner tone="success" className="mb-4" onDismiss={() => setReceiptDone(null)}>
          {receiptDone}
        </AlertBanner>
      )}

      <Tabs
        className="mb-4"
        value={tab}
        onChange={setTab}
        options={[
          { value: 'overview', label: 'Overview' },
          { value: 'statement', label: 'Statement' },
        ]}
      />

      {tab === 'overview' && (
        <div className="space-y-4">
          {balanceQ.loading ? (
            <LoadingState label="Loading balance…" />
          ) : balanceQ.error ? (
            <QueryErrorState error={balanceQ.error} onRetry={balanceQ.refetch} />
          ) : balanceQ.data && (
            <BalanceCard
              label="AR balance (owed by customer)"
              balance={balanceQ.data.balance}
              openingBalance={balanceQ.data.opening_balance}
              emphasize={Number(balanceQ.data.balance) > 0 ? 'negative' : 'neutral'}
              hint={
                Number(customer.credit_limit) > 0 && Number(balanceQ.data.balance) > Number(customer.credit_limit)
                  ? `Over credit limit (${money(customer.credit_limit)})`
                  : Number(customer.credit_limit) > 0
                    ? `Credit limit ${money(customer.credit_limit)}`
                    : 'No credit limit set'
              }
            />
          )}
          <div>
            {overviewRow('Phone', customer.phone)}
            {overviewRow('Email', customer.email)}
            {overviewRow('Tax number', customer.tax_number)}
            {overviewRow('Credit limit', Number(customer.credit_limit) > 0 ? money(customer.credit_limit) : 'None')}
            {overviewRow('Opening balance', money(customer.opening_balance))}
          </div>
        </div>
      )}

      {tab === 'statement' && (
        <StatementTable
          summary={statementQ.data}
          loading={statementQ.loading}
          error={statementQ.error}
          onRetry={statementQ.refetch}
        />
      )}

      {receiptOpen && (
        <SettlementFormModal
          title="Record customer receipt"
          partyLabel={`Customer · ${customer.name}`}
          accountLabel="Deposit into account"
          submitLabel="Post receipt"
          currentBalance={balanceQ.data?.balance}
          balanceLabel="AR balance"
          busy={receiptBusy}
          error={receiptError}
          onSubmit={submitReceipt}
          onClose={() => setReceiptOpen(false)}
        />
      )}

      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate customer"
          message={<>Deactivate <b>{customer.name}</b>? The customer keeps their history and balance but can no longer be selected on new documents.</>}
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
