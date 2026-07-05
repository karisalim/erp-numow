# TRANSITION_AND_MIGRATION_PLAN.md

> **Read-only architecture audit — 6 of 7.** How to evolve the system additively:
> the data migrations, compatibility layers, and the Gate A landing plan — with
> the non-negotiable safety rules. **Planning only.** No runtime code, migrations,
> DB, tests, or frontend were changed; `safety/backend-gate-a-wip-2026-07-04` is
> **not** merged. Nothing below is executed in this pass.

---

## 1. Non-negotiable principles

1. **Additive-first.** New authoritative tables land beside existing ones; the old
   table is demoted (cache / read-only), never dropped in the same step.
2. **No blind migration / no automatic mapping.** Any reclassification (category
   split, unit conversion) is an **explicit admin decision**, surfaced as a
   proposal — never inferred silently.
3. **No direct balance/stock correction without an auditable document.** Every
   quantity/amount change is the effect of a posted document (adjustment, wastage,
   opening-balance, journal), never a manual `UPDATE`.
4. **Preserve tenant/branch isolation and posted history.** Deactivate, never
   delete; reverse via compensating document; append-only ledgers stay append-only.
5. **Reversibility discipline.** Data migrations that provision real financial
   config (e.g. routing) declare an explicit no-op reverse and are documented as
   forward-only.

---

## 2. Data-migration & compatibility inventory

Each item: **Change · Migration approach · Compatibility layer · Safety.**

### 2.1 Route deduplication / deprecation (D-1…D-3, D-5…D-7)
- **Change:** converge `/api/auth/*`+`/api/accounts/*` → one prefix; legacy branch
  surfaces → `/api/branches/`; sale int-pk → UUID; retire direct-mutation POSTs.
- **Approach:** no DB migration — routing + view changes only, on a later slice.
- **Compat:** keep both prefixes during a **cutover window**; frontend already
  consumes `/api/branches/`, `/api/customers/`, `/sales/{uuid}/`. Emit deprecation
  notice; remove only after client-usage audit shows zero traffic on the old path.
- **Safety:** additive first (new canonical path), removal is a separate slice.

### 2.2 Inventory authority: `Product.stock` → per-warehouse (`WarehouseStock`) (R-1)
- **Change:** make `WarehouseStock` the authoritative on-hand; `Product.stock`
  becomes a derived cache. **Recorded directive R-B:** `WarehouseStock.quantity` is
  denominated in the **product base unit only** — conversions live on
  `ProductUnit`; separate balances per conversion unit are never stored.
- **Approach:** **derive** `WarehouseStock` by replaying `StockMovement` history
  (which already carries `warehouse`, `quantity_before/after`, `source_document_*`)
  per (tenant, product, warehouse). Movements lacking a warehouse land in an
  explicit "unassigned" bucket, targeting the **intended reconciliation
  invariant** `Σ WarehouseStock + unassigned == Product.stock` — which is **not
  yet guaranteed and must be verified by the data audit** before cutover, not
  assumed.
- **Compat:** keep `Product.stock` populated (derived) during transition so legacy
  readers keep working; cut readers over gradually.
- **Safety:** the migration is a **derivation + reconciliation report**, not a
  manual set. Any product where derived ≠ `Product.stock` is flagged for an
  **adjustment document**, never silently corrected. Unassigned-bucket cleanup is
  an admin task with an auditable adjustment.

### 2.3 Category split: `Category` → hierarchical SalesCategory + InventoryCategory (R-2 / CR-1 / R-J)
- **Change:** two new **hierarchical** category trees (self-parent «تندرج من»)
  replace the flat one — SalesCategory (menu) and InventoryCategory (stock),
  never merged ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.2/§6.3).
- **Approach:** create both tables empty; **no automatic mapping** of existing
  `Category` rows. Provide an admin-driven classification step that proposes (but
  does not commit) a mapping from the legacy category name, including its place
  in the hierarchy and its inheritable defaults (tax, revenue GL, COGS GL,
  station, POS visibility · inventory-asset/wastage/adjustment/variance GL).
- **Compat:** legacy `Category` retained **read-only**; products keep the legacy FK
  until reclassified; POS filtering falls back to legacy category until migrated.
- **Safety:** account links are set by the admin at classification time — the
  migration never guesses GL account mapping. From the first posted document
  onward, **resolved category defaults are snapshotted on the document** (R-J),
  so later re-parenting/re-mapping never alters posted history.

### 2.4 Units: fixed `unit`/`pack_qty` → UnitGroup/Unit/ProductUnit (R-3 / CR-7)
- **Change:** data-driven unit conversions. `ProductUnit` rows are **conversion
  definitions only** — stock balances remain in the base unit (§2.2); no
  migration ever creates a per-conversion-unit balance.
- **Approach:** seed a default UnitGroup/Unit set; for each product, generate a
  **proposed** `ProductUnit` from its current `unit` + `pack_qty` — presented for
  confirmation, not auto-committed.
- **Compat:** `Product.unit`/`pack_qty` retained until every product has a confirmed
  base `ProductUnit`; pricing/costing read legacy fields until cutover.
- **Safety:** no silent conversion; barcodes migrate to `ProductBarcodeUnit`
  additively.

### 2.5 Costing: `Product.cost` → base-unit average cost (R-4 / CR-7 / D-35)
- **Change:** the moving-average cost moves off `Product.cost` into its new home
  per **D-35** — either the base ProductUnit or (recommended) a dedicated
  InventoryCost/valuation record per product; COGS reads it. `ProductUnit`
  remains primarily a conversion definition and **conversion units never carry
  independent averages**.
- **Approach:** copy current `Product.cost` into the D-35 home as the opening
  average; forward purchases update the new field.
- **Compat:** `SaleItem.unit_cost` historical snapshots untouched; `Product.cost`
  kept as mirror during transition.
- **Safety:** forward-only; no recomputation of historical COGS.

### 2.6 General Ledger introduction (R-5 / CR-2)
- **Change:** add **ChartOfAccount (the full accounting ledger — a separate
  concept from the operational FinancialAccount)** + JournalEntry + balanced
  JournalLine + posting rules; posting engine writes GL **and** subledgers
  atomically.
- **FinancialAccount → GL mapping step:** add a `gl_account` FK on
  FinancialAccount and map every operational account (cashbox/main_safe/bank/
  card_settlement/wallet) to its ledger account before cutover. The GL-ish
  FinancialAccount types (`customer_ar`, `supplier_ap`, `expense`,
  `opening_balance`) map to GL **control** accounts and are flagged for cleanup —
  new GL-only accounts (inventory, revenue, VAT) are created **only** in
  ChartOfAccount, never as FinancialAccount rows.
- **Approach:** **forward-only.** New posted documents write GL journals from
  day one. Historical subledger balances enter GL via a single dated **opening
  journal** per account (balanced), **not** by retro-exploding historical sales/
  purchases into journal lines.
- **Compat:** subledgers (`FinancialAccountMovement`, AR/AP) remain the operational
  statements; GL control accounts reconcile to subledger totals.
- **Safety — the five reconciliation identities must hold at cutover and
  continuously after** ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §1):
  (1) Σ GL debits = Σ GL credits; (2) AR control = Σ `CustomerARMovement`;
  (3) AP control = Σ `SupplierAPMovement`; (4) Inventory control = inventory
  valuation (base-unit qty × moving-average cost); (5) each cash/bank GL account
  = its linked operational subledger balance. The opening journal is an
  auditable document.

### 2.7 `BranchSettings.default_*_id` placeholders → FKs (PLACE-1 / D-8)
- **Change:** replace BigInt placeholders with real FKs; or retire them in favour of
  `BranchWarehouse(role,is_default)` (the canonical home).
- **Approach:** the placeholders were **designed** for an additive FK swap (models
  document this). Reconcile any placeholder that disagrees with the canonical
  `BranchWarehouse` default via an admin decision, then swap.
- **Safety:** if placeholder ≠ canonical default, do **not** auto-pick — surface the
  conflict.

### 2.8 Opening balances → posted documents (§3.5 of workflow status)
- **Change:** `FinancialAccount.opening_balance` / `Customer.opening_balance` /
  `Supplier.opening_balance` (currently stored, never posted) become **opening-
  balance documents** that post real movements (and GL journals once GL exists).
- **Approach:** for each non-zero stored opening balance, generate a proposed
  opening-balance document for admin confirmation.
- **Safety:** balances become auditable; the stored hint field is retired only after
  the document exists. **Never** convert a stored hint into a silent balance.

### 2.9 `price_tier_id` placeholder → FK (PLACE-2)
- Additive FK swap once `PriceTier` exists; no data transform (currently all null/
  unenforced).

### 2.10 Product-type backfill (Slice 4/§6.4)
- **Change:** every existing `Product` gains `product_type` + `sellable` /
  `purchasable` / `track_inventory` / `base_unit` + category FKs.
- **Approach:** propose **Stock/Resale Item** for every existing product
  (conservative: sellable ✔, purchasable ✔, track_inventory ✔; base_unit seeded
  from the current fixed `unit`), presented for admin confirmation — **no silent
  reclassification** into Ingredient/Prep/Recipe types.
- **Compat:** unconfirmed products behave exactly as today.
- **Safety:** flags only widen behavior after explicit confirmation.

### 2.11 Recipe / variant / production introduction (Slices 11, 11b — forward-only)
- **Change:** net-new tables (ProductVariant, Recipe/RecipeVersion/RecipeLine,
  ModifierGroup/Option + RecipeConsumptionDelta, ProductionOrder, snapshot
  tables per D-31).
- **Approach:** forward-only. Recipes attach to products/variants from their
  activation date; RECIPE_CONSUME depletion and snapshots apply only to
  documents posted after activation. **No retro-costing** of historical sales.
- **Compat:** posted documents predating recipes carry **null snapshots** —
  every report must tolerate them (variance/food-cost reports simply exclude
  pre-recipe rows).
- **Safety:** RecipeVersion approval runs the cycle check (D-27) and the
  nesting-depth cap (D-26); production posts value output at actual batch cost,
  with **production variance recorded only against an approved standard/planned
  basis** (D-29) and **abnormal wastage separately expensed** (D-30, production
  scope). Posted
  production orders are never unposted (R-C) — corrections are reversal
  documents.

---

## 3. Gate A (safety branch) — **component-by-component review; NOT approved wholesale**

`safety/backend-gate-a-wip-2026-07-04` (9 files, +1057/−154) is the highest-value,
already-implemented change. It is quarantined per instruction and **must not be
merged as a single unit**. Each component gets its own review verdict; **migration
`0017` is explicitly NOT approved as-is** and must be replaced before landing.

### 3.1 Per-component review verdicts

| # | Component | What it does | Verdict | Condition |
|---|---|---|---|---|
| GA-1 | Env-driven `settings.py` + `.env.example` | `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/DB/CORS from env, dev-safe defaults | **Recommend approve** | Verify prod env vars are set before any deploy; no schema impact. |
| GA-2 | `sale_posting` strict routing | Every completed cash/card/wallet sale must resolve an active route or the sale rolls back (400) | **Recommend approve — contingent on GA-5 replacement** | Must not land before every existing branch has routing via the reviewed provisioning workflow (otherwise live branches stop selling). |
| GA-3 | `SaleSerializer` credit-limit guard | Blocks credit sale when `balance + total > credit_limit` (`<=0` treated as unlimited) | **Recommend approve — pending D-14** | The null/zero credit-limit semantics decision (D-14) must be ratified first; current `<=0 = unlimited` reading is a policy choice, not a given. |
| GA-4 | `SaleSerializer` negative-stock guard | Oversell blocked unless `BranchSettings.allow_negative_stock`; structured errors | **Recommend approve — pending D-15** | Confirm the override model (branch toggle only vs per-sale manager override) before landing. |
| GA-5 | **Migration `0017_backfill_branch_payment_routing`** | Blindly provisions default cashbox/card/wallet accounts + methods + default routes for every unrouted branch inside a schema migration; `noop_reverse` | **DO NOT APPROVE AS-IS** | Replace with the reviewed provisioning workflow in §3.2. Financial master data must never be created silently by a migration. |
| GA-6 | `BranchPaymentMethodSerializer` one-default guard | At most one active default route per (branch, method_type); deterministic `(-is_default,-id)` resolution | **Recommend approve** | The duplicate-default *demotion* moves into the §3.2 command (dry-run reviewable), not a migration. |
| GA-7 | Financially-correct void + void idempotency (in the WIP `views.py`/YAML) | Void posts compensating ledger entries under row lock; `Idempotency-Key` replay | **Recommend approve** | Confirm reversal entries follow the compensating-document pattern; add tests to the landing checklist. |
| GA-8 | Structured error shape `{field:[msg], code, detail}` | Stable machine-readable error codes | **Recommend approve** | FE already renders these. |
| GA-9 | +535 L tests | Strict routing, credit limit, negative stock, backfill coverage | **Recommend approve** | Re-point backfill tests at the §3.2 command; full suite green pre-merge. |
| GA-10 | `pos/urls.py` 1-line rename: `products/{pk}/warehouse-stock/` → `warehouse-stocks/` | Aligns the backend route with the plural path the frontend already calls ([erp.ts:168](superpos/src/api/erp.ts#L168)) — **fixes a live 404 mismatch on mvp** (product warehouse-breakdown drawer) | **Recommend approve** (trivial, standalone) | Can land ahead of every other GA component; no schema, no data. |

### 3.2 Required replacement for migration `0017`: dry-run provisioning + admin review

Instead of a blind data migration, payment-routing provisioning becomes an
**explicit, reviewable operation**:

1. **Management command** `provision_default_payment_routing`
   - `--dry-run` (default): reports, per tenant/branch, exactly what would be
     created or reused — accounts (with names), payment methods, routes, and any
     duplicate-default demotions — **without writing anything**.
   - `--apply [--tenant=<id>]`: executes only after the dry-run output has been
     reviewed/approved; idempotent (skips branches that already have routing);
     logs every created/reused row.
2. **Admin review workflow:** the dry-run report is confirmed by the tenant
   owner/admin (or an operator acting with their sign-off) before `--apply`; for
   new tenants, a guided setup screen creates routing explicitly at onboarding so
   the command is only a backfill tool for pre-existing tenants.
3. **The schema migration itself is reduced to nothing** (or at most a no-op
   placeholder) — no financial rows are created inside `migrate`.
4. **Strict-routing ordering guarantee:** GA-2 lands only after the command has
   been applied (and verified) for every active tenant, so no branch stops
   selling on deploy.

**Sequencing:** the Gate A components can land **before** the catalog/GL rework
(they do not depend on R-1…R-5) and remain the recommended first *code* slice
after architecture ratification — but only per-component, in the order:
GA-10 (standalone 404 fix, anytime) → GA-1 → GA-6/GA-8 → §3.2 command applied
everywhere → GA-2 → GA-3/GA-4 (after D-14/D-15) → GA-7 → GA-9 throughout.

---

## 4. Compatibility-window checklist (applies to every DEPRECATE item)
1. Ship the new canonical surface additively.
2. Announce deprecation in the OpenAPI schema + docs.
3. Audit client usage (frontend is the only known consumer today).
4. Migrate clients; keep the old surface serving.
5. Remove the old surface in a **separate** scheduled slice once traffic is zero.

---

## 5. Migration risk register

| Risk | Mitigation |
|---|---|
| Derived per-warehouse stock ≠ global `Product.stock` | Reconciliation report + admin adjustment document; never silent set. |
| Category reclassification wrong GL account | Admin sets account at classification; no auto-map (CR-1). |
| Blind financial provisioning at deploy time | Migration `0017` **not approved as-is** — replaced by the `provision_default_payment_routing --dry-run/--apply` command + admin review (§3.2); nothing financial is created inside `migrate`. |
| Strict routing lands before all branches are provisioned → live branches stop selling | GA-2 gated on §3.2 command applied + verified for every active tenant. |
| GL opening journal imbalance / control drift | Validate all five reconciliation identities (§2.6) at cutover and as a recurring check: balanced journals, AR/AP controls = subledger totals, inventory control = valuation, cash/bank GL = operational subledgers. |
| Route removal breaks an unknown client | Removal gated on zero-traffic audit; separate slice. |
| Opening-balance double count | Convert stored hint → document exactly once; retire the field after. |
| Circular recipe / runaway nesting | DAG validation + depth cap at RecipeVersion approval (D-26/D-27) — never discovered at posting time. |
| Legacy documents lack recipe/cost snapshots | Forward-only snapshots (§2.11); reports tolerate null snapshots and exclude pre-recipe rows from variance/food-cost analytics. |
| Prep-batch valuation error (yield mis-set) | Output valued at actual batch cost; **production variance is recorded only against an approved standard/planned basis** (D-29) and **abnormal wastage is separately expensed** (D-30, production scope) — deviation is never smeared into avg cost silently. |

Sequencing and slice gating in
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md); dispositions in
[KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md); conflicts in
[TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md).
