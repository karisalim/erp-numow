import React, { useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { FilterChips } from '../../components/ui/FilterBar';
import { settlementsApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { accountTypeLabel } from './accountTypes';
import type { CustomerReceipt, SupplierPayment } from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Settlements: posted customer receipts (money in) and supplier payments
 * (money out). Creation happens in the customer/supplier drawers; this
 * tab is the document list + detail view.
 * ──────────────────────────────────────────────────────────────────────────── */

type Kind = 'receipts' | 'payments';

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const DetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex justify-between gap-4 py-2 border-b border-neutral-100 text-[13px]">
    <span className="text-neutral-500">{label}</span>
    <span className="font-medium text-end">{children}</span>
  </div>
);

export const SettlementsTab: React.FC = () => {
  const money = useMoney();
  const [kind, setKind] = useState<Kind>('receipts');
  const [receiptDetail, setReceiptDetail] = useState<CustomerReceipt | null>(null);
  const [paymentDetail, setPaymentDetail] = useState<SupplierPayment | null>(null);

  const receiptsQ = useQuery(
    () => (kind === 'receipts' ? settlementsApi.listCustomerReceipts().then(asResults) : Promise.resolve(null)),
    [kind],
  );
  const paymentsQ = useQuery(
    () => (kind === 'payments' ? settlementsApi.listSupplierPayments().then(asResults) : Promise.resolve(null)),
    [kind],
  );

  const receiptColumns: Column<CustomerReceipt>[] = [
    { key: 'id', header: 'Receipt', render: (r) => <span className="font-mono font-bold">RCV-{r.id}</span> },
    { key: 'customer', header: 'Customer', render: (r) => <span className="font-semibold">{r.customer_name}</span> },
    { key: 'method', header: 'Method', render: (r) => <Badge kind="brand">{r.payment_method_name}</Badge> },
    { key: 'dest', header: 'Into account', className: 'hidden md:table-cell', render: (r) => <span className="text-neutral-600">{r.destination_account_name}</span> },
    { key: 'amount', header: 'Amount', align: 'end', mono: true, className: 'font-semibold', render: (r) => money(r.amount) },
    { key: 'when', header: 'Posted', render: (r) => <span className="text-neutral-500">{fmtDateTime(r.posted_at)}</span> },
  ];

  const paymentColumns: Column<SupplierPayment>[] = [
    { key: 'id', header: 'Payment', render: (p) => <span className="font-mono font-bold">PAY-{p.id}</span> },
    { key: 'supplier', header: 'Supplier', render: (p) => <span className="font-semibold">{p.supplier_name}</span> },
    { key: 'method', header: 'Method', render: (p) => <Badge kind="brand">{p.payment_method_name}</Badge> },
    { key: 'src', header: 'From account', className: 'hidden md:table-cell', render: (p) => <span className="text-neutral-600">{p.source_account_name}</span> },
    { key: 'amount', header: 'Amount', align: 'end', mono: true, className: 'font-semibold', render: (p) => money(p.amount) },
    { key: 'when', header: 'Posted', render: (p) => <span className="text-neutral-500">{fmtDateTime(p.posted_at)}</span> },
  ];

  return (
    <>
      <div className="mb-3">
        <FilterChips<Kind>
          value={kind}
          onChange={setKind}
          options={[
            { value: 'receipts', label: 'Customer receipts' },
            { value: 'payments', label: 'Supplier payments' },
          ]}
        />
      </div>

      {kind === 'receipts' ? (
        <DataTable<CustomerReceipt>
          columns={receiptColumns}
          rows={receiptsQ.data ?? []}
          rowKey={(r) => r.id}
          loading={receiptsQ.loading}
          error={receiptsQ.error}
          onRetry={receiptsQ.refetch}
          emptyTitle="No customer receipts"
          emptyHint="Record receipts from a customer's detail drawer (Customers → open a customer → Record receipt)."
          emptyIcon="cash"
          onRowClick={setReceiptDetail}
        />
      ) : (
        <DataTable<SupplierPayment>
          columns={paymentColumns}
          rows={paymentsQ.data ?? []}
          rowKey={(p) => p.id}
          loading={paymentsQ.loading}
          error={paymentsQ.error}
          onRetry={paymentsQ.refetch}
          emptyTitle="No supplier payments"
          emptyHint="Record payments from a supplier's detail drawer (Suppliers → open a supplier → Record payment)."
          emptyIcon="cash"
          onRowClick={setPaymentDetail}
        />
      )}

      {receiptDetail && (
        <Modal title={`Customer receipt RCV-${receiptDetail.id}`} onClose={() => setReceiptDetail(null)} maxWidth="max-w-[460px]">
          <div className="p-6">
            <div className="text-center mb-4">
              <div className="text-[26px] font-extrabold font-mono">{money(receiptDetail.amount)}</div>
              <Badge kind="success">Posted</Badge>
            </div>
            <DetailRow label="Customer">{receiptDetail.customer_name}</DetailRow>
            <DetailRow label="Method">{receiptDetail.payment_method_name} ({receiptDetail.payment_method_type})</DetailRow>
            <DetailRow label="Into account">{receiptDetail.destination_account_name} ({accountTypeLabel(receiptDetail.destination_account_type)})</DetailRow>
            <DetailRow label="Reference">{receiptDetail.reference || '—'}</DetailRow>
            <DetailRow label="Notes">{receiptDetail.notes || '—'}</DetailRow>
            <DetailRow label="Posted">{fmtDateTime(receiptDetail.posted_at)}</DetailRow>
            <DetailRow label="By">{receiptDetail.actor_user_username || '—'}</DetailRow>
          </div>
        </Modal>
      )}

      {paymentDetail && (
        <Modal title={`Supplier payment PAY-${paymentDetail.id}`} onClose={() => setPaymentDetail(null)} maxWidth="max-w-[460px]">
          <div className="p-6">
            <div className="text-center mb-4">
              <div className="text-[26px] font-extrabold font-mono">{money(paymentDetail.amount)}</div>
              <Badge kind="success">Posted</Badge>
            </div>
            <DetailRow label="Supplier">{paymentDetail.supplier_name}</DetailRow>
            <DetailRow label="Method">{paymentDetail.payment_method_name} ({paymentDetail.payment_method_type})</DetailRow>
            <DetailRow label="From account">{paymentDetail.source_account_name} ({accountTypeLabel(paymentDetail.source_account_type)})</DetailRow>
            <DetailRow label="Reference">{paymentDetail.reference || '—'}</DetailRow>
            <DetailRow label="Notes">{paymentDetail.notes || '—'}</DetailRow>
            <DetailRow label="Posted">{fmtDateTime(paymentDetail.posted_at)}</DetailRow>
            <DetailRow label="By">{paymentDetail.actor_user_username || '—'}</DetailRow>
          </div>
        </Modal>
      )}
    </>
  );
};
