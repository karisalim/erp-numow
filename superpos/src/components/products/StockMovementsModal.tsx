import React, { useEffect, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Icon } from '../ui/Icon';
import { fmtDecimal } from '../../utils/format';
import type { Product, BadgeKind } from '../../types';

interface StockMovement {
  id: number;
  product: number;
  product_name: string;
  qty: string | number;
  movement_type: string;
  movement_type_display?: string;
  note?: string;
  created_at: string;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

interface Props {
  product: Product;
  onClose: () => void;
}

const fmtDateTime = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
};

const fmtQty = (q: string | number): string => {
  const n = typeof q === 'number' ? q : Number(q);
  if (!Number.isFinite(n)) return String(q);
  const tidy = fmtDecimal(Math.abs(n));
  return n > 0 ? `+${tidy}` : n < 0 ? `-${tidy}` : tidy;
};

const typeBadge = (type: string): { kind: BadgeKind; label: string } => {
  switch (type) {
    case 'sale_out':    return { kind: 'danger',  label: 'Sale out' };
    case 'purchase_in': return { kind: 'success', label: 'Purchase in' };
    case 'receive_in':  return { kind: 'success', label: 'Receive in' };
    case 'return_in':   return { kind: 'warn',    label: 'Return in' };
    case 'adjustment':  return { kind: 'info',    label: 'Adjustment' };
    default:            return { kind: 'gray',    label: type };
  }
};

export const StockMovementsModal: React.FC<Props> = ({ product, onClose }) => {
  const [rows, setRows]       = useState<StockMovement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<PaginatedResponse<StockMovement> | StockMovement[]>('/stock-movements/', {
        params: { product_id: product.id, page_size: 100 },
      })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : res.data?.results ?? [];
        setRows(list);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        let msg = 'Failed to load stock movements.';
        if (err instanceof AxiosError && typeof err.response?.data?.detail === 'string') {
          msg = err.response.data.detail;
        }
        setError(msg);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  return (
    <Modal title={`Stock movements · ${product.name}`} onClose={onClose} maxWidth="max-w-[720px]">
      <div className="px-6 py-4 max-h-[70vh] overflow-auto">
        {error && (
          <div role="alert" className="mb-3 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2 text-[13px] text-danger-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-10 text-center text-neutral-500">
            <span className="inline-flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
              Loading…
            </span>
          </div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center text-neutral-500 text-[13px]">No stock movements recorded yet.</div>
        ) : (
          <table className="w-full text-[13px]">
            <thead className="text-[11.5px] uppercase tracking-wider text-neutral-500">
              <tr>
                <th className="text-start font-semibold py-2">Date</th>
                <th className="text-start font-semibold">Type</th>
                <th className="text-end font-semibold">Qty</th>
                <th className="text-start font-semibold ps-4">Note</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const b = typeBadge(r.movement_type);
                const qtyNum = Number(r.qty);
                return (
                  <tr key={r.id} className="border-t border-neutral-100">
                    <td className="py-1.5 font-mono text-[12px] text-neutral-600">{fmtDateTime(r.created_at)}</td>
                    <td><Badge kind={b.kind}>{b.label}</Badge></td>
                    <td className={`text-end font-mono tabular-nums ${qtyNum < 0 ? 'text-danger-600' : 'text-success-700'} font-semibold`}>
                      {fmtQty(r.qty)}
                    </td>
                    <td className="ps-4 text-neutral-600">{r.note || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onClose}>
          <Icon name="x" size={14} /> Close
        </Button>
      </div>
    </Modal>
  );
};
