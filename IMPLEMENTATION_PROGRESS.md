# IMPLEMENTATION_PROGRESS.md

> Living tracker for the controlled implementation of the ratified architecture
> package. One section per sprint. Updated after every audit and every
> implementation batch. Governance: a slice's code lands only when its gate has
> exited per [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)
> §3.0 (R-M), except components the register explicitly leaves ungated.

---

## Sprint 1 — Foundation (roadmap Slice 1 + Slice 2)

**Status: IN PROGRESS — Batch 1 (GA-1, GA-6, GA-8) executed 2026-07-12;
Batch 2 (steps 4–8: provisioning command, sales idempotency, GA-7, GA-9,
GA-2) executed 2026-07-13 on branch `s1/gate-a-foundation`; suite 389
green.** Remaining: steps 9–10 (GA-3/GA-4) blocked on G0 exit.
Audit date: 2026-07-12 · Auditor branch: `fix/ga-10-warehouse-stock-route` ·
Baseline: **365 backend tests green** (`python manage.py test`, 30.5 s).

### 0. Batch 1 execution record (2026-07-12, authorized)

**Scope executed:** plan steps 1–3 only — GA-1, GA-6, GA-8. Not touched: GL,
recipes, costing, production, frontend, GA-2/3/4/5/7, the safety branch.

- **Changed files:**
  - `superpos_backend/superpos_backend/settings.py` — GA-1: `SECRET_KEY`,
    `DEBUG`, `ALLOWED_HOSTS`, all `POSTGRES_*`, CORS now env-driven with
    dev-safe defaults (verified: prod-like env → `DEBUG=False`, host list,
    scoped CORS; empty env → prior dev behavior).
  - `superpos_backend/.env.example` — new (GA-1).
  - `superpos_backend/accounts/serializers.py` — GA-6: at most one ACTIVE
    default `BranchPaymentMethod` per (branch, method_type); the two-step
    demote-then-promote swap stays allowed.
  - `superpos_backend/pos/services/sale_posting.py` — GA-6: deterministic
    route resolution `(-is_default, -id)`; GA-8: `SalePostingError.code =
    'payment_routing_missing'`. **Routing policy unchanged** (legacy skip
    stays — strict routing is GA-2, step 8).
  - `superpos_backend/pos/serializers.py` — GA-8: sale-posting failure now
    returns `{'payment': [msg], 'code', 'field', 'detail'}` instead of a bare
    string.
  - `superpos_backend/pos/tests.py` — +5 tests.
- **Migrations created:** none (no schema change in this batch).
- **APIs added/changed:** no new endpoints. Behavior deltas:
  `POST/PATCH /api/branches/{id}/payment-methods/` now rejects a second
  active default of the same method_type (400 on `is_default`); sale-posting
  400 bodies gained stable `code`/`field`/`detail` keys (legacy `payment` key
  kept, now list-wrapped).
- **Tests added (5):** `GateADefaultRouteUniquenessTests` (second default
  rejected · non-default duplicate allowed · demote-then-promote swap allowed ·
  deterministic resolver on bad legacy data) +
  `SalePostingHardeningTests.test_posting_error_has_structured_shape`.
- **Tests executed:** full backend suite — **370 passed, 0 failed** (31.2 s).
- **Risks:** FE sale-error handling that assumed `payment` was a bare string
  would need the list form — the FE `parseApiError` already handles both
  (per FRONTEND_SLICE deliverables); `.env.example` documents but does not
  load env vars (no dotenv dependency added by design).
- **Remaining blockers:** unchanged (see §5) — next batch needs
  authorization; GA-3/GA-4 still need D-14 + G0 exit.

### 0b. Batch 2 execution record (2026-07-13, authorized)

**Scope executed:** plan steps 4–8 — provisioning command (R-F replacement
for GA-5), sales idempotency (Slice 2), GA-7 void reversal, GA-9 test pack,
GA-2 strict routing. Not touched: GL, recipes, costing, production, frontend,
GA-3/GA-4 (blocked on G0), the safety branch. No commits made.

- **Changed files:**
  - `superpos_backend/accounts/management/__init__.py`,
    `superpos_backend/accounts/management/commands/__init__.py`,
    `superpos_backend/accounts/management/commands/provision_default_payment_routing.py`
    — new (step 4). Dry-run by default (full pass inside a transaction,
    rolled back at the end so the printed plan is exact); `--apply` commits;
    `--tenant=<id>` scopes both passes. Pass 1 demotes duplicate active
    defaults keeping the newest (same `(-is_default, -id)` tie-break as the
    runtime resolver); pass 2 provisions cash/card/wallet routing only for
    branches with ZERO `BranchPaymentMethod` rows, reusing the tenant's first
    active account/method of each type. Partially-configured branches are
    never altered — missing active routes are surfaced as log-only `WARN`
    lines. Output is console-safe for Arabic names on legacy Windows
    codepages. No financial rows in any schema migration.
  - `superpos_backend/pos/views.py` — step 5: `SaleListCreateView.create`
    wires `idempotency.lookup/save` exactly like purchase invoices (replay →
    original response, payload mismatch → 409 `IDEMPOTENCY_CONFLICT`, no
    header → normal). Step 6 (GA-7): `void_sale` reimplemented — sale row
    locked via `select_for_update(of=('self',))`; compensating
    `FinancialAccountMovement` credit (`SALES_RETURN_OUT`) per original sale
    debit and compensating `CustomerARMovement` credit (`SALES_RETURN`) per
    AR debit, tagged `source_document_type='sale_void'` (originals never
    touched — compensating-document pattern, R-C); stock reversal unchanged
    but now stamped with source-document refs + actor; optional `reason`
    recorded in an `AuditLog` VOID entry with the reversal references;
    `Idempotency-Key` replay protection prevents double-reversal on retry;
    legacy pre-gate sales (no financial movement) void gracefully and are
    flagged `legacy_no_financial_movement`.
  - `superpos_backend/pos/services/sale_posting.py` — step 8 (GA-2): legacy
    best-effort skip REMOVED. `post_sale_ledgers` now raises
    `SalePostingError` (`code='payment_routing_missing'`) for ANY
    cash/card/wallet sale that cannot resolve an active route — including
    branches with zero `BranchPaymentMethod` rows. The caller's atomic block
    rolls the whole sale back → structured 400 (GA-8 shape). Zero-total sales
    still post nothing; credit still always posts to Customer AR.
  - `superpos_backend/pos/serializers.py` — comment-only update (strict
    routing note replaces the legacy-skip note).
  - `superpos_backend/pos/tests.py` — step 7 (GA-9): +19 net tests (see
    below); 3 legacy-skip tests converted 1:1 to strict-routing tests; the
    `SaleCheckoutPaymentTests` / `ReceiptLayoutTests` fixtures now grant
    default routing via the module-level `_grant_default_routing` helper.
- **Migrations created:** none (no schema change in this batch).
- **APIs added/changed:** no new endpoints. Behavior deltas:
  `POST /api/sales/` honors `Idempotency-Key` (replay / 409); a
  cash/card/wallet sale on a branch with no active route for that method now
  400s with `code='payment_routing_missing'` and rolls back atomically (was:
  silent-skip for zero-row branches); `POST /api/sales/<id|uuid>/void/`
  response gains a `void` object (`reason`, `finance_reversals`,
  `ar_reversals`, `legacy_no_financial_movement`) and honors
  `Idempotency-Key`.
- **Tests added (19 net):**
  `GateAVoidReversalTests` (8: cash/card/wallet/credit reversal + balances,
  legacy no-movement void, double-void guard, idempotent void replay,
  cross-tenant void → 404 with tenant-A rows untouched) ·
  `GateASaleIdempotencyTests` (4: replay without second sale, payload
  mismatch → 409, no-key normal, per-tenant key scoping) ·
  `ProvisionDefaultPaymentRoutingCommandTests` (7: dry-run default writes
  nothing, apply + idempotent re-apply, reuse of existing accounts/methods,
  configured-branch skip + WARN, duplicate-default demotion keeps newest,
  `--tenant` scoping leaves other tenants untouched, unknown tenant →
  CommandError). Replaced 1:1 (strict routing):
  `test_unrouted_branch_sale_fails_with_structured_error`,
  `test_unconfigured_tenant_sale_fails_and_rolls_back`,
  `test_unconfigured_tenant_sale_fails_and_creates_no_warehouse_stock`.
  All new assertions verify tenant scoping on created/reversed rows.
- **Tests executed:** full backend suite — **389 passed, 0 failed** (54–68 s).
  `python manage.py check` clean.
- **Ordering guarantee honored:** the dry-run was executed against the dev DB
  before strict routing tests landed; it SKIPs both configured branches and
  flags their missing method routes (`WARN`), and provisions the one unrouted
  branch — production rollout must run `--apply` per tenant and review the
  WARN lines before deploying this batch (see §4 risk 1).
- **Risks:** branches that are *partially* configured (some method types
  missing an active route) will 400 those methods under GA-2 — the command
  deliberately never alters them; the WARN lines in the dry-run output are
  the operator's checklist. FE already renders the structured 400 (GA-8).
- **Remaining blockers:** steps 9–10 (GA-3/GA-4) still need D-14 + G0
  sign-off/promotion.

### 1. Audit findings — current implementation state

| Gate A component | State on current branch | Evidence |
|---|---|---|
| GA-1 env-driven settings | **Missing.** Hardcoded `SECRET_KEY`, `DEBUG=True`, `ALLOWED_HOSTS=['*']`, DB password in `settings.py`; no `.env.example` | `superpos_backend/superpos_backend/settings.py:6-80` |
| GA-2 strict sale routing | **Partial.** Configured branch = strict (400 + rollback); legacy branch (zero `BranchPaymentMethod` rows) = best-effort skip with WARNING | `pos/services/sale_posting.py:143-161` |
| GA-3 credit-limit guard | **Missing.** `Customer.credit_limit` exists (default 0, not nullable) but nothing enforces it in the sale flow | `accounts/models.py:686`; no reference in `pos/serializers.py` |
| GA-4 negative-stock guard | **Missing.** `BranchSettings.allow_negative_stock` exists but sale flow oversells freely (warning only, `allow_oversell=True`) | `accounts/models.py:255`; `pos/serializers.py` `_apply_stock` |
| GA-5 migration `0017_backfill_branch_payment_routing` | **Not landed — and REJECTED as-is (R-F).** Also numerically collides with the current branch's `0017_warehouse_...` migration | safety branch diff; `pos/migrations/` now reaches `0020` |
| §3.2 provisioning command | **Missing.** No management commands exist anywhere in the backend | `find */management/commands` → empty |
| GA-6 one-default-route guard | **Missing.** `BranchPaymentMethodSerializer` lacks the (branch, method_type) single-active-default validation; resolution order `is_default→first or first` is non-deterministic vs the WIP's `(-is_default, -id)` | `accounts/serializers.py:492`; `sale_posting.py:87-95` |
| GA-7 financially-correct void | **Partial.** Void restores stock + `RETURN_IN` movement + warehouse cache, but posts **no compensating financial/AR ledger entries**, takes no row lock, has no idempotency | `pos/views.py:885-963` |
| GA-8 structured error shape | **Partial.** Purchase-invoice idempotency returns `{error:{code,detail}}`; sale-flow errors are plain strings (`{'payment': str(exc)}`) | `pos/views.py:1428-1435`; `pos/serializers.py` |
| GA-9 Gate A test pack (+535 L) | **Not landed.** Current suite (365 green) covers idempotency service, purchase-invoice idempotency, stock hardening, warehouse balances — not the Gate A guards | `pos/tests.py`, `pos/test_phase1_foundation.py` |
| GA-10 warehouse-stock route rename | **DONE** — landed as commit `8ba1554` on this branch | `git log`; route serves `warehouse-stocks/` |

**Slice 2 (sales idempotency):** service + `IdempotencyRecord` model + migration
`0014` exist and are wired to **purchase invoices only**. `POST /sales/`
(`SaleListCreateView.create`) has **no** idempotency handling.

**Structural fact:** the current branch has diverged past the safety branch —
migrations `0017`–`0020` (Warehouse, PurchaseInvoice, Sale.customer/unit_cost,
WarehouseStock) exist here but not there. Gate A components must be **ported as
fresh commits guided by the diff**, never merged or cherry-picked wholesale
(safety rule: no branch merging; `safety/backend-gate-a-wip-2026-07-04` is
never modified).

### 2. Decision-gate status affecting Sprint 1

- **G0 is OPEN.** D-15 (negative stock): Option A *selected* (2026-07-05) but
  the gate has not exited (no §4 sign-off, no ADR promotion). D-14
  (credit-limit null/zero semantics): **no option selected** — the pending
  question ("NULL = unlimited, 0 = no credit, positive = max limit?") is
  unanswered.
- Consequence (per the register's own scoping): **GA-3 and GA-4 are blocked**;
  every other Gate A component is explicitly ungated and may proceed
  ("component-by-component Gate A review may proceed in parallel",
  IMPLEMENTATION_ROADMAP §1).
- No new missing decisions were discovered in this audit — nothing added to
  ARCHITECTURE_DECISIONS_REQUIRED.md.

### 3. Sprint 1 execution plan (prepared, not yet executed)

Landing order per TRANSITION_AND_MIGRATION_PLAN §3.2, on a new branch
`s1/gate-a-foundation` cut from `fix/ga-10-warehouse-stock-route`:

| Step | Component | Gated on | Notes |
|---|---|---|---|
| 0 | GA-10 | — | Already landed (`8ba1554`). No action. |
| 1 | GA-1 env-driven settings + `.env.example` | — | **DONE — Batch 1 (2026-07-12).** |
| 2 | GA-6 one-default guard + deterministic `(-is_default,-id)` resolution | — | **DONE — Batch 1 (2026-07-12).** Duplicate-default *demotion* moves into the step-4 command. |
| 3 | GA-8 structured error shape on the sale flow | — | **DONE — Batch 1 (2026-07-12).** FE already renders it. |
| 4 | `provision_default_payment_routing` management command (`--dry-run` default / `--apply [--tenant]`) | — | **DONE — Batch 2 (2026-07-13).** Replaces GA-5. No financial rows created inside `migrate`; idempotent; logs every created/reused/demoted row. |
| 5 | Sales idempotency (Slice 2) | — | **DONE — Batch 2 (2026-07-13).** Wired into `SaleListCreateView.create` exactly as purchase invoices; replay → one Sale, conflict → 409. |
| 6 | GA-7 financially-correct void | — | **DONE — Batch 2 (2026-07-13).** Compensating reversal entries under `select_for_update`, `Idempotency-Key` replay, AuditLog with optional reason (R-C). |
| 7 | GA-9 test pack | — | **DONE — Batch 2 (2026-07-13).** Backfill tests re-pointed at the step-4 command; void-reversal + sales-idempotency tests added; suite 389 green. |
| 8 | GA-2 strict routing | Step 4 **applied & verified for every active tenant** | **DONE — Batch 2 (2026-07-13) in code.** Legacy skip removed. **Production rollout still requires running the step-4 command with `--apply` per tenant and clearing its WARN lines before deploy.** |
| 9 | GA-3 credit-limit guard | **D-14 answered + G0 exit** | If D-14 → "null = unlimited", requires an additive nullable migration on `Customer.credit_limit`. |
| 10 | GA-4 negative-stock guard | **G0 exit** (D-15 already selected: branch toggle only, no per-sale override) | Blocked oversell → structured 400 + full rollback. |

Steps 9–10 ship in a Sprint-1 follow-up batch the moment G0 exits; everything
else has now been executed (Batches 1–2).

**Explicitly out of Sprint 1 scope:** GL, recipes, production, costing,
category split, units, document numbering, returns, delivery, ETA (per sprint
roadmap and the §5 freeze in TARGET_BOUNDARIES.md).

### 4. Risks

| Risk | Mitigation |
|---|---|
| Strict routing (GA-2) lands before all tenants provisioned → branches stop selling | GA-2 is last; gated on dry-run review + `--apply` verified per tenant. |
| Porting from the diverged safety branch reintroduces `Product.stock`-era assumptions over the new `WarehouseStock` cache | Port by hand against current code; run stock-hardening + warehouse test files per step. |
| Void reversal entries double-post on retry | GA-7 ships with idempotency + row lock + already-voided guard, with tests. |
| D-14 decided differently than the WIP's `<=0 = unlimited` reading | GA-3 deliberately deferred; no code assumes either semantics until D-14 is answered. |
| Blocked-oversell (GA-4) breaks existing POS flows for branches relying on oversell | GA-4 deferred to G0 exit; default remains current behavior until then; FE PaymentModal already handles structured 400s. |

### 5. Remaining blockers

1. ~~User authorization to execute Sprint 1~~ — **Batches 1–2 authorized and
   executed** (2026-07-12 / 2026-07-13).
2. **D-14 answer + G0 sign-off/promotion** — blocks steps 9–10 only.
3. Access to a production-like tenant list for the step-8 provisioning
   verification (dev DB only has test data). **Operational note:** strict
   routing is now live in code — before deploying this branch to any real
   environment, run `python manage.py provision_default_payment_routing`
   (dry-run), review, then `--apply` per tenant and resolve every WARN line.

---

## Sprint 2 — Master Data Foundation (units / categories / product / warehouse authority)

**Status: IN PROGRESS — Batch 1 (Units Core Foundation) executed 2026-07-14
(committed `00fddae`); Batch 2 (Category Trees Foundation) executed 2026-07-14
on branch `s2/batch-2-category-trees`; suite 472 green.** Design authority:
the approved Sprint 2 design (plan approved 2026-07-13) + MASTER_DATA_CONTRACT
§2/§3. Remaining: Batch 0 governance (owner action — see flag below),
Batches 3–5.

**Governance flag (unresolved, carried from the design's Batch 0):**
ARCHITECTURE_DECISIONS_REQUIRED §4 still shows **G1 (D-01) and G2 (D-13) with
blank sign-off cells**. Batch 1 was executed on explicit user authorization;
the register still needs the G2 selection (conversion precision: implemented
as `Decimal(16,6)` factors + 3dp base-quantity quantize) recorded + ADR
promotion per R-M.

### 1. Batch 1 execution record (2026-07-14, authorized) — Units Core

**Scope executed:** dynamic unit foundation only — UnitGroup, Unit,
ProductUnit, ProductBarcodeUnit + conversion service + CRUD APIs + tests.
Not touched: recipes, costing, GL, categories, product-type changes, scan
precedence, purchase/sale flows, stock logic, frontend. No commits made.

- **Files changed:**
  - `superpos_backend/pos/models.py` — 4 new models (below); all additive,
    legacy `Product.unit` enum / `pack_qty` / `weighted` untouched and still
    behavior-authoritative.
  - `superpos_backend/pos/migrations/0021_units_foundation.py` — **new
    (migration 0021)**, schema-only, zero data rows (R-F), reversible.
  - `superpos_backend/pos/services/units.py` — new pure conversion service:
    `convert_to_base` (validates mapping ownership/activity, quantizes to
    3dp HALF_UP via `quantize_qty`), `get_base_product_unit`,
    `product_has_stock_history`, `assert_base_mapping_mutable` (base mapping
    immutable once StockMovements exist; creating the FIRST base mapping for
    a legacy product stays allowed — that is the Batch-4 seed path).
  - `superpos_backend/pos/serializers.py` — UnitGroupSerializer,
    UnitSerializer, ProductUnitSerializer, ProductBarcodeUnitSerializer
    (tenant-scoped FK validation + friendly 400 twins of every DB constraint;
    barcode collision check vs legacy `Product.barcode` namespace).
  - `superpos_backend/pos/views.py` — list/detail/deactivate views for
    unit-groups + units (Manager+ writes, Cashier+ reads — warehouse-route
    conventions); `_ProductScopedMixin` + nested product-units and
    product-barcodes views (cross-tenant product → 404).
  - `superpos_backend/pos/filters.py` — UnitGroupFilter, UnitFilter.
  - `superpos_backend/pos/urls.py` — routes per contract §2.4:
    `catalog/unit-groups/` (+detail/deactivate), `catalog/units/`
    (+detail/deactivate), `products/{pk}/units/` (+detail),
    `products/{pk}/barcodes/`.
  - `superpos_backend/pos/test_units.py` — new (+42 tests).
- **Models added:** `UnitGroup` (tenant family; group base = the factor-1
  unit — deliberately NO circular `base_unit` FK, deviating from the
  contract's *suggested* shape per the approved design); `Unit`
  (`factor_to_base Decimal(16,6) > 0`, `allow_decimal` as the data-driven
  successor of PIECE/weighted rules — plain data this batch); `ProductUnit`
  (`conversion_to_base Decimal(16,6) > 0` authoritative per product; DB
  partial-unique one `is_base` per product; DB CHECK base ⇒ conversion = 1);
  `ProductBarcodeUnit` (`(tenant, barcode)` unique; scan precedence deferred
  to Batch 3).
- **Migration numbers:** `pos/0021_units_foundation` (applied to dev DB).
- **Rules honored:** stock remains stored ONLY in the base unit (R-B) — this
  batch touches no stock-writing path; no hardcoded units (all rows; seeds
  arrive as the Batch-4 dry-run command, R-F); decimal quantities +
  product-specific conversion overrides supported; existing products fully
  compatible (zero Product schema/behavior change — verified by the
  unchanged 389 baseline plus an explicit legacy-sale compatibility test).
- **Tests executed:** full backend suite — **431 passed, 0 failed** (58.5 s;
  389 baseline + 42 new). `python manage.py check` clean;
  `makemigrations --check` clean. New coverage: catalog CRUD + tenant
  isolation + deactivate; ProductUnit rules (one base, base-conversion=1,
  uniqueness, cross-tenant 400/404, base immutability with history,
  first-base-on-legacy allowed); conversion math incl. the literal brief
  examples (milk 3 cartons → 36,000 ml; chocolate 2 bags → 10,000 g;
  fractional 0.5 carton → 6,000 ml; 3dp quantize); barcode uniqueness,
  cross-tenant reuse, legacy-namespace collision, belongs-to-product;
  legacy sale flow unchanged with mappings present.
- **Risks:**
  - G1/G2 sign-off cells still blank (flag above) — precision choice
    Decimal(16,6) needs formal D-13 ratification; revisiting it later would
    be an additive migration.
  - `allow_decimal` / ProductUnit roles are stored but consumed by nothing
    yet — behavior switch-over (POS qty rules, scan precedence) is Batch 3+
    with parity tests, so no regression surface exists today.
  - Legacy `Product.barcode` vs `ProductBarcodeUnit` namespaces are guarded
    serializer-side only (no cross-table DB constraint possible); direct ORM
    writes could still collide — the Batch-4 seed command re-checks.
  - Parallel sessions edit this repo — batch left uncommitted per
    instructions; commit before the next session starts Batch 2.
- **Next batch:** Batch 2 — Category trees (migration 0022: SalesCategory +
  InventoryCategory, cycle guard, resolution service + `resolved-defaults`
  preview, CRUD APIs, tests). Batch 0 (G1/G2 sign-off + ADR promotion)
  remains an owner action that should land before/with it.

### 2. Batch 2 execution record (2026-07-14, authorized) — Category Trees

**Scope executed:** hierarchical category foundation only — SalesCategory +
InventoryCategory (two independent self-parent trees) + CRUD APIs + tests.
Not touched: recipes/BOM, costing, COGS, GL, product types,
Product.sales_category/inventory_category (future batch), legacy `Category`
model + route (frozen as-is), `Product.category`, POS filtering, sale/purchase
flows, Unit models, WarehouseStock, frontend. No commits made.

- **Changed files:**
  - `superpos_backend/pos/models.py` — 2 new models (below); additive only.
  - `superpos_backend/pos/migrations/0022_category_trees.py` — **new
    (migration 0022)**, additive schema only (2 tables + 4 constraints),
    zero data rows (R-F), no changes to any existing table.
  - `superpos_backend/pos/serializers.py` — `_CategoryTreeSerializerMixin`
    (shared validation: same-tenant parent, active parent required for new
    assignments, self-parent rejected, walk-up ancestor cycle guard with
    corrupt-data protection, friendly sibling/root name-uniqueness 400s) +
    SalesCategorySerializer / InventoryCategorySerializer (parent queryset
    tenant-pinned in `__init__`).
  - `superpos_backend/pos/views.py` — list-create / detail (GET/PATCH, no
    DELETE) / deactivate views per tree — Manager+ writes, Cashier+ reads
    (unit/warehouse route conventions).
  - `superpos_backend/pos/filters.py` — SalesCategoryFilter,
    InventoryCategoryFilter (`parent`, `is_active`, `active` alias,
    `root=true` for top-level nodes).
  - `superpos_backend/pos/urls.py` — 6 routes (below).
  - `superpos_backend/pos/test_categories.py` — new (+41 tests).
- **Models added:** `SalesCategory` (menu/POS/sales-report tree) and
  `InventoryCategory` (stock/purchasing tree) — deliberately separate tables
  with separate self-FKs (D-01 option b; never merged, never sharing
  parents). Both: tenant FK, nullable self-parent (PROTECT — a parent with
  children cannot be deleted; deactivate instead), name, is_active,
  timestamps. Name uniqueness per (tenant, parent) plus a partial root-level
  constraint (NULL parents don't collide in Postgres). Unlimited depth.
  **Deviation note:** the goal's field list is exhaustive, so the approved
  design's extra SalesCategory fields (show_on_pos, sort_order,
  default_station, GL/tax placeholder ids) are deferred to a later additive
  batch — they ride the same tables.
- **Migration numbers:** `pos/0022_category_trees` (applied to dev DB;
  `makemigrations --check` clean).
- **API endpoints added:** `catalog/sales-categories/` (GET list + POST),
  `catalog/sales-categories/{id}/` (GET/PATCH),
  `catalog/sales-categories/{id}/deactivate/` (POST) — and the same trio
  under `catalog/inventory-categories/`. Tenant-scoped via TenantMixin;
  cross-tenant detail/patch → 404.
- **Tests executed:** full backend suite — **472 passed, 0 failed** (69.6 s;
  431 baseline + 41 new). `python manage.py check` clean. New coverage (run
  against BOTH trees via a shared mixin): root/child/multi-level creation
  (Beverages→Coffee→Hot Coffee→Espresso), rename, valid reparent,
  deactivate; self-parent rejected, descendant-as-parent rejected (A→B→C, C
  cannot parent A), direct-child-as-parent rejected, cross-tenant parent
  rejected, inactive parent rejected, sibling-duplicate rejected while same
  name under another parent allowed, root-duplicate rejected; list scoping,
  cross-tenant 404s, cashier read-only, `root` filter. Independence tests
  (same "Milk" in both trees per the brief's example; sales node can't
  parent an inventory node). Legacy compatibility tests (flat `categories/`
  route lists+creates; `Product.category` FK + `category_name` unchanged;
  POS `?category=` product filter still keyed to legacy Category).
- **Risks / blockers:**
  - G1 (D-01 category split) sign-off cell in ARCHITECTURE_DECISIONS_REQUIRED
    §4 is still blank — same governance flag as Batch 1; this batch
    implements the D-01 recommendation (option b) on explicit user
    authorization; register + ADR promotion remain an owner action.
  - Cycle detection is serializer-layer (per the goal: not DB-only); direct
    ORM writes could still create a cycle — the walk-up guard carries a
    visited-set so even corrupt data cannot loop it; the Batch-4 classify
    command should re-verify tree integrity.
  - Nothing consumes the trees yet (by design) — product linkage +
    inheritance resolution arrive with Batch 3's product foundation.
- **Legacy compatibility:** CONFIRMED — flat `Category`/`Product.category`
  untouched (no schema change to either), POS filter behavior proven by
  test, full 431-test baseline stayed green.
- **Next batch:** Batch 3 — Product foundation (migration 0023:
  product_type + PRODUCT_TYPE_FLAGS, sales/inventory category FKs,
  base_inventory_unit, scan precedence, serializer/import-export columns).
  Batch 0 (G1/G2 sign-off + ADR promotion) still pending owner action.

### 3. Batches 3+4 execution record (2026-07-15, authorized) — Product Type Foundation + Product Unit Integration

**Scope executed (per the owner's 2026-07-15 goal, which narrowed the
revised-plan scope):** Batch 3 = product classification foundation
(`product_type` + centralized behavior matrix + tree-category FKs +
`show_on_pos`/`is_discountable` + reverse barcode-collision guard);
Batch 4 = product↔unit integration via the existing Batch 1 models + the
`seed_product_units` command. **Deliberately NOT executed (deferred by the
goal):** scan precedence wiring, PriceTier/ProductUnitTierPrice (revised-plan
3b), `ProductUnit.default_sale_price`, barcode detail route, import/export
columns, Recipe/BOM, costing/COGS/GL, POS/sale/purchase/frontend changes.
No commits made.

- **Changed files:**
  - `superpos_backend/pos/services/product_types.py` — **new**: `ProductType`
    TextChoices + `PRODUCT_TYPE_BEHAVIOR` matrix (`can_sell`, `can_purchase`,
    `track_inventory`, `affects_stock`, `requires_cost`, `can_have_recipe`)
    + `get_behavior` (raises loudly on unknown types) — the single authority;
    no inline `product_type` branching anywhere else.
  - `superpos_backend/pos/models.py` — 5 additive Product fields (below) +
    `(tenant, product_type)` index + `type_behavior` property.
  - `superpos_backend/pos/migrations/0023_product_foundation.py` — **new**,
    additive only (5 AddField + 1 AddIndex), zero data rows (R-F).
  - `superpos_backend/pos/serializers.py` — ProductSerializer: new fields +
    read-only `behavior` flags + `product_type_display` + category names;
    tenant+active validation on both tree FKs (querysets tenant-pinned in
    `__init__`); reverse barcode-collision guard (only when the barcode
    CHANGES — pre-existing collisions never block legacy edits); type-change
    guard: track_inventory cannot be switched off once StockMovement history
    exists (same philosophy as base-unit immutability).
  - `superpos_backend/pos/views.py` — product list/detail `select_related`
    extended to the two new FKs (no N+1 from the name fields).
  - `superpos_backend/pos/management/__init__.py`,
    `.../commands/__init__.py`,
    `.../commands/seed_product_units.py` — **new command** (below).
  - `superpos_backend/pos/test_product_foundation.py` — new (+52 tests).
- **Fields added (Product, all additive):** `product_type` (choices:
  stock_item default / ingredient / prep_item / recipe_product / resale /
  packaging / service / bundle / fixed_asset), `sales_category` FK →
  SalesCategory (SET_NULL), `inventory_category` FK → InventoryCategory
  (SET_NULL), `show_on_pos` (default True), `is_discountable` (default
  True). Legacy `category`, `unit`, `pack_qty`, `barcode`, `weighted` all
  untouched and still governing behavior. **No `Product.base_unit` was
  added** — `ProductUnit.is_base` remains the only base-unit authority.
- **Migration numbers:** `pos/0023_product_foundation` (applied to dev DB;
  `makemigrations --check` clean).
- **API changes (additive only):** `products/` + `products/{id}/` expose the
  five new fields plus read-only `product_type_display`,
  `sales_category_name`, `inventory_category_name`, and calculated
  `behavior` flags. No route added/removed; every legacy key byte-identical.
- **Command added:** `seed_product_units` — dry-run default / `--apply` /
  `--tenant <id>`; idempotent (get_or_create on the DB uniqueness keys);
  Pass 1 unit substrate (Count/Piece, Mass/Gram+Kilogram,
  Volume/Milliliter+Liter, Packaging/Carton — existing rows reused, factors
  never edited), Pass 2 base mirror 1:1 of the legacy enum (kg stays kg;
  conversion=1, sale+purchase flags), Pass 3 pack mapping from `pack_qty>1`
  (Carton×pack_qty; skipped when the base already is carton), Pass 4
  log-only legacy↔pack barcode-collision audit. Never touches stock
  quantities. Dev DB dry-run verified (2 tenants, 50 base mappings planned,
  0 conflicts, rolled back); **`--apply` on dev/prod remains an operator
  action after reviewing the report** (TRANSITION §2.4 pattern).
- **Tests executed:** full backend suite — **524 passed, 0 failed** (45.1 s;
  472 baseline + 52 new). `python manage.py check` clean;
  `makemigrations --check` clean. New coverage: matrix completeness (keys ==
  enum) + per-type flag assertions + unknown-type raises; API round-trip of
  every type with matching read-only flags; spoofed `behavior` payload
  ignored; type-change guard (blocked with history → non-inventory type,
  allowed without history, allowed between inventory types); tree-FK tenant
  isolation both directions + inactive rejected + PATCH-to-null + SET_NULL
  on delete; visibility flag defaults/round-trip; reverse barcode collision
  on create+change, tenant-scoped, unchanged-barcode edits unaffected;
  multi-unit conversions (milk ml/bottle/carton 2→2000/3→36000, chocolate
  0.5 bag→2500 g), wrong-product unit rejected, pack-barcode validations
  both directions; seed command (dry-run writes nothing, 1:1 mirror per
  enum value, pack mapping, carton-base skip, idempotent double-apply,
  tenant scoping, manual base respected, stock+ledger untouched, unknown
  tenant errors); legacy compatibility (pre-Batch-3 payload creates fine,
  all legacy response keys present, sale flow identical even when
  classified `service`/hidden, seeded product sells unchanged).
- **Risks / blockers:**
  - **Enum wording conflict (flagged per SOURCE_OF_TRUTH):** the executed
    type list follows the owner's 2026-07-15 goal (`resale`, `bundle`,
    `fixed_asset`); MASTER_DATA_CONTRACT §11 spells `non_stock`,
    `bundle_combo`, `fixed_asset_purchase_only` (no `resale`/`prep_item`/
    `packaging`), and the revised plan used `non_stock`+`bundle_combo`.
    `service` covers the non_stock intent. Needs reconciling in the Batch 0
    ADR promotion before the values freeze into stored data.
  - **Naming conflict (flagged, owner's spelling kept):** v3.6 PRD §26.1
    names the visibility flag `visible_in_pos`; the goal + contract §11 say
    `show_on_pos` — implemented as `show_on_pos`; record in the ADR.
  - Behavior flags are advisory-only until Batch 5+/Sprint 3 consumers land
    (by design: classification only, nothing enforces `can_sell` etc. yet).
  - G1/G2 sign-off cells still blank (Batch 0 owner action, third batch
    executed on explicit authorization).
  - Deferred from the revised plan and still unscheduled here: scan
    precedence + barcode detail route, PriceTier/tier prices (3b),
    warehouse authority rescheduling.
- **Legacy compatibility:** CONFIRMED — zero legacy fields/routes changed,
  serializer additions are append-only, sale/stock/purchase flows untouched
  (proven by the 472-test baseline staying green + explicit parity tests).
- **Next batch:** revised-plan 3b (PriceTier + ProductUnitTierPrice +
  `catalog/price-tiers/` + `products/{id}/tier-prices/`) or Batch 5 POS
  integration — owner to sequence; Batch 0 still pending.

---

*(Later sprints get their own sections here after their pre-sprint audits.)*
