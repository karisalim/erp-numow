import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { purchasesApi } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import type { PurchaseInvoice } from '../../types/erp';

const PAGE_SIZE = 20;

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export const PurchasesPage: React.FC = () => {
  const money = useMoney();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const listQ = useQuery(() => purchasesApi.list({ page, page_size: PAGE_SIZE }), [page]);

  const columns: Column<PurchaseInvoice>[] = [
    {
      key: 'doc', header: 'Purchase',
      render: (p) => (
        <div>
          <div className="font-mono font-bold">PUR-{p.id}</div>
          {p.reference && <div className="text-[11.5px] text-neutral-400">{p.reference}</div>}
        </div>
      ),
    },
    { key: 'supplier', header: 'Supplier', render: (p) => <span className="font-semibold">{p.supplier_name}</span> },
    { key: 'branch', header: 'Branch', className: 'hidden md:table-cell', render: (p) => <span className="text-neutral-600">{p.branch_name}</span> },
    { key: 'date', header: 'Date', render: (p) => <span className="text-neutral-500">{fmtDate(p.posted_at ?? p.created_at)}</span> },
    { key: 'total', header: 'Total', align: 'end', mono: true, className: 'font-semibold', render: (p) => money(p.total_amount) },
    { key: 'posting', header: 'Posting', render: (p) => <StatusBadge domain="posting" value={p.posting_status} /> },
    { key: 'payment', header: 'Payment', render: (p) => <StatusBadge domain="payment" value={p.payment_status} /> },
    { key: 'chev', header: '', render: () => <Icon name="chevR" size={15} className="text-neutral-300 rtl:rotate-180" /> },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Purchases"
        subtitle="Stock purchase invoices · accounts payable"
        right={
          <Button size="sm" onClick={() => navigate('/purchases/new')}>
            <Icon name="plus" size={14} /> New purchase
          </Button>
        }
      />
      <div className="p-5 max-w-[1180px] w-full mx-auto">
        <DataTable<PurchaseInvoice>
          columns={columns}
          rows={listQ.data?.results ?? []}
          rowKey={(p) => p.id}
          loading={listQ.loading}
          error={listQ.error}
          onRetry={listQ.refetch}
          emptyTitle="No purchase invoices yet"
          emptyHint="Record a stock purchase to receive inventory, update costs and track supplier AP."
          emptyIcon="truck"
          emptyAction={
            <Button size="sm" onClick={() => navigate('/purchases/new')}>
              <Icon name="plus" size={14} /> New purchase
            </Button>
          }
          onRowClick={(p) => navigate(`/purchases/${p.id}`)}
          page={page}
          pageSize={PAGE_SIZE}
          count={listQ.data?.count ?? 0}
          onPage={setPage}
        />
      </div>
    </div>
  );
};
