import React, { useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { fmtDecimal } from '../../utils/format';
import type { Product } from '../../types';

interface Props {
  product: Product;
  onClose: () => void;
  onSuccess: (updatedStock: number, qty: number) => void;
}

interface CreatedMovement {
  id: number;
  qty: string | number;
  product: number;
}

export const ReceiveStockModal: React.FC<Props> = ({ product, onClose, onSuccess }) => {
  const [qty,     setQty]     = useState('1');
  const [note,    setNote]    = useState('');
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setError(null);

    const qtyNum = Number(qty);
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError('Qty must be greater than 0.');
      return;
    }

    setSaving(true);
    try {
      const { data } = await apiClient.post<CreatedMovement>('/stock-movements/', {
        product:       product.id,
        qty:           qty,             // keep as string so DRF parses Decimal cleanly
        movement_type: 'receive_in',
        note:          note.trim() || 'Stock received',
      });
      const currentStock = Number(product.stock || 0);
      const received     = Number(data.qty);
      onSuccess(currentStock + received, received);
    } catch (err) {
      let msg = 'Failed to record stock receipt.';
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        if (typeof data?.detail === 'string') {
          msg = data.detail;
        } else if (data && typeof data === 'object') {
          const first = Object.entries(data)[0];
          if (first) {
            const [field, value] = first;
            const text = Array.isArray(value) ? String(value[0]) : String(value);
            msg = field === 'non_field_errors' ? text : `${field}: ${text}`;
          }
        } else if (err.response?.status === 403) {
          msg = 'You do not have permission to receive stock.';
        }
      }
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`Receive stock · ${product.name}`} onClose={onClose} maxWidth="max-w-[480px]">
      <form onSubmit={submit}>
        <div className="px-6 py-5 space-y-3">
          {error && (
            <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2 text-[13px] text-danger-700">
              {error}
            </div>
          )}

          <div className="text-[12.5px] text-neutral-500">
            Current stock: <span className="font-mono font-semibold text-neutral-900">{fmtDecimal(product.stock)}</span>
            {product.unit && <> {product.unit_display || product.unit}</>}
          </div>

          <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700">
            <span>Qty received <span className="text-danger-600">*</span></span>
            <input
              type="number" min="0.001" step="0.001" autoFocus
              value={qty} disabled={saving}
              onChange={(e) => setQty(e.target.value)}
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            />
            <span className="text-[12px] font-normal text-neutral-500">Decimals supported (e.g. 0.5 kg).</span>
          </label>

          <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700">
            <span>Note</span>
            <input
              type="text" value={note} disabled={saving}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Supplier, invoice #, etc."
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            />
          </label>
        </div>

        <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                Saving…
              </>
            ) : (
              <><Icon name="plus" size={14} /> Receive stock</>
            )}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
