import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { SearchField } from '../../components/ui/FormField';
import { FilterBar, FilterChips } from '../../components/ui/FilterBar';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { PartyFormModal, type PartyFormValues } from '../../components/erp/PartyFormModal';
import { CustomerDrawer } from './CustomerDrawer';
import { customersApi } from '../../api/erp';
import { useQuery, useDebounced } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import type { Customer, CustomerPayload } from '../../types/erp';

const PAGE_SIZE = 20;

type ActiveFilter = 'all' | 'active' | 'inactive';

export const CustomersPage: React.FC = () => {
  const money = useMoney();
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounced(search);
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Customer | null>(null);
  const [formOpen, setFormOpen] = useState<'create' | 'edit' | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const listQ = useQuery(
    () => customersApi.list({
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch || undefined,
      is_active: activeFilter === 'all' ? undefined : activeFilter === 'active' ? 'true' : 'false',
    }),
    [page, debouncedSearch, activeFilter],
  );

  // Snap back to page 1 when filters change.
  const applyFilter = (fn: () => void) => { fn(); setPage(1); };

  const submitForm = async (values: PartyFormValues) => {
    setFormBusy(true);
    setFormError(null);
    const payload: CustomerPayload = {
      name: values.name,
      code: values.code,
      phone: values.phone,
      email: values.email,
      tax_number: values.tax_number,
      credit_limit: values.credit_limit || '0',
    };
    if (formOpen === 'create' && values.opening_balance) {
      payload.opening_balance = values.opening_balance;
    }
    try {
      if (formOpen === 'edit' && selected) {
        const updated = await customersApi.update(selected.id, payload);
        setSelected(updated);
      } else {
        await customersApi.create(payload);
      }
      setFormOpen(null);
      listQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setFormBusy(false);
    }
  };

  const columns: Column<Customer>[] = [
    {
      key: 'name', header: 'Customer',
      render: (c) => (
        <div>
          <div className="font-semibold">{c.name}</div>
          {c.code && <div className="text-[11.5px] text-neutral-400 font-mono">{c.code}</div>}
        </div>
      ),
    },
    { key: 'phone', header: 'Phone', render: (c) => <span className="text-neutral-600">{c.phone || '—'}</span> },
    { key: 'email', header: 'Email', className: 'hidden md:table-cell', render: (c) => <span className="text-neutral-600">{c.email || '—'}</span> },
    {
      key: 'credit', header: 'Credit limit', align: 'end', mono: true,
      render: (c) => (Number(c.credit_limit) > 0 ? money(c.credit_limit) : <span className="text-neutral-400">None</span>),
    },
    { key: 'status', header: 'Status', render: (c) => <ActiveBadge active={c.is_active} /> },
    { key: 'chev', header: '', render: () => <Icon name="chevR" size={15} className="text-neutral-300 rtl:rotate-180" /> },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Customers"
        subtitle="Accounts receivable · customer master data"
        right={
          <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
            <Icon name="plus" size={14} /> New customer
          </Button>
        }
      />
      <div className="p-5 max-w-[1180px] w-full mx-auto">
        <FilterBar>
          <SearchField
            value={search}
            onChange={(v) => applyFilter(() => setSearch(v))}
            placeholder="Search name, code, phone, email…"
            className="w-full sm:w-80"
          />
          <FilterChips<ActiveFilter>
            value={activeFilter}
            onChange={(v) => applyFilter(() => setActiveFilter(v))}
            options={[
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
              { value: 'all', label: 'All' },
            ]}
          />
        </FilterBar>

        <DataTable<Customer>
          columns={columns}
          rows={listQ.data?.results ?? []}
          rowKey={(c) => c.id}
          loading={listQ.loading}
          error={listQ.error}
          onRetry={listQ.refetch}
          emptyTitle={debouncedSearch ? 'No customers match your search' : 'No customers yet'}
          emptyHint={debouncedSearch ? 'Try a different name, code or phone number.' : 'Create your first customer to enable credit sales and AR tracking.'}
          emptyIcon="users"
          emptyAction={
            !debouncedSearch ? (
              <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
                <Icon name="plus" size={14} /> New customer
              </Button>
            ) : undefined
          }
          onRowClick={(c) => setSelected(c)}
          page={page}
          pageSize={PAGE_SIZE}
          count={listQ.data?.count ?? 0}
          onPage={setPage}
        />
      </div>

      {selected && formOpen !== 'edit' && (
        <CustomerDrawer
          customer={selected}
          onClose={() => setSelected(null)}
          onEdit={() => { setFormError(null); setFormOpen('edit'); }}
          onChanged={() => listQ.refetch()}
        />
      )}

      {formOpen && (
        <PartyFormModal
          title={formOpen === 'edit' ? `Edit ${selected?.name}` : 'New customer'}
          kind="customer"
          isEdit={formOpen === 'edit'}
          initial={formOpen === 'edit' && selected ? selected : undefined}
          busy={formBusy}
          error={formError}
          onSubmit={submitForm}
          onClose={() => setFormOpen(null)}
        />
      )}
    </div>
  );
};
