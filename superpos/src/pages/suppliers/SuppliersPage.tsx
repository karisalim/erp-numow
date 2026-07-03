import React, { useState } from 'react';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { SearchField } from '../../components/ui/FormField';
import { FilterBar, FilterChips } from '../../components/ui/FilterBar';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { PartyFormModal, type PartyFormValues } from '../../components/erp/PartyFormModal';
import { SupplierDrawer } from './SupplierDrawer';
import { suppliersApi } from '../../api/erp';
import { useQuery, useDebounced } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import type { Supplier, SupplierPayload } from '../../types/erp';

const PAGE_SIZE = 20;

type ActiveFilter = 'all' | 'active' | 'inactive';

export const SuppliersPage: React.FC = () => {
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounced(search);
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Supplier | null>(null);
  const [formOpen, setFormOpen] = useState<'create' | 'edit' | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const listQ = useQuery(
    () => suppliersApi.list({
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch || undefined,
      is_active: activeFilter === 'all' ? undefined : activeFilter === 'active' ? 'true' : 'false',
    }),
    [page, debouncedSearch, activeFilter],
  );

  const applyFilter = (fn: () => void) => { fn(); setPage(1); };

  const submitForm = async (values: PartyFormValues) => {
    setFormBusy(true);
    setFormError(null);
    const payload: SupplierPayload = {
      name: values.name,
      code: values.code,
      phone: values.phone,
      email: values.email,
      tax_number: values.tax_number,
    };
    if (formOpen === 'create' && values.opening_balance) {
      payload.opening_balance = values.opening_balance;
    }
    try {
      if (formOpen === 'edit' && selected) {
        const updated = await suppliersApi.update(selected.id, payload);
        setSelected(updated);
      } else {
        await suppliersApi.create(payload);
      }
      setFormOpen(null);
      listQ.refetch();
    } catch (err) {
      setFormError(parseApiError(err));
    } finally {
      setFormBusy(false);
    }
  };

  const columns: Column<Supplier>[] = [
    {
      key: 'name', header: 'Supplier',
      render: (s) => (
        <div>
          <div className="font-semibold">{s.name}</div>
          {s.code && <div className="text-[11.5px] text-neutral-400 font-mono">{s.code}</div>}
        </div>
      ),
    },
    { key: 'phone', header: 'Phone', render: (s) => <span className="text-neutral-600">{s.phone || '—'}</span> },
    { key: 'email', header: 'Email', className: 'hidden md:table-cell', render: (s) => <span className="text-neutral-600">{s.email || '—'}</span> },
    { key: 'tax', header: 'Tax no.', className: 'hidden lg:table-cell', render: (s) => <span className="text-neutral-600 font-mono text-[12.5px]">{s.tax_number || '—'}</span> },
    { key: 'status', header: 'Status', render: (s) => <ActiveBadge active={s.is_active} /> },
    { key: 'chev', header: '', render: () => <Icon name="chevR" size={15} className="text-neutral-300 rtl:rotate-180" /> },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Suppliers"
        subtitle="Accounts payable · supplier master data"
        right={
          <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
            <Icon name="plus" size={14} /> New supplier
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

        <DataTable<Supplier>
          columns={columns}
          rows={listQ.data?.results ?? []}
          rowKey={(s) => s.id}
          loading={listQ.loading}
          error={listQ.error}
          onRetry={listQ.refetch}
          emptyTitle={debouncedSearch ? 'No suppliers match your search' : 'No suppliers yet'}
          emptyHint={debouncedSearch ? 'Try a different name, code or phone number.' : 'Create your first supplier to record purchase invoices and AP.'}
          emptyIcon="box"
          emptyAction={
            !debouncedSearch ? (
              <Button size="sm" onClick={() => { setFormError(null); setFormOpen('create'); }}>
                <Icon name="plus" size={14} /> New supplier
              </Button>
            ) : undefined
          }
          onRowClick={(s) => setSelected(s)}
          page={page}
          pageSize={PAGE_SIZE}
          count={listQ.data?.count ?? 0}
          onPage={setPage}
        />
      </div>

      {selected && formOpen !== 'edit' && (
        <SupplierDrawer
          supplier={selected}
          onClose={() => setSelected(null)}
          onEdit={() => { setFormError(null); setFormOpen('edit'); }}
          onChanged={() => listQ.refetch()}
        />
      )}

      {formOpen && (
        <PartyFormModal
          title={formOpen === 'edit' ? `Edit ${selected?.name}` : 'New supplier'}
          kind="supplier"
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
