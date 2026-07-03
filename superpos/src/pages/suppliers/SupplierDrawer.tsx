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
import { suppliersApi, settlementsApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import type { Supplier } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Supplier detail drawer: overview (contact + AP balance), statement tab,
 * supplier payment recording (money OUT of a source account), deactivate.
 * ──────────────────────────────────────────────────────────────────────────── */

export const SupplierDrawer: React.FC<{
  supplier: Supplier;
  onClose: () => void;
  onEdit: () => void;
  onChanged: () => void;
}> = ({ supplier, onClose, onEdit, onChanged }) => {
  const money = useMoney();
  const [tab, setTab] = useState<'overview' | 'statement'>('overview');
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [paymentError, setPaymentError] = useState<ApiError | null>(null);
  const [paymentDone, setPaymentDone] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [deactivateBusy, setDeactivateBusy] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const balanceQ = useQuery(() => suppliersApi.balance(supplier.id), [supplier.id, refreshKey]);
  const statementQ = useQuery(() => suppliersApi.statement(supplier.id), [supplier.id, refreshKey]);

  const submitPayment = async (data: SettlementSubmit) => {
    setPaymentBusy(true);
    setPaymentError(null);
    try {
      const created = await settlementsApi.createSupplierPayment({
        supplier: supplier.id,
        payment_method: data.payment_method,
        source_account: data.account,
        amount: data.amount,
        reference: data.reference || undefined,
        notes: data.notes || undefined,
      });
      setPaymentOpen(false);
      setPaymentDone(`Payment #${created.id} posted — ${money(created.amount)} paid from ${created.source_account_name}.`);
      setRefreshKey((k) => k + 1);
      onChanged();
    } catch (err) {
      setPaymentError(parseApiError(err));
    } finally {
      setPaymentBusy(false);
    }
  };

  const doDeactivate = async () => {
    setDeactivateBusy(true);
    setDeactivateError(null);
    try {
      await suppliersApi.deactivate(supplier.id);
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
      title={supplier.name}
      subtitle={<span>Supplier{supplier.code ? ` · ${supplier.code}` : ''} <ActiveBadge active={supplier.is_active} /></span>}
      onClose={onClose}
      widthClassName="max-w-[640px]"
      footer={
        <>
          {supplier.is_active && (
            <Button variant="secondary" onClick={() => setConfirmDeactivate(true)}>Deactivate</Button>
          )}
          <Button variant="secondary" onClick={onEdit}><Icon name="edit" size={14} /> Edit</Button>
          <Button onClick={() => { setPaymentDone(null); setPaymentOpen(true); }}>
            <Icon name="cash" size={15} /> Record payment
          </Button>
        </>
      }
    >
      {paymentDone && (
        <AlertBanner tone="success" className="mb-4" onDismiss={() => setPaymentDone(null)}>
          {paymentDone}
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
              label="AP balance (owed to supplier)"
              balance={balanceQ.data.balance}
              openingBalance={balanceQ.data.opening_balance}
              emphasize={Number(balanceQ.data.balance) > 0 ? 'negative' : 'neutral'}
            />
          )}
          <div>
            {overviewRow('Phone', supplier.phone)}
            {overviewRow('Email', supplier.email)}
            {overviewRow('Tax number', supplier.tax_number)}
            {overviewRow('Opening balance', money(supplier.opening_balance))}
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

      {paymentOpen && (
        <SettlementFormModal
          title="Record supplier payment"
          partyLabel={`Supplier · ${supplier.name}`}
          accountLabel="Pay from account"
          submitLabel="Post payment"
          currentBalance={balanceQ.data?.balance}
          balanceLabel="AP balance"
          busy={paymentBusy}
          error={paymentError}
          onSubmit={submitPayment}
          onClose={() => setPaymentOpen(false)}
        />
      )}

      {confirmDeactivate && (
        <ConfirmDialog
          title="Deactivate supplier"
          message={<>Deactivate <b>{supplier.name}</b>? The supplier keeps their history and balance but can no longer be selected on new purchase documents.</>}
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
