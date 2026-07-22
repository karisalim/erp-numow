import React, { useState } from 'react';
import { Button } from '../../../components/ui/Button';
import { Icon } from '../../../components/ui/Icon';
import { EmptyState } from '../../../components/ui/states';
import { IngredientRow, type IngredientRowLine } from './IngredientRow';
import { IngredientPicker, type PickedIngredient } from './IngredientPicker';
import type { RecipeLine } from '../types';

const headCell = 'text-start text-[11px] tracking-wider uppercase text-neutral-500 font-bold px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50 whitespace-nowrap';

/**
 * Renders a recipe's ingredient lines as a table matching the app's
 * `DataTable` visual language exactly (same header/cell classes). Two
 * modes:
 *  - read-only: displays a saved `RecipeVersion`'s persisted `RecipeLine`s.
 *  - editable: displays + lets the caller add/change/remove DRAFT lines
 *    (via the `IngredientPicker` modal) before they're POSTed as a new
 *    version — nothing here saves anything itself, the parent owns that.
 */
export const IngredientTable: React.FC<{
  lines: (RecipeLine | IngredientRowLine)[];
  editable?: boolean;
  productId?: number;
  onAdd?: (line: PickedIngredient) => void;
  onQtyChange?: (index: number, value: string) => void;
  onRemove?: (index: number) => void;
}> = ({ lines, editable, productId, onAdd, onQtyChange, onRemove }) => {
  const [picking, setPicking] = useState(false);

  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-neutral-200 bg-neutral-50">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500">Ingredients</h3>
        {editable && (
          <Button size="sm" variant="secondary" onClick={() => setPicking(true)}>
            <Icon name="plus" size={13} /> Add ingredient
          </Button>
        )}
      </div>
      {lines.length === 0 ? (
        <EmptyState
          title="No ingredients yet"
          hint={editable ? 'Add at least one ingredient to save this recipe.' : 'This recipe version has no lines.'}
          icon="box"
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse min-w-[520px]">
            <thead>
              <tr>
                <th className={headCell}>Ingredient</th>
                <th className={`${headCell} text-end`}>Qty (entered)</th>
                <th className={headCell}>Unit</th>
                <th className={`${headCell} text-end`}>Qty (base)</th>
                {editable && <th className={headCell}></th>}
              </tr>
            </thead>
            <tbody>
              {lines.map((line, idx) => (
                <IngredientRow
                  key={'id' in line ? line.id : line.draftKey ?? idx}
                  line={line}
                  editable={editable}
                  onQtyChange={(v) => onQtyChange?.(idx, v)}
                  onRemove={() => onRemove?.(idx)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {picking && (
        <IngredientPicker
          excludeProductId={productId}
          onClose={() => setPicking(false)}
          onAdd={(line) => { onAdd?.(line); setPicking(false); }}
        />
      )}
    </div>
  );
};
