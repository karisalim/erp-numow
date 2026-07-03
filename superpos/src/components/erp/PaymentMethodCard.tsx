import React from 'react';
import { Icon } from '../ui/Icon';
import { PaymentRouteLabel } from './PaymentRouteLabel';
import type { PaymentMethodType } from '../../types/erp';

const METHOD_ICON: Record<PaymentMethodType, string> = {
  cash: 'cash',
  card: 'card',
  wallet: 'wallet',
  credit: 'user',
  custom: 'bank',
};

/**
 * Selectable payment-method tile (prototype payment modal): method name +
 * routing badge, blue outline when selected.
 */
export const PaymentMethodCard: React.FC<{
  methodType: PaymentMethodType;
  name: string;
  destination?: string;
  selected?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  onSelect?: () => void;
}> = ({ methodType, name, destination, selected, disabled, disabledReason, onSelect }) => (
  <button
    type="button"
    onClick={onSelect}
    disabled={disabled}
    title={disabled ? disabledReason : undefined}
    aria-pressed={selected}
    className={`text-start p-3 rounded-lg border-[1.5px] flex items-center gap-3 transition-colors focus-ring
      ${selected ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 bg-white hover:border-neutral-300'}
      ${disabled ? 'opacity-45 cursor-not-allowed' : ''}`}
  >
    <span className="text-neutral-700 shrink-0">
      <Icon name={METHOD_ICON[methodType] ?? 'bank'} size={20} />
    </span>
    <span className="min-w-0">
      <span className="block font-bold text-[13.5px] truncate">{name}</span>
      <span className="block mt-0.5">
        <PaymentRouteLabel methodType={methodType} destination={destination} />
      </span>
    </span>
  </button>
);
