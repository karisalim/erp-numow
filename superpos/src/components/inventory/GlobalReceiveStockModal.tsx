import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { fmtDecimal } from '../../utils/format';
import type { Product } from '../../types';

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

interface CreatedMovement {
  id: number;
  product: number;
  qty: string | number;
}

interface Props {
  onClose: () => void;
  onSuccess: (productName: string, qty: number) => void;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * GlobalReceiveStockModal — Inventory page entry point.
 *
 * Lets a manager pick any product via a searchable dropdown, enter a qty
 * (decimals allowed), add a note, and post a `receive_in` stock movement.
 * ──────────────────────────────────────────────────────────────────────────── */
export const GlobalReceiveStockModal: React.FC<Props> = ({ onClose, onSuccess }) => {
  const [products, setProducts] = useState<Product[]>([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<Product | null>(null);

  const [qty, setQty]   = useState('1');
  const [note, setNote] = useState('');

  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState<string | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);

  /* Fetch up to 200 active products to populate the picker. */
  useEffect(() => {
    let cancelled = false;
    setProductsLoading(true);
    apiClient
      .get<PaginatedResponse<Product> | Product[]>('/products/', {
        params: { active: 'true', page_size: 200 },
      })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : res.data?.results ?? [];
        setProducts(list);
      })
      .catch(() => {
        if (cancelled) return;
        setError('Could not load products for the picker.');
      })
      .finally(() => { if (!cancelled) setProductsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  /* Close the dropdown when clicking outside. */
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products.slice(0, 50);
    return products.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      String(p.barcode || '').toLowerCase().includes(q) ||
      String(p.sku || '').toLowerCase().includes(q),
    ).slice(0, 50);
  }, [products, search]);

  const handlePick = (p: Product) => {
    setPicked(p);
    setSearch(p.name);
    setOpen(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    setError(null);

    if (!picked) {
      setError('Please pick a product first.');
      return;
    }
    const qtyNum = Number(qty);
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError('Qty must be greater than 0.');
      return;
    }

    setSaving(true);
    try {
      const { data } = await apiClient.post<CreatedMovement>('/stock-movements/', {
        product:       picked.id,
        qty:           qty,
        movement_type: 'receive_in',
        note:          note.trim() || 'Stock received',
      });
      onSuccess(picked.name, Number(data.qty));
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
    <Modal title="Receive stock" onClose={onClose} maxWidth="max-w-[520px]">
      <form onSubmit={submit}>
        <div className="px-6 py-5 space-y-3">
          {error && (
            <div role="alert" className="rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2 text-[13px] text-danger-700">
              {error}
            </div>
          )}

          <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700">
            <span>Product <span className="text-danger-600">*</span></span>
            <div ref={wrapRef} className="relative">
              <input
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPicked(null); setOpen(true); }}
                onFocus={() => setOpen(true)}
                placeholder={productsLoading ? 'Loading products…' : 'Search by name, SKU or barcode…'}
                disabled={saving || productsLoading}
                className="w-full h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
                autoFocus
              />
              {open && filtered.length > 0 && (
                <ul
                  role="listbox"
                  className="absolute z-10 mt-1 w-full max-h-[280px] overflow-auto rounded-md border border-neutral-200 bg-white shadow-lg text-[13px]"
                >
                  {filtered.map((p) => (
                    <li key={String(p.id)}>
                      <button
                        type="button"
                        onClick={() => handlePick(p)}
                        className="w-full text-start px-3 py-2 hover:bg-brand-50 focus-ring flex items-center justify-between gap-3"
                      >
                        <span className="truncate">
                          <span className="font-semibold">{p.name}</span>
                          <span className="text-neutral-500 font-mono ms-2 text-[12px]">{p.barcode}</span>
                        </span>
                        <span className="text-[12px] text-neutral-500 shrink-0">
                          {fmtDecimal(p.stock)} {p.unit_display || p.unit || ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {open && !productsLoading && filtered.length === 0 && (
                <div className="absolute z-10 mt-1 w-full rounded-md border border-neutral-200 bg-white shadow-lg p-3 text-[13px] text-neutral-500">
                  No products match "{search}".
                </div>
              )}
            </div>
            {picked && (
              <span className="text-[12px] font-normal text-success-700">
                Selected: <b>{picked.name}</b> · current stock {fmtDecimal(picked.stock)}
              </span>
            )}
          </label>

          <label className="flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700">
            <span>Qty received <span className="text-danger-600">*</span></span>
            <input
              type="number" min="0.001" step="0.001"
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
          <Button type="submit" size="sm" disabled={saving || !picked}>
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
