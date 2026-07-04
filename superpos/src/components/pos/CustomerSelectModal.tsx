import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { SearchField } from '../ui/FormField';
import { LoadingState, EmptyState, QueryErrorState } from '../ui/states';
import { customersApi } from '../../api/erp';
import { useQuery, useDebounced } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import type { PosCustomer } from '../../store/posStore';

/* ─────────────────────────────────────────────────────────────────────────────
 * POS customer selector (DESIGN v3.6 §5.4). Default is Walk-in; selecting
 * a customer enables credit payment. Reads /api/customers/ (Cashier+).
 * ──────────────────────────────────────────────────────────────────────────── */

export const CustomerSelectModal: React.FC<{
  current: PosCustomer | null;
  onSelect: (customer: PosCustomer | null) => void;
  onClose: () => void;
}> = ({ current, onSelect, onClose }) => {
  const money = useMoney();
  const [search, setSearch] = useState('');
  const debounced = useDebounced(search, 300);

  const listQ = useQuery(
    () => customersApi.list({ is_active: 'true', page_size: 20, search: debounced || undefined }),
    [debounced],
  );

  return (
    <Modal title="Select customer" onClose={onClose} maxWidth="max-w-[480px]">
      <div className="p-5">
        <SearchField
          value={search}
          onChange={setSearch}
          placeholder="Search name, code, phone…"
          autoFocus
        />
        <button
          onClick={() => { onSelect(null); onClose(); }}
          className={`mt-3 w-full text-start px-3.5 py-2.5 rounded-lg border-[1.5px] flex items-center gap-3 focus-ring
            ${current === null ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 hover:border-neutral-300'}`}
        >
          <span className="w-8 h-8 rounded-full bg-neutral-200 grid place-items-center text-neutral-500 shrink-0">
            <Icon name="user" size={16} />
          </span>
          <span>
            <span className="block font-bold text-[13.5px]">Walk-in</span>
            <span className="block text-[11.5px] text-neutral-400">No customer account · cash-equivalent methods only</span>
          </span>
        </button>

        <div className="mt-2 max-h-[300px] overflow-y-auto flex flex-col gap-1.5">
          {listQ.loading ? (
            <LoadingState label="Searching customers…" />
          ) : listQ.error ? (
            <QueryErrorState error={listQ.error} onRetry={listQ.refetch} />
          ) : (listQ.data?.results ?? []).length === 0 ? (
            <EmptyState
              title="No customers found"
              hint={debounced ? 'Try a different search.' : 'Customers are created under the Customers screen by a manager.'}
              icon="users"
            />
          ) : (
            (listQ.data?.results ?? []).map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  onSelect({ id: c.id, name: c.name, credit_limit: c.credit_limit });
                  onClose();
                }}
                className={`w-full text-start px-3.5 py-2.5 rounded-lg border-[1.5px] flex items-center justify-between gap-3 focus-ring
                  ${current?.id === c.id ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 hover:border-neutral-300'}`}
              >
                <span className="min-w-0">
                  <span className="block font-bold text-[13.5px] truncate">{c.name}</span>
                  <span className="block text-[11.5px] text-neutral-400 truncate">
                    {c.phone || c.code || `#${c.id}`}
                  </span>
                </span>
                <span className="text-[11.5px] text-neutral-500 whitespace-nowrap">
                  {Number(c.credit_limit) > 0 ? <>Limit {money(c.credit_limit)}</> : 'No credit limit'}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
      <div className="px-5 py-3.5 border-t border-neutral-200 bg-neutral-50 flex justify-end">
        <Button variant="secondary" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  );
};
