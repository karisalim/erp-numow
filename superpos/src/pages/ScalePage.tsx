import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { useMoney } from '../utils/money';
import { fmtDecimal } from '../utils/format';
import type { Product } from '../types';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Icon } from '../components/ui/Icon';
import { Modal } from '../components/ui/Modal';
import { ProductFormModal, type FormMode } from '../components/products/ProductFormModal';

/* ─────────────────────────────────────────────────────────────────────────────
 * Scale page — read-only view over weighted Products.
 *
 * Single source of truth is the Product catalog: every weighted item with a
 * PLU shows up here automatically. Creation/edit happens on the Products
 * page; this screen only handles inline price tweaks, label previews, and
 * the Digi CSV export.
 * ──────────────────────────────────────────────────────────────────────────── */

interface PaginatedResponse<T> {
  count: number;
  next:  string | null;
  previous: string | null;
  results: T[];
}

interface CategoryDto {
  id:   number;
  name: string;
}

type Toast = { kind: 'success' | 'error'; message: string };

const LAST_EXPORT_KEY = 'scale_last_export';

const fmtDateTime = (iso?: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
};

const csvField = (raw: string): string => {
  const needsQuote = /[",\n\r]/.test(raw);
  const escaped = raw.replace(/"/g, '""');
  return needsQuote ? `"${escaped}"` : escaped;
};

const sanitizeName = (name: string): string =>
  name.replace(/\s+/g, ' ').trim();

const todayStamp = (): string => {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
};

const extractApiError = (err: unknown, fallback: string): string => {
  if (err instanceof AxiosError) {
    const data = err.response?.data;
    if (data && typeof data === 'object') {
      const first = Object.entries(data)[0];
      if (first) {
        const [, val] = first;
        return Array.isArray(val) ? String(val[0]) : String(val);
      }
    }
    return err.message || fallback;
  }
  return fallback;
};

const productId = (p: Product): number => (typeof p.id === 'number' ? p.id : Number(p.id));

/* ─────────────────────────────────────────────────────────────────────────────
 * Label preview modal.
 * ──────────────────────────────────────────────────────────────────────────── */
const LabelPreviewModal: React.FC<{
  product: Product;
  money: (n: number | string) => string;
  onClose: () => void;
}> = ({ product, money, onClose }) => (
  <Modal title="Shelf label preview" onClose={onClose} maxWidth="max-w-[420px]">
    <div className="p-6">
      <div className="border-2 border-neutral-300 rounded-lg p-5 bg-white font-mono">
        <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-1">SUPERPOS MARKET</div>
        <div className="text-[22px] font-bold leading-tight mb-1">{product.name}</div>
        <div className="text-[13px] text-neutral-600 mb-3">per kg · PLU {product.plu}</div>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[11px] text-neutral-500">Price per kg</div>
            <div className="text-[28px] font-bold text-brand-600 leading-none">{money(product.price)}</div>
          </div>
          <div className="text-end">
            <div className="text-[10px] text-neutral-400 mb-1">BARCODE PREFIX</div>
            <div className="font-mono text-[18px] font-bold">21{product.plu}</div>
            <div className="flex gap-0.5 mt-1 justify-end">
              {Array.from({ length: 20 }).map((_, i) => (
                <div
                  key={i}
                  className="bg-neutral-900"
                  style={{ width: i % 3 === 0 ? 3 : 2, height: i % 5 === 0 ? 28 : 22 }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="flex gap-2 mt-4">
        <Button variant="secondary" size="md" className="flex-1" onClick={onClose}>Cancel</Button>
        <Button size="md" className="flex-1" onClick={() => window.print()}>
          <Icon name="printer" size={16} /> Print label
        </Button>
      </div>
    </div>
  </Modal>
);

/* ─────────────────────────────────────────────────────────────────────────────
 * Scale page.
 * ──────────────────────────────────────────────────────────────────────────── */
export const ScalePage: React.FC = () => {
  const money = useMoney();

  const [items,   setItems]   = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [toast,   setToast]   = useState<Toast | null>(null);
  const [q,       setQ]       = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  const [editingPriceId, setEditingPriceId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Product | null>(null);
  const [exporting, setExporting] = useState(false);

  // ── ProductFormModal control + categories (needed as a modal prop) ──────
  const [formMode,   setFormMode]   = useState<FormMode | null>(null);
  const [formTarget, setFormTarget] = useState<Product | null>(null);
  const [categories, setCategories] = useState<CategoryDto[]>([]);

  // ── Inline "Add PLU" editor (no-modal fast path for missing PLUs) ───────
  const [editingPluId,    setEditingPluId]    = useState<number | null>(null);
  const [pluDraft,        setPluDraft]        = useState('');
  const [savingPluId,     setSavingPluId]     = useState<number | null>(null);

  const [lastExport, setLastExport] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : localStorage.getItem(LAST_EXPORT_KEY),
  );

  /* ─── Fetch all weighted products (follow pagination) ─────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const fetchAll = async (): Promise<Product[]> => {
      const collected: Product[] = [];
      let page = 1;
      const PAGE_SIZE = 200;
      for (let i = 0; i < 50; i++) {
        const resp = await apiClient.get<PaginatedResponse<Product> | Product[]>(
          '/products/',
          { params: { weighted: 'true', active: 'true', page, page_size: PAGE_SIZE } },
        );
        const data: PaginatedResponse<Product> | Product[] = resp.data;
        if (Array.isArray(data)) {
          collected.push(...data);
          break;
        }
        collected.push(...(data.results ?? []));
        if (!data.next) break;
        page += 1;
      }
      return collected;
    };

    fetchAll()
      .then((rows) => {
        if (cancelled) return;
        rows.sort((a, b) => (a.plu ?? '').localeCompare(b.plu ?? '', undefined, { numeric: true }));
        setItems(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = extractApiError(err, 'Failed to load weighted products.');
        setError(msg);
        setToast({ kind: 'error', message: msg });
        setItems([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [refreshKey]);

  /* ─── Fetch categories once (cheap, used by the in-place edit modal) ─── */
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<PaginatedResponse<CategoryDto> | CategoryDto[]>('/categories/')
      .then((resp) => {
        if (cancelled) return;
        const data = resp.data;
        setCategories(Array.isArray(data) ? data : (data.results ?? []));
      })
      .catch(() => { /* non-fatal — modal still renders with empty list */ });
    return () => { cancelled = true; };
  }, []);

  /* ─── Auto-dismiss toast ──────────────────────────────────────────────── */
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /* ─── Derived ─────────────────────────────────────────────────────────── */
  const missingPlu = useMemo(
    () => items.filter((p) => !p.plu || !p.plu.trim()).length,
    [items],
  );

  const exportable = useMemo(() => items.filter((p) => !!p.plu && p.plu.trim().length > 0), [items]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (p) =>
        p.name.toLowerCase().includes(needle) ||
        (p.plu ?? '').toLowerCase().includes(needle) ||
        p.sku.toLowerCase().includes(needle),
    );
  }, [items, q]);

  /* ─── ProductFormModal callbacks ──────────────────────────────────────── */
  const openCreate = () => { setFormTarget(null); setFormMode('create'); };
  const openEdit   = (product: Product) => { setFormTarget(product); setFormMode('edit'); };
  const closeForm  = () => { setFormMode(null); setFormTarget(null); };

  const onModalSuccess = (action: 'created' | 'updated', saved: Product) => {
    setItems((rows) => {
      // Keep only weighted products on this screen — if a manager unchecks
      // weighted while editing, the row should disappear.
      if (!saved.weighted) {
        return rows.filter((r) => productId(r) !== productId(saved));
      }
      const idx = rows.findIndex((r) => productId(r) === productId(saved));
      const next = idx === -1 ? [...rows, saved] : rows.map((r) => (productId(r) === productId(saved) ? saved : r));
      next.sort((a, b) => (a.plu ?? '').localeCompare(b.plu ?? '', undefined, { numeric: true }));
      return next;
    });
    closeForm();
    setToast({
      kind: 'success',
      message: action === 'created' ? `Added ${saved.name}.` : `Updated ${saved.name}.`,
    });
  };

  /* ─── Inline PLU edit (fast path for missing-PLU rows) ────────────────── */
  const openPluEditor = (product: Product) => {
    setEditingPluId(productId(product));
    setPluDraft(product.plu ?? '');
  };
  const cancelPluEdit = () => { setEditingPluId(null); setPluDraft(''); };

  const commitPlu = async (product: Product) => {
    const id  = productId(product);
    const plu = pluDraft.trim();
    if (!plu) { setToast({ kind: 'error', message: 'PLU code is required.' }); return; }
    if (plu.length > 10) { setToast({ kind: 'error', message: 'PLU must be 1–10 characters.' }); return; }
    if (plu === (product.plu ?? '')) { cancelPluEdit(); return; }

    setSavingPluId(id);
    try {
      const resp = await apiClient.patch<Product>(`/products/${id}/`, { plu });
      setItems((rows) => {
        const next = rows.map((r) => (productId(r) === id ? resp.data : r));
        next.sort((a, b) => (a.plu ?? '').localeCompare(b.plu ?? '', undefined, { numeric: true }));
        return next;
      });
      setToast({ kind: 'success', message: `Set PLU ${plu} on ${product.name}.` });
      cancelPluEdit();
    } catch (err) {
      setToast({ kind: 'error', message: extractApiError(err, 'Failed to set PLU.') });
    } finally {
      setSavingPluId(null);
    }
  };

  /* ─── Inline price edit (PATCH /products/:id/) ────────────────────────── */
  const commitPrice = async (product: Product, raw: string) => {
    setEditingPriceId(null);
    const n = parseFloat(raw);
    if (!Number.isFinite(n) || n <= 0) {
      setToast({ kind: 'error', message: 'Price must be greater than 0.' });
      return;
    }
    if (Math.abs(n - Number(product.price)) < 0.005) return;
    try {
      const resp = await apiClient.patch<Product>(`/products/${productId(product)}/`, {
        price: n.toFixed(2),
      });
      setItems((rows) =>
        rows.map((r) => (productId(r) === productId(product) ? resp.data : r)),
      );
      setToast({ kind: 'success', message: `Updated price for ${product.name}.` });
    } catch (err) {
      setToast({ kind: 'error', message: extractApiError(err, 'Failed to update price.') });
    }
  };

  /* ─── CSV export ──────────────────────────────────────────────────────── */
  const exportCsv = useCallback(async () => {
    if (exporting) return;
    if (exportable.length === 0) {
      setToast({
        kind: 'error',
        message: items.length === 0
          ? 'No weighted products to export. Mark items as weighted in Products.'
          : 'None of the weighted products have a PLU code set yet.',
      });
      return;
    }

    setExporting(true);
    try {
      const header = 'PLU,Product Name,Unit Price';
      const lines = exportable.map((p) => {
        const priceNum = Number(p.price);
        const price = Number.isFinite(priceNum) ? priceNum.toFixed(2) : '0.00';
        return [csvField(p.plu ?? ''), csvField(sanitizeName(p.name)), price].join(',');
      });
      const csv = [header, ...lines].join('\r\n') + '\r\n';

      // BOM for Excel + UTF-8 safety.
      const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `scale_plu_export_${todayStamp()}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      const stamp = new Date().toISOString();
      localStorage.setItem(LAST_EXPORT_KEY, stamp);
      setLastExport(stamp);

      setToast({
        kind: 'success',
        message: `Exported ${exportable.length} item${exportable.length === 1 ? '' : 's'}. Upload to Digi scale software now.`,
      });
    } finally {
      setExporting(false);
    }
  }, [exporting, exportable, items.length]);

  /* ─── Render ──────────────────────────────────────────────────────────── */
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Scale / PLU codes"
        subtitle="Weighted products from the catalog · export to Digi scale"
        right={
          <>
            <Button variant="secondary" size="sm" onClick={exportCsv} disabled={exporting || loading || exportable.length === 0}>
              <Icon name="archive" size={14} />
              {exporting ? 'Exporting…' : 'Export CSV'}
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Icon name="plus" size={14} /> New weighted product
            </Button>
          </>
        }
      />

      <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
        {toast && (
          <div
            role={toast.kind === 'success' ? 'status' : 'alert'}
            className={`flex items-start gap-2 rounded-md border px-3 py-2.5 text-[13px] ${
              toast.kind === 'success'
                ? 'border-success-600/30 bg-success-50 text-success-700'
                : 'border-danger-500/30 bg-danger-50 text-danger-700'
            }`}
          >
            <Icon name={toast.kind === 'success' ? 'check' : 'alert'} size={16} className="mt-0.5 shrink-0" />
            <span className="flex-1">{toast.message}</span>
            <button onClick={() => setToast(null)} className="shrink-0 hover:opacity-70 focus-ring rounded" aria-label="Dismiss">
              <Icon name="x" size={14} />
            </button>
          </div>
        )}

        {/* Info card. */}
        <Card className="p-4 bg-brand-50 border border-brand-100">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-100 text-brand-600 grid place-items-center shrink-0">
              <Icon name="barcode" size={20} />
            </div>
            <div>
              <div className="text-[13px] font-semibold text-brand-800 mb-1">Scale barcode format</div>
              <div className="text-[12.5px] text-brand-700 font-mono flex items-center gap-1 flex-wrap">
                <span className="bg-brand-200 px-1.5 py-0.5 rounded">21</span>
                <span className="text-brand-400">+</span>
                <span className="bg-brand-200 px-1.5 py-0.5 rounded">5-digit PLU</span>
                <span className="text-brand-400">+</span>
                <span className="bg-brand-200 px-1.5 py-0.5 rounded">5-digit weight (grams)</span>
                <span className="text-brand-400">+</span>
                <span className="bg-brand-200 px-1.5 py-0.5 rounded">check digit</span>
              </div>
              <div className="text-[12px] text-brand-600 mt-1">
                Example: <span className="font-mono font-semibold">2100041 01500 2</span> → PLU 00041 · 1.500 kg
              </div>
              <div className="text-[12px] text-brand-700 mt-2">
                Click <span className="font-semibold">Edit</span> on a row to set a missing PLU or change pricing. Adding a new weighted product
                from <span className="font-semibold">New weighted product</span> at the top wires it straight into both the catalog and this page.
              </div>
            </div>
          </div>
        </Card>

        {/* Metric cards. */}
        <div className="grid grid-cols-3 gap-4">
          <Card className="p-5 flex flex-col gap-1">
            <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Weighted products</div>
            <div className="text-[28px] font-bold tabular-nums font-mono">{items.length}</div>
          </Card>
          <Card className="p-5 flex flex-col gap-1">
            <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Last export</div>
            <div className="text-[15px] font-semibold text-neutral-700 mt-1.5">
              {lastExport ? fmtDateTime(lastExport) : 'Never'}
            </div>
          </Card>
          <Card className="p-5 flex flex-col gap-1">
            <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Missing PLU</div>
            <div className="flex items-center gap-2 mt-1.5">
              <span className={`w-2.5 h-2.5 rounded-full block ${missingPlu > 0 ? 'bg-warn-500' : 'bg-success-500'}`} />
              <span className={`text-[15px] font-semibold ${missingPlu > 0 ? 'text-warn-700' : 'text-success-700'}`}>
                {missingPlu > 0 ? `${missingPlu} need PLU` : 'All set'}
              </span>
            </div>
          </Card>
        </div>

        {/* Search. */}
        <Card className="p-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Icon name="search" size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by PLU, product name, or SKU…"
              className="w-full h-10 ps-9 pe-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            />
          </div>
          <Button variant="secondary" size="sm" onClick={() => setRefreshKey((k) => k + 1)}>
            <Icon name="sync" size={14} /> Refresh
          </Button>
        </Card>

        {/* Table. */}
        <Card className="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div className="overflow-auto flex-1">
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">PLU</th>
                  <th className="text-start font-semibold">Product name</th>
                  <th className="text-end font-semibold">Price / kg</th>
                  <th className="px-4 text-end font-semibold">Stock</th>
                  <th className="text-start font-semibold ps-4">Last updated</th>
                  <th className="px-4 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={6} className="py-12 text-center text-neutral-500">Loading…</td></tr>
                )}

                {!loading && error && (
                  <tr><td colSpan={6} className="py-12 text-center text-danger-600">{error}</td></tr>
                )}

                {!loading && !error && filtered.map((product) => {
                  const id = productId(product);
                  const noPlu = !product.plu || !product.plu.trim();
                  const editingPlu = editingPluId === id;
                  const savingPlu = savingPluId === id;
                  return (
                    <tr key={id} className="border-t border-neutral-100 hover:bg-neutral-50" style={{ height: 40 }}>
                      <td className="px-4 font-mono text-[12.5px] font-semibold">
                        {editingPlu ? (
                          <div className="inline-flex items-center gap-1">
                            <input
                              autoFocus
                              type="text" inputMode="numeric" maxLength={10}
                              value={pluDraft}
                              disabled={savingPlu}
                              onChange={(e) => setPluDraft(e.target.value.replace(/\s/g, ''))}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter')  commitPlu(product);
                                if (e.key === 'Escape') cancelPluEdit();
                              }}
                              placeholder="00041"
                              className="w-24 h-7 px-2 rounded border border-brand-400 focus-ring font-mono text-[12.5px]"
                            />
                            <button
                              type="button"
                              onClick={() => commitPlu(product)}
                              disabled={savingPlu}
                              className="w-7 h-7 grid place-items-center rounded text-success-700 hover:bg-success-50 focus-ring disabled:opacity-40"
                              title="Save"
                            >
                              {savingPlu
                                ? <span className="w-3 h-3 border-2 border-success-200 border-t-success-600 rounded-full spin" />
                                : <Icon name="check" size={14} />}
                            </button>
                            <button
                              type="button"
                              onClick={cancelPluEdit}
                              disabled={savingPlu}
                              className="w-7 h-7 grid place-items-center rounded text-neutral-500 hover:bg-neutral-100 focus-ring disabled:opacity-40"
                              title="Cancel"
                            >
                              <Icon name="x" size={14} />
                            </button>
                          </div>
                        ) : noPlu ? (
                          <button
                            type="button"
                            onClick={() => openPluEditor(product)}
                            className="inline-flex items-center gap-1 text-warn-700 hover:text-warn-800 hover:bg-warn-50 focus-ring rounded px-1.5 py-0.5"
                            title="Click to set a PLU code"
                          >
                            <Icon name="alert" size={12} />
                            <span>Add PLU</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => openPluEditor(product)}
                            className="text-brand-700 hover:text-brand-800 hover:bg-brand-50 focus-ring rounded px-1.5 py-0.5"
                            title="Click to change PLU"
                          >
                            {product.plu}
                          </button>
                        )}
                      </td>
                      <td className="font-medium">
                        <div>{product.name}</div>
                        <div className="text-[11.5px] text-neutral-400 font-mono">{product.sku}</div>
                      </td>
                      <td className="text-end pe-4">
                        {editingPriceId === id ? (
                          <input
                            autoFocus
                            type="number" step="0.01" min="0.01"
                            defaultValue={product.price}
                            className="w-28 h-8 px-2 text-end rounded border border-brand-400 focus-ring font-mono text-[13px] no-spin"
                            onBlur={(e) => commitPrice(product, e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter')  commitPrice(product, (e.target as HTMLInputElement).value);
                              if (e.key === 'Escape') setEditingPriceId(null);
                            }}
                          />
                        ) : (
                          <button
                            onClick={() => setEditingPriceId(id)}
                            className="font-mono tabular-nums hover:text-brand-600 focus-ring rounded px-1"
                            title="Click to edit"
                          >
                            {money(product.price)}
                          </button>
                        )}
                      </td>
                      <td className="px-4 text-end font-mono tabular-nums text-[12.5px]">
                        {fmtDecimal(product.stock)}
                      </td>
                      <td className="ps-4 text-neutral-500 text-[12.5px]">{fmtDateTime(product.updated_at)}</td>
                      <td className="px-4 text-end">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setPreview(product)}
                            disabled={noPlu}
                            className="h-7 px-2 rounded text-[12px] font-semibold text-brand-600 hover:bg-brand-50 focus-ring disabled:opacity-40 disabled:cursor-not-allowed"
                            title={noPlu ? 'Set a PLU on this product first.' : 'Preview shelf label'}
                          >
                            Preview
                          </button>
                          <button
                            type="button"
                            onClick={() => openEdit(product)}
                            className="h-7 px-2 rounded text-[12px] font-semibold text-neutral-600 hover:bg-neutral-100 focus-ring"
                          >
                            Edit
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {!loading && !error && filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-neutral-500">
                      {items.length === 0
                        ? <>
                            No weighted products yet.{' '}
                            <button
                              type="button"
                              onClick={openCreate}
                              className="text-brand-600 font-semibold hover:underline focus-ring rounded"
                            >
                              Add your first weighted product.
                            </button>
                          </>
                        : 'No products match the search.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="px-4 h-12 border-t border-neutral-200 flex items-center justify-between text-[12.5px] text-neutral-500">
            <span>
              Showing <b className="text-neutral-700">{filtered.length}</b> of {items.length}
              {missingPlu > 0 && <> · <b className="text-warn-700">{missingPlu} missing PLU</b></>}
            </span>
            <Button variant="secondary" size="sm" onClick={exportCsv} disabled={exporting || exportable.length === 0}>
              <Icon name="archive" size={14} /> Export to scale
            </Button>
          </div>
        </Card>
      </div>

      {preview && <LabelPreviewModal product={preview} money={money} onClose={() => setPreview(null)} />}
      {formMode && (
        <ProductFormModal
          mode={formMode}
          initialProduct={formTarget ?? undefined}
          categories={categories}
          initialWeighted={formMode === 'create'}
          onClose={closeForm}
          onSuccess={onModalSuccess}
        />
      )}
    </div>
  );
};
