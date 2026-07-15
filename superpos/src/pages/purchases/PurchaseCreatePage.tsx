import React, { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';
import { Header } from '../../components/layout/Header';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { SelectField, FormField, TextAreaField } from '../../components/ui/FormField';
import { AlertBanner } from '../../components/ui/states';
import { PaymentRouteLabel } from '../../components/erp/PaymentRouteLabel';
import { branchesApi, financeApi, purchasesApi, productUnitsApi, suppliersApi, warehousesApi, asResults } from '../../api/erp';
import { generateIdempotencyKey } from '../../api/idempotency';
import { useQuery, useDebounced } from '../../hooks/useQuery';
import { parseApiError, type ApiError } from '../../utils/apiError';
import { useMoney } from '../../utils/money';
import { useAuthStore } from '../../store/authStore';
import {
  COMPATIBLE_DESTINATIONS,
  type Paginated,
  type PaymentMethodType,
  type ProductUnit,
  type PurchaseInvoicePayload,
} from '../../types/erp';

/* ─────────────────────────────────────────────────────────────────────────────
 * Create + post a stock-item purchase invoice (backend Slice H).
 * Only `stock_item` lines are exposed — expense / service / fixed-asset /
 * non-stock line types are deliberately NOT selectable (unsupported flows).
 *
 * The POST carries an Idempotency-Key that stays stable for the lifetime
 * of this form, so a retry after a network timeout replays the original
 * posting instead of double-receiving stock.
 * ──────────────────────────────────────────────────────────────────────────── */

interface ProductLite {
  id: number;
  name: string;
  sku?: string;
  barcode?: string;
  cost?: number | string;
}

interface LineDraft {
  key: string;
  product: ProductLite | null;
  // Quantity in whichever unit this line is denominated in — the product's
  // base unit by default, or `productUnit`'s unit when one is chosen below.
  qty: string;
  unit_cost: string;
  discount_amount: string;
  tax_amount: string;
  /** Purchase-eligible ProductUnits for the picked product (Sprint 2). Empty
   * until a product is picked; a product with none configured behaves
   * exactly as before — plain base-unit qty/unit_cost. */
  purchaseUnits: ProductUnit[];
  /** Non-base unit chosen for this line, if any. */
  productUnit: ProductUnit | null;
}

const newLine = (): LineDraft => ({
  key: `l${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
  product: null,
  qty: '1',
  unit_cost: '',
  discount_amount: '',
  tax_amount: '',
  purchaseUnits: [],
  productUnit: null,
});

/* ── Inline product search picker ───────────────────────────────────────── */

const ProductPicker: React.FC<{
  value: ProductLite | null;
  onPick: (p: ProductLite | null) => void;
}> = ({ value, onPick }) => {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(term, 300);
  const boxRef = useRef<HTMLDivElement>(null);

  const q = useQuery(
    () =>
      debounced.trim().length >= 1 && open
        ? apiClient
            .get<Paginated<ProductLite>>('/products/', { params: { search: debounced.trim(), page_size: 10 } })
            .then((r) => r.data.results)
        : Promise.resolve([] as ProductLite[]),
    [debounced, open],
  );

  if (value) {
    return (
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-semibold text-[13.5px] truncate">{value.name}</span>
        <button
          type="button"
          onClick={() => { onPick(null); setTerm(''); }}
          aria-label="Change product"
          className="text-neutral-400 hover:text-neutral-600 shrink-0"
        >
          <Icon name="x" size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="relative" ref={boxRef}>
      <input
        value={term}
        onChange={(e) => { setTerm(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search product name / SKU / barcode…"
        className="w-full h-9 px-2.5 rounded-md border border-neutral-300 bg-white text-[13px] focus-ring"
      />
      {open && term.trim().length >= 1 && (
        <div className="absolute z-20 top-10 start-0 w-full min-w-[260px] bg-white border border-neutral-200 rounded-md shadow-lg max-h-56 overflow-y-auto">
          {q.loading ? (
            <div className="px-3 py-2 text-[12.5px] text-neutral-400">Searching…</div>
          ) : (q.data ?? []).length === 0 ? (
            <div className="px-3 py-2 text-[12.5px] text-neutral-400">No products found for “{term.trim()}”.</div>
          ) : (
            (q.data ?? []).map((p) => (
              <button
                key={p.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onPick(p); setOpen(false); }}
                className="w-full text-start px-3 py-2 hover:bg-neutral-50 text-[13px]"
              >
                <div className="font-semibold">{p.name}</div>
                <div className="text-[11.5px] text-neutral-400 font-mono">
                  {p.sku || p.barcode || `#${p.id}`}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
};

/* ── Page ───────────────────────────────────────────────────────────────── */

export const PurchaseCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const money = useMoney();
  const userBranch = useAuthStore((s) => s.user?.branch);

  const [supplierId, setSupplierId] = useState<number | ''>('');
  const [branchId, setBranchId] = useState<number | ''>(userBranch ?? '');
  const [warehouseId, setWarehouseId] = useState<number | ''>('');
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([newLine()]);
  const [paidAmount, setPaidAmount] = useState('');
  const [methodId, setMethodId] = useState<number | ''>('');
  const [sourceAccountId, setSourceAccountId] = useState<number | ''>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});
  // Stable per-form key: retries of the same submission replay, not repost.
  const idemKey = useRef(generateIdempotencyKey());

  const suppliersQ = useQuery(() => suppliersApi.list({ is_active: 'true', page_size: 200 }), []);
  const branchesQ = useQuery(() => branchesApi.list().then(asResults), []);
  const warehousesQ = useQuery(() => warehousesApi.list({ page_size: 200 }), []);
  const methodsQ = useQuery(() => financeApi.listPaymentMethods({ page_size: 100 }), []);
  const accountsQ = useQuery(() => financeApi.listAccounts({ page_size: 200 }), []);

  const methods = (methodsQ.data?.results ?? []).filter((m) => m.is_active && m.method_type !== 'credit');
  const selectedMethod = methods.find((m) => m.id === methodId);
  const compatibleAccounts = useMemo(() => {
    const active = (accountsQ.data?.results ?? []).filter((a) => a.is_active);
    if (!selectedMethod) return active;
    const allowed = COMPATIBLE_DESTINATIONS[selectedMethod.method_type as PaymentMethodType];
    return allowed ? active.filter((a) => allowed.includes(a.account_type)) : active;
  }, [accountsQ.data, selectedMethod]);

  const warehouses = (warehousesQ.data?.results ?? []).filter((w) => w.is_active);

  const setLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const lineTotal = (l: LineDraft): number => {
    const qty = Number(l.qty) || 0;
    const cost = Number(l.unit_cost) || 0;
    const disc = Number(l.discount_amount) || 0;
    const tax = Number(l.tax_amount) || 0;
    return qty * cost - disc + tax;
  };

  const totals = useMemo(() => {
    const subtotal = lines.reduce((s, l) => s + (Number(l.qty) || 0) * (Number(l.unit_cost) || 0), 0);
    const discount = lines.reduce((s, l) => s + (Number(l.discount_amount) || 0), 0);
    const tax = lines.reduce((s, l) => s + (Number(l.tax_amount) || 0), 0);
    const total = subtotal - discount + tax;
    const paid = Number(paidAmount) || 0;
    return { subtotal, discount, tax, total, paid, credit: Math.max(0, total - paid) };
  }, [lines, paidAmount]);

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!supplierId) errs.supplier = 'Select a supplier.';
    if (!branchId) errs.branch = 'Select a branch.';
    const usable = lines.filter((l) => l.product);
    if (usable.length === 0) errs.lines = 'Add at least one product line.';
    for (const l of usable) {
      if (!(Number(l.qty) > 0)) { errs.lines = 'Every line needs a quantity greater than zero.'; break; }
      if (!(Number(l.unit_cost) >= 0) || l.unit_cost === '') { errs.lines = 'Every line needs a unit cost.'; break; }
      // Client-side mirror of the backend's minimum_order_qty guard — fast
      // feedback only; the server check on post is authoritative either way.
      const minQty = l.productUnit?.minimum_order_qty;
      if (minQty && Number(l.qty) < Number(minQty)) {
        errs.lines = `${l.product?.name}: quantity must be at least ${minQty} ${l.productUnit?.unit_name} (minimum order qty).`;
        break;
      }
    }
    const paid = Number(paidAmount) || 0;
    if (paid < 0) errs.paid_amount = 'Paid amount cannot be negative.';
    if (paid > 0 && !methodId) errs.payment_method = 'Select how the paid amount was paid.';
    if (paid > 0 && !sourceAccountId) errs.source_account = 'Select the account the money left.';
    if (paid > totals.total + 0.005) errs.paid_amount = 'Paid amount cannot exceed the invoice total.';
    setLocalErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const submit = async () => {
    if (busy) return;
    setError(null);
    if (!validate()) return;
    const payload: PurchaseInvoicePayload = {
      branch: Number(branchId),
      supplier: Number(supplierId),
      reference: reference.trim() || undefined,
      notes: notes.trim() || undefined,
      paid_amount: (Number(paidAmount) || 0).toFixed(2),
      payment_method: Number(paidAmount) > 0 && methodId ? Number(methodId) : undefined,
      source_account: Number(paidAmount) > 0 && sourceAccountId ? Number(sourceAccountId) : undefined,
      lines: lines
        .filter((l) => l.product)
        .map((l) => ({
          product: l.product!.id,
          warehouse: warehouseId ? Number(warehouseId) : undefined,
          line_type: 'stock_item' as const,
          // Unit-aware line: server derives qty via convert_to_base — never
          // send both shapes.
          ...(l.productUnit
            ? { product_unit: l.productUnit.id, entered_qty: Number(l.qty).toFixed(3) }
            : { qty: Number(l.qty).toFixed(3) }),
          unit_cost: Number(l.unit_cost).toFixed(2),
          discount_amount: (Number(l.discount_amount) || 0).toFixed(2),
          tax_amount: (Number(l.tax_amount) || 0).toFixed(2),
        })),
    };
    setBusy(true);
    try {
      const created = await purchasesApi.create(payload, idemKey.current);
      navigate(`/purchases/${created.id}`, { replace: true });
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const err = (k: string) => localErrors[k] ?? error?.fieldErrors[k];

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-auto">
      <Header title="New purchase invoice" subtitle="Stock items only · posts immediately on save" />
      <div className="p-5 max-w-[980px] w-full mx-auto space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/purchases')}>
          <Icon name="chevL" size={15} className="rtl:rotate-180" /> Back to purchases
        </Button>

        {error && Object.keys(error.fieldErrors).length === 0 && (
          <AlertBanner tone={error.permissionDenied ? 'warn' : 'danger'} title={error.code === 'IDEMPOTENCY_CONFLICT' ? 'Duplicate submission' : undefined}>
            {error.message}
          </AlertBanner>
        )}

        <Card>
          <CardHeader title="Supplier & destination" />
          <CardBody className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <SelectField
              label="Supplier" required value={supplierId} error={err('supplier')}
              onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">{suppliersQ.loading ? 'Loading…' : 'Select supplier'}</option>
              {(suppliersQ.data?.results ?? []).map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </SelectField>
            <SelectField
              label="Branch" required value={branchId} error={err('branch')}
              onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">{branchesQ.loading ? 'Loading…' : 'Select branch'}</option>
              {(branchesQ.data ?? []).map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </SelectField>
            <SelectField
              label="Receive into warehouse" value={warehouseId} error={err('warehouse')}
              onChange={(e) => setWarehouseId(e.target.value ? Number(e.target.value) : '')}
              hint="Leave empty to use the branch's default warehouse."
            >
              <option value="">Branch default</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </SelectField>
            <FormField
              label="Supplier reference" value={reference} maxLength={120} error={err('reference')}
              onChange={(e) => setReference(e.target.value)} hint="Supplier invoice no. (optional)"
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Lines (stock items)"
            actions={
              <Button variant="secondary" size="sm" onClick={() => setLines((ls) => [...ls, newLine()])}>
                <Icon name="plus" size={14} /> Add line
              </Button>
            }
          />
          <CardBody className="p-0">
            {localErrors.lines && (
              <div className="px-4 pt-3"><AlertBanner tone="danger">{localErrors.lines}</AlertBanner></div>
            )}
            {error?.fieldErrors.lines && (
              <div className="px-4 pt-3"><AlertBanner tone="danger">{error.fieldErrors.lines}</AlertBanner></div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px]">
                <thead>
                  <tr>
                    {['Product', 'Qty', 'Unit cost', 'Discount', 'Tax', 'Line total', ''].map((h, i) => (
                      <th key={h || 'x'} className={`text-[11px] uppercase tracking-wider text-neutral-500 font-bold px-3 py-2.5 border-b border-neutral-200 bg-neutral-50 ${i > 0 && i < 6 ? 'text-end' : 'text-start'}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => (
                    <tr key={l.key}>
                      <td className="px-3 py-2 border-b border-neutral-100 min-w-[240px]">
                        <ProductPicker
                          value={l.product}
                          onPick={(p) => {
                            setLine(l.key, {
                              product: p,
                              // Prefill from catalog cost; editable.
                              unit_cost: p && l.unit_cost === '' && p.cost !== undefined ? String(p.cost) : l.unit_cost,
                              purchaseUnits: [],
                              productUnit: null,
                            });
                            if (p) {
                              productUnitsApi.list(p.id).then(asResults).then((units) => {
                                setLine(l.key, {
                                  purchaseUnits: units.filter((u) => u.is_active && u.is_purchase_unit && !u.is_base),
                                });
                              }).catch(() => {});
                            }
                          }}
                        />
                        {l.product && l.purchaseUnits.length > 0 && (
                          <select
                            value={l.productUnit?.id ?? ''}
                            onChange={(e) => {
                              const unit = l.purchaseUnits.find((u) => u.id === Number(e.target.value)) ?? null;
                              setLine(l.key, { productUnit: unit });
                            }}
                            className="mt-1.5 w-full h-8 px-2 rounded-md border border-neutral-300 bg-white text-[12px] focus-ring"
                            aria-label="Purchase unit"
                          >
                            <option value="">Base unit</option>
                            {l.purchaseUnits.map((u) => (
                              <option key={u.id} value={u.id}>
                                {u.unit_name} (× {u.conversion_to_base})
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      {(['qty', 'unit_cost', 'discount_amount', 'tax_amount'] as const).map((f) => (
                        <td key={f} className="px-3 py-2 border-b border-neutral-100 w-28">
                          <input
                            type="number"
                            min="0"
                            step={f === 'qty' ? '0.001' : '0.01'}
                            inputMode="decimal"
                            value={l[f]}
                            onChange={(e) => setLine(l.key, { [f]: e.target.value } as Partial<LineDraft>)}
                            className="w-full h-9 px-2 rounded-md border border-neutral-300 bg-white text-[13px] text-end font-mono focus-ring"
                            aria-label={f.replace(/_/g, ' ')}
                          />
                        </td>
                      ))}
                      <td className="px-3 py-2 border-b border-neutral-100 text-end font-mono font-bold text-[13.5px] w-28">
                        {money(lineTotal(l))}
                      </td>
                      <td className="px-2 py-2 border-b border-neutral-100 w-10">
                        <button
                          type="button"
                          onClick={() => setLines((ls) => (ls.length > 1 ? ls.filter((x) => x.key !== l.key) : ls.map((x) => (x.key === l.key ? newLine() : x))))}
                          aria-label="Remove line"
                          className="w-8 h-8 grid place-items-center rounded-md text-danger-600 hover:bg-danger-50 focus-ring"
                        >
                          <Icon name="trash" size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader title="Payment" />
            <CardBody className="space-y-4">
              <FormField
                label="Paid now" type="number" min="0" step="0.01" inputMode="decimal"
                value={paidAmount} error={err('paid_amount')}
                onChange={(e) => setPaidAmount(e.target.value)}
                hint="Leave 0 to record the full amount as supplier credit (AP)."
              />
              {Number(paidAmount) > 0 && (
                <>
                  <SelectField
                    label="Payment method" required value={methodId} error={err('payment_method')}
                    onChange={(e) => { setMethodId(e.target.value ? Number(e.target.value) : ''); setSourceAccountId(''); }}
                  >
                    <option value="">{methodsQ.loading ? 'Loading…' : 'Select method'}</option>
                    {methods.map((m) => (
                      <option key={m.id} value={m.id}>{m.name} ({m.method_type})</option>
                    ))}
                  </SelectField>
                  {selectedMethod && (
                    <PaymentRouteLabel methodType={selectedMethod.method_type as PaymentMethodType} />
                  )}
                  <SelectField
                    label="Pay from account" required value={sourceAccountId} error={err('source_account')}
                    onChange={(e) => setSourceAccountId(e.target.value ? Number(e.target.value) : '')}
                    hint="Only accounts compatible with the selected method are listed."
                  >
                    <option value="">{accountsQ.loading ? 'Loading…' : 'Select account'}</option>
                    {compatibleAccounts.map((a) => (
                      <option key={a.id} value={a.id}>{a.name} ({a.account_type.replace(/_/g, ' ')})</option>
                    ))}
                  </SelectField>
                </>
              )}
              <TextAreaField label="Notes" value={notes} error={err('notes')} onChange={(e) => setNotes(e.target.value)} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Totals" />
            <CardBody className="space-y-1.5 text-[13.5px]">
              <div className="flex justify-between"><span className="text-neutral-500">Subtotal</span><span className="font-mono">{money(totals.subtotal)}</span></div>
              <div className="flex justify-between"><span className="text-neutral-500">Discount</span><span className="font-mono">−{money(totals.discount)}</span></div>
              <div className="flex justify-between"><span className="text-neutral-500">Tax</span><span className="font-mono">{money(totals.tax)}</span></div>
              <div className="flex justify-between pt-2 mt-1 border-t border-neutral-200 text-[15px] font-extrabold">
                <span>Total</span><span className="font-mono">{money(totals.total)}</span>
              </div>
              <div className="flex justify-between"><span className="text-neutral-500">Paid now</span><span className="font-mono">{money(totals.paid)}</span></div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Remains on credit (AP)</span>
                <span className={`font-mono font-bold ${totals.credit > 0 ? 'text-warn-700' : ''}`}>{money(totals.credit)}</span>
              </div>
              <div className="pt-3">
                <AlertBanner tone="warn">
                  Saving posts this invoice immediately: stock is received, product costs update, and any unpaid
                  remainder becomes supplier AP. Posted invoices are read-only.
                </AlertBanner>
              </div>
              <Button className="w-full mt-2" size="lg" onClick={submit} disabled={busy}>
                {busy ? 'Posting…' : `Post purchase · ${money(totals.total)}`}
              </Button>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
};
