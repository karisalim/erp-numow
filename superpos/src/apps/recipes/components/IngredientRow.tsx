import React from 'react';
import { Icon } from '../../../components/ui/Icon';
import { formatQty } from '../utils/format';
import type { RecipeLine } from '../types';

export interface IngredientRowLine {
  draftKey?: string;
  component_product: number;
  component_product_name: string;
  component_unit?: number | null;
  component_unit_name: string;
  entered_qty: string;
}

/**
 * One ingredient line, as a table row. Read-only mode (viewing a saved
 * `RecipeVersion`) shows plain text; edit mode (composing a draft) shows a
 * quantity input + a remove button. `qty_base` — when present, i.e. a
 * server-persisted `RecipeLine` — is shown as a secondary, server-computed
 * value; this component never computes it itself.
 */
export const IngredientRow: React.FC<{
  line: IngredientRowLine | RecipeLine;
  editable?: boolean;
  onQtyChange?: (value: string) => void;
  onRemove?: () => void;
}> = ({ line, editable, onQtyChange, onRemove }) => {
  const qtyBase = 'qty_base' in line ? line.qty_base : undefined;

  return (
    <tr className="group">
      <td className="px-3.5 py-2.5 border-b border-neutral-100 text-[13.5px] group-hover:bg-neutral-50">
        <div className="font-semibold">{line.component_product_name}</div>
      </td>
      <td className="px-3.5 py-2.5 border-b border-neutral-100 text-[13.5px] text-end group-hover:bg-neutral-50">
        {editable ? (
          <input
            type="number"
            step="0.001"
            min="0.001"
            value={line.entered_qty}
            onChange={(e) => onQtyChange?.(e.target.value)}
            className="w-24 h-8 px-2 rounded border border-neutral-300 text-end text-[13.5px] focus-ring"
          />
        ) : (
          formatQty(line.entered_qty)
        )}
      </td>
      <td className="px-3.5 py-2.5 border-b border-neutral-100 text-[13.5px] group-hover:bg-neutral-50">
        {line.component_unit_name || <span className="text-neutral-400">base unit</span>}
      </td>
      <td className="px-3.5 py-2.5 border-b border-neutral-100 text-[13.5px] text-end text-neutral-500 font-mono tabular-nums group-hover:bg-neutral-50">
        {qtyBase !== undefined ? formatQty(qtyBase) : '—'}
      </td>
      {editable && (
        <td className="px-3.5 py-2.5 border-b border-neutral-100 text-end group-hover:bg-neutral-50">
          <button
            onClick={onRemove}
            aria-label="Remove ingredient"
            className="w-7 h-7 rounded grid place-items-center text-danger-500 hover:bg-danger-50 focus-ring"
          >
            <Icon name="trash" size={14} />
          </button>
        </td>
      )}
    </tr>
  );
};
