import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import apiClient from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { Badge } from '../ui/Badge';
import { FormField, SelectField } from '../ui/FormField';
import { ProductTypeBadge, StockStatusBadge, PosVisibilityBadge } from '../ui/StatusBadges';
import { categoriesApi, asResults } from '../../api/erp';
import { flattenTree } from '../../utils/tree';
import { ProductCostHistoryDrawer } from './ProductCostHistoryDrawer';
import { RecipeWorkflowCard } from './RecipeWorkflowCard';
import { DerivedCostField } from './DerivedCostField';
import { useProductTypeMetadata, findTypeMetadata } from '../../hooks/useProductTypeMetadata';
import type { Product, ProductUnit } from '../../types';
import type { CategoryTreeNode, ProductTypeValue, ProductTypeMetadata } from '../../types/erp';

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

/** Single Source of Truth (Batch 8 architectural-improvement pass): field
 * visibility is derived ENTIRELY from `GET /catalog/product-types/`
 * (`pos.services.product_types.PRODUCT_TYPE_BEHAVIOR`, fetched once and
 * cached by `useProductTypeMetadata`) — there is no second, hand-copied
 * behavior matrix in this file anymore. This function is a pure renderer:
 * it maps server-supplied booleans to which sections/inputs show, nothing
 * more. Every rule this drives (can_sell, show_on_pos, affects_stock/
 * track_inventory) is still independently enforced server-side
 * (`ProductSerializer.validate`, `SaleSerializer`, `PurchaseInvoiceLine
 * Serializer`) regardless of what this form shows or hides — the backend
 * never trusts this. `meta` is `undefined` only before the metadata fetch
 * resolves; callers gate on that via `typesLoading`. */
function fieldVisibility(meta: ProductTypeMetadata | undefined) {
  const b = meta?.behavior;
  const required = new Set(meta?.required_fields ?? []);
  const recommended = new Set(meta?.recommended_fields ?? []);
  return {
    showSale: !!b?.can_sell,          // Sales section: Price, Tax rate, Sales category
    showStock: !!b?.track_inventory,  // Inventory section: Stock, Unit, Pack qty, Weighted, Inventory category
    showCost: !!b?.requires_cost,     // Accounting section: opening Cost (create) / read-only mirror (edit)
    canPurchase: !!b?.can_purchase,   // Purchasing section content
    showBuildRecipe: meta?.value === 'recipe_product', // Recipe section
    // Barcode Strategy: hidden entirely for types that never scan (Prep
    // Item, Service, Fixed Asset) — `meta` undefined (still loading) shows
    // it by default so the field doesn't flicker away then back on load.
    showBarcode: meta ? !!meta.barcode_visible : true,
    required,
    recommended,
  };
}

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
function buildPayload(form: FormState, tab: Tab, isEdit: boolean, typeMeta: ProductTypeMetadata | undefined) {
  const visibility = fieldVisibility(typeMeta);
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
    // Hidden fields still round-trip a safe value (the backend model
    // requires `price`/`stock` regardless of type) — this is a display
    // concern only, never a semantic override of anything the backend
    // itself enforces (can_sell/show_on_pos rejection stays backend-side).
    price:    visibility.showSale  ? form.price          : '0',
    stock:    visibility.showStock ? (form.stock || '0') : '0',
    unit:     form.unit,
    pack_qty: form.pack_qty || '1',
  };
  // `cost` is AVCO-derived once a product exists (Sprint 3 Batch 3) — the
  // backend rejects it on PATCH. Only a create sends it, as the opening
  // cost; the Cost field itself is disabled during edit (see the input
  // below) so this omission never silently drops an in-progress edit.
  if (!isEdit) payload.cost = visibility.showCost ? (form.cost || '0') : '0';
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
    payload.reorder  = visibility.showStock ? Number(form.reorder || 0) : 0;
    payload.tax_rate = visibility.showSale ? form.tax_rate : '0';
    payload.color    = form.color || HIDDEN_DEFAULTS.color;
    payload.weighted = visibility.showStock && form.weighted;
    payload.active   = form.active;
    payload.product_type = form.product_type;
    // A non-sellable type may never be shown on POS — the frontend half of
    // the backend enforcement (`ProductSerializer.validate`); the backend
    // is still the sole authority, this just avoids sending an obviously
    // wrong value for a field the user never saw an input for.
    payload.show_on_pos = visibility.showSale && form.show_on_pos;
    payload.is_discountable = visibility.showSale && form.is_discountable;
    if (visibility.showSale && form.sales_category) {
      payload.sales_category = Number(form.sales_category);
    }
    if (visibility.showStock && form.inventory_category) {
      payload.inventory_category = Number(form.inventory_category);
    }
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

type Visibility = ReturnType<typeof fieldVisibility>;
type FieldKey = keyof FormState;

/** Phase 3 (Enterprise UX Polish) — the ONE place client-side field rules
 * live, reused for both live inline validation (as the user types) and the
 * pre-submit check, so the two never drift apart. These mirror
 * backend-enforced constraints only (required fields, the `tax_rate`
 * 0-1 CHECK constraint, positive-quantity constraints) — never a new rule
 * invented client-side; the backend is always re-checked on submit
 * regardless of what this says. */
function computeFieldError(key: FieldKey, form: FormState, visibility: Visibility): string | undefined {
  switch (key) {
    case 'name':
      return form.name.trim() ? undefined : 'Name is required.';
    case 'price': {
      if (!visibility.showSale) return undefined;
      const n = Number(form.price);
      if (!form.price || Number.isNaN(n) || n <= 0) return 'Price must be greater than 0.';
      return undefined;
    }
    case 'tax_rate': {
      if (!visibility.showSale) return undefined;
      const n = Number(form.tax_rate);
      if (form.tax_rate === '' || Number.isNaN(n) || n < 0 || n > 1) {
        return 'Tax rate must be between 0 and 1 (e.g. 0.14 for 14%).';
      }
      return undefined;
    }
    case 'pack_qty': {
      if (!visibility.showStock) return undefined;
      const n = Number(form.pack_qty);
      if (!form.pack_qty || Number.isNaN(n) || n <= 0) return 'Pack quantity must be greater than 0.';
      return undefined;
    }
    case 'plu': {
      if (!(visibility.showStock && form.weighted)) return undefined;
      const plu = form.plu.trim();
      if (!plu) return 'PLU code is required for weighted products.';
      if (plu.length > 10) return 'PLU code must be 10 characters or fewer.';
      return undefined;
    }
    default:
      return undefined;
  }
}

const VALIDATED_KEYS: FieldKey[] = ['name', 'price', 'tax_rate', 'pack_qty', 'plu'];

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
  // Inline validation (item 4): a field's error is shown once the user has
  // interacted with it (blur) OR after a submit attempt — never on a
  // pristine, untouched field, so a blank required input doesn't scream
  // "invalid" the instant the form opens.
  const [touched, setTouched]       = useState<Partial<Record<FieldKey, boolean>>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const [salesCategories, setSalesCategories] = useState<CategoryTreeNode[]>([]);
  const [inventoryCategories, setInventoryCategories] = useState<CategoryTreeNode[]>([]);
  const [showCostHistory, setShowCostHistory] = useState(false);
  // Batch 8 production-readiness pass: shown in place of the form right
  // after a brand-new Recipe product is created, offering a direct link
  // into the Recipe Editor instead of leaving the user to navigate to
  // /recipes and search for the product they just made.
  const [justCreatedRecipeProduct, setJustCreatedRecipeProduct] = useState<Product | null>(null);
  const navigate = useNavigate();

  // Single Source of Truth: fetched once per session (cached), never
  // hand-copied — see `fieldVisibility`'s docstring above.
  const { data: typeMetaList, loading: typesLoading } = useProductTypeMetadata();
  const typeMeta = findTypeMetadata(typeMetaList, form.product_type);
  const visibility = fieldVisibility(typeMeta);

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
  const blur = (k: FieldKey) => setTouched((t) => (t[k] ? t : { ...t, [k]: true }));

  /** Server error wins (it's the backend's own word); otherwise fall back
   * to the live client-side rule, but only once the field is "dirty"
   * (touched or a submit was attempted). */
  const displayError = (k: FieldKey): string | undefined =>
    fieldErrors[k] ?? ((touched[k] || submitAttempted) ? computeFieldError(k, form, visibility) : undefined);

  const liveErrors = useMemo(
    () => VALIDATED_KEYS.map((k) => computeFieldError(k, form, visibility)).filter(Boolean),
    [form, visibility],
  );

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving || isView) return;
    setFormError(null);
    setFieldErrors({});
    setSubmitAttempted(true);

    if (liveErrors.length > 0) return; // inline errors are already visible; nothing more to say

    setSaving(true);
    try {
      const payload = buildPayload(form, tab, isEdit, typeMeta);
      const resp = isEdit && initialProduct
        ? await apiClient.patch<Product>(`/products/${initialProduct.id}/`, payload)
        : await apiClient.post<Product>('/products/', payload);
      // Batch 8 production-readiness pass: a brand-new Recipe product gets
      // a direct "Build Recipe" offer instead of just closing — the exact
      // journey requested (Save → Build Recipe → Recipe Editor, no
      // re-search). Editing an existing product (even to Recipe type)
      // still just closes normally; the persistent Recipe workflow card
      // (below) covers that case without hijacking every edit-save.
      if (!isEdit && resp.data.product_type === 'recipe_product') {
        setJustCreatedRecipeProduct(resp.data);
      } else {
        onSuccess(isEdit ? 'updated' : 'created', resp.data);
      }
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

  // Batch 8 production-readiness pass: the "Product → Save → Build Recipe
  // → Recipe Editor" journey — a brand-new Recipe product goes straight to
  // this screen instead of the modal just closing. Confirms item 6's
  // constraint too: "Build Recipe" only ever appears once the product was
  // actually created (this screen literally cannot render before then).
  if (justCreatedRecipeProduct) {
    return (
      <Modal title="Recipe product created" onClose={() => onSuccess('created', justCreatedRecipeProduct)} maxWidth="max-w-[480px]">
        <div className="p-6 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-full bg-success-50 text-success-600 grid place-items-center">
            <Icon name="check" size={22} />
          </div>
          <div>
            <div className="text-[15px] font-semibold text-neutral-900">
              "{justCreatedRecipeProduct.name}" created
            </div>
            <p className="text-[13px] text-neutral-500 mt-1">
              This is a Recipe product — it needs a Bill of Materials before it can be
              sold. Build it now, or come back to it later from the Recipes app.
            </p>
          </div>
          <div className="flex gap-2 w-full mt-2">
            <Button
              variant="secondary" className="flex-1"
              onClick={() => onSuccess('created', justCreatedRecipeProduct)}
            >
              Later
            </Button>
            <Button
              className="flex-1"
              onClick={() => {
                const product = justCreatedRecipeProduct;
                onSuccess('created', product);
                navigate(`/recipes/new?product_id=${product.id}`);
              }}
            >
              <Icon name="layers" size={14} /> Build Recipe
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  const savingProps = { disabled: isView || saving, readOnly: isView };

  return (
    <>
    <Modal title={title} onClose={onClose} maxWidth={tab === 'full' ? 'max-w-[760px]' : 'max-w-[640px]'}>
      {/* `noValidate`: item 4 explicitly forbids relying on browser popup
          alerts for validation — every rule below surfaces inline at its
          own field (`computeFieldError`/`displayError`) instead. Without
          this, the native "Please fill out this field" tooltip would fire
          on submit and swallow the event before our own handler runs. */}
      <form onSubmit={submit} noValidate className="flex flex-col max-h-[80vh]">
        {/* Tab switcher — hidden in view mode */}
        {!isView && (
          <div className="px-6 pt-4 flex items-center gap-3 flex-wrap">
            <div className="inline-flex bg-neutral-100 rounded-md p-0.5">
              <TabButton active={tab === 'quick'} onClick={() => setTab('quick')} disabled={isEdit}>
                Quick Add
              </TabButton>
              <TabButton active={tab === 'full'} onClick={() => setTab('full')}>
                Full Add
              </TabButton>
            </div>
            {isEdit && (
              <span className="text-[12px] text-neutral-500">
                Editing uses the full form.
              </span>
            )}
            {initialProduct && (
              <div className="flex items-center gap-1.5 ms-auto">
                <ProductTypeBadge productType={initialProduct.product_type} />
                {visibility.showStock && (
                  <StockStatusBadge stock={Number(form.stock)} reorder={Number(form.reorder)} />
                )}
                {typeMeta && <PosVisibilityBadge showOnPos={form.show_on_pos} canSell={visibility.showSale} />}
              </div>
            )}
          </div>
        )}

        {/* Form error banner — reserved for SERVER-side errors only; every
            client-known rule surfaces inline at its own field instead of a
            popup/banner (item 4). */}
        {formError && (
          <div className="mx-6 mt-4 flex items-start gap-2 rounded-md border border-danger-500/30 bg-danger-50 px-3 py-2.5 text-[13px] text-danger-700">
            <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <div className="p-6 overflow-y-auto space-y-6">
          {/* ── General ─────────────────────────────────────────────── */}
          <Section title="General" icon="doc" description="Identity — how this product is found and named.">
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <FormField
                label="Name" required showValid
                value={form.name} onBlur={() => blur('name')}
                error={displayError('name')}
                disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                onChange={(e) => set('name', e.target.value)}
                containerClassName="col-span-2"
              />
              {/* Barcode Strategy: optional for every type, shown for every
                  type except Prep Item / Service / Fixed Asset (which never
                  scan — Name/SKU stay the identifier instead). Driven
                  entirely by backend metadata, never a hardcoded list here. */}
              {visibility.showBarcode && (
                <FormField
                  label="Barcode"
                  hint="Optional — used for POS scanning. Leave blank if this item isn't scanned."
                  value={form.barcode}
                  disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                  onChange={(e) => set('barcode', e.target.value)}
                />
              )}
              <SelectField
                label="Category" hint="Legacy flat category — kept for backward compatibility."
                value={form.category} disabled={savingProps.disabled}
                onChange={(e) => set('category', e.target.value)}
              >
                <option value="">— None —</option>
                {categories.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
              </SelectField>

              {tab === 'full' && (
                <>
                  <FormField
                    label="SKU" hint="Defaults to barcode when left blank."
                    value={form.sku} disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                    onChange={(e) => set('sku', e.target.value)}
                  />
                  <SelectField
                    label="Product type" loading={typesLoading}
                    hint="Governs every section below — required fields, sale/purchase/inventory behavior."
                    value={form.product_type} disabled={savingProps.disabled || typesLoading}
                    onChange={(e) => set('product_type', e.target.value as ProductTypeValue)}
                  >
                    {(typeMetaList ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </SelectField>

                  <div className="flex items-center gap-2">
                    <input
                      type="color" value={form.color} disabled={savingProps.disabled}
                      onChange={(e) => set('color', e.target.value)}
                      className="w-10 h-10 rounded-md border border-neutral-300 bg-white cursor-pointer disabled:cursor-not-allowed"
                    />
                    <FormField
                      label="Color"
                      value={form.color} disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                      onChange={(e) => set('color', e.target.value)}
                      className="font-mono text-[12px]"
                      containerClassName="flex-1"
                    />
                  </div>

                  <CheckboxField
                    label="Active (sellable)"
                    checked={form.active} disabled={savingProps.disabled}
                    onChange={(v) => set('active', v)}
                  />

                  {initialProduct?.behavior && (
                    <div className="col-span-2 -mt-1 flex flex-wrap gap-1.5">
                      {Object.entries(initialProduct.behavior)
                        .filter(([, v]) => v)
                        .map(([flag]) => (
                          <Badge key={flag} kind="gray">{flag.replace(/_/g, ' ')}</Badge>
                        ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </Section>

          {/* ── Sales ───────────────────────────────────────────────── */}
          {visibility.showSale && (
            <Section title="Sales" icon="cash" description="What a customer pays and where this shows up on the menu.">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <FormField
                  label="Price" required showValid
                  type="number" step="0.01" min="0"
                  value={form.price} onBlur={() => blur('price')}
                  error={displayError('price')}
                  disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                  onChange={(e) => set('price', e.target.value)}
                />
                {tab === 'full' && (
                  <FormField
                    label="Tax rate (fraction)"
                    type="number" step="0.01" min="0" max="1"
                    value={form.tax_rate} onBlur={() => blur('tax_rate')}
                    error={displayError('tax_rate')}
                    disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                    onChange={(e) => set('tax_rate', e.target.value)}
                  />
                )}
                {tab === 'full' && (
                  <SelectField
                    label="Sales category"
                    recommended={visibility.recommended.has('sales_category')}
                    hint="Menu/POS classification (category tree) — independent of the legacy Category above."
                    value={form.sales_category} disabled={savingProps.disabled}
                    onChange={(e) => set('sales_category', e.target.value)}
                    containerClassName="col-span-2"
                  >
                    <option value="">— None —</option>
                    {flattenTree(salesCategories).map(({ node, depth }) => (
                      <option key={node.id} value={String(node.id)}>
                        {'  '.repeat(depth)}{depth > 0 ? '↳ ' : ''}{node.name}
                      </option>
                    ))}
                  </SelectField>
                )}
              </div>
            </Section>
          )}

          {/* ── Inventory ───────────────────────────────────────────── */}
          {visibility.showStock && tab === 'full' && (
            <Section title="Inventory" icon="box" description="What's on hand and how it's counted.">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <FormField
                  label="Stock" hint="Supports decimals for weighted SKUs."
                  type="number" min="0" step="0.001"
                  value={form.stock} disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                  onChange={(e) => set('stock', e.target.value)}
                />
                <SelectField
                  label="Unit"
                  value={form.unit} disabled={savingProps.disabled}
                  onChange={(e) => set('unit', e.target.value as ProductUnit)}
                >
                  {UNIT_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}
                </SelectField>
                <FormField
                  label="Pack qty" hint="Pieces per sellable unit (e.g. 24 for a carton)."
                  type="number" min="0.001" step="0.001"
                  value={form.pack_qty} onBlur={() => blur('pack_qty')}
                  error={displayError('pack_qty')}
                  disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                  onChange={(e) => set('pack_qty', e.target.value)}
                />
                <SelectField
                  label="Inventory category"
                  recommended={visibility.recommended.has('inventory_category')}
                  hint="Stock/purchasing classification (category tree)."
                  value={form.inventory_category} disabled={savingProps.disabled}
                  onChange={(e) => set('inventory_category', e.target.value)}
                >
                  <option value="">— None —</option>
                  {flattenTree(inventoryCategories).map(({ node, depth }) => (
                    <option key={node.id} value={String(node.id)}>
                      {'  '.repeat(depth)}{depth > 0 ? '↳ ' : ''}{node.name}
                    </option>
                  ))}
                </SelectField>

                <CheckboxField
                  label="Weighted (priced by weight)"
                  checked={form.weighted} disabled={savingProps.disabled}
                  onChange={(v) => set('weighted', v)}
                />

                {form.weighted && (
                  <FormField
                    label="PLU code" required
                    hint="1–10 chars. Used by the scale to identify this product (e.g. 00041)."
                    inputMode="numeric" maxLength={10} placeholder="e.g. 00041"
                    value={form.plu} onBlur={() => blur('plu')}
                    error={displayError('plu')}
                    disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                    onChange={(e) => set('plu', e.target.value.replace(/\s/g, ''))}
                    className="font-mono"
                    containerClassName="col-span-2 max-w-[220px]"
                  />
                )}
              </div>
            </Section>
          )}

          {/* ── Purchasing ──────────────────────────────────────────── */}
          {tab === 'full' && (
            <Section title="Purchasing" icon="truck" description="Whether — and how — this product is replenished.">
              {visibility.canPurchase ? (
                <div className="flex items-center gap-3">
                  <Badge kind="success">Can be purchased</Badge>
                  {visibility.showStock && (
                    <FormField
                      label="Reorder point" hint="Low-stock alert threshold."
                      type="number" min="0" step="1"
                      value={form.reorder} disabled={savingProps.disabled} readOnly={savingProps.readOnly}
                      onChange={(e) => set('reorder', e.target.value)}
                      containerClassName="max-w-[160px]"
                    />
                  )}
                </div>
              ) : (
                <div className="flex items-start gap-2 text-[12.5px] text-neutral-500">
                  <Badge kind="gray">Not purchasable</Badge>
                  <span>
                    "{typeMeta?.label ?? form.product_type}" products are rejected by purchase
                    invoices ({visibility.showBuildRecipe ? 'assembled from a recipe' : 'not stocked directly'}) —
                    enforced server-side, not just hidden here.
                  </span>
                </div>
              )}
            </Section>
          )}

          {/* ── Recipe ──────────────────────────────────────────────── */}
          {visibility.showBuildRecipe && tab === 'full' && isEdit && initialProduct && (
            <Section title="Recipe" icon="layers" description="The Bill of Materials this product sells through.">
              <RecipeWorkflowCard
                productId={initialProduct.id}
                canSell={visibility.showSale}
                showOnPos={form.show_on_pos}
              />
            </Section>
          )}

          {/* ── Accounting ──────────────────────────────────────────── */}
          {(visibility.showCost || (visibility.showBuildRecipe && (isEdit || isView))) && tab === 'full' && (
            <Section title="Accounting" icon="chart" description="Cost basis and margin.">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                {visibility.showCost && (
                  <FormField
                    label="Cost"
                    hint={
                      (isEdit || isView) && initialProduct
                        ? 'Calculated automatically (moving-average) from purchases and stock counts.'
                        : 'Opening cost — used to seed the moving-average once this product is created.'
                    }
                    type="number" step="0.01" min="0"
                    value={form.cost} disabled={savingProps.disabled || isEdit} readOnly={isView || isEdit}
                    onChange={(e) => set('cost', e.target.value)}
                  />
                )}
                {visibility.showCost && (isEdit || isView) && initialProduct && (
                  <div className="flex items-end pb-1">
                    <button
                      type="button" onClick={() => setShowCostHistory(true)}
                      className="text-[12.5px] text-brand-600 hover:underline font-semibold"
                    >
                      View cost history →
                    </button>
                  </div>
                )}
                {/* Recipe products have no cost of their own to enter — a
                    real, live, server-computed derived-cost BREAKDOWN
                    (item 7) instead of hiding the section or showing a
                    single opaque number. */}
                {!visibility.showCost && visibility.showBuildRecipe && (isEdit || isView) && initialProduct && (
                  <DerivedCostField productId={initialProduct.id} />
                )}
                {typeof initialProduct?.margin === 'number' && (
                  <div>
                    <div className="text-[12.5px] font-semibold text-neutral-700 mb-1.5">Margin</div>
                    <div className="h-10 flex items-center">
                      <Badge kind={initialProduct.margin >= 0 ? 'success' : 'danger'} size="md">
                        {initialProduct.margin.toFixed(0)}%
                      </Badge>
                    </div>
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* ── POS ──────────────────────────────────────────────────── */}
          {visibility.showSale && tab === 'full' && (
            <Section title="POS" icon="pos" description="Visibility and pricing behavior at the register.">
              <div className="flex flex-col gap-2">
                <CheckboxField
                  label="Show on POS"
                  checked={form.show_on_pos} disabled={savingProps.disabled}
                  onChange={(v) => set('show_on_pos', v)}
                />
                <CheckboxField
                  label="Discountable"
                  checked={form.is_discountable} disabled={savingProps.disabled}
                  onChange={(v) => set('is_discountable', v)}
                />
              </div>
            </Section>
          )}
        </div>

        <div className="px-6 h-14 border-t border-neutral-200 flex items-center justify-end gap-2 shrink-0">
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
    {showCostHistory && initialProduct && (
      <ProductCostHistoryDrawer product={initialProduct} onClose={() => setShowCostHistory(false)} />
    )}
    </>
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

/** A workflow section — a titled group with an icon + one-line description,
 * consistent across the whole form (item 2: organize into General/Sales/
 * Inventory/Purchasing/Recipe/Accounting/POS; item 10: standardized
 * spacing/typography). A section that has no visible fields for the
 * current product type is simply never rendered by its caller — this
 * component doesn't hide itself, callers gate on `visibility` so the
 * "which sections exist" decision stays in one place (`fieldVisibility`). */
const Section: React.FC<React.PropsWithChildren<{ title: string; icon: string; description: string }>> = ({
  title, icon, description, children,
}) => (
  <section>
    <div className="flex items-center gap-2 mb-3 pb-2 border-b border-neutral-100">
      <div className="w-7 h-7 rounded-md bg-neutral-100 text-neutral-500 grid place-items-center shrink-0">
        <Icon name={icon} size={14} />
      </div>
      <div>
        <h3 className="text-[13px] font-bold text-neutral-800">{title}</h3>
        <p className="text-[11.5px] text-neutral-400 leading-tight">{description}</p>
      </div>
    </div>
    {children}
  </section>
);

const CheckboxField: React.FC<{
  label: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void;
}> = ({ label, checked, disabled, onChange }) => (
  <label className={`flex items-center gap-2 text-[13px] text-neutral-700 ${disabled ? 'opacity-60' : ''}`}>
    <input
      type="checkbox" checked={checked} disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      className="w-4 h-4 rounded border-neutral-300 text-brand-500 focus-ring"
    />
    {label}
  </label>
);
