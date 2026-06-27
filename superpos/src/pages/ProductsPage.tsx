import React, { useEffect, useMemo, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import { fmtDecimal, stockLabel } from '../utils/format';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../components/ui/Icon';
import { Modal } from '../components/ui/Modal';
import { ProductFormModal, type FormMode } from '../components/products/ProductFormModal';
import { ProductImportControl } from '../components/products/ProductImportControl';
import { ProductActionsMenu, type RowAction } from '../components/products/ProductActionsMenu';
import { StockMovementsModal } from '../components/products/StockMovementsModal';
import { ReceiveStockModal } from '../components/products/ReceiveStockModal';
import type { Product } from '../types';

type StockFilter = 'All' | 'In stock' | 'Low' | 'Out';

interface Category {
  id: number;
  name: string;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

type Toast = { kind: 'success' | 'warn' | 'error'; message: string };

const PAGE_SIZE = 20;

function stockFilterToParams(filter: StockFilter): Record<string, true> {
  switch (filter) {
    case 'Low': return { low_stock:    true };
    case 'Out': return { out_of_stock: true };
    default:    return {};
  }
}

function colorFor(p: Product): string { return p.color || '#6B7280'; }

function initialsFor(name: string): string {
  return name.split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

export const ProductsPage: React.FC = () => {
  const { online, pendingSync } = useAppStore();
  const currency = useAuthStore((s) => s.user?.tenant_currency) || 'EGP';
  const money = (n: number | string | null | undefined) => {
    const num = typeof n === 'number' ? n : Number(n ?? 0);
    return `${currency} ${Number.isFinite(num) ? num.toFixed(2) : '0.00'}`;
  };

  // ── Filter state ────────────────────────────────────────────────────────
  const [q, setQ]                     = useState('');
  const [debouncedQ, setDebouncedQ]   = useState('');
  const [cat, setCat]                 = useState('All');
  const [stockFilter, setStockFilter] = useState<StockFilter>('All');
  const [page, setPage]               = useState(1);
  const [refreshKey, setRefreshKey]   = useState(0);

  // ── Server-driven data ──────────────────────────────────────────────────
  const [categories, setCategories] = useState<Category[]>([]);
  const [products,   setProducts]   = useState<Product[]>([]);
  const [total,      setTotal]      = useState(0);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  // ── Modal & action state ────────────────────────────────────────────────
  const [formModal, setFormModal] = useState<{ mode: FormMode; product?: Product } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Product | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [historyProduct, setHistoryProduct] = useState<Product | null>(null);
  const [receiveProduct, setReceiveProduct] = useState<Product | null>(null);

  const refetch = () => setRefreshKey((k) => k + 1);

  // ── Auto-dismiss toast after 5s ─────────────────────────────────────────
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  // ── Fetch categories on mount and after mutations (new categories may
  //    appear via CSV import) ─────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<PaginatedResponse<Category> | Category[]>('/categories/')
      .then((r) => {
        if (cancelled) return;
        const list = Array.isArray(r.data) ? r.data : r.data.results ?? [];
        setCategories(list);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [refreshKey]);

  // ── Debounce search ─────────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  // ── Reset to page 1 on filter change ────────────────────────────────────
  useEffect(() => { setPage(1); }, [debouncedQ, cat, stockFilter]);

  // ── Fetch products ──────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const params: Record<string, unknown> = { page };
    if (debouncedQ)        params.search   = debouncedQ;
    if (cat && cat !== 'All') params.category = cat;
    Object.assign(params, stockFilterToParams(stockFilter));

    setLoading(true);
    setError(null);

    apiClient
      .get<PaginatedResponse<Product>>('/products/', { params })
      .then((r) => {
        if (cancelled) return;
        setProducts(r.data.results);
        setTotal(r.data.count);
      })
      .catch((err: AxiosError) => {
        if (cancelled) return;
        const status = err.response?.status;
        setError(
          status === 401 ? 'Your session has expired. Please sign in again.' :
          status === 403 ? 'You do not have permission to view products.'    :
                           'Failed to load products. Please try again.',
        );
        setProducts([]);
        setTotal(0);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [page, debouncedQ, cat, stockFilter, refreshKey]);

  // ── Client-side "In stock" refinement on the current page ──────────────
  const visible = useMemo(() => {
    if (stockFilter === 'In stock') return products.filter((p) => p.stock > 0);
    return products;
  }, [products, stockFilter]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const subtitle  = `${total} SKU${total === 1 ? '' : 's'} · ${categories.length} categor${categories.length === 1 ? 'y' : 'ies'}`;

  /* ─── Row-action handlers ─────────────────────────────────────────────── */

  const handleRowAction = (p: Product, action: RowAction) => {
    if (action === 'view')    setFormModal({ mode: 'view', product: p });
    if (action === 'edit')    setFormModal({ mode: 'edit', product: p });
    if (action === 'history') setHistoryProduct(p);
    if (action === 'receive') setReceiveProduct(p);
    if (action === 'delete')  setConfirmDelete(p);
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await apiClient.delete(`/products/${confirmDelete.id}/`);
      setToast({ kind: 'success', message: `✅ Deleted "${confirmDelete.name}".` });
      setConfirmDelete(null);
      refetch();
    } catch (err) {
      let msg = `Failed to delete "${confirmDelete.name}".`;
      if (err instanceof AxiosError) {
        if (err.response?.status === 403) msg = 'You do not have permission to delete products.';
        else if (err.response?.status === 404) msg = 'Product no longer exists.';
      }
      setToast({ kind: 'error', message: msg });
    } finally {
      setDeleting(false);
    }
  };

  /* ─── Render ──────────────────────────────────────────────────────────── */

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header
        title="Products"
        subtitle={subtitle}
        online={online}
        pendingSync={pendingSync}
        right={
          <>
            <ProductImportControl
              onComplete={(banner) => setToast(banner)}
              onChanged={refetch}
            />
            <Button size="sm" onClick={() => setFormModal({ mode: 'create' })}>
              <Icon name="plus" size={14} /> New product
            </Button>
          </>
        }
      />

      <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
        {/* Inline toast banner */}
        {toast && (
          <div
            role="status"
            className={`flex items-start gap-2 rounded-md border px-3 py-2.5 text-[13px] ${
              toast.kind === 'success'
                ? 'border-success-600/30 bg-success-50 text-success-700'
                : toast.kind === 'warn'
                ? 'border-warn-600/40 bg-warn-50 text-warn-700'
                : 'border-danger-500/30 bg-danger-50 text-danger-700'
            }`}
          >
            <span className="flex-1">{toast.message}</span>
            <button
              type="button"
              onClick={() => setToast(null)}
              className="shrink-0 text-current/70 hover:text-current focus-ring rounded"
              aria-label="Dismiss"
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        )}

        {/* Filters */}
        <Card className="p-3 flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[280px]">
            <Icon name="search" size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name, SKU or barcode…"
              className="w-full h-10 ps-9 pe-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Category</span>
            <select
              value={cat}
              onChange={(e) => setCat(e.target.value)}
              className="h-10 px-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
            >
              <option>All</option>
              {categories.map((c) => (
                <option key={c.id} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Stock</span>
            <div className="flex bg-neutral-100 rounded-md p-0.5">
              {(['All', 'In stock', 'Low', 'Out'] as StockFilter[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setStockFilter(s)}
                  className={`h-9 px-3 text-[13px] rounded focus-ring
                    ${stockFilter === s ? 'bg-white shadow-sm font-semibold' : 'text-neutral-600 hover:text-neutral-900'}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {/* Error banner */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700"
          >
            <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Table */}
        <Card className="flex-1 min-h-0 overflow-hidden flex flex-col">
          <div className="overflow-auto flex-1">
            <table className="w-full text-[13.5px]">
              <thead className="bg-neutral-50 text-[11.5px] uppercase tracking-wider text-neutral-500 sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">Product</th>
                  <th className="text-start font-semibold">SKU</th>
                  <th className="text-start font-semibold">Barcode</th>
                  <th className="text-start font-semibold">Category</th>
                  <th className="text-end font-semibold">Cost</th>
                  <th className="text-end font-semibold">Price</th>
                  <th className="text-end font-semibold">Margin</th>
                  <th className="text-end font-semibold">Stock</th>
                  <th className="px-4 text-start font-semibold">Status</th>
                  <th className="px-4 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={10} className="py-12 text-center text-neutral-500">
                      <span className="inline-flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
                        Loading products…
                      </span>
                    </td>
                  </tr>
                )}

                {!loading && visible.map((p) => {
                  const stockNum   = Number(p.stock ?? 0);
                  const reorderNum = Number(p.reorder ?? 0);
                  const b = stockLabel(stockNum, reorderNum);
                  const priceNum = Number(p.price ?? 0);
                  const costNum  = Number(p.cost ?? 0);
                  const margin = priceNum ? ((priceNum - costNum) / priceNum * 100).toFixed(0) : '0';
                  const categoryLabel = p.category_name || (typeof p.category === 'string' ? p.category : '—');
                  const stockDisplay = fmtDecimal(stockNum);
                  return (
                    <tr key={String(p.id)} className="border-t border-neutral-100 hover:bg-neutral-50" style={{ height: 36 }}>
                      <td className="px-4 py-1.5">
                        <div className="flex items-center gap-2.5">
                          <div
                            className="w-7 h-7 rounded grid place-items-center text-white text-[9.5px] font-bold shrink-0"
                            style={{ background: colorFor(p) }}
                          >
                            {initialsFor(p.name)}
                          </div>
                          <span className="font-medium truncate">{p.name}</span>
                          {p.weighted && <Badge kind="info">{p.unit_display || p.unit || 'kg'}</Badge>}
                        </div>
                      </td>
                      <td className="font-mono text-[12px] text-neutral-600">{p.sku}</td>
                      <td className="font-mono text-[12px] text-neutral-600">{p.barcode}</td>
                      <td className="text-neutral-600">{categoryLabel}</td>
                      <td className="text-end font-mono tabular-nums text-neutral-500">{money(p.cost)}</td>
                      <td className="text-end font-mono tabular-nums font-semibold">{money(p.price)}</td>
                      <td className="text-end font-mono tabular-nums text-neutral-600">{margin}%</td>
                      <td className="text-end font-mono tabular-nums">
                        <span className={stockNum === 0 ? 'text-danger-600 font-semibold' : stockNum < reorderNum ? 'text-warn-700 font-semibold' : ''}>
                          {stockDisplay}
                        </span>
                      </td>
                      <td className="px-4"><Badge kind={b.kind}>{b.label}</Badge></td>
                      <td className="px-4 text-end">
                        <ProductActionsMenu onSelect={(action) => handleRowAction(p, action)} />
                      </td>
                    </tr>
                  );
                })}

                {!loading && visible.length === 0 && !error && (
                  <tr>
                    <td colSpan={10} className="py-12 text-center text-neutral-500">
                      No products match these filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="px-4 h-12 border-t border-neutral-200 flex items-center justify-between text-[12.5px] text-neutral-500">
            <span>
              Showing <b className="text-neutral-700">{visible.length}</b> of {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="px-2">Page {page} of {pageCount}</span>
              <button
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={page >= pageCount || loading}
                className="h-8 px-3 rounded border border-neutral-300 bg-white hover:bg-neutral-50 focus-ring disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </Card>
      </div>

      {/* Create / Edit / View modal */}
      {formModal && (
        <ProductFormModal
          mode={formModal.mode}
          initialProduct={formModal.product}
          categories={categories}
          onClose={() => setFormModal(null)}
          onSuccess={(action, product) => {
            setFormModal(null);
            setToast({
              kind: 'success',
              message: action === 'created'
                ? `✅ Created "${product.name}".`
                : `✅ Updated "${product.name}".`,
            });
            refetch();
          }}
        />
      )}

      {/* Stock movements (history) */}
      {historyProduct && (
        <StockMovementsModal
          product={historyProduct}
          onClose={() => setHistoryProduct(null)}
        />
      )}

      {/* Receive stock */}
      {receiveProduct && (
        <ReceiveStockModal
          product={receiveProduct}
          onClose={() => setReceiveProduct(null)}
          onSuccess={(newStock, qty) => {
            setReceiveProduct(null);
            setToast({
              kind: 'success',
              message: `Received ${fmtDecimal(qty)} into "${receiveProduct.name}". New stock: ${fmtDecimal(newStock)}.`,
            });
            refetch();
          }}
        />
      )}

      {/* Delete confirmation */}
      {confirmDelete && (
        <Modal
          title="Delete product"
          onClose={() => !deleting && setConfirmDelete(null)}
          maxWidth="max-w-[420px]"
        >
          <div className="px-6 py-5 text-[14px] text-neutral-700">
            Are you sure you want to delete{' '}
            <b className="text-neutral-900">"{confirmDelete.name}"</b>? This action cannot be undone.
          </div>
          <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
            <Button
              type="button" variant="secondary" size="sm"
              onClick={() => setConfirmDelete(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              type="button" variant="danger" size="sm"
              onClick={doDelete}
              disabled={deleting}
            >
              {deleting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                  Deleting…
                </>
              ) : 'Delete product'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
};
