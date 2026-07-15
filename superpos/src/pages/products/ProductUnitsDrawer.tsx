import React, { useState } from 'react';
import { Drawer } from '../../components/ui/Drawer';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { DataTable, type Column } from '../../components/ui/DataTable';
import { ActiveBadge } from '../../components/ui/StatusBadge';
import { Badge } from '../../components/ui/Badge';
import { FormField, SelectField, FieldError } from '../../components/ui/FormField';
import { unitsApi, productUnitsApi, priceTiersApi, asResults } from '../../api/erp';
import { useQuery } from '../../hooks/useQuery';
import { useMoney } from '../../utils/money';
import { parseApiError, type ApiError } from '../../utils/apiError';
import type { Product } from '../../types';
import type { ProductUnit, ProductBarcodeUnit, ProductUnitTierPrice } from '../../types/erp';

interface ProductUnitsDrawerProps {
  product: Product;
  onClose: () => void;
}

/**
 * Manages one product's Sprint 2 unit-of-sale data — conversion mappings
 * (carton = 12 base units, ...), their pack barcodes, and per-tier prices.
 * All additive/optional: a product with none of this configured behaves
 * exactly as before (base-unit-only sales, legacy Product.barcode scanning).
 */
export const ProductUnitsDrawer: React.FC<ProductUnitsDrawerProps> = ({ product, onClose }) => {
  const money = useMoney();
  const productId = Number(product.id);

  const tenantUnitsQ = useQuery(() => unitsApi.list({ active: 'true' }).then(asResults), []);
  const mappingsQ    = useQuery(() => productUnitsApi.list(productId).then(asResults), [productId]);
  const barcodesQ    = useQuery(() => productUnitsApi.listBarcodes(productId).then(asResults), [productId]);
  const tiersQ       = useQuery(() => priceTiersApi.list({ is_active: 'true' }).then(asResults), []);

  const mappings = mappingsQ.data ?? [];
  const tenantUnits = tenantUnitsQ.data ?? [];
  const barcodes = barcodesQ.data ?? [];
  const tiers = tiersQ.data ?? [];

  /* ── Add unit mapping ────────────────────────────────────────────────── */
  const [addingUnit, setAddingUnit] = useState(false);
  const [unitForm, setUnitForm] = useState({
    unit: '', conversion_to_base: '1', is_base: false,
    is_sale_unit: true, is_purchase_unit: false, minimum_order_qty: '',
  });
  const [unitBusy, setUnitBusy] = useState(false);
  const [unitError, setUnitError] = useState<ApiError | null>(null);

  const submitUnit = async () => {
    if (!unitForm.unit) return;
    setUnitBusy(true);
    setUnitError(null);
    try {
      await productUnitsApi.create(productId, {
        unit: Number(unitForm.unit),
        conversion_to_base: unitForm.conversion_to_base,
        is_base: unitForm.is_base,
        is_sale_unit: unitForm.is_sale_unit,
        is_purchase_unit: unitForm.is_purchase_unit,
        minimum_order_qty: unitForm.minimum_order_qty || null,
      });
      setAddingUnit(false);
      setUnitForm({ unit: '', conversion_to_base: '1', is_base: false, is_sale_unit: true, is_purchase_unit: false, minimum_order_qty: '' });
      mappingsQ.refetch();
    } catch (err) {
      setUnitError(parseApiError(err));
    } finally {
      setUnitBusy(false);
    }
  };

  /* ── Add barcode ─────────────────────────────────────────────────────── */
  const [addingBarcode, setAddingBarcode] = useState(false);
  const [barcodeForm, setBarcodeForm] = useState({ product_unit: '', barcode: '', is_default: false });
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const [barcodeError, setBarcodeError] = useState<ApiError | null>(null);

  const submitBarcode = async () => {
    if (!barcodeForm.product_unit || !barcodeForm.barcode.trim()) return;
    setBarcodeBusy(true);
    setBarcodeError(null);
    try {
      await productUnitsApi.createBarcode(productId, {
        product_unit: Number(barcodeForm.product_unit),
        barcode: barcodeForm.barcode.trim(),
        is_default: barcodeForm.is_default,
      });
      setAddingBarcode(false);
      setBarcodeForm({ product_unit: '', barcode: '', is_default: false });
      barcodesQ.refetch();
    } catch (err) {
      setBarcodeError(parseApiError(err));
    } finally {
      setBarcodeBusy(false);
    }
  };

  /* ── Tier prices (scoped to a selected unit mapping) ────────────────────── */
  const [tierUnitId, setTierUnitId] = useState<number | null>(null);
  const tierPricesQ = useQuery(
    () => tierUnitId ? priceTiersApi.listTierPrices(productId, tierUnitId).then(asResults) : Promise.resolve<ProductUnitTierPrice[]>([]),
    [productId, tierUnitId],
  );
  const [addingTierPrice, setAddingTierPrice] = useState(false);
  const [tierPriceForm, setTierPriceForm] = useState({ price_tier: '', price: '' });
  const [tierPriceBusy, setTierPriceBusy] = useState(false);
  const [tierPriceError, setTierPriceError] = useState<ApiError | null>(null);

  const submitTierPrice = async () => {
    if (!tierUnitId || !tierPriceForm.price_tier || !tierPriceForm.price) return;
    setTierPriceBusy(true);
    setTierPriceError(null);
    try {
      await priceTiersApi.createTierPrice(productId, tierUnitId, {
        price_tier: Number(tierPriceForm.price_tier),
        price: tierPriceForm.price,
      });
      setAddingTierPrice(false);
      setTierPriceForm({ price_tier: '', price: '' });
      tierPricesQ.refetch();
    } catch (err) {
      setTierPriceError(parseApiError(err));
    } finally {
      setTierPriceBusy(false);
    }
  };

  const unitColumns: Column<ProductUnit>[] = [
    {
      key: 'unit', header: 'Unit',
      render: (u) => (
        <div className="flex items-center gap-1.5">
          <span className="font-semibold">{u.unit_name}</span>
          {u.is_base && <Badge kind="brand">base</Badge>}
        </div>
      ),
    },
    { key: 'conv', header: 'Conversion', align: 'end', mono: true, render: (u) => `× ${u.conversion_to_base}` },
    {
      key: 'flags', header: 'Eligible for',
      render: (u) => (
        <div className="flex gap-1">
          {u.is_sale_unit && <Badge kind="success">sale</Badge>}
          {u.is_purchase_unit && <Badge kind="info">purchase</Badge>}
          {!u.is_sale_unit && !u.is_purchase_unit && <span className="text-neutral-400">—</span>}
        </div>
      ),
    },
    { key: 'min', header: 'Min order qty', align: 'end', mono: true, render: (u) => u.minimum_order_qty ?? '—' },
    { key: 'status', header: 'Status', render: (u) => <ActiveBadge active={u.is_active} /> },
  ];

  const barcodeColumns: Column<ProductBarcodeUnit>[] = [
    { key: 'barcode', header: 'Barcode', render: (b) => <span className="font-mono">{b.barcode}</span> },
    { key: 'unit', header: 'Unit', render: (b) => b.unit_name },
    { key: 'default', header: 'Default', render: (b) => b.is_default ? <Badge kind="brand">default</Badge> : '—' },
  ];

  const tierPriceColumns: Column<ProductUnitTierPrice>[] = [
    { key: 'tier', header: 'Price tier', render: (t) => t.price_tier_name },
    { key: 'price', header: 'Price', align: 'end', mono: true, render: (t) => money(t.price) },
    { key: 'status', header: 'Status', render: (t) => <ActiveBadge active={t.is_active} /> },
  ];

  return (
    <Drawer
      title="Units & pricing"
      subtitle={product.name}
      onClose={onClose}
      widthClassName="max-w-[640px]"
    >
      <div className="space-y-6">
        {/* ── Unit conversions ─────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Unit conversions</h3>
            <Button size="sm" variant="secondary" onClick={() => { setUnitError(null); setAddingUnit((v) => !v); }}>
              <Icon name="plus" size={13} /> Add unit
            </Button>
          </div>
          {addingUnit && (
            <div className="border border-neutral-200 rounded-md p-3 mb-3 space-y-3 bg-neutral-50">
              <div className="grid grid-cols-2 gap-3">
                <SelectField
                  label="Unit" value={unitForm.unit}
                  onChange={(e) => setUnitForm((s) => ({ ...s, unit: e.target.value }))}
                  error={unitError?.fieldErrors.unit}
                >
                  <option value="">Select…</option>
                  {tenantUnits.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.unit_group_name})</option>)}
                </SelectField>
                <FormField
                  label="Conversion to base" type="number" step="0.000001" min="0.000001"
                  value={unitForm.conversion_to_base}
                  onChange={(e) => setUnitForm((s) => ({ ...s, conversion_to_base: e.target.value }))}
                  error={unitError?.fieldErrors.conversion_to_base}
                  disabled={unitForm.is_base}
                />
              </div>
              <FormField
                label="Minimum order qty (optional)" type="number" step="0.001" min="0.001"
                value={unitForm.minimum_order_qty}
                onChange={(e) => setUnitForm((s) => ({ ...s, minimum_order_qty: e.target.value }))}
                error={unitError?.fieldErrors.minimum_order_qty}
                hint="Enforced on purchase-invoice lines using this unit."
              />
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" className="accent-brand-600"
                    checked={unitForm.is_base}
                    onChange={(e) => setUnitForm((s) => ({ ...s, is_base: e.target.checked, conversion_to_base: e.target.checked ? '1' : s.conversion_to_base }))}
                  /> Base unit
                </label>
                <label className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" className="accent-brand-600"
                    checked={unitForm.is_sale_unit}
                    onChange={(e) => setUnitForm((s) => ({ ...s, is_sale_unit: e.target.checked }))}
                  /> Sale-eligible
                </label>
                <label className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" className="accent-brand-600"
                    checked={unitForm.is_purchase_unit}
                    onChange={(e) => setUnitForm((s) => ({ ...s, is_purchase_unit: e.target.checked }))}
                  /> Purchase-eligible
                </label>
              </div>
              {unitError && !Object.keys(unitError.fieldErrors).length && <FieldError error={unitError.message} />}
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setAddingUnit(false)} disabled={unitBusy}>Cancel</Button>
                <Button size="sm" onClick={submitUnit} disabled={unitBusy || !unitForm.unit}>
                  {unitBusy ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>
          )}
          <DataTable<ProductUnit>
            columns={unitColumns}
            rows={mappings}
            rowKey={(u) => u.id}
            loading={mappingsQ.loading}
            error={mappingsQ.error}
            onRetry={mappingsQ.refetch}
            emptyTitle="No extra units configured"
            emptyHint="This product sells and is purchased at its legacy base unit only — nothing else changes."
          />
        </section>

        {/* ── Pack barcodes ────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Pack barcodes</h3>
            <Button size="sm" variant="secondary" disabled={mappings.length === 0}
              onClick={() => { setBarcodeError(null); setAddingBarcode((v) => !v); }}>
              <Icon name="plus" size={13} /> Add barcode
            </Button>
          </div>
          {addingBarcode && (
            <div className="border border-neutral-200 rounded-md p-3 mb-3 space-y-3 bg-neutral-50">
              <div className="grid grid-cols-2 gap-3">
                <SelectField
                  label="Unit" value={barcodeForm.product_unit}
                  onChange={(e) => setBarcodeForm((s) => ({ ...s, product_unit: e.target.value }))}
                  error={barcodeError?.fieldErrors.product_unit}
                >
                  <option value="">Select…</option>
                  {mappings.map((u) => <option key={u.id} value={u.id}>{u.unit_name}{u.is_base ? ' (base)' : ''}</option>)}
                </SelectField>
                <FormField
                  label="Barcode"
                  value={barcodeForm.barcode}
                  onChange={(e) => setBarcodeForm((s) => ({ ...s, barcode: e.target.value }))}
                  error={barcodeError?.fieldErrors.barcode}
                />
              </div>
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" className="accent-brand-600"
                  checked={barcodeForm.is_default}
                  onChange={(e) => setBarcodeForm((s) => ({ ...s, is_default: e.target.checked }))}
                /> Default barcode for this unit
              </label>
              {barcodeError && !Object.keys(barcodeError.fieldErrors).length && <FieldError error={barcodeError.message} />}
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setAddingBarcode(false)} disabled={barcodeBusy}>Cancel</Button>
                <Button size="sm" onClick={submitBarcode} disabled={barcodeBusy || !barcodeForm.product_unit || !barcodeForm.barcode.trim()}>
                  {barcodeBusy ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>
          )}
          <DataTable<ProductBarcodeUnit>
            columns={barcodeColumns}
            rows={barcodes}
            rowKey={(b) => b.id}
            loading={barcodesQ.loading}
            error={barcodesQ.error}
            onRetry={barcodesQ.refetch}
            emptyTitle="No pack barcodes"
            emptyHint="Scanning still falls back to this product's legacy barcode."
          />
        </section>

        {/* ── Tier prices ──────────────────────────────────────────────── */}
        <section>
          <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">Tier prices</h3>
          <SelectField
            label="Unit"
            value={tierUnitId ?? ''}
            onChange={(e) => setTierUnitId(e.target.value ? Number(e.target.value) : null)}
            containerClassName="mb-3"
          >
            <option value="">Select a unit to manage its tier prices…</option>
            {mappings.map((u) => <option key={u.id} value={u.id}>{u.unit_name}{u.is_base ? ' (base)' : ''}</option>)}
          </SelectField>

          {tierUnitId && (
            <>
              <div className="flex items-center justify-end mb-2">
                <Button size="sm" variant="secondary" disabled={tiers.length === 0}
                  onClick={() => { setTierPriceError(null); setAddingTierPrice((v) => !v); }}>
                  <Icon name="plus" size={13} /> Add tier price
                </Button>
              </div>
              {tiers.length === 0 && (
                <div className="text-[12.5px] text-neutral-500 bg-neutral-50 border border-neutral-200 rounded-md px-3 py-2 mb-3">
                  No price tiers exist yet — create one under Price Tiers first.
                </div>
              )}
              {addingTierPrice && (
                <div className="border border-neutral-200 rounded-md p-3 mb-3 space-y-3 bg-neutral-50">
                  <div className="grid grid-cols-2 gap-3">
                    <SelectField
                      label="Price tier" value={tierPriceForm.price_tier}
                      onChange={(e) => setTierPriceForm((s) => ({ ...s, price_tier: e.target.value }))}
                      error={tierPriceError?.fieldErrors.price_tier}
                    >
                      <option value="">Select…</option>
                      {tiers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </SelectField>
                    <FormField
                      label="Price" type="number" step="0.01" min="0.01"
                      value={tierPriceForm.price}
                      onChange={(e) => setTierPriceForm((s) => ({ ...s, price: e.target.value }))}
                      error={tierPriceError?.fieldErrors.price}
                    />
                  </div>
                  {tierPriceError && !Object.keys(tierPriceError.fieldErrors).length && <FieldError error={tierPriceError.message} />}
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setAddingTierPrice(false)} disabled={tierPriceBusy}>Cancel</Button>
                    <Button size="sm" onClick={submitTierPrice} disabled={tierPriceBusy || !tierPriceForm.price_tier || !tierPriceForm.price}>
                      {tierPriceBusy ? 'Saving…' : 'Save'}
                    </Button>
                  </div>
                </div>
              )}
              <DataTable<ProductUnitTierPrice>
                columns={tierPriceColumns}
                rows={tierPricesQ.data ?? []}
                rowKey={(t) => t.id}
                loading={tierPricesQ.loading}
                error={tierPricesQ.error}
                onRetry={tierPricesQ.refetch}
                emptyTitle="No tier prices for this unit"
                emptyHint="Sales fall back to this product's base retail price until a tier price is set."
              />
            </>
          )}
        </section>
      </div>
    </Drawer>
  );
};
