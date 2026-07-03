import type { AccountType } from '../../types/erp';
import type { BadgeKind } from '../../types';

/** Display metadata for FinancialAccount.account_type (backend enum). */
export const ACCOUNT_TYPES: Record<AccountType, { label: string; badge: BadgeKind }> = {
  cashbox:         { label: 'Cashbox',         badge: 'success' },
  main_safe:       { label: 'Main Safe',       badge: 'gray' },
  bank:            { label: 'Bank',            badge: 'brand' },
  card_settlement: { label: 'Card Settlement', badge: 'info' },
  wallet:          { label: 'Wallet',          badge: 'violet' },
  customer_ar:     { label: 'Customer AR',     badge: 'warn' },
  supplier_ap:     { label: 'Supplier AP',     badge: 'warn' },
  expense:         { label: 'Expense',         badge: 'danger' },
  opening_balance: { label: 'Opening Balance', badge: 'gray' },
  other:           { label: 'Other',           badge: 'gray' },
};

export const accountTypeLabel = (t: string): string =>
  ACCOUNT_TYPES[t as AccountType]?.label ?? t.replace(/_/g, ' ');

export const accountTypeBadge = (t: string): BadgeKind =>
  ACCOUNT_TYPES[t as AccountType]?.badge ?? 'gray';
