import React from 'react';
import { useMoney } from '../../utils/money';

/**
 * Current-balance summary card for a party (AR/AP) or financial account.
 * Shows opening balance + derived current balance from the backend
 * balance endpoints — never computed client-side.
 */
export const BalanceCard: React.FC<{
  label: string;
  balance: string | number;
  openingBalance?: string | number;
  /** Tone of the main figure: AR debt = warn when > 0, etc. */
  emphasize?: 'neutral' | 'positive' | 'negative';
  hint?: string;
  className?: string;
}> = ({ label, balance, openingBalance, emphasize = 'neutral', hint, className = '' }) => {
  const money = useMoney();
  const toneClass =
    emphasize === 'positive' ? 'text-success-600'
    : emphasize === 'negative' ? 'text-danger-600'
    : 'text-neutral-900';
  return (
    <div className={`bg-white border border-neutral-200 rounded-lg shadow-sm p-4 ${className}`}>
      <div className="text-[12px] text-neutral-500 font-semibold">{label}</div>
      <div className={`text-[24px] font-extrabold tracking-tight mt-1.5 tabular-nums ${toneClass}`}>
        {money(balance)}
      </div>
      {openingBalance !== undefined && (
        <div className="text-[11.5px] text-neutral-400 mt-0.5">
          Opening balance {money(openingBalance)}
        </div>
      )}
      {hint && <div className="text-[11.5px] text-neutral-500 mt-1">{hint}</div>}
    </div>
  );
};
