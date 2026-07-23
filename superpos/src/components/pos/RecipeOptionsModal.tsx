import React, { useEffect, useMemo, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { posApi } from '../../api/pos';
import type {
  RecipeVariantDto, RecipeModifierGroupDto, RecipeModifierOptionDto,
} from '../../api/pos';
import { useMoney } from '../../utils/money';
import type { Product } from '../../types';
import type { PosRecipeChoice } from '../../store/posStore';

interface GroupWithOptions {
  group: RecipeModifierGroupDto;
  options: RecipeModifierOptionDto[];
}

interface RecipeOptionsModalProps {
  product: Product;
  onConfirm: (qty: number, choice: PosRecipeChoice) => void;
  onClose: () => void;
}

/**
 * Sprint 5 Batch 9 — the POS-side counterpart to `UnitPickerModal`: lets the
 * cashier pick a size Variant and/or ModifierOptions for a recipe product
 * before it's added to the cart. Mirrors that modal's self-contained
 * fetch-then-render-then-confirm shape (one file, one responsibility).
 *
 * Fan-out to build the full picture (no combined endpoint exists yet):
 *   1. GET .../variants/               → this product's size options
 *   2. GET .../modifier-groups/        → which ModifierGroups are attached
 *   3. GET catalog/modifier-groups/{id}/          → each group's own rules
 *   4. GET catalog/modifier-groups/{id}/options/  → each active group's options
 * Only fired once, when this modal mounts for a tapped product — never for
 * the whole grid up front.
 */
export const RecipeOptionsModal: React.FC<RecipeOptionsModalProps> = ({
  product, onConfirm, onClose,
}) => {
  const money = useMoney();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [variants, setVariants] = useState<RecipeVariantDto[]>([]);
  const [groups, setGroups] = useState<GroupWithOptions[]>([]);

  const [step, setStep] = useState<'variant' | 'modifiers'>('variant');
  const [selectedVariantId, setSelectedVariantId] = useState<number | null>(null);
  const [selectedOptionIds, setSelectedOptionIds] = useState<Set<number>>(new Set());
  const [qty, setQty] = useState(1);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [variantList, links] = await Promise.all([
          posApi.listProductVariants(Number(product.id)),
          posApi.listProductModifierGroupLinks(Number(product.id)),
        ]);
        const activeVariants = variantList
          .filter((v) => v.is_active)
          .sort((a, b) => a.sort_order - b.sort_order);

        const groupDetails = await Promise.all(
          links.map(async (link) => {
            const group = await posApi.getModifierGroup(link.modifier_group);
            if (!group.is_active) return null;
            const options = (await posApi.listModifierGroupOptions(group.id))
              .filter((o) => o.is_active)
              .sort((a, b) => a.sort_order - b.sort_order);
            if (options.length === 0) return null;
            return { group, options };
          }),
        );

        if (cancelled) return;
        setVariants(activeVariants);
        setGroups(groupDetails.filter((g): g is GroupWithOptions => g != null));
        setStep(activeVariants.length > 0 ? 'variant' : 'modifiers');
      } catch {
        if (!cancelled) setError('Failed to load options for this product.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [product.id]);

  const selectedVariant = variants.find((v) => v.id === selectedVariantId) ?? null;
  const basePrice = selectedVariant ? Number(selectedVariant.price) : Number(product.price);

  const selectedOptions = useMemo(
    () => groups.flatMap((g) => g.options).filter((o) => selectedOptionIds.has(o.id)),
    [groups, selectedOptionIds],
  );
  const modifierTotal = selectedOptions.reduce((s, o) => s + Number(o.price_delta), 0);
  const unitPrice = basePrice + modifierTotal;

  const toggleOption = (group: RecipeModifierGroupDto, optionId: number) => {
    setSelectedOptionIds((prev) => {
      const next = new Set(prev);
      const groupOptionIds = new Set(
        groups.find((g) => g.group.id === group.id)?.options.map((o) => o.id) ?? [],
      );
      if (group.selection_type === 'single') {
        // Radio behavior: clear every other option in this group first.
        for (const id of groupOptionIds) next.delete(id);
        if (!prev.has(optionId)) next.add(optionId);
        return next;
      }
      // Checkbox behavior, respecting max_select.
      if (next.has(optionId)) {
        next.delete(optionId);
      } else {
        const countInGroup = [...next].filter((id) => groupOptionIds.has(id)).length;
        if (group.max_select != null && countInGroup >= group.max_select) return prev;
        next.add(optionId);
      }
      return next;
    });
  };

  /** A group's selection satisfies its own declared min/max (a UX-level
   * gate only — the backend's own check is narrower, see the payload
   * comment in `api/pos.ts`; this just keeps the cashier from submitting
   * an obviously-incomplete pick). */
  const groupSatisfied = (g: GroupWithOptions): boolean => {
    const count = g.options.filter((o) => selectedOptionIds.has(o.id)).length;
    const min = g.group.min_select ?? 0;
    const max = g.group.max_select ?? Infinity;
    return count >= min && count <= max;
  };

  const variantStepValid = variants.length === 0 || selectedVariantId != null;
  const modifiersStepValid = groups.every(groupSatisfied);
  const canProceedFromVariant = variantStepValid;
  const canConfirm = variantStepValid && modifiersStepValid;

  const handlePrimaryAction = () => {
    if (step === 'variant' && groups.length > 0) {
      setStep('modifiers');
      return;
    }
    if (!canConfirm) return;
    onConfirm(qty, {
      variantId: selectedVariant?.id,
      variantName: selectedVariant?.name,
      variantPrice: basePrice,
      modifiers: selectedOptions.map((o) => ({ id: o.id, name: o.name, priceDelta: Number(o.price_delta) })),
    });
  };

  const showQtyAndTotal = !loading && !error && (step === 'modifiers' || groups.length === 0);
  const primaryLabel = step === 'variant' && groups.length > 0 ? 'Continue' : 'Add to cart';
  const primaryDisabled = loading || !!error
    || (step === 'variant' ? !canProceedFromVariant : !canConfirm);

  return (
    <Modal title={`Customize — ${product.name}`} onClose={onClose}>
      <div className="p-5 space-y-4">
        {loading ? (
          <div className="py-6 text-center text-[13px] text-neutral-500">Loading options…</div>
        ) : error ? (
          <div className="py-6 text-center text-[13px] text-danger-600">{error}</div>
        ) : (
          <>
            {step === 'variant' && variants.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[12.5px] font-semibold text-neutral-700">Size / variant</div>
                {variants.map((v) => (
                  <label
                    key={v.id}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-md border cursor-pointer
                      ${selectedVariantId === v.id ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 hover:bg-neutral-50'}`}
                  >
                    <input
                      type="radio" name="variant"
                      checked={selectedVariantId === v.id}
                      onChange={() => setSelectedVariantId(v.id)}
                      className="accent-brand-600"
                    />
                    <span className="flex-1 text-[13.5px] font-semibold">{v.name}</span>
                    <span className="font-mono text-[13px] tabular-nums text-neutral-600">{money(Number(v.price))}</span>
                  </label>
                ))}
              </div>
            )}

            {step === 'modifiers' && variants.length > 0 && (
              <button
                type="button" onClick={() => setStep('variant')}
                className="text-[12px] font-semibold text-brand-600 hover:underline inline-flex items-center gap-1"
              >
                <Icon name="chevL" size={12} /> {selectedVariant?.name ?? 'Change size'}
              </button>
            )}

            {step === 'modifiers' && groups.map((g) => {
              const count = g.options.filter((o) => selectedOptionIds.has(o.id)).length;
              const min = g.group.min_select ?? 0;
              const max = g.group.max_select;
              return (
                <div key={g.group.id} className="space-y-1.5">
                  <div className="flex items-baseline justify-between">
                    <div className="text-[12.5px] font-semibold text-neutral-700">{g.group.name}</div>
                    <div className={`text-[11px] ${groupSatisfied(g) ? 'text-neutral-400' : 'text-warn-600 font-semibold'}`}>
                      {min > 0 ? `Select ${max != null && max !== min ? `${min}–${max}` : min}` : max != null ? `Up to ${max}` : 'Optional'}
                    </div>
                  </div>
                  {g.options.map((o) => {
                    const checked = selectedOptionIds.has(o.id);
                    const delta = Number(o.price_delta);
                    return (
                      <label
                        key={o.id}
                        className={`flex items-center gap-3 px-3 py-2 rounded-md border cursor-pointer
                          ${checked ? 'border-brand-500 bg-brand-50' : 'border-neutral-200 hover:bg-neutral-50'}`}
                      >
                        <input
                          type={g.group.selection_type === 'single' ? 'radio' : 'checkbox'}
                          name={`group-${g.group.id}`}
                          checked={checked}
                          onChange={() => toggleOption(g.group, o.id)}
                          className="accent-brand-600"
                        />
                        <span className="flex-1 text-[13px]">{o.name}</span>
                        <span className="font-mono text-[12.5px] tabular-nums text-neutral-500">
                          {delta === 0 ? '—' : delta > 0 ? `+${money(delta)}` : `−${money(Math.abs(delta))}`}
                        </span>
                      </label>
                    );
                  })}
                  <div className="text-[10.5px] text-neutral-400">{count} selected</div>
                </div>
              );
            })}

            {step === 'modifiers' && groups.length === 0 && variants.length === 0 && (
              <div className="py-4 text-center text-[13px] text-neutral-500">
                No customization options for this product.
              </div>
            )}

            {showQtyAndTotal && (
              <div className="flex items-center justify-between gap-3 pt-1 border-t border-neutral-200">
                <span className="text-[12.5px] font-semibold text-neutral-700 pt-3">Quantity</span>
                <div className="flex items-center gap-1 bg-neutral-100 rounded-md p-1 mt-3">
                  <button
                    onClick={() => setQty((q) => Math.max(1, q - 1))}
                    className="w-8 h-8 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
                    aria-label="Decrease quantity"
                  >
                    <Icon name="minus" size={14} />
                  </button>
                  <span className="w-10 text-center font-mono text-[14px] font-semibold tabular-nums">{qty}</span>
                  <button
                    onClick={() => setQty((q) => q + 1)}
                    className="w-8 h-8 rounded grid place-items-center bg-white border border-neutral-300 hover:border-brand-500 focus-ring"
                    aria-label="Increase quantity"
                  >
                    <Icon name="plus" size={14} />
                  </button>
                </div>
              </div>
            )}

            {showQtyAndTotal && (
              <div className="flex items-center justify-between border-t border-neutral-200 pt-3">
                <span className="text-[12.5px] text-neutral-500">{money(unitPrice)} each</span>
                <span className="font-mono text-[18px] font-bold tabular-nums">{money(unitPrice * qty)}</span>
              </div>
            )}
          </>
        )}

        <div className="flex gap-2 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button className="flex-1" disabled={primaryDisabled} onClick={handlePrimaryAction}>
            {primaryLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
