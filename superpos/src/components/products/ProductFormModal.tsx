import React, { useEffect, useState } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { Badge } from '../ui/Badge';
import { categoriesApi, asResults } from '../../api/erp';
import { flattenTree } from '../../utils/tree';
import type { Product, ProductUnit } from '../../types';
import type { CategoryTreeNode, ProductTypeValue } from '../../types/erp';

export type FormMode = 'create' | 'edit' | 'view';
type Tab = 'quick' | 'full';

interface Category {
  id: number;
  name: string;
}

interface Props {
  mode: FormMode;
  initialProduct?: Product;
  categories: Category[];
  /**
   * Pre-check "Weighted" on the new-product form and start on the Full Add
   * tab so the PLU input is visible. Used by the Scale page's create flow.
   */
  initialWeighted?: boolean;
  onClose: () => void;
  onSuccess: (action: 'created' | 'updated', product: Product) => void;
}

interface FormState {
  name:     string;
  barcode:  string;
  sku:      string;
  plu:      string;
  price:    string;
  cost:     string;
  tax_rate: string;
  stock:    string;
  reorder:  string;
  category: string;     // empty = none; otherwise stringified id
  unit:     ProductUnit;
  pack_qty: string;
  weighted: boolean;
  color:    string;
  active:   boolean;
  product_type: ProductTypeValue;
  sales_category: string;      // empty = none; otherwise stringified id
  inventory_category: string;  // empty = none; otherwise stringified id
  show_on_pos: boolean;
  is_discountable: boolean;
}

const UNIT_OPTIONS: ProductUnit[] = ['piece', 'kg', 'liter', 'carton'];

/** Mirrors pos/services/product_types.py ProductType — labels only; the
 * behavior matrix itself stays server-side (read-only `behavior` on the
 * product), never duplicated here. */
const PRODUCT_TYPE_OPTIONS: { value: ProductTypeValue; label: string }[] = [
  { value: 'stock_item',     label: 'Stock item' },
  { value: 'ingredient',     label: 'Ingredient' },
  { value: 'prep_item',      label: 'Prep item' },
  { value: 'recipe_product', label: 'Recipe product' },
  { value: 'resale',         label: 'Resale' },
  { value: 'packaging',      label: 'Packaging' },
  { value: 'service',        label: 'Service' },
  { value: 'bundle',         label: 'Bundle' },
  { value: 'fixed_asset',    label: 'Fixed asset' },
];

const HIDDEN_DEFAULTS = {
  reorder:  '10',
  tax_rate: '0.10',
  color:    '#6B7280',
  weighted: false,
  active:   true,
  product_type: 'stock_item' as ProductTypeValue,
  show_on_pos: true,
  is_discountable: true,
};

function blankForm(): FormState {
  return {
    name: '', barcode: '', sku: '', plu: '',
    price: '', cost: '0', stock: '0',
    reorder: HIDDEN_DEFAULTS.reorder,
    tax_rate: HIDDEN_DEFAULTS.tax_rate,
    category: '',
    unit: 'piece',
    pack_qty: '1',
    weighted: HIDDEN_DEFAULTS.weighted,
    color: HIDDEN_DEFAULTS.color,
    active: HIDDEN_DEFAULTS.active,
    product_type: HIDDEN_DEFAULTS.product_type,
    sales_category: '',
    inventory_category: '',
    show_on_pos: HIDDEN_DEFAULTS.show_on_pos,
    is_discountable: HIDDEN_DEFAULTS.is_discountable,
  };
}

function formFromProduct(p: Product): FormState {
  return {
    name:     p.name ?? '',
    barcode:  p.barcode ?? '',
    sku:      p.sku ?? '',
    plu:      p.plu ?? '',
    price:    String(p.price ?? ''),
    cost:     String(p.cost ?? ''),
    tax_rate: String(p.tax_rate ?? HIDDEN_DEFAULTS.tax_rate),
    stock:    String(p.stock ?? 0),
    reorder:  String(p.reorder ?? HIDDEN_DEFAULTS.reorder),
    category: p.category != null && typeof p.category === 'number' ? String(p.category) : '',
    unit:     (p.unit as ProductUnit) ?? 'piece',
    pack_qty: String(p.pack_qty ?? '1'),
    weighted: !!p.weighted,
    color:    p.color || HIDDEN_DEFAULTS.color,
    active:   p.active ?? true,
    product_type: p.product_type ?? HIDDEN_DEFAULTS.product_type,
    sales_category: p.sales_category != null ? String(p.sales_category) : '',
    inventory_category: p.inventory_category != null ? String(p.inventory_category) : '',
    show_on_pos: p.show_on_pos ?? HIDDEN_DEFAULTS.show_on_pos,
    is_discountable: p.is_discountable ?? HIDDEN_DEFAULTS.is_discountable,
  };
}

/** Convert form → payload, applying Quick Add defaults for hidden fields. */
function buildPayload(form: FormState, tab: Tab, isEdit: boolean) {
  const sku = form.sku.trim() || form.barcode.trim();
  // PLU is only meaningful for weighted items (the scale prints `21<PLU><wt>`),
  // but we still send '' explicitly so editing a non-weighted product clears
  // any stale PLU on the server.
  const plu = form.weighted ? form.plu.trim() : '';
  const payload: Record<string, unknown> = {
    name:     form.name.trim(),
    barcode:  form.barcode.trim(),
    sku,
    plu,
    price:    form.price,
    stock:    form.stock || '0',
    unit:     form.unit,
    pack_qty: form.pack_qty || '1',
  };
  // `cost` is AVCO-derived once a product exists (Sprint 3 Batch 3) — the
  // backend rejects it on PATCH. Only a create sends it, as the opening
  // cost; the Cost field itself is disabled during edit (see the input
  // below) so this omission never silently drops an in-progress edit.
  if (!isEdit) payload.cost = form.cost || '0';
  if (form.category) payload.category = Number(form.category);

  if (tab === 'quick') {
    payload.reorder  = Number(HIDDEN_DEFAULTS.reorder);
    payload.tax_rate = HIDDEN_DEFAULTS.tax_rate;
    payload.color    = HIDDEN_DEFAULTS.color;
    payload.weighted = HIDDEN_DEFAULTS.weighted;
    payload.active   = HIDDEN_DEFAULTS.active;
    payload.product_type = HIDDEN_DEFAULTS.product_type;
    payload.show_on_pos = HIDDEN_DEFAULTS.show_on_pos;
    payload.is_discountable = HIDDEN_DEFAULTS.is_discountable;
  } else {
    payload.reorder  = Number(form.reorder || 0);
    payload.tax_rate = form.tax_rate;
    payload.color    = form.color || HIDDEN_DEFAULTS.color;
    payload.weighted = form.weighted;
    payload.active   = form.active;
    payload.product_type = form.product_type;
    payload.show_on_pos = form.show_on_pos;
    payload.is_discountable = form.is_discountable;
    if (form.sales_category) payload.sales_category = Number(form.sales_category);
    if (form.inventory_category) payload.inventory_category = Number(form.inventory_category);
  }
  return payload;
}

/** Pull DRF-style { field: [msg] } error payload into a flat record. */
function parseFieldErrors(err: unknown): { fieldErrors: Record<string, string>; formError: string | null } {
  const fieldErrors: Record<string, string> = {};
  let formError: string | null = null;

  if (err instanceof AxiosError) {
    const data = err.response?.data;
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      for (const [key, val] of Object.entries(data as Record<string, unknown>)) {
        const msg = Array.isArray(val) ? String(val[0]) : String(val);
        if (key === 'detail' || key === 'non_field_errors') {
          formError = msg;
        } else {
          fieldErrors[key] = msg;
        }
      }
    } else if (err.response?.status === 403) {
      formError = 'You do not have permission to do that.';
    } else {
      formError = 'Request failed. Please try again.';
    }
  } else {
    formError = 'Unexpected error.';
  }
  return { fieldErrors, formError };
}

/* ─────────────────────────────────────────────────────────────────────────── */

export const ProductFormModal: React.FC<Props> = ({
  mode, initialProduct, categories, initialWeighted, onClose, onSuccess,
}) => {
  const isView = mode === 'view';
  const isEdit = mode === 'edit';
  // Pre-checking "Weighted" only makes sense when we're not loading an
  // existing record — and the PLU input only lives on the Full tab.
  const initialTab: Tab = mode === 'create' && !initialWeighted ? 'quick' : 'full';

  const [tab, setTab]               = useState<Tab>(initialTab);
  const [form, setForm]             = useState<FormState>(() => {
    if (initialProduct) return formFromProduct(initialProduct);
    const base = blankForm();
    if (initialWeighted) base.weighted = true;
    return base;
  });
  const [saving, setSaving]         = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError]   = useState<string | null>(null);

  const [salesCategories, setSalesCategories] = useState<CategoryTreeNode[]>([]);
  const [inventoryCategories, setInventoryCategories] = useState<CategoryTreeNode[]>([]);

  // Keep state in sync if the parent swaps the product mid-flight (e.g. View → Edit).
  useEffect(() => {
    if (initialProduct) setForm(formFromProduct(initialProduct));
  }, [initialProduct]);

  // Sprint 2 Batch 2 category trees — fetched here rather than hoisted into
  // ProductsPage since they're only needed while this modal is open.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      categoriesApi.listSales({ is_active: 'true' }).then(asResults),
      categoriesApi.listInventory({ is_active: 'true' }).then(asResults),
    ])
      .then(([sales, inventory]) => {
        if (cancelled) return;
        setSalesCategories(sales);
        setInventoryCategories(inventory);
      })
      .catch(() => { /* non-critical — the selects just stay empty */ });
    return () => { cancelled = true; };
  }, []);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    if (fieldErrors[k]) {
      setFieldErrors((fe) => { const c = { ...fe }; delete c[k]; return c; });
    }
  };

  const validateLocal = (): string | null => {
    if (!form.name.trim())    return 'Name is required.';
    if (!form.barcode.trim()) return 'Barcode is required.';
    const price = Number(form.price);
    if (!form.price || Number.isNaN(price) || price <= 0) return 'Price must be greater than 0.';
    if (form.weighted) {
      const plu = form.plu.trim();
      if (!plu || plu.length > 10) return 'PLU code is required (1–10 characters) for weighted products.';
    }
    return null;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving || isView) return;
    setFormError(null);
    setFieldErrors({});

    const localError = validateLocal();
    if (localError) { setFormError(localError); return; }

    setSaving(true);
    try {
      const payload = buildPayload(form, tab, isEdit);
      const resp = isEdit && initialProduct
        ? await apiClient.patch<Product>(`/products/${initialProduct.id}/`, payload)
        : await apiClient.post<Product>('/products/', payload);
      onSuccess(isEdit ? 'updated' : 'created', resp.data);
    } catch (err) {
      const { fieldErrors: fe, formError: fmErr } = parseFieldErrors(err);
      setFieldErrors(fe);
      setFormError(fmErr);
    } finally {
      setSaving(false);
    }
  };

  const title =
    mode === 'view'   ? `Product · ${initialProduct?.name ?? ''}` :
    mode === 'edit'   ? `Edit product · ${initialProduct?.name ?? ''}` :
                        'New product';

  return (
    <Modal title={title} onClose={onClose} maxWidth="max-w-[640px]">
      <form onSubmit={submit} className="flex flex-col">
        {/* Tab switcher — hidden in view mode */}
        {!isView && (
          <div className="px-6 pt-4">
            <div className="inline-flex bg-neutral-100 rounded-md p-0.5">
              <TabButton active={tab === 'quick'} onClick={() => setTab('quick')} disabled={isEdit}>
                Quick Add
              </TabButton>
              <TabButton active={tab === 'full'} onClick={() => setTab('full')}>
                Full Add
              </TabButton>
            </div>
            {isEdit && (
              <span className="ms-3 text-[12px] text-neutral-500">
                Editing uses the full form.
              </span>
            )}
          </div>
        )}

        {/* Form error banner */}
        {formError && (
          <div className="mx-6 mt-4 flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <div className="p-6 grid grid-cols-2 gap-x-4 gap-y-3">
          <Field label="Name" required error={fieldErrors.name} className="col-span-2">
            <input
              type="text" value={form.name} disabled={isView || saving}
              onChange={(e) => set('name', e.target.value)}
              className={inputCls(!!fieldErrors.name, isView)}
            />
          </Field>

          <Field label="Barcode" required error={fieldErrors.barcode}>
            <input
              type="text" value={form.barcode} disabled={isView || saving}
              onChange={(e) => set('barcode', e.target.value)}
              className={inputCls(!!fieldErrors.barcode, isView)}
            />
          </Field>

          <Field label="Price" required error={fieldErrors.price}>
            <input
              type="number" step="0.01" min="0"
              value={form.price} disabled={isView || saving}
              onChange={(e) => set('price', e.target.value)}
              className={inputCls(!!fieldErrors.price, isView)}
            />
          </Field>

          <Field label="Cost" error={fieldErrors.cost}>
            <input
              type="number" step="0.01" min="0"
              value={form.cost} disabled={isView || isEdit || saving}
              onChange={(e) => set('cost', e.target.value)}
              className={inputCls(!!fieldErrors.cost, isView || isEdit)}
            />
          </Field>

          <Field label="Stock" error={fieldErrors.stock} hint="Supports decimals for weighted SKUs">
            <input
              type="number" min="0" step="0.001"
              value={form.stock} disabled={isView || saving}
              onChange={(e) => set('stock', e.target.value)}
              className={inputCls(!!fieldErrors.stock, isView)}
            />
          </Field>

          <Field label="Category" error={fieldErrors.category}>
            <select
              value={form.category} disabled={isView || saving}
              onChange={(e) => set('category', e.target.value)}
              className={inputCls(!!fieldErrors.category, isView)}
            >
              <option value="">— None —</option>
              {categories.map((c) => (
                <option key={c.id} value={String(c.id)}>{c.name}</option>
              ))}
            </select>
          </Field>

          <Field label="Unit" error={fieldErrors.unit}>
            <select
              value={form.unit} disabled={isView || saving}
              onChange={(e) => set('unit', e.target.value as ProductUnit)}
              className={inputCls(!!fieldErrors.unit, isView)}
            >
              {UNIT_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>

          <Field label="Pack qty" error={fieldErrors.pack_qty} hint="Pieces per sellable unit (e.g. 24 for a carton)">
            <input
              type="number" min="0.001" step="0.001"
              value={form.pack_qty} disabled={isView || saving}
              onChange={(e) => set('pack_qty', e.target.value)}
              className={inputCls(!!fieldErrors.pack_qty, isView)}
            />
          </Field>

          {/* Full-add-only fields */}
          {tab === 'full' && (
            <>
              <Field label="SKU" error={fieldErrors.sku}>
                <input
                  type="text" value={form.sku} placeholder="Defaults to barcode"
                  disabled={isView || saving}
                  onChange={(e) => set('sku', e.target.value)}
                  className={inputCls(!!fieldErrors.sku, isView)}
                />
              </Field>

              <Field label="Reorder point" error={fieldErrors.reorder}>
                <input
                  type="number" min="0" step="1"
                  value={form.reorder} disabled={isView || saving}
                  onChange={(e) => set('reorder', e.target.value)}
                  className={inputCls(!!fieldErrors.reorder, isView)}
                />
              </Field>

              <Field label="Tax rate (fraction)" error={fieldErrors.tax_rate}>
                <input
                  type="number" step="0.01" min="0" max="1"
                  value={form.tax_rate} disabled={isView || saving}
                  onChange={(e) => set('tax_rate', e.target.value)}
                  className={inputCls(!!fieldErrors.tax_rate, isView)}
                />
              </Field>

              <Field label="Color" error={fieldErrors.color}>
                <div className="flex items-center gap-2">
                  <input
                    type="color" value={form.color} disabled={isView || saving}
                    onChange={(e) => set('color', e.target.value)}
                    className="w-10 h-10 rounded-md border border-neutral-300 bg-white cursor-pointer disabled:cursor-not-allowed"
                  />
                  <input
                    type="text" value={form.color} disabled={isView || saving}
                    onChange={(e) => set('color', e.target.value)}
                    className={`${inputCls(!!fieldErrors.color, isView)} font-mono text-[12px]`}
                  />
                </div>
              </Field>

              <Field label="Product type" error={fieldErrors.product_type} className="col-span-2">
                <select
                  value={form.product_type} disabled={isView || saving}
                  onChange={(e) => set('product_type', e.target.value as ProductTypeValue)}
                  className={inputCls(!!fieldErrors.product_type, isView)}
                >
                  {PRODUCT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </Field>

              {initialProduct?.behavior && (
                <div className="col-span-2 -mt-1 flex flex-wrap gap-1.5">
                  {Object.entries(initialProduct.behavior)
                    .filter(([, v]) => v)
                    .map(([flag]) => (
                      <Badge key={flag} kind="gray">{flag.replace(/_/g, ' ')}</Badge>
                    ))}
                </div>
              )}

              <Field label="Sales category" error={fieldErrors.sales_category} hint="Menu/POS classification (Batch 2 tree) — independent of the legacy Category above.">
                <select
                  value={form.sales_category} disabled={isView || saving}
                  onChange={(e) => set('sales_category', e.target.value)}
                  className={inputCls(!!fieldErrors.sales_category, isView)}
                >
                  <option value="">— None —</option>
                  {flattenTree(salesCategories).map(({ node, depth }) => (
                    <option key={node.id} value={String(node.id)}>
                      {'  '.repeat(depth)}{depth > 0 ? '↳ ' : ''}{node.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Inventory category" error={fieldErrors.inventory_category} hint="Stock/purchasing classification (Batch 2 tree).">
                <select
                  value={form.inventory_category} disabled={isView || saving}
                  onChange={(e) => set('inventory_category', e.target.value)}
                  className={inputCls(!!fieldErrors.inventory_category, isView)}
                >
                  <option value="">— None —</option>
                  {flattenTree(inventoryCategories).map(({ node, depth }) => (
                    <option key={node.id} value={String(node.id)}>
                      {'  '.repeat(depth)}{depth > 0 ? '↳ ' : ''}{node.name}
                    </option>
                  ))}
                </select>
              </Field>

              <label className="flex items-center gap-2 text-[13px] text-neutral-700 mt-1">
                <input
                  type="checkbox" checked={form.weighted} disabled={isView || saving}
                  onChange={(e) => set('weighted', e.target.checked)}
                  className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
                />
                Weighted (priced by weight)
              </label>

              <label className="flex items-center gap-2 text-[13px] text-neutral-700 mt-1">
                <input
                  type="checkbox" checked={form.active} disabled={isView || saving}
                  onChange={(e) => set('active', e.target.checked)}
                  className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
                />
                Active (sellable)
              </label>

              <label className="flex items-center gap-2 text-[13px] text-neutral-700 mt-1">
                <input
                  type="checkbox" checked={form.show_on_pos} disabled={isView || saving}
                  onChange={(e) => set('show_on_pos', e.target.checked)}
                  className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
                />
                Show on POS
              </label>

              <label className="flex items-center gap-2 text-[13px] text-neutral-700 mt-1">
                <input
                  type="checkbox" checked={form.is_discountable} disabled={isView || saving}
                  onChange={(e) => set('is_discountable', e.target.checked)}
                  className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
                />
                Discountable
              </label>

              {/* PLU input — only relevant for weighted SKUs. The Digi scale
                  reads this PLU back inside the 13-digit weight barcode. */}
              {form.weighted && (
                <Field
                  label="PLU code"
                  required
                  error={fieldErrors.plu}
                  hint="1–10 chars. Used by the scale to identify this product (e.g. 00041)."
                  className="col-span-2"
                >
                  <input
                    type="text" inputMode="numeric" maxLength={10}
                    value={form.plu} disabled={isView || saving}
                    onChange={(e) => set('plu', e.target.value.replace(/\s/g, ''))}
                    placeholder="e.g. 00041"
                    className={`${inputCls(!!fieldErrors.plu, isView)} font-mono w-48`}
                  />
                </Field>
              )}
            </>
          )}
        </div>

        <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            {isView ? 'Close' : 'Cancel'}
          </Button>
          {!isView && (
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                  Saving…
                </>
              ) : isEdit ? 'Save changes' : 'Create product'}
            </Button>
          )}
        </div>
      </form>
    </Modal>
  );
};

/* ── Local helpers ────────────────────────────────────────────────────────── */

const TabButton: React.FC<React.PropsWithChildren<{
  active: boolean; onClick: () => void; disabled?: boolean;
}>> = ({ active, onClick, disabled, children }) => (
  <button
    type="button" onClick={onClick} disabled={disabled}
    className={`h-9 px-3 text-[13px] rounded focus-ring transition
      ${active ? 'bg-white shadow-sm font-semibold' : 'text-neutral-600 hover:text-neutral-900'}
      ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
  >
    {children}
  </button>
);

const Field: React.FC<React.PropsWithChildren<{
  label: string; required?: boolean; error?: string; hint?: string; className?: string;
}>> = ({ label, required, error, hint, className = '', children }) => (
  <label className={`flex flex-col gap-1 text-[12.5px] font-semibold text-neutral-700 ${className}`}>
    <span>
      {label}
      {required && <span className="text-danger-600 ms-0.5">*</span>}
    </span>
    {children}
    {error
      ? <span className="text-[12px] font-normal text-danger-600">{error}</span>
      : hint
        ? <span className="text-[12px] font-normal text-neutral-500">{hint}</span>
        : null}
  </label>
);

function inputCls(hasError: boolean, disabled: boolean) {
  return [
    'h-10 px-3 rounded-md border bg-white text-[14px] focus-ring',
    hasError ? 'border-danger-500' : 'border-neutral-300',
    disabled ? 'bg-neutral-50 text-neutral-500 cursor-not-allowed' : '',
  ].filter(Boolean).join(' ');
}
