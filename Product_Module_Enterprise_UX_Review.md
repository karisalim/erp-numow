# Product Module — Enterprise UX Review

**Date:** 2026-07-23
**Scope:** Product module only (Product Type UX, dynamic form, required fields,
barcode strategy, recipe workflow/status, validation UX, cost display) plus a
lightweight pass over adjacent grids. **No backend business rule was
duplicated in React** — every rule below is read from
`GET /api/catalog/product-types/` (backend) or enforced server-side; the
frontend only renders/guides.

**What actually changed in this pass** (the rest of the form was already
built in the prior Phase 3 pass and is reviewed, not rebuilt, below):
- **Barcode Strategy** (item 4) was a real gap — `Product.barcode` was
  DB/API-required for every type. Implemented backend-first:
  `Product.barcode` is now `blank=True` with a **partial unique constraint**
  (`UNIQUE(tenant, barcode) WHERE barcode <> ''`) so any number of products
  may leave it blank without colliding; `required_fields` in
  `product_type_metadata()` never lists `barcode` for any type; a new
  `barcode_visible` boolean per type drives the frontend (hidden for
  **Prep Item / Service / Fixed Asset** — types that never scan). Verified
  live in a real browser: the field disappears for Service/Prep Item and
  reappears, unlabeled-required, for Ingredient/Stock Item.
- Removing `Meta.unique_together` on `barcode` also silently removed DRF's
  auto-generated duplicate-barcode validator (it only derives from
  `unique_together`, not from raw `Meta.constraints`), which would have
  turned a duplicate non-blank barcode into an uncaught 500. Caught by a new
  test before shipping; fixed with an explicit tenant-scoped uniqueness
  check in `ProductSerializer.validate()`.
- 7 new backend tests, full suite re-run (821/821 passing), `npm run build`
  clean, confirmed live via Playwright.

## 1. Product Type UX

| Type | Barcode | Sale fields | Stock fields | Purchase | Cost | Recipe |
|---|---|---|---|---|---|---|
| Stock Item | Visible, optional | Price, tax, sales category | Stock, unit, pack qty, inventory category | Yes, reorder point | Editable at create, AVCO-derived after | — |
| Resale | Visible, optional | same as above | same as above | Yes | AVCO-derived | — |
| Ingredient | Visible, optional | hidden (can't sell) | Stock/unit/pack/category | Yes | AVCO-derived | — |
| Packaging | Visible, optional | hidden | Stock/unit/pack/category | Yes | AVCO-derived | — |
| Prep Item | **Hidden** | hidden | Stock/unit/pack/category | **No** (assembled, not bought) | AVCO-derived | Recipe section (component of others) |
| Recipe Product | Visible, optional | Price, tax, sales category | hidden (no own stock) | No | **Derived breakdown, read-only** | Full workflow card |
| Service | **Hidden** | Price, tax, sales category | hidden | No | hidden (no cost concept) | — |
| Bundle | Visible, optional | Price, tax, sales category | hidden | No | hidden | — |
| Fixed Asset | **Hidden** | hidden | hidden | Yes, reorder point | Editable at create | — |

Every row above is read from the live `GET /catalog/product-types/`
response, not hand-maintained — the table only documents what that endpoint
already returns.

## 2. Dynamic Form Architecture

Already a sectioned workflow, not flat hide/show: **General → Sales →
Inventory → Purchasing → Recipe → Accounting → POS**, each a titled block
with an icon and one-line description; a section with nothing relevant to
render for the current type is simply absent, not shown-disabled. This
matches the item-2 ask (Tabs/sections instead of raw show/hide) — sections
read as sequential steps, closer to Dynamics 365's "FastTab" pattern than a
single dense form.

## 3. Required Fields

`required_fields`/`recommended_fields` come from the same behavior matrix
that drives everything else — never a second list. Two honest tiers:
**Required** (backend 400s if missing — currently only `name`, `price` when
sellable, `cost` at create time when cost-bearing) and **Recommended** (a
muted pill + tooltip, never blocks submit — `sales_category` when sellable,
`inventory_category` when stock-tracked). `barcode` is in neither list for
any type as of this pass — it's a visibility decision, not a requirement
one, matching how SAP/Dynamics/Odoo all treat GTIN/barcode as optional
metadata rather than a mandatory master-data field.

## 4. Barcode Strategy — before/after

**Before this pass:** every type required a barcode; the DB uniqueness
constraint would have rejected a second blank one had the requirement ever
been relaxed carelessly.
**After:** optional everywhere, hidden for the three types that never scan
(Prep Item, Service, Fixed Asset). When hidden, Name (always required and
always shown) is the identifier — no dangling "how do I find this record"
gap. A tenant-level "make barcode mandatory for Stock Items" setting was
considered and deliberately **not** built this pass — no tenant-settings
precedent exists yet for per-type field policy, and nothing in the current
codebase reads such a flag; documented below as a future recommendation
rather than half-wired.

## 5. Recipe Workflow

Confirmed unchanged and correct: "Build Recipe" only renders on the
success screen shown immediately after a Recipe Product is actually
created (the screen structurally cannot render pre-creation — it's fed the
just-created `Product` object). Once a product exists, the persistent
**Recipe workflow card** in the Accounting/Recipe section drives
`No Recipe → Build Recipe`, `Draft → Continue Editing + Manage Versions`,
`Active → Open Recipe + Version History`, with a "not POS-ready yet"
warning when a recipe is active but the product can't sell or isn't shown
on POS.

## 6. Recipe Status

`RecipeStatusBadge` (No Recipe / Draft / Active / POS Ready — 4 distinct
tones) is rendered directly inside the workflow card header, always
visible whenever the Recipe section shows at all — confirmed present in
code and did not need re-wiring this pass.

## 7. Visual Guidance

Every section has a one-line description; every optional-but-suggested
field carries a "Recommended" pill with a tooltip explaining why; the
Purchasing section explicitly states *why* a type can't be purchased
instead of just hiding the controls ("assembled from a recipe" /
"not stocked directly"); empty states, loading spinners, and disabled/
read-only states were standardized in the prior Phase 3 pass and re-checked
here — no regression from the barcode change (the field simply doesn't
render rather than rendering disabled).

## 8. Validation UX

Inline only, no browser popups (`noValidate` + a single
`computeFieldError()` used for both live-as-you-type feedback and the
pre-submit gate) — confirmed still correct after removing `barcode` from
the validated-key list (it's optional now, so it has nothing to validate).
Server errors still win over client guesses when they arrive.

## 9. Cost Display

Recipe Products show a live, read-only **Derived cost** card with an
expandable per-ingredient breakdown (never a single opaque number, never a
hidden section) — sourced from the same cost-preview endpoint the Recipe
Editor itself uses, so the two never disagree.

## 10. Enterprise Review — grids

`ProductsPage`'s table now shows an em-dash placeholder for a blank
barcode instead of empty whitespace, so "no barcode set" reads
intentionally rather than looking broken. The shared `DataTable` component
(sorting, sticky header, pagination, keyboard row activation) was already
in place from the Phase 3 pass; `ProductsPage` itself uses a hand-rolled
table rather than `DataTable` — noted again here as a real, still-open
inconsistency (see §12).

## 11. Comparison against SAP / Dynamics 365 / Odoo

| Dimension | This app | SAP B1 / Dynamics / Odoo |
|---|---|---|
| Type-driven field visibility | Yes, server-metadata-driven | Yes (item groups / product categories) |
| Required vs recommended distinction | Yes, two explicit tiers | Usually binary (required or not); this app's "Recommended" nudge is arguably friendlier |
| Barcode optionality | Now optional, type-aware visibility | Optional everywhere; GTIN is metadata, not a gate |
| Sectioned/workflow form | Yes | Yes (FastTabs / notebook tabs) |
| Recipe/BOM status workflow | Yes, explicit stage badges + actions | Yes, typically a status field + separate BOM screen |
| Derived cost transparency | Yes, live breakdown | Yes (standard cost roll-up view) |
| Per-type barcode policy toggle (tenant setting) | **No** | Some (SAP: item-group level settings) |
| Grid consistency (one shared table component everywhere) | Partial | Yes, uniformly |

## 12. Already Implemented / Improved / Still Recommended

**Already implemented (this pass and prior):** type-driven visible/required/
read-only fields; sectioned dynamic form; required-vs-recommended metadata;
inline validation with no popups; recipe workflow gated on product
existence; recipe status badges; derived recipe cost breakdown; barcode now
optional and type-aware.

**Improved this pass:** Barcode Strategy end to end (model → metadata →
form); a real duplicate-barcode 500 bug caught and fixed before shipping;
Products grid blank-barcode display.

**Still recommended for a future phase (not built, with reasons):**
1. Migrate `ProductsPage`'s hand-rolled table onto the shared `DataTable`
   component for full parity (sort/sticky/keyboard) — deferred to avoid
   touching a working screen outside this pass's stated scope.
2. A tenant-level setting to make barcode mandatory for Stock Items only,
   per the original ask's "(or Required only if company setting enables
   it)" — no tenant-settings precedent for per-type policy exists yet;
   building one well is its own small feature, not a one-line addition.
3. QR/PLU are already supported as separate identifiers (PLU for weighted
   items); a unified "any of barcode/SKU/PLU/QR" search box across Products
   exists via name/SKU/barcode search already — QR-specific scanning is a
   POS hardware integration question, out of this module's scope.
