# Batch 5b — Frontend Sprint 2 Integration + Missing-UI Design

**Status: IN PROGRESS. This file is the durable execution plan — read it first if resuming
after a context reset. Update the checkboxes as work lands; do not restart finished sub-batches.**

Branch: `s2/batch-5b-frontend-pos-integration` (based on `s2/batch-5a-pos-backend`, which is
merged/pushed — backend for Sprint 2 is complete through Phase 1.5 + Batch 5a).

Source of truth for the gap analysis this plan closes: the Frontend/Backend Integration Audit
appended to `/root/.claude/plans/snuggly-sparking-noodle.md` (Parts 1–10). Do not re-derive that
audit — read it if you need the "why" behind a task below.

Verification command for every sub-batch (no test framework configured on the frontend — this
is the full check): `cd superpos && npm run build` (runs `tsc` then `vite build`). Must pass
clean before a sub-batch is considered done. Where feasible, also boot `npm run dev` and smoke
the flow manually / describe why that wasn't possible.

---

## Locked backend contracts (verified directly from source, do not re-guess these)

- `GET /api/products/scan/<barcode>/` → `{type:'barcode', product, product_unit?}` where
  `product_unit = {id, unit_id, unit_name, conversion_to_base, is_base}` — OR
  `{type:'weight_encoded', product, plu, quantity, price_each, line_total}` for scale barcodes
  (views.py `product_scan`). Replaces `/products/barcode/<code>/` (legacy, no unit info).
- `POST /api/sales/` item shape — EITHER legacy `{product, qty, price_each}` OR unit-aware
  `{product, product_unit, entered_qty}` (server derives `qty`/`price_each`). Top-level optional
  `price_tier` (write-only FK id). Never send both shapes on the same line.
- `GET /api/products/<id>/units/` → `ProductUnitSerializer` list: `{id, unit, unit_name,
  unit_symbol, allow_decimal, conversion_to_base, is_base, is_sale_unit, is_purchase_unit,
  is_recipe_unit, minimum_order_qty, is_active}`. Filter client-side to `is_active &&
  is_sale_unit` for the POS unit picker, `is_active && is_purchase_unit` for purchase lines.
- `GET /api/products/<id>/units/<unit_id>/tier-prices/` → `ProductUnitTierPriceSerializer` list:
  `{id, price_tier, price_tier_name, price, is_active}`. Used only for a DISPLAY estimate in the
  unit picker (mirrors backend's own tier→Product.price fallback for preview purposes) — the
  authoritative price is always whatever the server returns after `POST /sales/`.
- `GET /api/catalog/price-tiers/` → `PriceTierSerializer`: `{id, name, is_active}`.
- `GET /api/catalog/unit-groups/`, `GET /api/catalog/units/` → `UnitGroupSerializer` /
  `UnitSerializer` (`Unit` adds `standard_code`, `standard_code_display`, `factor_to_base`,
  `allow_decimal`).
- `GET /api/catalog/standard-unit-codes/` → `[{code, label}, ...]`, no auth-tenant scoping
  needed beyond `IsCashierOrAbove`, no pagination.
- `GET/POST /api/products/<id>/barcodes/` → `ProductBarcodeUnitSerializer`: `{id, product_unit,
  unit_name, conversion_to_base, barcode, is_default}`.
- `GET/POST /api/catalog/sales-categories/`, `/api/catalog/inventory-categories/` →
  `{id, name, parent, parent_name, is_active}` (two independent trees, `parent` nullable FK).
- `ProductSerializer` (Sprint 2 fields) — `product_type`, `product_type_display`, `behavior`
  (read-only flags: `can_sell`, `can_purchase`, `track_inventory`, `affects_stock`,
  `requires_cost`, `can_have_recipe`), `sales_category`/`sales_category_name`,
  `inventory_category`/`inventory_category_name`, `show_on_pos`, `is_discountable`.
  `ProductType` choices: `stock_item, ingredient, prep_item, recipe_product, resale, packaging,
  service, bundle, fixed_asset`.
- `ProductFilter` supports `?show_on_pos=true` (opt-in, must be passed explicitly) and the
  product list view has `search_fields = ['name','barcode','sku']` (DRF SearchFilter — `?search=`
  already works, nothing to add backend-side).
- `PurchaseInvoiceLineSerializer` — same `product_unit`+`entered_qty` optional pattern as sale
  items; `minimum_order_qty` enforcement happens server-side in
  `pos/services/purchase_invoices.py` (400 if `entered_qty < product_unit.minimum_order_qty`) —
  frontend should mirror it client-side too for instant feedback, but the server check is
  authoritative either way.

---

## Sub-batch 5b-1 — POS core unit-aware selling (P0, critical path)

- [ ] `types/erp.ts`: add `Unit`, `UnitGroup`, `UnitPayload`, `UnitGroupPayload`, `ProductUnit`,
      `ProductUnitPayload`, `ProductBarcodeUnit`, `ProductBarcodeUnitPayload`, `PriceTier`,
      `PriceTierPayload`, `ProductUnitTierPrice`, `ProductUnitTierPricePayload`,
      `StandardUnitCode { code: string; label: string }`.
- [ ] `api/erp.ts`: add `unitsApi` (unitGroups list/create/update/deactivate, units
      list/create/update/deactivate, standardCodes list), `productUnitsApi` (list/create/update
      per product, list/create/update barcodes per product), `priceTiersApi`
      (list/create/update/deactivate, tierPrices list/create/update per product+unit).
- [ ] `api/pos.ts` (NEW): typed wrappers for POS-specific calls — `scanBarcode(code)`,
      `listPosProducts(params)` (always injects `show_on_pos: 'true'`), `createSale(payload,
      idempotencyKey)`. Keeps `POSPage.tsx` from hand-rolling `apiClient` calls for the new
      unit-aware surface, matching the `api/erp.ts` convention used by every other v3.6 module.
- [ ] `types/index.ts`: extend `CartItem` with optional `productUnitId?: number`,
      `unitLabel?: string`, `enteredQty?: number` (kept optional so legacy base-unit lines are
      unchanged — `qty` stays the base-unit quantity for those).
- [ ] `store/posStore.ts`: `addItem` gains an optional 4th param for the chosen `ProductUnit` +
      resolved display price; add `priceTierId: number | null` + `setPriceTier` to `PosState`
      (mirrors `customer`/`discountType` pattern already there).
- [ ] NEW `components/pos/UnitPickerModal.tsx`: opens when a product with >1 sale-eligible
      `ProductUnit` is tapped/scanned; lists eligible units + entered-qty input, previews price
      per unit (via tier-prices lookup, falling back to `Product.price` — see contract note
      above), confirms into `addItem`. Products with exactly one (or zero) sale ProductUnit skip
      the modal entirely — base-unit flow is unchanged for the common case.
- [ ] `POSPage.tsx`:
  - switch barcode submit to `api/pos.ts#scanBarcode` (`/products/scan/`), branch on
    `type: 'weight_encoded' | 'barcode'`, and when `product_unit` is present and non-base, open
    `UnitPickerModal` pre-filled instead of adding directly.
  - switch quick-grid/product fetch to `listPosProducts({ show_on_pos: 'true', active: 'true' })`.
  - add a product search box (debounced, `?search=`) — currently absent entirely.
  - add a price-tier dropdown (populated from `priceTiersApi`), wired to `posStore.priceTierId`.
  - `completeSale()`: for lines carrying `productUnitId`, send `{product, product_unit,
    entered_qty}` instead of `{product, qty, price_each}`; include top-level `price_tier` when
    set.
  - remove the hardcoded `['5410188006353', ...]` demo-barcode buttons (Part 7 cleanup, bundled
    here since it's the same file/area).
- [ ] `components/pos/CartLine.tsx`: when a line has `unitLabel`, show "`entered_qty` ×
      `unitLabel`" instead of the raw base-unit `qty`.
- [ ] Verify: `npm run build` clean. Boot `npm run dev`, confirm the page loads without console
      errors (backend needed for a full click-through — note in the wrap-up whether that was
      possible in this environment).
- [ ] Commit + push.

## Sub-batch 5b-2 — Admin CRUD for Units & Price Tiers (P1, currently zero UI)

- [ ] NEW `pages/units/UnitsPage.tsx` — modeled on `pages/customers/CustomersPage.tsx`
      (`useQuery` + `DataTable` + `FilterBar` + Modal form): two sections/tabs, Unit Groups and
      Units, create/edit/deactivate, `standard_code` as an optional searchable `<select>`
      populated from `unitsApi.standardCodes()`.
- [ ] NEW `pages/pricing/PriceTiersPage.tsx` — same pattern, simpler (flat list, name +
      is_active).
- [ ] NEW `pages/products/ProductUnitsDrawer.tsx` — opened from a row action on
      `ProductsPage.tsx`; manages one product's `ProductUnit` conversions (incl.
      `minimum_order_qty`, `is_sale_unit`/`is_purchase_unit` toggles), its `ProductBarcodeUnit`
      pack barcodes, and per-unit `ProductUnitTierPrice` rows (nested small table per unit).
- [ ] `Sidebar.tsx` + `App.tsx` + `auth/permissions.ts` (`ROUTE_MIN_ROLE`): add `/units` and
      `/price-tiers` routes (Manager+, lazy-loaded like the other ERP modules).
- [ ] `ProductsPage.tsx`: add a "Units & pricing" row action opening `ProductUnitsDrawer`.
- [ ] Verify + commit + push.

## Sub-batch 5b-3 — Category Trees UI + Product classification (P2)

- [ ] NEW `pages/categories/CategoriesPage.tsx` — two tabs (Sales / Inventory), tree view
      (indent by depth) + create/edit/deactivate modal with a parent picker scoped to the same
      tree and excluding descendants of the node being edited (mirrors the backend's cycle
      guard, for a fast UI rejection before the round trip).
  - `Sidebar.tsx`/`App.tsx`/permissions: add `/categories` route (Manager+).
- [ ] `components/products/ProductFormModal.tsx`: add `product_type` select (9 values from
      `ProductType`), read-only behavior-flag chips once the product exists (`can_sell`,
      `can_purchase`, etc. — informational, not editable), `sales_category`/`inventory_category`
      selects (tree-aware, indent by depth), `show_on_pos`/`is_discountable` toggles. Legacy flat
      `category` field stays untouched (still authoritative for existing behavior per backend
      contract) — the new fields are additive alongside it, not a replacement.
- [ ] Verify + commit + push.

## Sub-batch 5b-4 — Purchases unit-awareness + cleanup (P2/P3)

- [ ] `types/erp.ts`: extend `PurchaseInvoiceLinePayload` with optional `product_unit` /
      `entered_qty` (qty/unit_cost stay for the legacy shape).
- [ ] `pages/purchases/PurchaseCreatePage.tsx`: per-line unit picker (purchase-eligible
      `ProductUnit`s only, `is_purchase_unit`), client-side `minimum_order_qty` check before
      submit (mirrors the server's own guard for instant feedback — server check remains
      authoritative).
- [ ] Delete dead `src/data/mock.ts` (confirmed 0 importers in the audit).
- [ ] Optional/stretch if time remains: consolidate the duplicated `Sale` DTOs
      (`SaleRow`/`SaleResponseDto`/`SaleDetail`) into one canonical type in `types/erp.ts`. Not
      required to consider Batch 5b done — only do this if 5b-1..5b-4 are fully green first.
- [ ] Verify + commit + push.

## Final wrap-up (after all sub-batches)

- [ ] Full `npm run build` clean on the final state.
- [ ] Update `IMPLEMENTATION_PROGRESS.md` with a Batch 5b execution record (same format as prior
      batches: scope, changed files, new pages/routes, risks, what's still manual-QA-only).
- [ ] Push final branch state; report to the user what was built, what's stubbed/needs real
      backend data to fully exercise, and any explicit scope cuts made along the way.
