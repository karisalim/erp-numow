# Sprint 5 Batch 8 — Recipe Management Frontend: Architecture Review

Verified end-to-end in a real browser (Playwright, headless Chromium) against
the real Django backend and Postgres, not just `npm run build`. Screenshots
of every flow below were captured during that run.

## 1. What this batch is

A fully independent React feature app at `superpos/src/apps/recipes/`,
covering Recipes/BOM, Size Variants, Modifiers, and food-cost reporting. It
is mounted into the main app as a **single route**
(`<Route path="/recipes/*" element={<Guarded min="Manager"><Lazy><RecipesApp/></Lazy></Guarded>} />`
in `App.tsx`) and a **single sidebar entry** (`Sidebar.tsx`'s `NAV_GROUPS`).
Nothing else in the existing app (POS, Inventory, Sales, Products) was
touched except those two integration points plus the pre-existing
`tsconfig.json`/`node_modules/.bin/vite` environment fixes noted in §7.

## 2. File tree

```
src/apps/recipes/
  api/
    recipesApi.ts        ProductVariant / Recipe / RecipeVersion CRUD + activate
    modifiersApi.ts      ModifierGroup / ModifierOption / ProductModifierGroup / Consumption CRUD
    reportsApi.ts         recipe-profitability, ingredient-consumption
    catalogApi.ts         thin reuse wrappers: product search, product units, branch list
    index.ts               re-exports
  components/
    RecipeHeader.tsx       breadcrumb + title + Recipe/BOM + variant badge
    RecipeInfoCard.tsx     read-only product/recipe/version summary stats
    IngredientRow.tsx      one ingredient line (view or editable-qty mode)
    IngredientTable.tsx    table shell + "Add ingredient" trigger
    IngredientPicker.tsx   product search -> unit/qty modal
    CostPreview.tsx        honest "no live cost" banner (see §4 gap G-1)
    VersionSelector.tsx    version list + activate action
    ModifierPanel.tsx      attach/detach modifier groups on a product
    VariantList.tsx        list + create size variants
    RecipeProductForm.tsx  the reusable editor (see §3)
  hooks/
    useProductSearch.ts    debounced catalog search
    useRecipeVersions.ts    fetch a recipe's versions
  pages/
    RecipeDashboardPage.tsx  /recipes
    RecipeDetailPage.tsx     /recipes/:id
    RecipeEditorPage.tsx     /recipes/new, /recipes/:id/edit
    RecipeVersionsPage.tsx   /recipes/:id/versions
    ModifiersPage.tsx        /recipes/modifiers
    RecipeReportsPage.tsx    /recipes/reports
    index.ts
  routes/
    index.tsx               <RecipesApp> — the one mount point into App.tsx
  services/
    navigation.ts           centralized route-string builders
    productEligibility.ts   isRecipeProduct() — reads product_type, decides nothing
  store/
    recipesStore.ts         zustand — Recipe Editor draft-lines state only
  types/
    index.ts                mirrors every Sprint 5 serializer field-for-field
  utils/
    format.ts                display-only formatting (qty/percent/date)
```

Also touched outside `apps/recipes/`:
- `App.tsx` — 2 lines added (lazy import + route).
- `components/layout/Sidebar.tsx` — 1 nav entry added to the existing
  "Catalog & Stock" group.
- `auth/permissions.ts` — 1 line (`'/recipes': 'Manager'`, cosmetic
  sidebar-visibility floor; the real enforcement is the backend's own
  `IsManagerOrAbove`/`IsCashierOrAbove` permission classes, unchanged).
- `tsconfig.json` — see §7 (environment fix, unrelated to this feature).

## 3. `RecipeProductForm` — the reusable editor

Per the explicit requirement, the ingredient-editing UI is **not** a page —
it's `components/RecipeProductForm.tsx`, taking `productId` (required),
`variantId` (optional, `null` = base recipe), and `autoEdit`/`onSaved`
(optional). `RecipeEditorPage`/`RecipeDetailPage` are thin wrappers that
render it inside the Recipe app's own header chrome. It carries **no
route-level assumptions** (no `useParams`, no page header) — it can be
dropped into `ProductFormModal` later (when `product_type ===
'recipe_product'`) exactly as asked, without a rewrite.

## 4. Backend integration — what's used, what's missing

### Sprint 5 endpoints consumed (all of them)

| Endpoint | Used by |
|---|---|
| `GET/POST /products/{id}/variants/`, `GET/PATCH .../{pk}/`, `POST .../deactivate/` | `VariantList` |
| `GET/POST /products/{id}/recipes/`, `GET/PATCH .../{pk}/` | `RecipeProductForm` |
| `GET/POST /products/{id}/recipes/{rid}/versions/`, `GET .../{pk}/`, `POST .../{pk}/activate/` | `RecipeProductForm`, `VersionSelector`, `RecipeVersionsPage` |
| `GET/POST /catalog/modifier-groups/`, `GET/PATCH .../{pk}/`, `POST .../deactivate/` | `ModifiersPage` |
| `GET/POST /catalog/modifier-groups/{gid}/options/`, `GET/PATCH .../{pk}/`, `POST .../deactivate/` | `ModifiersPage` (group drawer) |
| `GET/POST /catalog/modifier-options/{oid}/consumptions/`, `GET/PATCH .../{pk}/` | `ModifiersPage` (group drawer) |
| `GET/POST /products/{id}/modifier-groups/`, `DELETE .../{pk}/` | `ModifierPanel` |
| `GET /reports/recipe-profitability/` | `RecipeReportsPage` |
| `GET /reports/ingredient-consumption/` | `RecipeReportsPage` |

Every cost/margin/qty_base value rendered anywhere in this batch is read
directly from these responses — grep confirms zero `*` / `/` arithmetic on
a cost-shaped field anywhere in `apps/recipes/`.

### Pre-existing (non-Sprint-5) endpoints reused, not duplicated

`GET /products/` (search + list), `GET /products/{id}/`, `GET
/products/{id}/units/`, `GET /accounts/branches/` — all wrapped once in
`api/catalogApi.ts`, never called with raw `axios`/`apiClient` from a
component.

### Gaps found — documented, not worked around

- **G-1 (real, load-bearing): no endpoint computes a recipe's cost before
  it's sold.** `RecipeVersionSerializer`'s response has no cost field, and
  `recipes.services.costing.compute_recipe_cost()` is internal-only,
  called by `SaleSerializer` at sale time. `CostPreview.tsx` therefore
  shows **no number** — it explains why and links to the Profitability
  report once real sales exist, rather than reimplementing the
  branch-scoped AVCO lookup in React (explicitly banned by the brief).
  **Recommended fix:** a `GET /products/{id}/recipes/{rid}/versions/{vid}/preview-cost/?branch_id=` endpoint reusing the existing service function.
- **G-2: `GET /products/` has no `product_type` filter.** `pos/filters.py`'s
  `ProductFilter.Meta.fields` is `category, active, weighted, plu,
  show_on_pos` only. `RecipeDashboardPage`/`RecipeEditorPage`'s product
  picker fetch a larger page (`page_size=200` / `20`) and filter
  `product_type === 'recipe_product'` client-side — narrowing an
  already-returned field for *display*, not recomputing anything, but
  real request-size waste at catalog scale. **Recommended fix:** add
  `product_type` to `ProductFilter`.
- **G-3: no tenant-wide "recipe completeness" or variant-count endpoint.**
  `/products/{pk}/recipes/` and `/products/{pk}/variants/` are both
  product-scoped — there's no bulk way to know "how many recipe products
  are missing an active recipe" or "how many variants exist across the
  tenant" without an N+1 loop. Rather than loop per-row to fake it,
  `RecipeSummary` only shows the 2 stats that ARE cheap (product count from
  the one products fetch, modifier-group count from the one groups fetch)
  — see that component's own docstring. The reference mockup's
  "Neg ingredient" per-row status column is the same class of gap; not
  built for the same reason.
- **G-4: `ModifierGroup`'s `selection_type`/`min_select`/`max_select`
  fields exist on the backend but have no UI here** — `ModifiersPage`
  displays `selection_type` (read-only) but has no create/edit control for
  any of the three. Low priority: POS-side modifier *selection*
  (respecting `min_select`/`max_select` at checkout) isn't built yet
  either (Batch 9, not this batch), so editing them has no visible effect
  until POS consumes them.

## 5. Design system compliance

Every screen reuses existing primitives exactly — `DataTable`, `Drawer`,
`Modal`, `ConfirmDialog`, `Button`, `FormField`/`SelectField`/`FieldError`/
`SearchField`, `Badge`/`StatusBadge`/`ActiveBadge`, `Icon`, `Tabs`,
`AlertBanner`/`LoadingState`/`EmptyState`/`ErrorState`, `useQuery`/
`useDebounced`, `useMoney`. No new design tokens, no new colors, no
parallel table/modal implementation. `IngredientRow`/`IngredientTable`
hand-render `<table>`/`<tr>`/`<td>` (not `DataTable<T>`) only because a
draft row needs an inline-editable `<input>` cell — the header/cell CSS
classes are copied verbatim from `DataTable.tsx` so it's visually
identical.

## 6. Manual verification (real browser, real backend)

Seeded a demo tenant/branch/user + 3 ingredients + 1 `RECIPE_PRODUCT`
directly via Django shell, then drove the actual UI with Playwright:

1. **Dashboard** (`/recipes`) — stats tile + product list render correctly
   from real `/products/` data, filtered to Recipe type.
2. **Create a recipe** — "Create recipe" → draft mode → `IngredientPicker`
   search ("Chicken") → real `/products/?search=Chicken` results → pick →
   unit auto-loaded from `/products/{id}/units/` → qty entered → added to
   draft table. Repeated for a second ingredient.
3. **Save** — `POST .../versions/` with the 2 lines succeeds, returns a
   DRAFT `v1`; success banner with an "Activate this version" action shown.
4. **Activate** — `POST .../versions/{id}/activate/` succeeds; `RECIPE
   STATUS` flips to Active, `ACTIVE VERSION` shows `v1 · 2 ingredients`.
5. **Version history page** (`/recipes/:id/versions`) — shows `v1 Active`
   with its 2 ingredient lines, independently of the detail page.
6. **Variant creation** — "Add variant" → "Large" @ EGP 70.00 → appears in
   the Size Variants list, links to its own scoped editor
   (`?variant_id=`).
7. **Modifiers** (`/recipes/modifiers`) — created group "Extras"
   ("Choose any"), opened its drawer, added option "Extra Cheese" (EGP
   6.00) — **and, on a repeat run, the backend's own duplicate-name
   validation surfaced correctly in the UI** ("An option with this name
   already exists in this modifier group.") via the existing
   `parseApiError`/`FieldError` pipeline. Consumption sub-panel correctly
   resolves a searched ingredient's units and renders the qty/unit form.
8. **Reports** (`/recipes/reports`) — Tabs, branch selector, date-range
   inputs all render and drive real requests to both report endpoints;
   correct empty state ("No recipe sales in this range") since no sale was
   posted in this seed.
9. **`npm run build`** — clean (`tsc` + `vite build`), no new warnings
   beyond the pre-existing chunk-size notice.

No console errors beyond a pre-existing, unrelated `favicon.ico` 404 (every
page in this app has it, not introduced by this batch).

## 7. Technical debt / things fixed incidentally

- `tsconfig.json` had `baseUrl` flagged deprecated by the TypeScript 6.0.2
  now installed in this environment, which made `tsc` fail outright before
  any of this batch's code could even be type-checked. Added
  `"ignoreDeprecations": "6.0"` — the compiler's own suggested fix,
  behavior-neutral. Unrelated to Recipes; blocks every future batch's
  build verification equally, so fixing it here was necessary to verify
  anything at all.
- `node_modules/.bin/vite` had lost its executable bit in this container
  (`chmod +x` applied) — a local environment artifact, not a repo file
  change.
- Both are infrastructure fixes, not scoped to `apps/recipes/`, and were
  required before `npm run build` could run for the first time in this
  session.

## 8. Explicit non-goals (per the brief)

- No cost/margin computed in React anywhere (grep-verified).
- No `Product.cost` write path touched or referenced.
- No duplication of backend validation (depth/cycle checks, tenant
  scoping, unit compatibility) — every save just POSTs and renders
  whatever the server returns, success or 400.
- No direct `apiClient`/`axios` calls from any component — everything
  routes through `apps/recipes/api/`.
- POS-side consumption of modifiers/variants at checkout — out of scope
  for this batch (Batch 9), not started.
