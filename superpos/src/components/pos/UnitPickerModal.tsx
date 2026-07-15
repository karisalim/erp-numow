import React, { useEffect, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { productUnitsApi, asResults } from '../../api/erp';
import { previewUnitPrice } from '../../utils/pricing';
import { useMoney } from '../../utils/money';
import type { Product } from '../../types';
import type { ProductUnit } from '../../types/erp';
import type { PosUnitChoice } from '../../store/posStore';

interface UnitPickerModalProps {
  product: Product;
  /** Active sale's price tier, if any — used only to preview a price;
   * the server resolves the authoritative price at checkout. */
  priceTierId: number | null;
  onConfirm: (qty: number, unit?: PosUnitChoice) => void;
  onClose: () => void;
}

/**
 * Lets the cashier pick which pack size of a product to add (base unit,
 * carton, box, …) when it has more than one sale-eligible ProductUnit.
 * Products with a single sale unit never reach this modal — POSPage adds
 * them straight to the cart with the legacy base-unit shape.
 */
export const UnitPickerModal: React.FC<UnitPickerModalProps> = ({
  product, priceTierId, onConfirm, onClose,
}) => {
  const money = useMoney();
  const [units, setUnits] = useState<ProductUnit[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [previewPrice, setPreviewPrice] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    productUnitsApi.list(Number(product.id))
      .then((data) => {
        if (cancelled) return;
        const list = asResults(data).filter((u) => u.is_active && u.is_sale_unit);
        setUnits(list);
        const base = list.find((u) => u.is_base);
        setSelectedId(base?.id ?? list[0]?.id ?? null);
      })
      .catch(() => { if (!cancelled) setError('Failed to load units for this product.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  const selectedUnit = units?.find((u) => u.id === selectedId) ?? null;

  // Preview price for the selected unit: tier price if one matches (mirrors
  // the backend's own resolve_unit_price fallback), else the product's base
  // retail price. Display-only — the server recomputes the real price_each.
  useEffect(() => {
    if (!selectedUnit) { setPreviewPrice(null); return; }
    if (selectedUnit.is_base) { setPreviewPrice(Number(product.price)); return; }
    let cancelled = false;
    previewUnitPrice(Number(product.id), selectedUnit.id, priceTierId, Number(product.price))
      .then((price) => { if (!cancelled) setPreviewPrice(price); });
    return () => { cancelled = true; };
  }, [selectedUnit, priceTierId, product.id, product.price]);

  useEffect(() => {
    if (selectedUnit && !selectedUnit.allow_decimal) {
      setQty((q) => Math.max(1, Math.round(q)));
    }
  }, [selectedUnit]);

  const handleConfirm = () => {
    if (!selectedUnit || qty <= 0) return;
    if (selectedUnit.is_base) {
      onConfirm(qty, undefined);
    } else {
      onConfirm(qty, {
        productUnitId: selectedUnit.id,
        unitLabel: selectedUnit.unit_name,
        displayPrice: previewPrice ?? Number(product.price),
      });
    }
  };

  const step = selectedUnit?.allow_decimal ? 0.1 : 1;
  const lineTotal = previewPrice != null ? qty * previewPrice : null;

  return (
    <Modal title={`Select unit — ${product.name}`} onClose={onClose}>
      <div className="p-5 space-y-4">
        {loading ? (
          <div className="py-6 text-center text-[13px] text-neutral-500">Loading units…</div>
        ) : error ? (
          <div className="py-6 text-center text-[13px] text-danger-600">{error}</div>
        ) : !units || units.length === 0 ? (
          <div className="py-6 text-center text-[13px] text-neutral-500">
            No sale-eligible units configured for this product.
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              {units.map((u) => (
                <label
                  key={u.id}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-md border cursor-pointer
                    ${selectedId === u.id ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 hover:bg-neutral-50'}`}
                >
                  <input
                    type="radio"
                    name="unit"
                    checked={selectedId === u.id}
                    onChange={() => setSelectedId(u.id)}
                    className="accent-brand-600"
                  />
                  <div className="flex-1">
                    <div className="text-[13.5px] font-semibold">
                      {u.unit_name}{u.is_base && <span className="ms-1.5 text-[11px] font-normal text-neutral-400">(base unit)</span>}
                    </div>
                    {!u.is_base && (
                      <div className="text-[11.5px] text-neutral-500">
                        1 {u.unit_name} = {u.conversion_to_base} × base unit
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>

            <div className="flex items-center justify-between gap-3 pt-1">
              <span className="text-[12.5px] font-semibold text-neutral-700">Quantity</span>
              <div className="flex items-center gap-1 bg-neutral-100 rounded-md p-1">
                <button
                  onClick={() => setQty((q) => Math.max(step, +(q - step).toFixed(3)))}
                  className="w-8 h-8 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
                  aria-label="Decrease quantity"
                >
                  <Icon name="minus" size={14} />
                </button>
                <span className="w-16 text-center font-mono text-[14px] font-semibold tabular-nums">
                  {selectedUnit?.allow_decimal ? qty.toFixed(3) : qty}
                </span>
                <button
                  onClick={() => setQty((q) => +(q + step).toFixed(3))}
                  className="w-8 h-8 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
                  aria-label="Increase quantity"
                >
                  <Icon name="plus" size={14} />
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-neutral-200 pt-3">
              <span className="text-[12.5px] text-neutral-500">
                {previewPrice != null ? `${money(previewPrice)} / ${selectedUnit?.unit_name}` : '—'}
              </span>
              <span className="font-mono text-[18px] font-bold tabular-nums">
                {lineTotal != null ? money(lineTotal) : '—'}
              </span>
            </div>
          </>
        )}

        <div className="flex gap-2 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1"
            disabled={!selectedUnit || qty <= 0 || loading}
            onClick={handleConfirm}
          >
            Add to cart
          </Button>
        </div>
      </div>
    </Modal>
  );
};
