import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FormField } from '../ui/FormField';
import { useMoney } from '../../utils/money';
import type { PosDiscountType } from '../../store/posStore';

/* ─────────────────────────────────────────────────────────────────────────────
 * Invoice-level discount (percent or fixed) — mirrors the backend Sale
 * contract exactly: percent applies to the pre-tax subtotal (≤ 100),
 * fixed subtracts from the invoice total. The backend recomputes and
 * validates the same rules on POST.
 * ──────────────────────────────────────────────────────────────────────────── */

export const DiscountModal: React.FC<{
  subtotal: number;
  currentType: PosDiscountType | null;
  currentValue: number;
  onApply: (type: PosDiscountType | null, value: number) => void;
  onClose: () => void;
}> = ({ subtotal, currentType, currentValue, onApply, onClose }) => {
  const money = useMoney();
  const [type, setType] = useState<PosDiscountType>(currentType ?? 'percent');
  const [value, setValue] = useState(currentValue > 0 ? String(currentValue) : '');
  const [error, setError] = useState<string | null>(null);

  const num = Number(value) || 0;
  const preview = type === 'percent' ? (subtotal * num) / 100 : num;

  const apply = () => {
    if (num <= 0) { setError('Enter a discount greater than zero, or remove the discount.'); return; }
    if (type === 'percent' && num > 100) { setError('Percent discount cannot exceed 100%.'); return; }
    if (type === 'fixed' && num > subtotal) { setError('Fixed discount cannot exceed the subtotal.'); return; }
    onApply(type, num);
    onClose();
  };

  return (
    <Modal title="Invoice discount" onClose={onClose} maxWidth="max-w-[420px]">
      <div className="p-5 space-y-4">
        <div className="inline-flex bg-neutral-100 rounded-lg p-[3px]">
          {(['percent', 'fixed'] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setType(t); setError(null); }}
              className={`h-8 px-4 rounded-md text-[13px] font-semibold transition-colors focus-ring
                ${type === t ? 'bg-white text-neutral-900 shadow-sm' : 'text-neutral-600'}`}
            >
              {t === 'percent' ? 'Percent %' : 'Fixed amount'}
            </button>
          ))}
        </div>

        <FormField
          label={type === 'percent' ? 'Discount %' : 'Discount amount'}
          type="number"
          min="0"
          max={type === 'percent' ? 100 : undefined}
          step={type === 'percent' ? '0.5' : '0.01'}
          inputMode="decimal"
          value={value}
          error={error ?? undefined}
          onChange={(e) => { setValue(e.target.value); setError(null); }}
          autoFocus
        />

        <div className="flex justify-between items-center px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-md text-[13px]">
          <span className="text-neutral-500">Discount preview</span>
          <span className="font-mono font-bold">−{money(preview)}</span>
        </div>
      </div>
      <div className="px-5 py-3.5 border-t border-neutral-200 bg-neutral-50 flex justify-between gap-2">
        <Button
          variant="ghost"
          onClick={() => { onApply(null, 0); onClose(); }}
          disabled={!currentType}
        >
          Remove discount
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={apply}>Apply</Button>
        </div>
      </div>
    </Modal>
  );
};
