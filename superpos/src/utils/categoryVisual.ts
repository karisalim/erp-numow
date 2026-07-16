/**
 * Deterministic "visual identity" for a product tile — an emoji + a color
 * gradient — derived from its category/product name. Purely cosmetic
 * (POS grid, product table icons); never used for business logic.
 */

export interface CategoryVisual {
  emoji: string;
  /** Tailwind gradient classes for the tile background. */
  gradient: string;
}

// Keyword → visual. Matched case-insensitively against category name first,
// then product name, so "Fresh Milk 1L" hits "milk" even with no category.
const KEYWORD_VISUALS: Array<{ keywords: string[]; visual: CategoryVisual }> = [
  { keywords: ['fruit', 'vegetable', 'produce'], visual: { emoji: '🍎', gradient: 'from-rose-400 to-red-500' } },
  { keywords: ['dairy', 'milk', 'cheese', 'yogurt', 'yoghurt', 'butter'], visual: { emoji: '🥛', gradient: 'from-sky-400 to-blue-500' } },
  { keywords: ['bakery', 'bread', 'bake', 'pastry'], visual: { emoji: '🍞', gradient: 'from-amber-400 to-orange-500' } },
  { keywords: ['meat', 'poultry', 'chicken', 'beef', 'lamb'], visual: { emoji: '🥩', gradient: 'from-red-500 to-rose-600' } },
  { keywords: ['fish', 'seafood', 'shrimp'], visual: { emoji: '🐟', gradient: 'from-cyan-400 to-sky-500' } },
  { keywords: ['drink', 'beverage', 'juice', 'soda', 'water'], visual: { emoji: '🥤', gradient: 'from-teal-400 to-cyan-500' } },
  { keywords: ['coffee', 'tea'], visual: { emoji: '☕', gradient: 'from-amber-600 to-yellow-700' } },
  { keywords: ['snack', 'chip', 'candy', 'sweet', 'chocolate'], visual: { emoji: '🍫', gradient: 'from-orange-400 to-amber-600' } },
  { keywords: ['frozen', 'ice cream'], visual: { emoji: '🧊', gradient: 'from-indigo-400 to-blue-500' } },
  { keywords: ['cleaning', 'detergent', 'household'], visual: { emoji: '🧴', gradient: 'from-emerald-400 to-teal-500' } },
  { keywords: ['personal care', 'cosmetic', 'beauty', 'hygiene'], visual: { emoji: '🧼', gradient: 'from-pink-400 to-rose-500' } },
  { keywords: ['baby'], visual: { emoji: '🍼', gradient: 'from-violet-400 to-purple-500' } },
  { keywords: ['pet'], visual: { emoji: '🐾', gradient: 'from-lime-400 to-green-500' } },
  { keywords: ['stationery', 'office'], visual: { emoji: '✏️', gradient: 'from-slate-400 to-slate-600' } },
  { keywords: ['grain', 'rice', 'pasta', 'flour', 'cereal'], visual: { emoji: '🌾', gradient: 'from-yellow-500 to-amber-600' } },
  { keywords: ['spice', 'sauce', 'oil', 'condiment'], visual: { emoji: '🧂', gradient: 'from-orange-500 to-red-500' } },
  { keywords: ['egg'], visual: { emoji: '🥚', gradient: 'from-amber-300 to-orange-400' } },
];

// Hash-based fallback palette for anything with no keyword match, so the
// grid stays colorful and varied instead of collapsing to one gray tile.
const FALLBACK_VISUALS: CategoryVisual[] = [
  { emoji: '🛒', gradient: 'from-brand-400 to-brand-600' },
  { emoji: '📦', gradient: 'from-violet-400 to-violet-600' },
  { emoji: '🏷️', gradient: 'from-teal-400 to-emerald-600' },
  { emoji: '✨', gradient: 'from-fuchsia-400 to-pink-600' },
  { emoji: '🔹', gradient: 'from-indigo-400 to-indigo-600' },
  { emoji: '🧺', gradient: 'from-amber-400 to-orange-600' },
];

const hash = (s: string): number => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
};

const matchKeywords = (haystack: string): CategoryVisual | null => {
  for (const { keywords, visual } of KEYWORD_VISUALS) {
    if (keywords.some((k) => haystack.includes(k))) return visual;
  }
  return null;
};

/**
 * Look up a visual for a product. The category name is checked first and
 * wins outright when it matches — otherwise a generic word in the product
 * name (e.g. "Fresh Milk" containing "fresh") could shadow a more specific
 * category match (e.g. "Dairy"). Only falls back to the product name when
 * the category itself doesn't match anything.
 */
export function productVisual(name: string, categoryName?: string | null): CategoryVisual {
  const category = (categoryName ?? '').toLowerCase();
  const productName = name.toLowerCase();
  const visual = (category && matchKeywords(category)) || matchKeywords(productName);
  if (visual) return visual;
  const key = categoryName || name;
  return FALLBACK_VISUALS[hash(key) % FALLBACK_VISUALS.length];
}
