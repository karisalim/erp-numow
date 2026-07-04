import React, { useState, useEffect, useMemo } from 'react';
import type { PaymentMethod } from '../../types';
import type { PosCustomer, PosPaymentMode } from '../../store/posStore';
import { useMoney } from '../../utils/money';
import { useQuery } from '../../hooks/useQuery';
import { financeApi } from '../../api/erp';
import { useAuthStore } from '../../store/authStore';
import { Icon } from '../ui/Icon';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Keypad } from '../ui/Keypad';
import { AlertBanner } from '../ui/states';
import { PaymentMethodCard } from '../erp/PaymentMethodCard';
import { routeHint, ROUTE_BADGE } from '../erp/PaymentRouteLabel';
import type { BranchPaymentMethod, PaymentMethodType } from '../../types/erp';

export type PaymentModalMode = Exclude<PosPaymentMode, null>;

interface PaymentModalProps {
  mode: PaymentModalMode;
  setMode: (mode: PosPaymentMode) => void;
  total: number;
  customer: PosCustomer | null;
  onComplete: (method: PaymentMethod, paid: number, change: number) => void;
  /** Close payment and open the customer selector (credit needs a customer). */
  onSelectCustomer: () => void;
  online: boolean;
}

/** The four canonical v3.6 sale methods, in prototype order. */
const CANONICAL: { id: PaymentMethod; label: string }[] = [
  { id: 'cash',   label: 'Cash' },
  { id: 'card',   label: 'Card / Visa' },
  { id: 'wallet', label: 'Wallet' },
  { id: 'credit', label: 'Credit' },
];

interface MethodOption {
  id: PaymentMethod;
  label: string;
  destination?: string;      // configured destination account name
  enabled: boolean;
  disabledReason?: string;
}

export const PaymentModal: React.FC<PaymentModalProps> = ({
  mode,
  setMode,
  total,
  customer,
  onComplete,
  onSelectCustomer,
  online,
}) => {
  const money = useMoney();
  const branchId = useAuthStore((s) => s.user?.branch);
  const [cash, setCash] = useState('');
  const cashNum = parseFloat(cash || '0');
  const change = cashNum - total;

  // ── Verified payment configuration ────────────────────────────────────────
  // Tenant methods are Cashier-readable; branch routing is Manager+ — a 403
  // there is expected for cashiers and we fall back to the tenant method
  // list with the canonical v3.6 destination labels. The backend remains
  // authoritative: a genuinely misconfigured route fails the sale POST with
  // a clear error, it is never silently absorbed here.
  const methodsQ = useQuery(() => financeApi.listPaymentMethods({ page_size: 100 }), []);
  const routingQ = useQuery(
    () =>
      branchId
        ? financeApi.listBranchPaymentMethods(branchId).catch(() => null as BranchPaymentMethod[] | null)
        : Promise.resolve(null as BranchPaymentMethod[] | null),
    [branchId],
  );

  const options = useMemo<MethodOption[]>(() => {
    const tenantMethods = (methodsQ.data?.results ?? []).filter((m) => m.is_active);
    const routing = (routingQ.data ?? []).filter((r) => r.is_active);

    return CANONICAL.map(({ id, label }) => {
      const route = routing.find((r) => r.payment_method_type === id);
      const tenantHas = tenantMethods.some((m) => m.method_type === id);

      let enabled: boolean;
      let disabledReason: string | undefined;
      if (routing.length > 0) {
        // Branch routing is configured and readable → it is the truth.
        enabled = Boolean(route);
        if (!enabled) disabledReason = 'Not enabled for this branch.';
      } else if (tenantMethods.length > 0) {
        // No readable routing — fall back to tenant method catalog.
        enabled = tenantHas;
        if (!enabled) disabledReason = 'No active payment method of this type is configured.';
      } else {
        // Legacy tenant with no configured methods: allow all four; the
        // backend posts without ledger routing (with a warning).
        enabled = true;
      }

      if (id === 'credit' && enabled && !customer) {
        enabled = false;
        disabledReason = 'Select a customer first — credit increases their balance.';
      }

      return { id, label, destination: route?.destination_account_name, enabled, disabledReason };
    });
  }, [methodsQ.data, routingQ.data, customer]);

  const currentOption = options.find((o) => o.id === mode);

  // Equivalent of <input max="999999"> — stops a 13-digit barcode scan from
  // landing in the cash field and breaking the layout / paid validation.
  const CASH_MAX = 999999;

  const press = (k: string) => {
    if (k === 'C') setCash('');
    else if (k === '⌫') setCash(c => c.slice(0, -1));
    else if (k === '.') { if (!cash.includes('.')) setCash(c => (c || '0') + '.'); }
    else setCash(c => {
      const next = (c + k).replace(/^0+(\d)/, '$1');
      return parseFloat(next || '0') > CASH_MAX ? c : next;
    });
  };

  const quickAmounts = [total, Math.ceil(total / 5) * 5, Math.ceil(total / 10) * 10, Math.ceil(total / 20) * 20]
    .filter((v, i, a) => a.indexOf(v) === i);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMode(null);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [setMode]);

  const routeBadgeFor = (m: PaymentMethod, destination?: string) => {
    const cfg = ROUTE_BADGE[m as PaymentMethodType];
    return <Badge kind={cfg.kind}>→ {destination || cfg.fallbackDest}</Badge>;
  };

  return (
    <div className="fixed inset-0 z-[1100] bg-black/50 backdrop-blur-sm grid place-items-center p-6 fade-in">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-[820px] overflow-hidden max-h-[94vh] overflow-y-auto">
        {/* Header */}
        <div className="px-6 h-14 border-b border-neutral-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-[16px] font-semibold">
              {mode === 'choose' && 'Select payment method'}
              {mode === 'cash' && 'Cash payment'}
              {mode === 'card' && 'Card payment'}
              {mode === 'wallet' && 'Wallet payment'}
              {mode === 'credit' && 'Credit sale'}
            </h2>
            {!online && <Badge kind="warn">Offline — the sale cannot be posted</Badge>}
          </div>
          <button
            onClick={() => setMode(null)}
            className="w-9 h-9 grid place-items-center rounded-md hover:bg-neutral-100 text-neutral-500 focus-ring"
            aria-label="Close payment modal"
          >
            <Icon name="x" size={18} />
          </button>
        </div>

        {/* Choose method */}
        {mode === 'choose' && (
          <div className="p-6">
            <div className="bg-neutral-900 text-white rounded-xl px-5 py-4 mb-5 flex items-center justify-between">
              <div>
                <div className="text-[12px] opacity-70">Amount due</div>
                {customer && (
                  <div className="text-[11.5px] opacity-70 mt-0.5">Customer: {customer.name}</div>
                )}
              </div>
              <div className="font-mono text-[32px] font-extrabold tabular-nums">{money(total)}</div>
            </div>

            {methodsQ.loading || routingQ.loading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {CANONICAL.map((m) => (
                  <div key={m.id} className="h-[64px] rounded-lg border-[1.5px] border-neutral-200 bg-neutral-50 animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {options.map((o) => (
                  <PaymentMethodCard
                    key={o.id}
                    methodType={o.id as PaymentMethodType}
                    name={o.label}
                    destination={o.destination}
                    disabled={!o.enabled}
                    disabledReason={o.disabledReason}
                    onSelect={() => o.enabled && setMode(o.id)}
                  />
                ))}
              </div>
            )}

            {/* Credit needs a customer — offer the shortcut instead of a dead tile. */}
            {!customer && options.find((o) => o.id === 'credit' && o.disabledReason?.startsWith('Select a customer')) && (
              <button
                onClick={onSelectCustomer}
                className="mt-3 w-full text-start px-3.5 py-2.5 rounded-lg bg-warn-50 border border-warn-500/30 text-warn-700 text-[12.5px] font-semibold flex items-center gap-2 focus-ring"
              >
                <Icon name="user" size={15} /> Credit requires a customer — tap to select one.
              </button>
            )}

            {methodsQ.error && (
              <AlertBanner tone="warn" className="mt-3">
                Could not load the configured payment methods ({methodsQ.error.message}). The canonical
                methods are shown; the backend will still reject anything not allowed.
              </AlertBanner>
            )}

            <p className="text-center text-[11.5px] text-neutral-500 mt-5">
              <kbd className="px-1.5 py-0.5 rounded border border-neutral-300 bg-neutral-50 font-mono">Esc</kbd> to cancel
            </p>
          </div>
        )}

        {/* Cash payment */}
        {mode === 'cash' && (
          <div className="grid grid-cols-1 md:grid-cols-2">
            <div className="p-6 border-e border-neutral-200">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Amount due</div>
                  <div className="font-mono text-[40px] font-bold tabular-nums leading-none mt-1">{money(total)}</div>
                </div>
                {routeBadgeFor('cash', currentOption?.destination)}
              </div>
              <div className="mt-6">
                <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">Cash received</div>
                <div className="h-16 px-4 rounded-lg border-2 border-brand-500 bg-white flex items-center justify-end font-mono text-[32px] font-bold tabular-nums">
                  {cash || '0'}
                  <span className="caret" aria-hidden />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 mt-4">
                {quickAmounts.map(v => (
                  <button
                    key={v}
                    onClick={() => setCash(v.toFixed(2))}
                    className="h-11 rounded-md border border-neutral-300 bg-white text-[14px] font-semibold hover:border-brand-500 hover:bg-brand-50 focus-ring"
                  >
                    {money(v)}
                  </button>
                ))}
              </div>
              <div className={`mt-5 rounded-lg p-4 ${cashNum >= total ? 'bg-success-50 border border-success-500/30' : 'bg-neutral-50 border border-neutral-200'}`}>
                <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Change</div>
                <div className={`font-mono text-[36px] font-bold tabular-nums leading-none mt-1 ${cashNum >= total ? 'text-success-700' : 'text-neutral-400'}`}>
                  {cashNum >= total ? money(change) : '—'}
                </div>
              </div>
            </div>
            <div className="p-6 flex flex-col">
              <Keypad onPress={press} />
              <div className="mt-4 flex gap-2">
                <Button variant="secondary" size="lg" className="flex-1" onClick={() => setMode('choose')}>
                  Back
                </Button>
                <Button
                  variant="success"
                  size="lg"
                  className="flex-[2]"
                  disabled={cashNum < total}
                  onClick={() => onComplete('cash', cashNum, change)}
                >
                  <Icon name="check" size={18} /> Confirm · {money(total)}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Card / Wallet payment — recorded manually.
            There is NO terminal or wallet-gateway integration in this version:
            the cashier takes the payment on the external device, then confirms
            here so the sale is recorded with the correct method. Never present
            this step as an automated authorization. */}
        {(mode === 'card' || mode === 'wallet') && (
          <div className="p-10 text-center">
            <div className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Amount due</div>
            <div className="font-mono text-[40px] font-bold tabular-nums">{money(total)}</div>
            <div className="mt-3 flex items-center justify-center gap-2">
              {routeBadgeFor(mode, currentOption?.destination)}
            </div>
            <p className="text-[12px] text-neutral-500 mt-1">{routeHint(mode as PaymentMethodType)}</p>

            <div className="my-7 grid place-items-center">
              <div className="w-24 h-24 rounded-full bg-brand-50 text-brand-600 grid place-items-center">
                <Icon name={mode === 'card' ? 'card' : 'wallet'} size={40} />
              </div>
            </div>

            <div className="text-[16px] font-semibold">
              {mode === 'card'
                ? 'Take the payment on your card terminal'
                : 'Collect the payment via the customer’s wallet'}
            </div>
            <div className="text-[13px] text-neutral-500 mt-1 max-w-[420px] mx-auto">
              This system is not connected to the {mode === 'card' ? 'terminal' : 'wallet provider'}.
              Confirm below only after the payment has been approved on the external device.
            </div>

            <div className="mt-8 flex gap-2 justify-center">
              <Button size="lg" variant="secondary" onClick={() => setMode('choose')}>
                Back
              </Button>
              <Button size="lg" variant="success" onClick={() => onComplete(mode, total, 0)}>
                <Icon name="check" size={18} /> Payment received · record {mode}
              </Button>
            </div>
          </div>
        )}

        {/* Credit sale — customer pays later; increases their AR balance. */}
        {mode === 'credit' && customer && (
          <div className="p-8">
            <div className="text-center">
              <div className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Credit amount</div>
              <div className="font-mono text-[40px] font-bold tabular-nums">{money(total)}</div>
              <div className="mt-3 flex items-center justify-center">
                {routeBadgeFor('credit', currentOption?.destination)}
              </div>
            </div>

            <div className="mt-6 max-w-[440px] mx-auto space-y-3">
              <AlertBanner tone="warn" title="No money is received now">
                This will increase <b>{customer.name}</b>'s balance by <b>{money(total)}</b>.
                The customer pays later via a customer receipt.
              </AlertBanner>
              {Number(customer.credit_limit) > 0 && (
                <div className="text-[12.5px] text-neutral-500 text-center">
                  Credit limit: {money(customer.credit_limit)} — the backend blocks the sale if this
                  would be exceeded.
                </div>
              )}
            </div>

            <div className="mt-8 flex gap-2 justify-center">
              <Button size="lg" variant="secondary" onClick={() => setMode('choose')}>
                Back
              </Button>
              <Button size="lg" variant="success" onClick={() => onComplete('credit', 0, 0)}>
                <Icon name="check" size={18} /> Post credit sale
              </Button>
            </div>
          </div>
        )}

        {/* Credit picked but customer vanished (deselected) — guard rail. */}
        {mode === 'credit' && !customer && (
          <div className="p-10 text-center space-y-4">
            <AlertBanner tone="warn">A customer is required for a credit sale.</AlertBanner>
            <Button variant="secondary" onClick={onSelectCustomer}>
              <Icon name="user" size={15} /> Select customer
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
