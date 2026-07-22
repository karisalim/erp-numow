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
| F-5 | Performance | `get_cost_for_sale` issues 2–3 queries per distinct component (tenant-wide seed lookup + `get_or_create`) during a recipe sale. Bounded by recipe size (café recipes are small); cached per-call within `compute_recipe_sale_lines`. | **P3** | **DOCUMENTED** — acceptable at current scale; batch-resolve is the future optimization (R-2). |
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
- **R-2 (perf, P3):** batch-resolve component costs once per sale (one query
  keyed by `(product_id, branch_id)`) instead of per-component `get_or_create`.
- **R-3 (perf, P3):** add `StockMovement(tenant, movement_type, created_at)`
  index (via `AddIndex`, consider `CONCURRENTLY`) when the ingredient report
  slows at volume.
- **R-4 (business rule, P3):** enforce `ModifierGroup.min_select/max_select/
  selection_type` server-side at sale time (today the frontend will enforce
  it; the backend validates membership but not cardinality).

---

## Gate decision

Sprint 5 backend is **cleared for the frontend batches (8–10).** All P1
defects found are fixed and regression-tested; the full suite is green (759
tests); migrations are additive-only; the API surface is additive. The two
documented residual risks (F-4 idempotency race, F-5/F-6 perf) are
pre-existing or scale-dependent, carry explicit recommendations, and do not
block the frontend work.
