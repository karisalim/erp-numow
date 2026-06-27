import React, { useState, useEffect } from 'react';
import type { CardStage, PaymentMethod } from '../../types';
import { useMoney } from '../../utils/money';
import { Icon } from '../ui/Icon';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Keypad } from '../ui/Keypad';

interface PaymentModalProps {
  mode: 'choose' | 'cash' | 'card';
  setMode: (mode: 'choose' | 'cash' | 'card' | null) => void;
  total: number;
  onComplete: (method: PaymentMethod, paid: number, change: number) => void;
  online: boolean;
}

export const PaymentModal: React.FC<PaymentModalProps> = ({
  mode,
  setMode,
  total,
  onComplete,
  online,
}) => {
  const money = useMoney();
  const [cash, setCash] = useState('');
  const [cardStage, setCardStage] = useState<CardStage>('waiting');
  const cashNum = parseFloat(cash || '0');
  const change = cashNum - total;

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
    if (mode === 'card') {
      setCardStage('waiting');
      const t1 = setTimeout(() => setCardStage('processing'), 1500);
      const t2 = setTimeout(() => setCardStage('success'), 3800);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  }, [mode]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMode(null);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [setMode]);

  return (
    <div className="fixed inset-0 z-[1100] bg-black/50 backdrop-blur-sm grid place-items-center p-6 fade-in">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-[820px] overflow-hidden">
        {/* Header */}
        <div className="px-6 h-14 border-b border-neutral-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-[16px] font-semibold">
              {mode === 'choose' && 'Select payment method'}
              {mode === 'cash' && 'Cash payment'}
              {mode === 'card' && 'Card payment'}
            </h2>
            {!online && mode === 'card' && <Badge kind="warn">Offline — card disabled</Badge>}
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
            <div className="text-center mb-6">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Total due</div>
              <div className="font-mono text-[44px] font-bold tabular-nums leading-none mt-1">{money(total)}</div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[
                { id: 'cash',   label: 'Cash',   icon: 'cash',   desc: 'Counter receipt',           enabled: true   },
                { id: 'card',   label: 'Card',   icon: 'card',   desc: 'Tap / chip / swipe',        enabled: online },
                { id: 'wallet', label: 'Wallet', icon: 'wallet', desc: 'QR code · Vodafone Cash',   enabled: online },
              ].map(m => (
                <button
                  key={m.id}
                  disabled={!m.enabled}
                  onClick={() => setMode(m.id === 'wallet' ? 'card' : m.id as 'cash' | 'card')}
                  className="border-2 border-neutral-200 rounded-lg p-5 text-start hover:border-brand-500 hover:bg-brand-50 transition-colors disabled:opacity-50 disabled:hover:border-neutral-200 disabled:hover:bg-white disabled:cursor-not-allowed focus-ring"
                >
                  <div className="w-10 h-10 rounded-md bg-brand-50 text-brand-600 grid place-items-center mb-3">
                    <Icon name={m.icon} size={22} />
                  </div>
                  <div className="text-[15px] font-semibold">{m.label}</div>
                  <div className="text-[12px] text-neutral-500 mt-0.5">{m.desc}</div>
                  {!m.enabled && (
                    <div className="mt-2 text-[11px] font-semibold text-warn-700">Requires online</div>
                  )}
                </button>
              ))}
            </div>
            <p className="text-center text-[11.5px] text-neutral-500 mt-5">
              <kbd className="px-1.5 py-0.5 rounded border border-neutral-300 bg-neutral-50 font-mono">Esc</kbd> to cancel
            </p>
          </div>
        )}

        {/* Cash payment */}
        {mode === 'cash' && (
          <div className="grid grid-cols-2">
            <div className="p-6 border-e border-neutral-200">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Amount due</div>
              <div className="font-mono text-[40px] font-bold tabular-nums leading-none mt-1">{money(total)}</div>
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

        {/* Card payment */}
        {mode === 'card' && (
          <div className="p-10 text-center">
            <div className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Amount</div>
            <div className="font-mono text-[40px] font-bold tabular-nums">{money(total)}</div>

            <div className="my-8 relative h-40 grid place-items-center">
              {cardStage === 'waiting' && (
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-brand-500/30 pulse-ring" />
                  <div className="relative w-24 h-24 rounded-full bg-brand-500 grid place-items-center text-white shadow-lg">
                    <Icon name="card" size={36} />
                  </div>
                </div>
              )}
              {cardStage === 'processing' && (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-16 h-16 border-4 border-brand-100 border-t-brand-500 rounded-full spin" />
                </div>
              )}
              {cardStage === 'success' && (
                <div className="flex flex-col items-center gap-2 fade-in">
                  <div className="w-24 h-24 rounded-full bg-success-500 grid place-items-center text-white shadow-lg">
                    <Icon name="check" size={48} />
                  </div>
                </div>
              )}
            </div>

            <div className="text-[16px] font-semibold">
              {cardStage === 'waiting' && 'Insert, tap, or swipe card'}
              {cardStage === 'processing' && 'Contacting payment processor…'}
              {cardStage === 'success' && 'Approved · Visa ending 4242'}
            </div>
            <div className="text-[13px] text-neutral-500 mt-1">
              {cardStage === 'waiting' && 'Connected to terminal · PAX A920'}
              {cardStage === 'processing' && 'Authorization in progress'}
              {cardStage === 'success' && <>Authorization #A8392 · {new Date().toLocaleTimeString()}</>}
            </div>

            <div className="mt-8 flex gap-2 justify-center">
              {cardStage === 'success' ? (
                <Button size="lg" variant="success" onClick={() => onComplete('card', total, 0)}>
                  Continue to receipt <Icon name="chevR" size={16} />
                </Button>
              ) : (
                <Button size="lg" variant="secondary" onClick={() => setMode('choose')}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
