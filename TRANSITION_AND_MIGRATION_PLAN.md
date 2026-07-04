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
  becomes a derived cache.
- **Approach:** **derive** `WarehouseStock` by replaying `StockMovement` history
  (which already carries `warehouse`, `quantity_before/after`, `source_document_*`)
  per (tenant, product, warehouse). Movements lacking a warehouse land in an
  explicit "unassigned" bucket, preserving the current invariant
  `Σ WarehouseStock + unassigned == Product.stock`.
- **Compat:** keep `Product.stock` populated (derived) during transition so legacy
  readers keep working; cut readers over gradually.
- **Safety:** the migration is a **derivation + reconciliation report**, not a
  manual set. Any product where derived ≠ `Product.stock` is flagged for an
  **adjustment document**, never silently corrected. Unassigned-bucket cleanup is
  an admin task with an auditable adjustment.

### 2.3 Category split: `Category` → SalesCategory + InventoryCategory (R-2 / CR-1)
- **Change:** two new category trees replace the flat one.
- **Approach:** create both tables empty; **no automatic mapping** of existing
  `Category` rows. Provide an admin-driven classification step that proposes (but
  does not commit) a mapping from the legacy category name.
- **Compat:** legacy `Category` retained **read-only**; products keep the legacy FK
  until reclassified; POS filtering falls back to legacy category until migrated.
- **Safety:** revenue/asset account links are set by the admin at classification
  time — the migration never guesses GL account mapping.

### 2.4 Units: fixed `unit`/`pack_qty` → UnitGroup/Unit/ProductUnit (R-3 / CR-7)
- **Change:** data-driven unit conversions.
- **Approach:** seed a default UnitGroup/Unit set; for each product, generate a
  **proposed** `ProductUnit` from its current `unit` + `pack_qty` — presented for
  confirmation, not auto-committed.
- **Compat:** `Product.unit`/`pack_qty` retained until every product has a confirmed
  base `ProductUnit`; pricing/costing read legacy fields until cutover.
- **Safety:** no silent conversion; barcodes migrate to `ProductBarcodeUnit`
  additively.

### 2.5 Costing: `Product.cost` → `ProductUnit.avg_cost` (R-4 / CR-7)
- **Change:** moving-average cost moves onto the base ProductUnit; COGS reads it.
- **Approach:** copy current `Product.cost` to the confirmed base `ProductUnit.avg_cost`
  as the opening average; forward purchases update the new field.
- **Compat:** `SaleItem.unit_cost` historical snapshots untouched; `Product.cost`
  kept as mirror during transition.
- **Safety:** forward-only; no recomputation of historical COGS.

### 2.6 General Ledger introduction (R-5 / CR-2)
- **Change:** add ChartOfAccount + JournalEntry + balanced JournalLine + posting
  rules; posting engine writes GL **and** subledgers atomically.
- **Approach:** **forward-only.** New posted documents write GL journals from
  day one. Historical subledger balances enter GL via a single dated **opening
  journal** per account (balanced), **not** by retro-exploding historical sales/
  purchases into journal lines.
- **Compat:** subledgers (`FinancialAccountMovement`, AR/AP) remain the operational
  statements; GL control accounts reconcile to subledger totals.
- **Safety:** opening journal is an auditable document; trial balance validates
  GL = Σ subledgers at cutover.

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

---

## 3. Gate A (safety branch) landing plan — **review, do not merge now**

`safety/backend-gate-a-wip-2026-07-04` (9 files, +1057/−154) is the highest-value,
already-implemented change. It is quarantined per instruction. When later approved
as a slice, land it as follows (review checklist, not an action here):

| Component | What it does | Landing note |
|---|---|---|
| Env-driven `settings.py` + `.env.example` | `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/DB/CORS from env with dev-safe defaults | No schema; verify prod env is set before deploy. |
| `sale_posting` strict | Every completed cash/card/wallet sale must resolve an active route or the sale rolls back (400) | Removes the "silent skip"; depends on 2.10 below. |
| `SaleSerializer` guards | Credit-limit enforcement; negative-stock blocked unless `BranchSettings.allow_negative_stock`; structured `{field:[msg],code,detail}` errors | Behavioral change — FE already renders these. |
| `BranchPaymentMethodSerializer` | At most one active default route per (branch, method_type) | Backed by deterministic `(-is_default,-id)` resolution. |
| **Migration `0017_backfill_branch_payment_routing`** | Provisions default cashbox/card/wallet accounts + methods + default `BranchPaymentMethod` for every branch with no routing; demotes duplicate active defaults | **Forward-only** (`noop_reverse`) — provisioned config becomes real tenant data once sales post against it. Idempotent (skips already-configured branches). **Review provisioned account/method naming per tenant before deploy.** |
| +535 L tests | Cover strict routing, credit limit, negative stock, backfill | Run full suite pre-merge. |

**Sequencing:** Gate A can land **before** the catalog/GL rework (it is
self-contained and does not depend on R-1…R-5), and is the recommended first *code*
slice after architecture ratification.

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
| Gate A backfill provisions unwanted accounts | Review per-tenant naming; migration reuses existing accounts of a type before creating. |
| GL opening journal imbalance | Validate trial balance = Σ subledgers at cutover before enabling GL reports. |
| Route removal breaks an unknown client | Removal gated on zero-traffic audit; separate slice. |
| Opening-balance double count | Convert stored hint → document exactly once; retire the field after. |

Sequencing and slice gating in
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md); dispositions in
[KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md); conflicts in
[TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md).
