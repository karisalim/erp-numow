import React, { useEffect, useMemo, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FormField, SelectField, TextAreaField } from '../ui/FormField';
import { AlertBanner } from '../ui/states';
import { PaymentRouteLabel, routeHint } from './PaymentRouteLabel';
import { financeApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { parseApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import {
  COMPATIBLE_DESTINATIONS,
  type FinancialAccount,
  type PaymentMethodRecord,
  type PaymentMethodType,
} from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Shared settlement form for Customer Receipt (money in → destination
 * account) and Supplier Payment (money out ← source account).
 *
 * Account options are filtered by the v3.6 method→account-type
 * compatibility map (cash → cashbox/main_safe, card → card_settlement,
 * wallet → wallet). The backend revalidates; this filter just prevents
 * obviously-invalid picks.
 * ──────────────────────────────────────────────────────────────────────────── */

export interface SettlementSubmit {
  payment_method: number;
  account: number;
  amount: string;
  reference: string;
  notes: string;
}

export const SettlementFormModal: React.FC<{
  title: string;
  partyLabel: string;      // e.g. "Customer · Nour Hotel"
  accountLabel: string;    // "Deposit into account" / "Pay from account"
  submitLabel: string;
  currentBalance?: string; // shown for context when available
  balanceLabel?: string;
  busy: boolean;
  error: ReturnType<typeof parseApiError> | null;
  onSubmit: (data: SettlementSubmit) => void;
  onClose: () => void;
}> = ({ title, partyLabel, accountLabel, submitLabel, currentBalance, balanceLabel, busy, error, onSubmit, onClose }) => {
  const money = useMoney();
  const [methodId, setMethodId] = useState<number | ''>('');
  const [accountId, setAccountId] = useState<number | ''>('');
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const methodsQ = useQuery(() => financeApi.listPaymentMethods({ page_size: 100 }), []);
  const accountsQ = useQuery(() => financeApi.listAccounts({ page_size: 200 }), []);

  const methods = (methodsQ.data?.results ?? []).filter((m: PaymentMethodRecord) => m.is_active && m.method_type !== 'credit');
  const accounts = accountsQ.data?.results ?? [];

  const selectedMethod = methods.find((m) => m.id === methodId);

  const compatibleAccounts = useMemo(() => {
    const active = accounts.filter((a: FinancialAccount) => a.is_active);
    if (!selectedMethod) return active;
    const allowed = COMPATIBLE_DESTINATIONS[selectedMethod.method_type as PaymentMethodType];
    if (!allowed) return active; // custom → any account
    return active.filter((a) => allowed.includes(a.account_type));
  }, [accounts, selectedMethod]);

  // Live balance per account, shown next to its name in the picker so a
  // cashier can see at a glance which treasury actually has funds — fetched
  // lazily per account (there's no bulk endpoint) and cached for the modal's
  // lifetime.
  const [balances, setBalances] = useState<Record<number, string>>({});
  useEffect(() => {
    const missing = compatibleAccounts.filter((a) => !(a.id in balances));
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.allSettled(missing.map((a) => financeApi.accountBalance(a.id)))
      .then((results) => {
        if (cancelled) return;
        setBalances((prev) => {
          const next = { ...prev };
          results.forEach((r, i) => {
            if (r.status === 'fulfilled') next[missing[i].id] = r.value.balance;
          });
          return next;
        });
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compatibleAccounts]);

  const handleSubmit = () => {
    const errs: Record<string, string> = {};
    if (!methodId) errs.payment_method = 'Select a payment method.';
    if (!accountId) errs.account = 'Select an account.';
    const amt = Number(amount);
    if (!amount || !Number.isFinite(amt) || amt <= 0) errs.amount = 'Enter an amount greater than zero.';
    setLocalErrors(errs);
    if (Object.keys(errs).length > 0) return;
    onSubmit({
      payment_method: Number(methodId),
      account: Number(accountId),
      amount: amt.toFixed(2),
      reference: reference.trim(),
      notes: notes.trim(),
    });
  };

  const fieldError = (name: string) =>
    localErrors[name] ?? error?.fieldErrors[name === 'account' ? 'destination_account' : name] ?? error?.fieldErrors[name === 'account' ? 'source_account' : name];

  const noMethods = !methodsQ.loading && methods.length === 0;

  return (
    <Modal title={title} onClose={busy ? () => undefined : onClose} maxWidth="max-w-[520px]">
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-md">
          <span className="text-[13px] font-semibold text-neutral-700 truncate">{partyLabel}</span>
          {currentBalance !== undefined && (
            <span className="text-[12.5px] text-neutral-500 whitespace-nowrap">
              {balanceLabel ?? 'Balance'} <b className="tabular-nums text-neutral-800">{money(currentBalance)}</b>
            </span>
          )}
        </div>

        {error && !error.permissionDenied && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone="danger">{error.message}</AlertBanner>
        )}
        {error?.permissionDenied && <AlertBanner tone="warn">{error.message}</AlertBanner>}

        {(methodsQ.error || accountsQ.error) && (
          <AlertBanner tone="danger">
            Failed to load payment configuration. {(methodsQ.error ?? accountsQ.error)?.message}
          </AlertBanner>
        )}
        {noMethods && !methodsQ.error && (
          <AlertBanner tone="warn" title="No payment methods configured">
            Ask an administrator to create payment methods under Finance → Payment methods before recording settlements.
          </AlertBanner>
        )}

        <SelectField
          label="Payment method"
          required
          value={methodId}
          error={fieldError('payment_method')}
          onChange={(e) => { setMethodId(e.target.value ? Number(e.target.value) : ''); setAccountId(''); }}
        >
          <option value="">{methodsQ.loading ? 'Loading…' : 'Select method'}</option>
          {methods.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.method_type})
            </option>
          ))}
        </SelectField>

        {selectedMethod && (
          <div className="flex items-center gap-2 text-[12px] text-neutral-500">
            <PaymentRouteLabel methodType={selectedMethod.method_type as PaymentMethodType} />
            <span>{routeHint(selectedMethod.method_type as PaymentMethodType)}</span>
          </div>
        )}

        <SelectField
          label={accountLabel}
          required
          value={accountId}
          error={fieldError('account')}
          onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : '')}
          hint={selectedMethod ? 'Only accounts compatible with the selected method are listed.' : undefined}
        >
          <option value="">{accountsQ.loading ? 'Loading…' : 'Select account'}</option>
          {compatibleAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.account_type.replace(/_/g, ' ')})
              {a.id in balances
                ? ` — ${a.currency ? a.currency + ' ' : ''}${Number(balances[a.id]).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : ''}
            </option>
          ))}
        </SelectField>
        {selectedMethod && compatibleAccounts.length === 0 && !accountsQ.loading && (
          <AlertBanner tone="warn">
            No active {COMPATIBLE_DESTINATIONS[selectedMethod.method_type as PaymentMethodType]?.join(' / ') ?? ''} account exists.
            Create one under Finance → Accounts first.
          </AlertBanner>
        )}

        <FormField
          label="Amount"
          required
          type="number"
          min="0.01"
          step="0.01"
          inputMode="decimal"
          value={amount}
          error={fieldError('amount')}
          onChange={(e) => setAmount(e.target.value)}
        />
        <FormField
          label="Reference"
          value={reference}
          maxLength={120}
          error={error?.fieldErrors.reference}
          onChange={(e) => setReference(e.target.value)}
          hint="Optional — receipt no., transfer ref., cheque no."
        />
        <TextAreaField
          label="Notes"
          value={notes}
          maxLength={255}
          error={error?.fieldErrors.notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <div className="px-6 py-4 border-t border-neutral-200 bg-neutral-50 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={busy || noMethods}>
          {busy ? 'Posting…' : submitLabel}
        </Button>
      </div>
    </Modal>
  );
};
