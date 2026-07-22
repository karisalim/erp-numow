# Sprint 5 — Architecture Decisions & Production-Readiness Gate (Batch 7)

**Status:** Backend complete (Batches 1–6 + hotfixes). This document is the
Batch 7 output: a validation gate, not a feature batch. It records every
architectural decision made during Sprint 5, the results of a production-
readiness review (data integrity, concurrency/ACID, idempotency, snapshot
completeness, ledger consistency, performance, migrations, API contract),
a test coverage matrix, the defects fixed in Batch 7, and the residual
risks deliberately left open with rationale.

Scope of Sprint 5: Recipes/BOM, Size Variants, Dynamic Modifiers,
branch-scoped AVCO costing, `RECIPE_CONSUME` depletion at sale time, and
recipe/food-cost reporting. Frontend (Batches 8–10) has not started; this
gate precedes it.

---

## Part A — Architectural decisions (the "why")

Governance decision IDs (D-xx) trace to `ARCHITECTURE_DECISIONS_REQUIRED.md`
§3.5/§4, where the owner authorization for the Sprint 5 subset of gate G4
and the D-09 reopen is recorded (2026-07-22).

### A-1. Branch-scoped average cost; warehouse-scoped quantity (D-09 → Option B)

- **Decision:** `InventoryCost` moved from one row per product (tenant-wide,
  `OneToOneField`) to one row per `(product, branch)` (`ForeignKey` + nullable
  `branch`). `branch=NULL` is retained as the tenant-wide fallback row.
  Stock *quantity* stays warehouse-level (`WarehouseStock`, unchanged); only
  the *average cost* dimension became branch-scoped.
- **Why:** the owner's worked example — buying cheese into Cairo's kitchen
  must not silently reprice Alexandria's stock. This is the exact upgrade
  path the `InventoryCost` docstring had anticipated since Sprint 3.
- **Alternatives rejected:** warehouse-level average cost (finer than the
  owner asked for, more rows, no requirement); keeping tenant-wide and
  reporting branch margin only (doesn't solve cross-branch reprice).
- **Backward compatibility:** every pre-Sprint-5 call site passes
  `branch=None` and is byte-for-byte unchanged (same `Product.stock`-based
  blend). A real branch uses `get_branch_stock_balance(product, branch)`
  (sum of that branch's warehouses' `WarehouseStock`) as the moving-average
  denominator. For a single-branch tenant the two are numerically identical,
  which is why the entire Sprint 3/4 costing suite stayed green.
- **Uniqueness:** paired constraints — `UniqueConstraint(product, branch)`
  plus a partial `UniqueConstraint(product) WHERE branch IS NULL` — because
  Postgres treats NULLs as distinct in a plain unique index, so the second
  constraint is required to enforce "at most one tenant-wide row per
  product." (Same pattern `SalesCategory`/`InventoryCategory` use for
  "unique root name where parent IS NULL".)
- **`Product.cost` mirror:** still synced unconditionally on every cost
  write regardless of branch — a deliberate 2dp display mirror of "whichever
  branch/tenant-wide row last transacted," **not** a partitioned per-branch
  truth. Authoritative per-branch cost is read from the `InventoryCost` row
  directly. Documented, not a bug.

### A-2. Size Variants as variant-of-one-product (D-24)

- **Decision:** `ProductVariant(product FK, name, own price, sort_order)`.
  Each variant carries its **own independent price** (not a multiplier of
  the parent) and its **own independent Recipe** (not a scaled base recipe).
  No barcode — a variant is never routed through `ProductBarcodeUnit`.
- **Why:** a Large pizza is not "1.5× a Small" in either price or
  ingredients; cafés set both independently.

### A-3. Recipe / RecipeVersion / RecipeLine with versioning (D-26, D-27, D-28)

- **Decision:** `Recipe(product, variant NULL=base)` → `RecipeVersion`
  (status DRAFT/ACTIVE/ARCHIVED, at most one ACTIVE per recipe via a partial
  unique constraint) → `RecipeLine(component_product, component_unit,
  entered_qty, qty_base)`.
- **Nesting depth 2 (D-26), DAG validation at save (D-27):** a recipe may
  reference a sub-recipe (recipe → sub-recipe → raw ingredient) but no
  deeper; a component chain looping back to the product is rejected at save.
  Cheap given the depth-2 cap; enforced in `validate_recipe_lines`.
- **Theoretical consumption only (D-28):** depletion posts in real time from
  the recipe's immutable snapshot; periodic-count variance is out of scope.
- **Recipe cost is never cached/stored** — always rolled up live from
  components' current branch-scoped average at read/sale time. The recipe
  *definition* is stable; the recipe *cost* moves with ingredient prices, by
  design (the owner's "recipe stays the same, cost of the new sale changes
  automatically" requirement).

### A-4. Dynamic Modifiers with per-variant consumption deltas (D-23, D-34)

- **Decision:** `ModifierGroup` (selection_type SINGLE/MULTIPLE, min/max) →
  `ModifierOption(price_delta, can be 0 or negative)` →
  `ModifierOptionConsumption(variant NULL=agnostic, component_product,
  entered_qty signed, qty_base signed)`. `ProductModifierGroup` links which
  products offer which groups.
- **Price on the option, cost derived from consumption (D-23):** a modifier's
  cost is always its own consumption delta valued at branch-scoped average —
  never hand-entered.
- **Free/comp modifier still counts COGS (D-34):** a zero-price modifier that
  consumes inventory still contributes its ingredient cost to the item's
  food cost.

### A-5. `RECIPE_CONSUME` stock depletion at sale time

- **Decision:** a new `StockMovement.MovementType.RECIPE_CONSUME`. A recipe
  product (`affects_stock=False`) has no stock of its own; at sale time each
  **component** is depleted with one `RECIPE_CONSUME` movement at the
  branch's kitchen warehouse (`resolve_kitchen_warehouse`: prefer
  `role=KITCHEN`, fall back to `role=SALES`, else raise).
- **Centralized eligibility (`is_recipe_eligible`)** — one predicate decides
  the recipe path vs the legacy stock path (`not affects_stock and
  can_have_recipe and type != BUNDLE`). `BUNDLE` is deliberately excluded:
  its `can_have_recipe=True` is a Sprint-2 placeholder for a future,
  different "bundle explosion" feature, so a BUNDLE falls through to the
  legacy `SALE_OUT` path unchanged. Used identically in `validate()`,
  `create()`, `_apply_stock()`, and `void_sale()` — never re-derived inline.

### A-6. Immutable per-sale cost snapshot, stored as normalized split rows (D-31)

- **Decision:** `SaleItemRecipeCostSnapshot` (one per recipe sale line,
  `total_recipe_cost` mirrored onto `SaleItem.unit_cost`) + normalized
  `SaleItemRecipeCostSnapshotLine` rows (D-31 Option B — rows, not a JSON
  blob).
- **Split, not netted (post-Batch-5 review):** the snapshot stores **one row
  per source** — every base `RecipeLine` and every selected modifier's
  consumption is its own row, even when they touch the same component. A
  removal modifier's negative qty/cost keeps its real sign. This maximizes
  auditability ("recipe called for 20g onion" + "'No Onion' removed 20g" are
  two visible rows). Netting happens **only** where a single number is
  required: (1) validation at sale-creation (net per component may never go
  negative → `RecipeError`/400), and (2) stock deduction in `_apply_stock`
  (sum the stored rows per component → one `RECIPE_CONSUME` movement).
- **Rounding:** `total_recipe_cost` sums raw (unrounded) per-line costs and
  quantizes to money **once** — never sums pre-rounded per-line amounts,
  which would drift on components whose raw cost isn't a clean 2dp value.
- **Sole source of truth:** once written, the snapshot (and its lines) is the
  only record of that sale line's cost and consumption, forever. No later
  operation — void, refund, any future feature — recomputes
  `compute_recipe_cost`/`compute_modifier_deltas`/`compute_recipe_sale_lines`
  for a posted sale. Re-invoking them would let history drift as recipes are
  edited or ingredient prices move.
- **Completeness:** every field needed to reconstruct a historical line is
  frozen — `product_name`, `variant_name`/`variant_price`, per-modifier
  `group_name`/`option_name`/`price_delta`, per-line `component_name`/
  `qty_base`/`unit_cost`/`line_cost`/`is_modifier_line`. Every live FK on the
  chain is `SET_NULL`, so deleting a variant/modifier/recipe/product leaves
  the historical sale intact.

### A-7. Void reverses from the ledger, never from live definitions

- **Decision:** voiding a recipe sale skips the (never-decremented) recipe
  product's own stock and instead reverses every `RECIPE_CONSUME` movement
  the sale posted — read straight from the `StockMovement` ledger, restoring
  each ingredient at the warehouse it left from with a `RETURN_IN`. Recipes
  or modifier definitions may have changed since the sale; only the frozen
  movements are trusted.

### A-8. Reporting reuses the existing COGS pipeline (zero write-side change)

- **Decision:** a recipe sale writes its total recipe cost into the existing
  `SaleItem.unit_cost` field, so the entire Sprint 3/4 COGS/gross-profit/
  margin/dashboard pipeline works for recipe products with no changes. Batch
  6's two reports (`recipe_profitability`, `ingredient_consumption_report`)
  are pure reads over data Batches 1–5 already write.

---

## Part B — Production-readiness review findings

Severity: **P1** = fix before frontend; **P2** = fix soon / documented; **P3** = backlog.

| # | Area | Finding | Severity | Disposition |
|---|------|---------|----------|-------------|
| F-1 | Ledger consistency | `RECIPE_CONSUME` was in neither `_IN_TYPES` nor `_OUT_TYPES`, so `get_product_stock_balance` and the stock-statement summary silently ignored recipe-ingredient consumption — overstating an ingredient's on-hand on the `/stock-balance/` and `/stock-movements/` reconciliation endpoints (the authoritative `Product.stock`/`WarehouseStock` were always correct). | **P1** | **FIXED** — added to `_OUT_TYPES`; regression test added. |
| F-2 | Data integrity / API contract | The sale path accepted **any** tenant `modifier_option_id` without checking the option's group is attached to the product via `ProductModifierGroup`. A buggy/hostile client could apply an arbitrary price delta (incl. a negative "discount") and arbitrary ingredient consumption to any recipe product. | **P1** | **FIXED** — `validate()` now rejects modifiers not offered for the product; fixtures updated; regression test added. |
| F-3 | Performance (hot path) | Recipe snapshot lines were written one `INSERT` per component in the revenue path. | **P2** | **FIXED** — single `bulk_create` per recipe sale line. |
| F-4 | Idempotency (concurrency) | `lookup → work → save` is check-then-act with no reservation row. Two concurrent requests with the same `Idempotency-Key` can both pass `lookup` and both post a real sale; only one `IdempotencyRecord` survives. **Pre-existing and cross-cutting** (sales, purchases, voids) — not introduced by Sprint 5. | **P2** | **DOCUMENTED** — see Recommendation R-1; not fixed here (framework change touching all POST endpoints; deserves its own batch + owner sign-off). |
| F-5 | Performance | `get_cost_for_sale` issues 2–3 queries per distinct component (tenant-wide seed lookup + `get_or_create`) during a recipe sale. Bounded by recipe size (café recipes are small); cached per-call within `compute_recipe_sale_lines`. | **P3** | **SUPERSEDED — measured and fixed as F-8 in Part E** (verification pass): the seed lookup was unconditional, not just present; fixed by trying the plain row lookup first. |
| F-6 | Performance | No composite index on `StockMovement(tenant, movement_type, created_at)` for `ingredient_consumption_report`'s scan. Manager-only, occasional report. | **P3** | **DOCUMENTED** — add via `AddIndex` (consider `CONCURRENTLY`) when volume warrants (R-3). |
| F-7 | Ledger chain | `RECIPE_CONSUME` and void `RETURN_IN` rows don't populate `quantity_before`/`quantity_after` (they use manual `StockMovement.objects.create`, like the legacy `SALE_OUT` path). The running-ledger chain tolerates NULLs by design. | P3 | **ACCEPTED** — consistent with the pre-existing legacy sale/void paths; documented. |

### ACID / transaction safety (the emphasized focus)

- **Atomicity:** `SaleSerializer.create()` wraps the whole sale — `Sale`,
  `SaleItem`s, `SaleItemModifier`s, cost snapshots, `_apply_stock` (an inner
  savepoint), and the financial/AR ledger posting — in one
  `transaction.atomic()`. Any failure (e.g. no kitchen warehouse, a negative
  net, a payment-routing violation) rolls back the entire sale. There is no
  half-posted state.
- **Isolation / locking:** `Product.deduct_stock`, `record_stock_in/out`,
  `apply_warehouse_delta`, and the AVCO writers all `select_for_update()` the
  contended rows; the void path uses atomic `F()`-expression updates for the
  stock restore (no lost update) and `select_for_update` on `WarehouseStock`.
  Void row-locks the `Sale` (`of=('self',)`) so a concurrent double-void
  serializes and the loser returns 400.
- **Lock ordering / deadlock:** the purchase path locks **Product → InventoryCost**;
  the sale path locks only **Product** (per component); the branch-scoped
  cost read in a sale is a `get_or_create` (no `select_for_update`). No path
  acquires these two locks in the opposite order, so no lock-order inversion
  between concurrent sales and purchases on the same product.
- **Lock-hold duration (perf):** locks are held only for the duration of the
  enclosing request transaction. The F-3 `bulk_create` fix and the F-5
  observation are about total query count under lock, not lock contention
  per se. No long-running work happens while a row lock is held.

### Migration safety

All Sprint 5 migrations are additive and reversible. Operation census:
`recipes/0001–0005` = `CreateModel` ×8 + `AddConstraint` ×13 + `AddField`
×1; `pos/0029` = `AddField(branch)` + `AlterField(product OneToOne→FK)` +
2 `AddConstraint`; `pos/0030` = `AddField(SaleItem.variant)` +
`AlterField(movement_type choices)`; `pos/0031` = `AddField` ×2. **Zero
`RunPython`, zero data mutation on existing rows.** The one cardinality
change (`InventoryCost.product` OneToOne→FK) drops a unique index and keeps
the column; existing rows keep `branch=NULL` and remain valid under the new
paired constraints. Data backfill for existing tenants is an explicit,
idempotent, re-runnable management command (`backfill_branch_inventory_cost
--dry-run/--apply`), never an automatic migration mutation (R-F discipline).
`makemigrations --check --dry-run` is clean.

### API contract

Every Sprint 5 wire change is additive: new endpoints (variants, recipes,
modifiers CRUD; `reports/recipe-profitability/`,
`reports/ingredient-consumption/`), new **optional** sale-item input fields
(`variant`, `modifier_option_ids`), and new **optional** response fields.
No existing response field was removed or renamed. Legacy stock-item sales
send neither new field and behave exactly as before. Tenant isolation on
the new inputs is enforced by per-request field querysets
(`variant`/`modifier_option_ids` scoped to the caller's tenant); F-2 closed
the remaining product-scope hole.

---

## Part C — Test coverage matrix

Full suite: **759 passing**, 0 new migrations. New in Batch 7: 2 regression
tests (F-1, F-2). Legend: ✅ covered · ⚠️ partial/indirect · ➖ N/A.

| Behavior | Unit | API/E2E | Regression guard | Status |
|----------|:----:|:-------:|:----------------:|:------:|
| Branch-scoped AVCO blend (2 branches, disjoint history) | ✅ | ✅ | Sprint 3 suite stays green | ✅ |
| `get_branch_stock_balance` (multi-warehouse, cross-branch exclusion) | ✅ | ➖ | — | ✅ |
| Recipe cost roll-up (worked example, branch-scoped) | ✅ | ✅ | — | ✅ |
| Depth-2 nesting / depth-3 rejection / cycle rejection | ✅ | ✅ | — | ✅ |
| One-ACTIVE-version invariant + atomic activate | ✅ | ✅ | — | ✅ |
| Modifier deltas: positive / negative / free-still-COGS / variant-scoped | ✅ | ✅ | — | ✅ |
| Recipe sale E2E: RECIPE_CONSUME per component, branch/warehouse correct | ➖ | ✅ | — | ✅ |
| Cost snapshot immutability under later ingredient reprice | ➖ | ✅ | — | ✅ |
| Split snapshot rows (base + modifier same component stay separate) | ➖ | ✅ | rounding-once guard | ✅ |
| Negative-net modifier rejected (never a negative RECIPE_CONSUME) | ➖ | ✅ | — | ✅ |
| Net-to-zero modifier (base fires 0, not original qty) | ➖ | ✅ | — | ✅ |
| Void restores ingredients from ledger (not phantom product bump) | ➖ | ✅ | — | ✅ |
| BUNDLE falls through to legacy SALE_OUT path | ➖ | ✅ | — | ✅ |
| Variant/modifier snapshot survives rename + deletion | ➖ | ✅ | — | ✅ |
| Dashboard/COGS reflect recipe sales with zero view changes | ➖ | ✅ | — | ✅ |
| Recipe profitability + ingredient consumption reports | ➖ | ✅ | branch filter, voided excluded, ordering, 403 | ✅ |
| **F-1: RECIPE_CONSUME counts as outflow in ledger balance** | ➖ | ✅ | **Batch 7 new** | ✅ |
| **F-2: modifier-not-offered rejected** | ➖ | ✅ | **Batch 7 new** | ✅ |
| Non-recipe (legacy) sale unchanged | ➖ | ✅ | Sprint 1–4 suite | ✅ |
| Idempotency under **concurrent** same-key POST | ➖ | ➖ | — | ⚠️ **gap (F-4, R-1)** |
| Concurrent recipe sale vs purchase on same ingredient (lock order) | ➖ | ➖ | reasoned safe, not load-tested | ⚠️ documented |

The two ⚠️ rows are concurrency behaviors that a single-threaded test
client cannot exercise deterministically; they are reasoned about above and
carried as recommendations rather than asserted by a test.

---

## Part D — Recommendations (future hardening, not done in Batch 7)

- **R-1 (idempotency, P2):** replace check-then-act with a reservation row —
  insert the `IdempotencyRecord` up front and let the `(tenant, key)` unique
  constraint reject a concurrent duplicate, storing the response on
  completion. Cross-cutting (sales/purchases/voids); its own batch + owner
  sign-off. This is the single most valuable production-hardening item.
- ~~R-2 (perf, P3): batch-resolve component costs~~ — **done in the
  verification pass below** (F-8).
- **R-3 (perf, P3):** add `StockMovement(tenant, movement_type, created_at)`
  index (via `AddIndex`, consider `CONCURRENTLY`) when the ingredient report
  slows at volume.
- **R-4 (business rule, P3):** enforce `ModifierGroup.min_select/max_select/
  selection_type` server-side at sale time (today the frontend will enforce
  it; the backend validates membership but not cardinality).

---

## Part E — Verification Pass (measured, not reasoned)

A second pass over this same gate, done on the owner's explicit instruction
to verify with **real measurements** rather than trust the reasoning above:
a real regression audit, actual query-count measurement (`CaptureQueriesContext`),
an end-to-end reconciliation test across every read surface, a documentation/
API-contract sync check, and a `coverage.py`-measured gap review (not a guess
at what's untested).

### E-1. Regression audit

Ran the full suite (`manage.py test`, no filters) and confirmed the reported
"Ran N tests" count matches the sum of test methods added per batch — no
silently-skipped or vacuously-passing test discovered. Full suite: **771
passing** (759 at the end of Batch 7's first pass + 12 new in this
verification pass: 2 real-defect regression tests below, 2 report input-
validation tests × 2 endpoints, 4 query-count guards, 1 end-to-end
reconciliation test, 1 non-numeric-branch_id test × 2 endpoints).

### E-2. Query-count measurement (N+1) — one real finding, fixed

Measured with `django.test.utils.CaptureQueriesContext`, not estimated:

| Path | Before | After | Fix |
|---|---|---|---|
| Recipe sale, 2 base lines + 1 modifier line (3 distinct components) | **63 queries** | **60 queries** | F-8 below |
| Void of a 2-ingredient recipe sale | 31 queries | — (no fix needed; pinned as a regression guard) | — |
| `recipe-profitability`, 10 sale lines / 2 products | ≤5 queries (DB-side aggregate, confirmed flat regardless of row count) | — | — |
| `ingredient-consumption-report`, 10 movements / 1 `(product,branch)` | 2 queries (confirmed flat, not 10+) | — | — |

- **F-8 (P2, perf — new, found by measurement, not present in the first
  pass's reasoning):** `costing.get_or_create_inventory_cost` unconditionally
  ran a "tenant-wide seed" query before ever checking whether the
  `(product, branch)` row it actually wants already exists — 2 queries for
  every single call, even in the overwhelmingly common case (a branch's
  ingredient after its first purchase) where the row is already there. This
  function is called once per recipe component on every recipe sale — the
  revenue hot path. **Fixed:** try the plain `(product, branch)` lookup
  first; only pay for the seed-resolution queries on the genuine cold-start
  path (a product/branch pair with no row yet, which happens at most once,
  ever, per pair). Confirms **R-2** from the first pass's reasoning was
  correct in spirit — the actual fix ended up being "look before you seed"
  rather than a batch-resolve rewrite, a smaller and equally effective
  change.
- All four paths above are now pinned with `assertLessEqual(len(queries), N)`
  regression guards (generous ceilings, not razor-thin) so a future N+1
  regression on any of them fails a specific test instead of showing up as
  an unexplained slowdown.

### E-3. End-to-end data integrity (Sale → every report)

New test: two real recipe sales posted through the actual `/sales/` API
(not a bypassed fixture) at two branches with *different* branch-scoped
ingredient costs (D-09) and one shared modifier. Verified the exact same
numbers reconcile across five independently-computed layers:

1. `SaleItem.unit_cost` / `SaleItemRecipeCostSnapshot.total_recipe_cost`
2. The `RECIPE_CONSUME` ledger's net quantity per ingredient per branch
3. `dashboard_summary`'s branch-filtered and unfiltered COGS
4. `recipe_profitability`'s `food_cost` (grouped from `SaleItem`)
5. `ingredient_consumption_report`'s summed `cost_consumed` (grouped from
   `StockMovement` — a **different table**, computed independently)

All five converged on **59.00** (22.00 + 37.00, the two branches' recipe
costs) — proving the Sprint 3/4 COGS pipeline and the Sprint 5 recipe-costing
pipeline, despite reading from different tables with independent aggregation
logic, never drift apart for the same underlying sales. This is the
strongest data-integrity guarantee this gate can offer short of production
traffic.

### E-4. Documentation & API contract sync

Cross-checked Sprint 5 against every doc that could plausibly need updating:

- **`IMPLEMENTATION_PROGRESS.md`** and **`ARCHITECTURE_DECISIONS_REQUIRED.md`**
  — the two *living* documents in this repo, updated every batch throughout
  Sprint 5 (confirmed current as of this pass).
- **`API_CONTRACT.md`, `API_AND_MODEL_INVENTORY.md`, `TARGET_BOUNDARIES.md`,
  `IMPLEMENTATION_ROADMAP.md`, `SOURCE_OF_TRUTH.md`, `INDEX.md`** — confirmed
  these are a single frozen, numbered **"read-only architecture audit — N of
  7"** series, each explicitly headed "no runtime code changed" and tied to
  a specific pre-Sprint-1 branch (`safety/backend-gate-a-wip-2026-07-04`,
  itself unmerged). They are point-in-time target-state/audit snapshots by
  design, not living trackers — editing them to "catch up" to Sprint 2–5
  would misrepresent what they are. **No edit made; this is a verified
  finding, not an oversight.**
- **Target-model fidelity check** — compared the actual Sprint 5 schema
  against `TARGET_BOUNDARIES.md` §6's proposed target model line by line.
  Confirmed matches: §6.6 variant-owns-its-own-RecipeVersion; §6.10
  modifier price-delta + per-variant consumption delta; **§6.13's
  profitability terminology matches Batch 6's report fields exactly**
  (`gross_profit`, `gross_margin_pct`, `food_cost_pct` — term-for-term,
  confirming R-L compliance). Confirmed **deliberate** divergences (every
  one already covered by an explicit Sprint 5 scope decision, not a new
  finding — restated here only so nobody mistakes §6 as a literal spec of
  what shipped): §6.7's `RecipeVersion` proposes `effective_from`/
  `effective_to` dates and a 4-stage `draft → approved → active → retired`
  lifecycle; the actual model has 3 stages (`DRAFT/ACTIVE/ARCHIVED`), no
  approval step, no date-effective window. §6.7/§6.9's `RecipeLine`
  proposes a per-line normal-loss/yield factor and a per-line warehouse (or
  warehouse role); the actual model has neither — warehouse is resolved
  once per branch (`resolve_kitchen_warehouse`), and yield/loss is entirely
  out of scope (Production Orders, D-29/D-30, explicitly excluded by the
  owner). Both simplifications are the direct, correct consequence of the
  "no Production Orders this sprint" decision recorded in Phase 0.

### E-5. Coverage gap review — measured with `coverage.py`, not guessed

**Correction (2026-07-22, owner pre-close-out review):** the original 91%
figure below was measured by running `coverage run ... manage.py test
recipes pos.test_costing pos.test_reporting` — three test modules, not the
full suite. That undercounted `pos/services/stock_movements.py` badly (49%
in that scoped run) because most of its coverage comes from `pos/tests.py`,
which the scoped run never executed. Re-measured against the full suite
(`coverage run --source=recipes,pos.services.costing,pos.services
.stock_movements manage.py test`, all 781 tests) — the honest baseline was
**95%**, not 91%; a coverage figure is only meaningful measured against the
same suite that will actually run in CI, never a hand-picked subset.

| Module | Corrected baseline (full suite) | After this review's fixes |
|---|---|---|
| `pos/services/costing.py` | 97% (2 missing: L259-260) | **100%** |
| `pos/services/stock_movements.py` | 96% (5 missing, all pre-existing optional-filter branches, not Sprint-5 code) | 96% (unchanged — see below) |
| `recipes/models.py` | 93% (11 missing, all `__str__` methods) | 93% (unchanged — see below) |
| `recipes/serializers.py` | 85% | 86% |
| `recipes/views.py` | 83% | **96%** |
| **Sprint-5-relevant total** | **95%** (corrected) | **97%** |

Gaps found and closed in this review (all real, plausible-in-production
gaps, not defensive padding):

- **`update_cost_from_adjustment`'s cold-start branch** (`pos/services
  /costing.py:259-260` — a positive stock-count adjustment on a
  `(product, branch)` pair with no prior `InventoryCost` row at all) had
  zero coverage; every existing test called `apply_purchase_receipt` first,
  which always creates the row before the adjustment path could ever hit
  its own `if inv_cost is None` branch. Real scenario: an ingredient
  entered via a physical count before it was ever purchased through the
  system. New test:
  `test_update_cost_from_adjustment_on_product_with_no_prior_inventory_cost_row`.
  `pos/services/costing.py` is now **100%** covered.
- **Every GET/PATCH/deactivate admin endpoint for Recipe, RecipeVersion,
  ModifierGroup, and ModifierOption had never been called by a single
  test** — the existing suite exercised the POST/create paths heavily
  (needed for the sale-integration tests) but never a plain retrieve,
  update, or deactivate on any of these five view classes, and never the
  `?variant_id=` filter on the recipe list. Closed with 6 new tests:
  `test_recipe_detail_get_and_patch`, `test_recipe_detail_cashier_can_read
  _but_not_write`, `test_recipe_list_filters_by_variant_id`,
  `test_recipe_version_detail_get`,
  `test_modifier_group_detail_get_patch_and_deactivate`,
  `test_modifier_option_detail_get_patch_and_deactivate`,
  `test_modifier_option_consumption_detail_get`. This took
  `recipes/views.py` from 83% to 96%.
- **AR/GL isolation for a recipe sale was asserted only by code-reading,
  never by a running test** — see F-9 in Part F below. New test:
  `test_credit_recipe_sale_posts_correct_ar_charge_unaffected_by_recipe_logic`.
- **Combined void scenario** — see F-10 in Part F below. New test:
  `test_void_recipe_sale_with_variant_modifier_and_oversell_combined`.

Remaining gaps reviewed and **deliberately left uncovered**, each verified
line-by-line (not assumed) to be a defensive/unreachable branch or a
pattern consistent with the rest of the codebase's own baseline (not a
Sprint-5-introduced risk):

- `recipes/services/costing.py:161` — an active `RecipeVersion` with zero
  active lines, handled safely (returns 0).
- `recipes/models.py`'s 11 missing lines — every one is a `__str__` method
  (Django-admin display only, zero business logic, never exercised by an
  API test anywhere in this codebase's existing convention).
- `recipes/views.py`'s remaining 10 lines — the `else:
  serializer.save(product=...)` no-tenant fallback branches (same pattern,
  same coverage level, as every pre-existing Units/Price-Tiers/Categories
  admin view in this repo) and a handful of `IsCashierOrAbove()` /
  `get_queryset()` lines on view classes whose write half is tested but
  whose plain-GET half wasn't worth a dedicated test once the sibling
  classes above proved the shared `_ProductScopedMixin`/
  `_ModifierGroupScopedMixin` pattern works correctly.
- `pos/services/stock_movements.py`'s 5 missing lines — optional-filter
  combinations (`branch`/`warehouse`/`actor_user`/date-range) inside a
  pre-existing (Sprint 1-2 era) stock-statement query builder, not
  Sprint-5-introduced code; every combination that Sprint 5 itself
  exercises (branch + product) is covered.
- `recipes/serializers.py`'s remaining 27 lines — cross-tenant FK guards,
  name-uniqueness guards, and unit-conversion error translation, all
  identical in shape to guards already tested on every other Sprint 2-5
  serializer in this codebase (`ProductUnitSerializer`, `PriceTierSerializer`,
  etc.) — not re-tested per serializer as a matter of this repo's own
  established convention, not a Sprint-5-specific gap.

---

## Part F — Pre-close-out owner review (2026-07-22)

The Business Owner asked six specific questions before signing off on
Sprint 5. Each was answered by re-running real code, not by re-reasoning
from the verification pass's existing prose — three led to genuine gaps,
closed with new tests in this same pass (see E-5 above for the coverage
deltas).

### F-1 (was Q1). What are the 60 queries, and is there more to squeeze?

Re-ran the 60-query recipe sale (2 base recipe lines + 1 modifier line, 3
distinct components) under `CaptureQueriesContext` and categorized every
query by table:

| Count | Table / operation | Why |
|---|---|---|
| 12 | `SAVEPOINT`/`RELEASE` (6 pairs) | Nested-transaction overhead — each of the 3 components' `stock_movements.record_stock_out()` call opens its own `@transaction.atomic()` block (2 savepoints per component: the stock-out call itself, plus one more nested inside it). |
| 8 | `pos_product` (5 SELECT + 3 UPDATE) | 1 SELECT for the sold product, 3 `select_for_update()` SELECTs + 3 stock-counter UPDATEs, one pair per component. |
| 6 | `pos_warehousestock` (3+3) | One SELECT + one UPDATE per component (`apply_warehouse_delta`). |
| 4 | `accounts_tenant` | Four independent tenant lookups in one request (permission classes, `TenantMixin._tenant()`, serializer context) instead of one resolved-and-reused value. |
| 3 | `pos_inventorycost` (SELECT) | One per component's `get_cost_for_sale()` — already minimal post-F-8 (1 query when the row exists, not 2). |
| 3 | `pos_stockmovement` (INSERT) | One `RECIPE_CONSUME` row per component — necessary, one write per real ledger entry. |
| 3 | `pos_saleitem` | 1 INSERT + 2 SELECT. |
| 2 | `pos_branchwarehouse` | `resolve_kitchen_warehouse`'s try-KITCHEN-then-SALES fallback — resolved **once** per sale, not once per component (already correctly cached). |
| 2 each | `recipes_saleitemmodifier`, `recipes_saleitemrecipecostsnapshot`, `recipes_saleitemrecipecostsnapshotline`, `accounts_financialaccountmovement` | 1 INSERT (the snapshot-line INSERT is a single `bulk_create` regardless of line count) + 1 SELECT reading the row back for the response payload. |
| 1 each | 11 more tables | Recipe/version/line/modifier-group/modifier-option reads (one each, correctly not repeated), the `Sale` INSERT, the `Payment` INSERT, payment-routing/account reads. |

**Real remaining opportunity, found but not taken:** the 4 `accounts_tenant`
re-fetches and the 12 SAVEPOINT/RELEASE pairs together are ~16 of the 60
queries (27%). The tenant re-fetches are collapsible if `_tenant()` cached
its result on the request instead of re-querying. The savepoints are
collapsible by not wrapping each component's `record_stock_out()` call in
its own `atomic()` when it's already running inside the sale's outer
transaction — but that call is written to be independently atomic on
purpose (so a partial per-component failure can't leave a half-written
`StockMovement`), and removing it changes a real correctness property, not
just a performance one. **Not done in this pass** — matches this project's
own standing rule ("don't refactor working code without measurable
benefit"): at Sprint 5's current scale (a handful of components per sale)
this is single-digit-millisecond overhead, and the fix for the savepoints
specifically trades a small perf gain for touching lock-sensitive code
right after a gate review, which is the wrong moment to do it. Flagged as
a **P3 backlog item** for whenever real production query-volume data
justifies it — not before.

### F-2 (was Q2). Do the Batch 6 reports paginate? If not, what's the plan?

**No.** Both `recipe_profitability` and `ingredient_consumption_report`
(`pos/views.py`) are plain `@api_view` functions returning
`Response({'results': rows})` — no `ListAPIView`, no
`StandardPageNumberPagination`, no `LIMIT`.

The actual risk differs by endpoint:

- **`recipe_profitability`** aggregates entirely in SQL
  (`.values(...).annotate(...)`) — response size is bounded by the number
  of distinct `(product, variant)` pairs *sold in the window*, which
  tracks menu size, not transaction volume. Low risk at any realistic
  catalog size.
- **`ingredient_consumption_report`** aggregates in **Python**, iterating
  every `RECIPE_CONSUME` `StockMovement` row in the window
  (`movements.iterator()`) to build the per-ingredient totals dict. The
  *response* is still bounded by distinct ingredients (catalog-sized), but
  the *request's work* scales linearly with movement-row count — a
  year-long window on a high-volume tenant reads every recipe-consumption
  row ever written in that window, in Python, on every request.

**Plan (not done in this pass — a real architectural choice, not a quick
fix, so it's recorded here for the next sprint rather than rushed into a
gate-review turn):** convert `ingredient_consumption_report`'s
per-movement Python loop to a SQL-side `.values('product').annotate(qty=
Sum(...))`, matching `recipe_profitability`'s own pattern. The blocker is
that `cost_consumed` needs each movement's own `(product, branch)`-scoped
`InventoryCost.avg_unit_cost`, which isn't stored on the movement row
itself — doing this in pure SQL needs either a correlated subquery per
`(product, branch)` or a join against `InventoryCost`, not just a
straight `Sum()`. Recommended as a Sprint 6 backlog item once there's a
tenant with enough real transaction volume to justify it; not urgent
today.

### F-3 (was Q3). Was performance measured at production-scale data volume?

**No — say so plainly.** Every query-count test in Sprint 5 (the 60/35/≤5
regression guards) uses realistic-but-small fixtures: one sale with 3
components, 10 movements, 10 sale lines. These prove query **count** stays
flat as row count grows (the actual N+1 defense) — they do **not** measure
wall-clock latency under production-scale volume (thousands of sales,
tens of thousands of `RECIPE_CONSUME` rows). No load/stress test exists
anywhere in this sprint or the ones before it. Do not read "60 queries,
measured" as "verified fast at scale" — those are different claims, and
only the first one has evidence behind it. A real stress-test pass (seed
10k+ sales, measure `ingredient_consumption_report` and
`recipe_profitability` latency directly, ideally against
production-realistic Postgres statistics/indexes) is recommended as a
dedicated pre-launch task, not something this backend-correctness gate
was ever scoped to cover.

### F-4 (was Q4). Coverage, module-by-module, with an honest account of the remainder.

See the corrected **E-5** above for the full table and per-module
breakdown — summary: **97%** Sprint-5-relevant coverage (up from a
corrected 95% baseline; the previously-reported 91% was a measurement
error, not a real number — see E-5's correction note), `pos/services
/costing.py` now 100%. The remaining 3% is, line-by-line: `__str__`
methods (`recipes/models.py`), pre-existing shared-module optional-filter
combinations (`pos/services/stock_movements.py`), one degenerate-but-safe
recipe-cost edge case, and cross-tenant/uniqueness validation guards
whose shape is already proven by identical, already-tested guards
elsewhere in this codebase's own established convention.

### F-5 (was Q5). Is FinancialAccountMovement / CustomerARMovement / the GL pipeline unaffected?

**Yes — verified two ways, not just asserted:**

1. **Structurally**, by reading the call graph: `SaleSerializer.create()`
   calls `pos.services.sale_posting.post_sale_ledgers(sale=sale,
   method=..., customer=..., actor_user=...)` exactly **once per sale**,
   *after* every item (recipe or plain stock-item) has already been
   processed. That function reads only `sale.total`, `method`, and
   `customer` — it never reads `SaleItem.variant`, `SaleItemModifier`, or
   any recipe-cost-snapshot table. It cannot be affected by anything
   Sprint 5 added because it has no code path that touches those tables.
2. **Empirically**, by two runs of real code: the F-1 query trace above
   shows a cash recipe sale creates exactly the same
   `accounts_financialaccountmovement` shape (1 SELECT + 1 INSERT) as any
   ordinary cash sale. New test
   `test_credit_recipe_sale_posts_correct_ar_charge_unaffected_by_recipe_logic`
   posts a **credit** sale of a recipe product with a modifier and asserts
   the resulting `CustomerARMovement.debit` equals `sale.total` exactly
   (base price + modifier price delta + tax), `source_document_type`/`_id`
   point at the sale, and zero `FinancialAccountMovement` rows are created
   (credit sales never touch the cash-drawer ledger) — closing what was
   previously an inference from Sprint 3's `Batch4NoGlPostingTests` (which
   never actually posted a recipe sale) into a direct proof.

### F-6 (was Q6). Was void tested with Variant + Modifier + Oversell combined?

**No, until this pass — a real, now-closed gap.** The pre-existing void
test (`test_void_recipe_sale_restores_ingredient_stock`) used a plain
base-recipe sale with no variant and no modifier; the oversell test
(`test_oversell_recipe_ingredient_still_succeeds_with_warning`) and the
variant test (`test_recipe_sale_with_variant_uses_variant_recipe_and_price`)
each proved their own mechanism independently at **sale** time, but none
of the three had ever been combined with each other, and none had ever
been combined with **void**.

New test
`test_void_recipe_sale_with_variant_modifier_and_oversell_combined`: sells
the "Large" variant (its own independent 300g-chicken recipe) plus the
Extra Cheese modifier (40g cheese), with the variant's own chicken
ingredient deliberately oversold (stock=10 against a 300g requirement,
confirmed via the sale-time warning and a post-sale negative stock
balance) — then voids the sale and asserts both `RECIPE_CONSUME` rows
(chicken 300g, cheese 40g) reverse via `RETURN_IN` for their **exact**
consumed quantities, restoring stock to precisely its pre-sale value even
though it went negative in between; that the base recipe's lettuce line
(irrelevant to the variant's own recipe) never appears in the sale's
movements at all; and that the recipe product itself never gets a
phantom stock movement. Passed on the first run.

---

## Gate decision

Sprint 5 backend is **cleared for the frontend batches (8–10).** All P1
defects from the first pass are fixed and regression-tested; the
verification pass found one additional real perf issue (F-8, fixed) and
closed two real coverage gaps with regression tests; the pre-close-out
owner review (Part F) closed three further gaps (the AR/GL isolation proof,
the combined variant+modifier+oversell void scenario, and the
`update_cost_from_adjustment` cold-start branch) and corrected a coverage
measurement methodology error (91% → the honest 95% baseline → 97% after
fixes) — no new correctness defect was found at any stage. The full suite
is green (**781 tests**); migrations are additive-only; the API surface is
additive; an end-to-end reconciliation test proves the COGS and
recipe-costing pipelines agree exactly across five independent read paths.
Two scale-dependent items are explicitly **not yet verified** and must not
be read as covered by this gate: real production-volume performance
(F-3 — no stress/load test exists at any point in this sprint) and
`ingredient_consumption_report`'s Python-side aggregation cost on a
long date range at high transaction volume (F-2). Both are recommended,
scoped Sprint 6 backlog items, not blockers for the frontend batches,
which do not depend on either.
