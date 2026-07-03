import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Tabs } from '../../components/ui/Tabs';
import { AccountsTab } from './AccountsTab';
import { PaymentMethodsTab } from './PaymentMethodsTab';
import { BranchRoutingTab } from './BranchRoutingTab';
import { SettlementsTab } from './SettlementsTab';

/* ─────────────────────────────────────────────────────────────────────────────
 * Treasury / Finance hub: financial accounts (+balances/movements),
 * tenant payment methods, per-branch payment routing, and posted
 * settlement documents. All backed by verified /api/finance/,
 * /api/branches/{id}/payment-methods/ and settlement endpoints.
 * ──────────────────────────────────────────────────────────────────────────── */

type FinanceTab = 'accounts' | 'methods' | 'routing' | 'settlements';

export const FinancePage: React.FC = () => {
  const [tab, setTab] = useState<FinanceTab>('accounts');

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="Treasury / Finance" subtitle="Cashbox · Card settlement · Wallet · Payment routing" />
      <div className="p-5 max-w-[1180px] w-full mx-auto">
        <Tabs
          className="mb-4"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'accounts', label: 'Accounts' },
            { value: 'methods', label: 'Payment methods' },
            { value: 'routing', label: 'Branch routing' },
            { value: 'settlements', label: 'Settlements' },
          ]}
        />
        {tab === 'accounts' && <AccountsTab />}
        {tab === 'methods' && <PaymentMethodsTab />}
        {tab === 'routing' && <BranchRoutingTab />}
        {tab === 'settlements' && <SettlementsTab />}
      </div>
    </div>
  );
};
