import React from 'react';
import { Badge } from '../ui/Badge';
import type { BadgeKind } from '../../types';
import type { PaymentMethodType } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Payment routing clarity (DESIGN v3.6 §5.6): every payment method shows
 * where the money actually goes. Colors follow the prototype payment modal:
 * cash → green, card → cyan, wallet → violet, credit → amber.
 * ──────────────────────────────────────────────────────────────────────────── */

export const ROUTE_BADGE: Record<PaymentMethodType, { kind: BadgeKind; fallbackDest: string }> = {
  cash:   { kind: 'success', fallbackDest: 'Cashbox / Drawer' },
  card:   { kind: 'info',    fallbackDest: 'Card Settlement' },
  wallet: { kind: 'violet',  fallbackDest: 'Wallet Account' },
  credit: { kind: 'warn',    fallbackDest: 'Customer Balance' },
  custom: { kind: 'gray',    fallbackDest: 'Configured account' },
};

/** "→ <destination account>" badge. */
export const PaymentRouteLabel: React.FC<{
  methodType: PaymentMethodType;
  /** Actual configured destination account name; falls back to the v3.6 contract label. */
  destination?: string;
}> = ({ methodType, destination }) => {
  const cfg = ROUTE_BADGE[methodType] ?? ROUTE_BADGE.custom;
  return <Badge kind={cfg.kind}>→ {destination || cfg.fallbackDest}</Badge>;
};

/** Cashier-facing hint explaining the money destination (prototype payment modal). */
export function routeHint(methodType: PaymentMethodType): string {
  switch (methodType) {
    case 'cash':   return 'Cash increases the cashbox / drawer balance.';
    case 'card':   return 'Card routes to Card Settlement — it does NOT enter the cashbox.';
    case 'wallet': return 'Wallet routes to the Wallet Account, not the cashbox.';
    case 'credit': return 'Credit is not money received now — it increases the customer balance.';
    default:       return 'Routed to the configured destination account.';
  }
}
