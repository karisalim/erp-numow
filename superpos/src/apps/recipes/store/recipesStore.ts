import { create } from 'zustand';
import type { RecipeLineInput } from '../types';

/**
 * Recipe app state — independent of `posStore`/`appStore` on purpose (per
 * the Batch 8 brief: no Recipes-specific state lives in the POS stores).
 *
 * Scope is deliberately narrow: the one genuinely complex piece of client
 * state in this feature is the Recipe Editor's in-progress DRAFT (the set
 * of ingredient lines being assembled before the "Save" POST creates a new
 * `RecipeVersion`). Every list/detail page still fetches its own data via
 * `useQuery` + the api layer, matching every other page in this codebase —
 * a global store for read data would just be a second cache to keep in
 * sync with the server for no benefit.
 *
 * Nothing here computes cost, margin, or validates a business rule — it
 * only holds the rows the user has assembled so far; `RecipeProductForm`
 * sends them to the backend as-is and reads back whatever the server
 * decides (accept or 400).
 */
interface DraftLine extends RecipeLineInput {
  /** Client-only row key for React lists / edit-in-place — never sent to
   * the server (the POST body only ever carries the fields in
   * RecipeLineInput). */
  draftKey: string;
  component_product_name: string;
  component_unit_name: string;
}

interface RecipesState {
  /** The product this draft belongs to, so a stale draft from a previous
   * product never leaks into a new editor session. */
  draftProductId: number | null;
  draftVariantId: number | null;
  draftLines: DraftLine[];

  startDraft: (productId: number, variantId: number | null) => void;
  addDraftLine: (line: Omit<DraftLine, 'draftKey'>) => void;
  updateDraftLine: (draftKey: string, patch: Partial<Omit<DraftLine, 'draftKey'>>) => void;
  removeDraftLine: (draftKey: string) => void;
  clearDraft: () => void;
}

let keySeq = 0;
const nextKey = () => `draft-${++keySeq}-${Date.now()}`;

export const useRecipesStore = create<RecipesState>((set) => ({
  draftProductId: null,
  draftVariantId: null,
  draftLines: [],

  startDraft: (productId, variantId) =>
    set({ draftProductId: productId, draftVariantId: variantId, draftLines: [] }),

  addDraftLine: (line) =>
    set((s) => ({ draftLines: [...s.draftLines, { ...line, draftKey: nextKey() }] })),

  updateDraftLine: (draftKey, patch) =>
    set((s) => ({
      draftLines: s.draftLines.map((l) => (l.draftKey === draftKey ? { ...l, ...patch } : l)),
    })),

  removeDraftLine: (draftKey) =>
    set((s) => ({ draftLines: s.draftLines.filter((l) => l.draftKey !== draftKey) })),

  clearDraft: () => set({ draftProductId: null, draftVariantId: null, draftLines: [] }),
}));
