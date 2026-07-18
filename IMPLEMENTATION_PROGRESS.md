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
on branch `s2/batch-2-category-trees`; Batches 3+4 (Product Type Foundation +
Unit Integration) executed 2026-07-15; Batch 4 remainder (Tier Pricing
Foundation) executed 2026-07-15; Phase 1.5 (Standard Unit Codes, UN/CEFACT
Rec 20 subset) executed 2026-07-15 on branch `s2/batch-4-tier-pricing-remainder`;
Batch 5a (POS Integration, backend only) executed 2026-07-15/16 on branch
`s2/batch-5a-pos-backend`; suite 574 green; Batch 5b (frontend integration —
POS unit-aware selling, Units/Price-Tier/Category-Tree admin UI, purchase
unit picker) executed 2026-07-15 on branch
`s2/batch-5b-frontend-pos-integration`.** Design authority: the approved
Sprint 2 design (plan approved 2026-07-13) + MASTER_DATA_CONTRACT §2/§3,
preceded by a full frontend/backend integration audit (see the plan file
referenced in that session) that catalogued every gap this batch closes.
Sprint 2 is now functionally complete end-to-end (backend + frontend);
remaining work is UX polish / manual QA against a live backend, not new
scope.

**Governance flag — RESOLVED 2026-07-15 (see §4 below):**
ARCHITECTURE_DECISIONS_REQUIRED §4 now records **G1 (D-01) and G2 (D-13,
units/inventory scope) sign-off**, plus two new traceability-only decisions
(D-36 product_type enum wording, D-37 show_on_pos naming). **ADR promotion
into the next source-of-truth docs version (R-M) is still a separate,
outstanding follow-up** — sign-off-complete is not the same as fully
gate-closed in the strict R-M sense.

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

### 4. Batch 4 remainder execution record (2026-07-15, authorized) — Tier Pricing Foundation

**Scope executed (per the owner's 2026-07-15 planning session):** Batch 0
governance closure (G1/G2 sign-off + D-36/D-37 naming decisions recorded in
`ARCHITECTURE_DECISIONS_REQUIRED.md`) + the revised-plan 3b pricing item,
narrowed to a real ERP price-tier foundation on the owner's explicit
principles (dedicated `PriceTier` model, `ProductUnitTierPrice` keyed on
`(product_unit, price_tier)` not `product_unit` alone, `Product.price` as
fallback only, **never** a price computed from `conversion_to_base`) +
`ProductUnit.minimum_order_qty`. **Deliberately NOT executed (deferred by the
owner):** `Product.default_station` (revisit once the Preparation
Station/Kitchen-Bar domain is designed), barcode scan-precedence wiring,
`ProductVariant`, POS/sale/purchase flow consumption (Batch 5a), frontend
(Batch 5b).

- **Governance (§0, no schema):** `ARCHITECTURE_DECISIONS_REQUIRED.md` —
  G1 (D-01) and G2 (D-13, units/inventory scope) sign-off recorded in §4 and
  §3.5 consultation log; D-13's avg-cost-precision half stays Open under G3
  (unrelated to units). Two new traceability-only decisions appended
  (§3.4a, never renumbered): D-36 (keep the implemented `product_type` enum
  wording over `MASTER_DATA_CONTRACT §11`'s spelling) and D-37 (keep
  `show_on_pos` over PRD v3.6's `visible_in_pos`). **ADR promotion (folding
  into the next PRD/FLOW/DOMAIN/DESIGN version, R-M) has NOT happened yet —
  sign-off-complete, not fully gate-closed in the strict R-M sense.**
- **Changed files:**
  - `superpos_backend/pos/models.py` — `ProductUnit.minimum_order_qty`
    (nullable, `> 0` CHECK when set) + 2 new models (below).
  - `superpos_backend/pos/migrations/0024_product_unit_pricing_foundation.py`
    — **new**, additive schema only (2 tables + field/constraint additions),
    zero data rows (R-F).
  - `superpos_backend/pos/services/pricing.py` — **new**: single authority
    `resolve_unit_price(*, product_unit, price_tier=None) -> Decimal`. Order:
    active `ProductUnitTierPrice` row for `(product_unit, price_tier)` when a
    tier is given and a row exists; otherwise `product_unit.product.price`.
    No other code path may derive a unit price by scaling `Product.price`
    with `conversion_to_base`.
  - `superpos_backend/pos/serializers.py` — `PriceTierSerializer`,
    `ProductUnitTierPriceSerializer` (tenant/active `price_tier` validation,
    `(product_unit, price_tier)` uniqueness 400-twin of the DB constraint,
    `price > 0`); `ProductUnitSerializer` gained `minimum_order_qty` +
    `validate_minimum_order_qty` (`> 0` when set, `null` allowed).
  - `superpos_backend/pos/views.py` — `PriceTierListCreateView`/`Detail`/
    `Deactivate` (flat, tenant-scoped, same conventions as `UnitGroup`);
    `_ProductUnitScopedMixin` + `ProductUnitTierPriceListCreateView`/`Detail`
    nested two levels under product → product_unit.
  - `superpos_backend/pos/urls.py` — `catalog/price-tiers/` (+detail/
    deactivate), `products/{pk}/units/{unit_pk}/tier-prices/` (+detail).
  - `superpos_backend/pos/test_pricing.py` — new (+25 tests).
- **Models added:** `PriceTier` (tenant-scoped, free-text `name` — not a
  fixed enum, since each tenant names its own tiers; `unique(tenant, name)`).
  `ProductUnitTierPrice` (`tenant`, `product` convenience FK mirroring the
  `ProductBarcodeUnit.product` pattern, `product_unit` FK `CASCADE`,
  `price_tier` FK `PROTECT` — a tier referenced by any price is deactivated,
  never deleted, `price` `Decimal(10,2)`, `is_active`;
  **`unique(product_unit, price_tier)`, not `product_unit` alone** — the
  same unit supports multiple tiers by design; `price > 0` CHECK).
  **Discovery confirming the design direction:** `accounts.Customer.
  price_tier_id` and `accounts.BranchSettings.default_price_tier_id` were
  already forward-declared plain `BigIntegerField`s awaiting exactly this
  model (comment: *"price_tier_id is a forward-declared plain BigInt because
  PriceTier ... does not exist today"*); neither field is read anywhere yet,
  so wiring them to real FKs + automatic tier resolution in the sale flow is
  deliberately deferred to Batch 5a+ as a separate decision (see below).
- **Migration numbers:** `pos/0024_product_unit_pricing_foundation` (applied
  to dev DB; `makemigrations --check` clean).
- **API endpoints added:** `catalog/price-tiers/` (GET list + POST),
  `catalog/price-tiers/{id}/` (GET/PATCH),
  `catalog/price-tiers/{id}/deactivate/` (POST);
  `products/{pk}/units/{unit_pk}/tier-prices/` (GET list + POST),
  `products/{pk}/units/{unit_pk}/tier-prices/{id}/` (GET/PATCH — PATCH
  `is_active=false` deactivates, no DELETE). `products/{pk}/units/{id}/`
  response gains `minimum_order_qty` (nullable). Tenant-scoped via
  `TenantMixin`; cross-tenant product/unit/tier → 404/400 per the existing
  conventions.
- **Tests executed:** full backend suite — **549 passed, 0 failed** (42.6 s;
  524 baseline + 25 new). `python manage.py check` clean;
  `makemigrations --check` clean. New coverage: `PriceTier` CRUD + tenant
  isolation + deactivate + cashier read-only; `ProductUnitTierPrice` CRUD,
  **the same product_unit holding two active tier prices simultaneously**
  (the core requirement), duplicate `(product_unit, price_tier)` pair
  rejected, non-positive price rejected, cross-tenant `price_tier` rejected,
  inactive `price_tier` rejected, cross-tenant product/unit scope 404s;
  `minimum_order_qty` null/positive/non-positive validation;
  `resolve_unit_price` — tier price used when present, falls back to
  `Product.price` when a tier is given but has no matching row, falls back
  when no tier is given at all, ignores inactive tier-price rows, and an
  **explicit regression test asserting the resolved price is never equal to
  `Product.price * conversion_to_base`** for a 12,000x carton mapping.
- **Risks / blockers:**
  - `Customer.price_tier_id` / `BranchSettings.default_price_tier_id` →
    real FK conversion + automatic tier resolution in the sale flow is
    explicitly out of scope here — a cross-app (`accounts` + `pos`) decision
    on fields that may already carry data, deserving its own gate rather than
    silent inclusion. Batch 5a will accept an explicit `price_tier_id` on the
    sale request instead.
  - `default_station` remains fully deferred (owner decision) — no code, no
    migration, not even a placeholder field.
  - G1/G2 are sign-off-complete but not ADR-promoted (see governance note
    above) — v3.6 stays authoritative per R-M until promotion lands.
- **Legacy compatibility:** CONFIRMED — zero legacy fields/routes changed,
  every addition is either a new table or a nullable field with a DB default
  of NULL, sale/stock/purchase flows untouched (proven by the 524-test
  baseline staying green + the new suite).
- **Next batch:** Batch 5a — POS integration (backend only): barcode
  resolution (`ProductBarcodeUnit` → `ProductUnit` → `Product`, legacy
  `Product.barcode` fallback), `SaleItem`/`PurchaseInvoiceLine` audit
  snapshot (`product_unit`, entered quantity, converted base quantity, price
  actually used), `show_on_pos` catalog filtering, `minimum_order_qty`
  purchase-line validation. Batch 5b (frontend) follows once 5a is stable —
  first frontend change in the entire Sprint 1+2 stack.

### 5. Phase 1.5 execution record (2026-07-15, authorized) — Standard Unit Codes

**Scope executed (per the owner's 2026-07-15 manual-testing follow-up):**
during manual Postman verification of Batch 4, the owner raised a real
master-data gap — `Unit.name` is free text with zero cross-branch
standardization — and asked for a UN/CEFACT Recommendation 20 code tag (the
same code set the Egyptian e-invoice/e-receipt system, ETA, requires in its
`unitType` field) to be added **before** Batch 5a, since sale/purchase/
barcode flows will be built on top of unit master data. Explicit owner
constraints: `standard_code` is **purely optional** metadata (never required,
never enforced, no dropdown-only mode); no data migration backfills existing
units; implemented as a Python `TextChoices` enum (no new DB table, no
joins, zero query overhead) rather than a shared lookup table; a curated,
verified subset (not the full 2138-row Rec 20 list, which is ~95% obscure
physics/engineering units irrelevant to retail/F&B/wholesale). **No ETA API
integration in this batch** — code storage only, for future compatibility.

- **Changed files:**
  - `superpos_backend/pos/services/standard_units.py` — **new**:
    `StandardUnitCode(models.TextChoices)`, 87 verified UN/CEFACT Rec 20
    codes across count, mass, volume, length, area, time, and
    packaging/trade categories. Every code/label pair was cross-checked
    against the source Rec 20 list the owner supplied — no invented codes,
    favoring correctness over hitting a round number.
  - `superpos_backend/pos/models.py` — `Unit.standard_code`
    (`CharField(max_length=10, choices=StandardUnitCode.choices,
    blank=True, default='')`) — same optional-field convention already used
    for `Product.plu`/`Unit.symbol`.
  - `superpos_backend/pos/migrations/0025_unit_standard_code.py` — **new**,
    additive-only (single `AddField`, no data migration, existing rows keep
    `standard_code=''`).
  - `superpos_backend/pos/serializers.py` — `UnitSerializer` gained
    `standard_code` (writable, optional) + `standard_code_display`
    (read-only, `get_standard_code_display()`).
  - `superpos_backend/pos/views.py` — `StandardUnitCodeListView` (GET-only,
    no DB query, returns the static enum as `[{code, label}, ...]`).
  - `superpos_backend/pos/urls.py` — `catalog/standard-unit-codes/`.
  - `superpos_backend/pos/test_units.py` — new `StandardUnitCodeTests`
    class (+6 tests).
- **Migration numbers:** `pos/0025_unit_standard_code` (applied to dev DB;
  `makemigrations --check` clean).
- **API endpoints added:** `GET catalog/standard-unit-codes/` (Cashier+
  read, static list, no tenant scoping — shared across all tenants, same
  philosophy as the legacy `Product.unit` choices). `catalog/units/` and
  `catalog/units/{id}/` responses gain `standard_code` (writable) +
  `standard_code_display` (read-only); both blank/omittable.
- **Tests executed:** full backend suite — **555 passed, 0 failed** (87.4 s;
  549 baseline + 6 new). `python manage.py check` clean;
  `makemigrations --check` clean. New coverage: pre-existing fixture units
  confirmed to still carry `standard_code=''` after the migration; a unit
  created without `standard_code` still succeeds; a unit created with a
  valid code (`KGM`) persists the code and its display label; an invalid
  code is rejected with 400; the new list endpoint returns the full set
  including known entries and is readable by Cashier role.
- **Risks / blockers:** none — additive field, additive endpoint, zero
  existing behavior changed. The 87-code list is intentionally
  extensible: adding a code later is a one-line enum change plus a matching
  additive migration, never a backfill of existing `Unit` rows.
- **Legacy compatibility:** CONFIRMED — every existing `Unit` row keeps
  working with `standard_code=''`; no screen, endpoint, or validation rule
  changed for callers that never send the field.
- **Next:** owner-mandated architecture review checkpoint (see plan file)
  before opening any Batch 5a code, then Batch 5a — POS integration
  (backend only), per the Batch 4 remainder record above.

### 6. Batch 5a execution record (2026-07-15/16, authorized) — POS Integration (backend only)

**Scope executed:** the architecture review checkpoint passed (manage.py
check clean, no missing migrations, `PriceTier`/`ProductUnitTierPrice`
untouched, `Customer.price_tier_id`/`BranchSettings.default_price_tier_id`
still plain BigInt) on branch `s2/batch-5a-pos-backend` (cut from the
Phase 1.5 tip). Then: barcode resolution service, `SaleItem`/
`PurchaseInvoiceLine` audit snapshot, `show_on_pos` catalog filter,
`minimum_order_qty` purchase enforcement. **Deliberately NOT executed:**
frontend (Batch 5b), `Customer.price_tier_id`/`BranchSettings.
default_price_tier_id` → real FK + automatic tier resolution (still a
separate deferred decision — this batch accepts an explicit `price_tier`
on the sale request instead), `default_station`.

- **Changed files:**
  - `superpos_backend/pos/services/barcode_resolution.py` — **new**:
    `resolve_barcode(*, tenant, code) -> (Product, ProductUnit|None) | None`.
    Mandatory chain `ProductBarcodeUnit → ProductUnit → Product` first;
    legacy `Product.barcode` fallback paired with `get_base_product_unit`
    second. No `scan_priority` field needed (uniqueness within each table
    plus this fixed two-step order is sufficient).
  - `superpos_backend/pos/views.py` — `product_scan`'s plain-barcode branch
    now calls `resolve_barcode` instead of querying `Product.barcode`
    directly; response gains an additive `product_unit` key (present only
    when a unit resolved) — the `weight_encoded` shape and the `barcode`
    shape's existing keys are byte-identical to before. New
    `StandardUnitCodeListView` import wiring unaffected.
  - `superpos_backend/pos/models.py` — `SaleItem.product_unit` (`SET_NULL`,
    nullable) + `SaleItem.entered_qty`; `PurchaseInvoiceLine.product_unit`
    (`SET_NULL`, nullable) + `PurchaseInvoiceLine.entered_qty`. `qty` on
    both models keeps its existing meaning (base-unit quantity, matching
    every stock-writing path) — a unit-aware line's `qty` is always the
    `convert_to_base` result, never `entered_qty` itself.
  - `superpos_backend/pos/migrations/0026_batch5a_audit_snapshot.py` —
    **new**, 4 additive `AddField`s, zero data rows (R-F).
  - `superpos_backend/pos/serializers.py` —
    * `SaleItemSerializer`: `qty`/`price_each` no longer field-required
      (unit-aware lines omit them); new `product_unit`/`entered_qty`.
    * `SaleSerializer`: new write-only `price_tier` (per-sale hint, not a
      Sale column); `validate()` derives `qty` (`convert_to_base`) and
      `price_each` (`resolve_unit_price`) for any line carrying
      `product_unit`, enforces `entered_qty` presence/positivity and
      `product_unit.product == line.product`; the legacy no-`product_unit`
      shape is completely unchanged (same required-field checks as before).
      New `_money_qty` static helper resolves which quantity subtotal/tax/
      line_total math uses: `entered_qty` for a unit-aware line (its
      `price_each` is priced per THAT unit), the legacy `qty` otherwise —
      required so `qty` can stay base-unit-denominated without breaking the
      money math (multiplying a base-unit quantity by a whole-carton price
      would be wrong by the conversion factor).
    * `PurchaseInvoiceLineSerializer`: same `product_unit`/`entered_qty`
      addition; `qty` no longer field-required (derived server-side for a
      unit-aware line); `validate()` requires `qty` only for the legacy
      shape, `entered_qty` only for the unit-aware shape.
  - `superpos_backend/pos/services/purchase_invoices.py` —
    `post_purchase_invoice` gains the same conversion + `minimum_order_qty`
    enforcement; `moving_average_cost` is fed a per-BASE-unit cost rate
    (`line_subtotal ÷ base qty` — the real total money paid divided by the
    real base quantity received, standard weighted-average COGS math, never
    a price/cost multiplied by `conversion_to_base`) so `Product.cost`'s
    long-standing per-base-unit meaning stays intact for unit-aware lines.
  - `superpos_backend/pos/filters.py` — `ProductFilter` gains `show_on_pos`
    as an opt-in filter field (django-filter auto-generates it from
    `Meta.fields`); omitted by default, so every existing caller (admin
    product screens) sees every product exactly as before.
  - `superpos_backend/pos/test_pos_integration.py` — **new** (+19 tests):
    barcode resolution service (chain-first, legacy fallback, tenant
    isolation, unknown code), `product_scan` endpoint wiring, unit-aware
    Sale lines (tier price resolved / fallback to `Product.price` /
    missing `entered_qty` rejected / cross-product `product_unit` rejected
    / legacy shape byte-identical), unit-aware `PurchaseInvoiceLine`
    (conversion + moving-average correctness / `minimum_order_qty`
    rejection with full rollback / legacy shape byte-identical),
    `show_on_pos` filter (default unfiltered / `true` hides / `false`
    isolates).
- **Migration numbers:** `pos/0026_batch5a_audit_snapshot` (applied to dev
  DB; `makemigrations --check` clean).
- **API changes (additive only):**
  * `POST /api/sales/` — `items[]` accepts `product_unit` + `entered_qty`
    as an alternative to `qty`/`price_each`; top-level optional `price_tier`.
    Response `items[]` gains `product_unit`/`entered_qty` (null for legacy
    rows/lines).
  * `POST /api/purchase-invoices/` — `lines[]` accepts `product_unit` +
    `entered_qty` as an alternative to `qty`; response `lines[]` gains the
    same two fields.
  * `GET /api/products/scan/<barcode>/` — plain-barcode responses gain an
    additive `product_unit` object when one resolves; a pack-level
    (`ProductBarcodeUnit`) barcode now resolves at all (previously 404).
  * `GET /api/products/` — new opt-in `?show_on_pos=true|false` filter.
  No existing route removed or renamed; no existing response key removed.
- **Tests executed:** full backend suite — **574 passed, 0 failed** (79.4 s;
  555 baseline + 19 new). `python manage.py check` clean;
  `makemigrations --check` clean.
- **Risks / blockers:**
  - `Customer.price_tier_id`/`BranchSettings.default_price_tier_id` remain
    plain BigInt, unread anywhere — still an explicit `price_tier` on the
    sale request, per the Batch 4 remainder decision. Auto-resolution from
    customer/branch is a separate future decision.
  - The moving-average-cost re-denomination (`line_subtotal ÷ base qty`)
    is new math introduced by this batch; it is exercised by
    `test_unit_aware_line_converts_qty_and_updates_moving_average` with a
    zero-stock fixture chosen specifically so the result is an exact
    division (no rounding ambiguity to mask a formula error) — a
    non-zero-stock, non-exact-division scenario is not separately covered
    yet.
  - `scan_priority` was confirmed unnecessary per the original planning
    note; if a future requirement needs per-barcode priority ordering
    within a single table, this simplification would need revisiting.
- **Legacy compatibility:** CONFIRMED — every existing Sale/PurchaseInvoice
  line shape (no `product_unit`) is byte-identical to pre-Batch-5a
  behavior (explicit regression tests), `product_by_barcode` untouched,
  admin product screens see every product by default (`show_on_pos` is
  opt-in), the 555-test baseline stayed green.
- **Next:** Batch 5b (frontend) — first frontend change across the entire
  Sprint 1+2 stack; needs its own UX-focused planning session before any
  code (unit picker on the sale screen, price-tier selection, POS catalog
  filtering, barcode-scan UI, purchase-line unit picker).

### 7. Batch 5b execution record (2026-07-15, authorized) — Frontend Integration (POS + admin UI)

Preceded by a full read-only Frontend/Backend Integration Audit (Parts 1–10,
112 backend URL patterns inventoried, 124 endpoint-method rows classified
consumed/partial/never) that found **zero frontend consumer for every
Sprint 2 backend addition** — Units, Category Trees, Product Types,
PriceTier/ProductUnitTierPrice, Barcode Resolution, Standard Unit Codes,
`show_on_pos`, `minimum_order_qty` — not just on POS but across product
admin, purchasing, and settings. This batch closes that gap.

- **Scope executed (sub-batches 5b-1 → 5b-4, all on one branch):**
  1. **POS core unit-aware selling.** Barcode scan switched from the legacy
     `/products/barcode/<code>/` to `/products/scan/<code>/` (server-side
     weight-barcode decode + `ProductBarcodeUnit → ProductUnit → Product`
     resolution) — removes a duplicated, drifted client-side scale-barcode
     parser (`utils/barcode.ts` had default prefix `'21'` vs. the backend's
     `'23'` default; deleted, now dead). Product catalog fetch now passes
     `show_on_pos=true`. New server-side product search box (previously
     absent — discovery was scan-or-8-tiles only). New `UnitPickerModal`
     lets the cashier choose a non-base `ProductUnit` with a live price
     preview (tier price if one matches the active tier, else the
     product's base price — mirrors the backend's own `resolve_unit_price`
     fallback, display-only). Unit-aware lines send `{product,
     product_unit, entered_qty}`; the server derives `qty`/`price_each` —
     never computed client-side. Optional price-tier selector wired to the
     sale's top-level `price_tier`. Removed the hardcoded demo-barcode
     buttons.
  2. **Admin CRUD for Units and Price Tiers** (previously zero UI —
     Django admin only). New `/units` page (Unit Groups + Units tabs,
     `standard_code` picker sourced from `/catalog/standard-unit-codes/`).
     New `/price-tiers` page. New `ProductUnitsDrawer` (row action on
     Products → "Units & pricing") managing one product's `ProductUnit`
     conversions (incl. `minimum_order_qty`, sale/purchase eligibility),
     `ProductBarcodeUnit` pack barcodes, and per-tier
     `ProductUnitTierPrice` rows.
  3. **Category Trees admin UI + product classification form.** New
     `/categories` page (Sales/Inventory tabs, indented tree view,
     create/edit/deactivate with a parent picker that excludes a node's
     own subtree — client-side mirror of the backend's cycle guard, which
     stays authoritative). `ProductFormModal` (Full Add tab, additive):
     `product_type` select (9 values, labels only — the behavior matrix
     itself is never duplicated client-side; existing products show their
     server-computed `behavior` flags read-only), `sales_category`/
     `inventory_category` tree-aware selects, `show_on_pos`/
     `is_discountable` toggles. Legacy flat `category` field and Quick Add
     tab untouched.
  4. **Purchase-line unit awareness + cleanup.** `PurchaseCreatePage` gets
     a per-line purchase-eligible unit picker; unit-aware lines send
     `{product_unit, entered_qty}` instead of `{qty}`; client-side
     `minimum_order_qty` check mirrors the server's own guard for instant
     feedback (server check stays authoritative). Deleted the confirmed-
     dead `src/data/mock.ts` (zero importers anywhere in the tree, per the
     audit).
- **Changed / new files (highlights):**
  * New: `superpos/src/api/pos.ts` (typed POS layer — `scanBarcode`,
    `listPosProducts`, `createSale`), `utils/pricing.ts`
    (`previewUnitPrice`, shared by `UnitPickerModal` and `POSPage`),
    `utils/tree.ts` (`flattenTree`, `descendantIds`, shared by
    `CategoriesPage` and `ProductFormModal`'s category selects).
  * New pages: `pages/units/UnitsPage.tsx`, `pages/pricing/PriceTiersPage.tsx`,
    `pages/categories/CategoriesPage.tsx`, `pages/products/ProductUnitsDrawer.tsx`.
  * New component: `components/pos/UnitPickerModal.tsx`.
  * Modified: `api/erp.ts` (+`unitsApi`, `productUnitsApi`, `priceTiersApi`,
    `categoriesApi`), `types/erp.ts` (+`Unit`, `UnitGroup`, `ProductUnit`,
    `ProductBarcodeUnit`, `PriceTier`, `ProductUnitTierPrice`,
    `StandardUnitCode`, `CategoryTreeNode`, `ProductTypeValue`,
    `ProductTypeBehavior`, extended `PurchaseInvoiceLinePayload`),
    `types/index.ts` (extended `Product` with the Sprint 2 fields,
    extended `CartItem` with `productUnitId`/`unitLabel`), `store/posStore.ts`
    (`addItem` unit param, `priceTierId` state), `pages/POSPage.tsx`,
    `components/pos/CartLine.tsx`, `components/pos/QuickProductCard.tsx`
    (optional "choose unit" affordance), `components/products/ProductFormModal.tsx`,
    `components/products/ProductActionsMenu.tsx` (+`units` row action),
    `pages/ProductsPage.tsx`, `pages/purchases/PurchaseCreatePage.tsx`,
    `App.tsx` (+`/units`, `/price-tiers`, `/categories` routes, Manager+),
    `auth/permissions.ts`, `components/layout/Sidebar.tsx`, both i18n
    locale files.
  * Deleted (confirmed dead): `src/utils/barcode.ts`, `src/data/mock.ts`.
- **Migration numbers:** none — frontend-only batch, no backend schema touched.
- **API changes:** none — this batch is pure frontend consumption of
  already-shipped Batch 1/2/3/4/5a endpoints; no backend route, field, or
  response shape was added or changed.
- **Tests executed:** the frontend has no test framework configured
  (`package.json` has no `test` script) — verification was `tsc --noEmit`
  + `vite build` (full production build), run clean after every
  sub-batch, plus a `vite dev` boot-and-serve smoke check (200 on `/` and
  on the entry module with no console/transform errors). **No interactive
  browser click-through was performed** — there is no running backend in
  this environment to exercise the flows end-to-end against, so unit
  picker behavior, tier-price preview correctness, and the new admin CRUD
  screens are verified by type-safety and code review only, not by
  observed runtime behavior. This is an explicit gap, not a claimed pass —
  flagged here per the project's testing discipline (see the repo's UI
  verification guidance) rather than asserting the UI "works."
  Two pre-existing, unrelated environment issues were found and fixed
  locally to make the build runnable at all (not committed — they're
  container/`node_modules` state, not project changes): a lost executable
  bit on `node_modules/.bin/*` (caused `npm run build` to silently resolve
  a wrong, incompatible global `tsc`) and a missing optional native
  dependency (`@rollup/rollup-linux-x64-gnu`, the documented npm optional-
  deps bug). A fresh `npm install` on a clean checkout should not hit
  either.
- **Risks / blockers:**
  - **No live QA.** Per the above, nothing in this batch has been clicked
    through against a real backend + database. The highest-risk surfaces
    to verify first: `UnitPickerModal`'s tier-price preview fetch timing,
    the POS sale payload's `product_unit`/`entered_qty` shape against a
    real `/sales/` POST, and `ProductUnitsDrawer`'s nested create flows.
  - `Customer.price_tier_id`/`BranchSettings.default_price_tier_id` are
    still not surfaced anywhere in the frontend (matches the backend's own
    deferred-decision stance from Batch 5a) — price tier selection on POS
    is always an explicit per-sale choice, never auto-resolved from the
    customer or branch.
  - Split payment, per-line discounts, and the dedicated `/sales/<uuid>/receipt/`
    endpoint remain out of scope for this batch (flagged in the audit,
    not part of the Sprint 2 backend gap this batch was closing).
  - Bundle size warning from `vite build` (main chunk >500kB) is
    pre-existing and unrelated to this batch's changes — not addressed
    here (would need route-level code-splitting beyond the already-lazy
    ERP module pages).
- **Legacy compatibility:** every new field/prop is optional and additive;
  a product/sale/purchase-line with no Sprint 2 data configured renders
  and behaves exactly as before this batch (base-unit-only, legacy
  barcode-equivalent flow via `/products/scan/`'s own fallback, no unit
  picker ever shown, no category/type fields required). No existing page,
  route, or component was removed except the two confirmed-dead files.
- **Next:** Live QA against a running backend (the gap flagged above);
  optional stretch cleanup noted in `BATCH5B_FRONTEND_PLAN.md` (consolidating
  the duplicated `Sale` DTOs) was not attempted — all four planned
  sub-batches were completed first and this was explicitly lower priority.

---

## Sprint 3 — Costing (AVCO Engine)

**Pre-sprint architecture review checkpoint (2026-07-16, before any Sprint 3
code):** verified Sprint 2 is genuinely complete before starting new work —
574/574 tests green, `manage.py check` clean, `makemigrations --check`
clean, zero TODO/FIXME/XXX in any Sprint 2 service file (frontend or
backend). Spot-checked the three highest-risk surfaces directly against
source: `ProductUnitTierPrice` (`pos/models.py`) confirmed
`unique(product_unit, price_tier)` — not `product_unit` alone — with
`PROTECT` on `price_tier`; `pos/services/pricing.py#resolve_unit_price`
confirmed it never derives a price from `conversion_to_base`; barcode
resolution (`pos/services/barcode_resolution.py#resolve_barcode`) confirmed
the mandatory `ProductBarcodeUnit → ProductUnit → Product` chain with
legacy-barcode fallback; POS unit-aware selling confirmed end-to-end
(already DB-verified earlier this session with a real posted sale carrying
`product_unit_id`/`entered_qty`/derived `qty`/`price_each`). Sprint 2
declared closed; Sprint 3 proceeds on branch `s3/batch-1-inventory-cost-model`.

Governance: Phase 0 (owner authorization to close the AVCO-relevant subset
of gate G3 — D-07, D-09, D-12, D-13's avg-cost half, D-31 costing-ledger
scope, D-35 — leaving D-02/D-08/D-10/D-11/D-16/D-17/D-22 GL/tax/period
decisions Open and deferred to a future GL slice) is recorded in
`ARCHITECTURE_DECISIONS_REQUIRED.md` per the Sprint 3 plan.

### Batch 1 — `InventoryCost` + `InventoryCostMovement` data model

- **Scope:** ship the D-35(b) valuation record additively — dark launch,
  zero behavior change. No purchase-posting wiring yet (Batch 2).
- **Files changed:**
  - `pos/models.py` — two new model classes placed after `StockMovement`:
    `InventoryCost` (`OneToOneField(Product)`, `avg_unit_cost` at
    `Decimal(14,4)` — the new D-13 internal-precision tier, distinct from
    money-2dp and qty-3dp) and `InventoryCostMovement` (append-only audit
    ledger mirroring `StockMovement`'s `source_document_type`/
    `source_document_id`/`actor_user` linkage pattern).
  - `pos/migrations/0027_inventory_cost.py` — schema-only, two
    `CreateModel` operations, zero `AlterField`/`RemoveField` on any
    existing table. Verified additive by reverse-migrating to
    `0026_batch5a_audit_snapshot` and re-applying cleanly.
  - `pos/management/commands/seed_inventory_costs.py` (new) — mirrors the
    `seed_product_units`/`provision_default_payment_routing` pattern
    exactly: `--dry-run` (default)/`--apply`, `--tenant` scoping, backfills
    `InventoryCost` from each product's current `Product.cost` as the
    opening value. No `InventoryCostMovement` row written by the seed — an
    opening value is not a "movement" (same convention D-17 uses for
    FinancialAccount/Customer/Supplier opening balances). Idempotent
    (`get_or_create` keyed on `product`), never overwrites an existing row.
  - `pos/test_costing.py` (new) — 10 tests: model creation, the
    `OneToOneField` uniqueness constraint (`IntegrityError` on a second row
    for the same product), 4dp precision round-trip, movement ordering
    (newest first), nullable qty/unit-cost fields for a future
    non-purchase movement (Batch 3's manual adjustment), and 5 tests for
    the seed command (dry-run doesn't write, apply creates from
    `Product.cost`, apply is idempotent, apply never overwrites an
    existing row, tenant scoping).
- **Migration number:** `0027_inventory_cost` (additive only).
- **API changes:** none — no serializer/view/url touched this batch.
- **Tests executed:** `pos.test_costing` (10/10 green) + full suite
  (584/584 green — 574 baseline + 10 new). `manage.py check` clean,
  `makemigrations --check` clean before and after.
- **Not touched this batch:** `purchase_invoices.py`, `serializers.py`,
  `views.py`, `urls.py`, frontend — confirmed via `git status` showing only
  `pos/models.py` (modified) plus the three new files above.
- **Risks:** none identified — the new tables are empty until the seed
  command runs, and nothing reads or writes them outside the seed command
  and the new tests.
- **Next:** Batch 2 — extract `moving_average_cost()` into
  `pos/services/costing.py` and wire `post_purchase_invoice()` to write
  through `InventoryCost` instead of inlining the math.

### Batch 2 — `pos/services/costing.py` (AVCO engine) + purchase-posting wiring

**Scope executed:** extracted the moving-average formula out of
`purchase_invoices.py` into a dedicated service, matching the AVCO rule set
the Business Owner confirmed against SAP/Oracle/Odoo/Cleverence practice
(2026-07-16 planning session, before any code was written): the average
updates on exactly two events — a purchase receipt and a positive inventory
count — everything else (sale, sale return, purchase return, shrinkage
adjustment, transfer, recipe consumption) consumes the current average via
a read-only accessor without changing it. **Deliberately NOT executed:**
wiring `update_cost_from_adjustment` into the actual stock-adjustment
endpoint (owner's explicit call — the function exists in `costing.py` now,
the endpoint wiring is Batch 3, alongside the manual cost-override flow it
sits next to).

- **Changed files:**
  - `superpos_backend/pos/services/costing.py` — **new**: `CostingError`;
    `quantize_cost` (4dp HALF_UP, D-13) / `quantize_money` (2dp HALF_UP,
    D-12); `moving_average_cost` (pure function, extracted verbatim from
    `purchase_invoices.py`, now quantized to 4dp instead of 2dp);
    `get_or_create_inventory_cost` (defensive lazy fetch for a product that
    predates the Batch 1 seed); `initialize_inventory_cost` (opening-value
    seed at product-create time, no movement row); `apply_purchase_receipt`
    (`@transaction.atomic`, locks `Product`+`InventoryCost`, blends via
    `moving_average_cost`, syncs the `Product.cost` mirror, writes one
    `InventoryCostMovement`); `update_cost_from_adjustment` (same blend
    math, `source_document_type='stock_adjustment'`, rejects `qty <= 0` —
    a shrinkage adjustment has no cost to blend in and must never call
    this function); `get_cost_for_sale` / `get_cost_for_return` (read-only,
    identical implementation today — kept as two names because a future
    purchase-return should read the *original* purchase line's cost
    snapshot rather than the live average, while a sale return reads the
    live average like a sale does; neither return document exists yet, so
    this is a placeholder read accessor per the owner's "design
    accommodates future consumers" instruction, not built-ahead logic).
  - `superpos_backend/pos/services/purchase_invoices.py` — removed the
    inline `moving_average_cost()` definition (now
    `moving_average_cost = costing_svc.moving_average_cost`, a thin
    backward-compat re-export — confirmed no external caller imported the
    old inline function directly) and the inline
    `select_for_update()`/`.update(cost=...)` block; `post_purchase_invoice`
    now calls `costing_svc.apply_purchase_receipt(...)` per stock line,
    immediately followed by `stock.record_stock_in(...)` in the same
    transaction (Postgres allows re-acquiring a row lock already held in
    the same transaction, so the "cost computed on pre-increase stock, then
    stock increases" ordering guarantee from the original inline code is
    unchanged). Module docstring corrected — no longer claims `Product.cost`
    is the moving-average field's sole home.
  - `superpos_backend/pos/test_costing.py` — +14 tests:
    `MovingAverageCostFunctionTests` (the Business Owner's exact worked
    example 10kg@500→10kg@600→550; the pre-extraction single-purchase
    assertion ported at 4dp; a 3-purchase sequential-compounding chain —
    closing a real coverage gap, no prior test verified a second purchase
    blending into an already-updated average; negative-stock/zero-
    denominator fallback regression; a small-quantity high-precision case
    validating D-13's stated 4dp rationale) and `CostingServiceTests`
    (`apply_purchase_receipt` updates `InventoryCost` + syncs the
    `Product.cost` mirror + writes a movement row; confirms it does NOT
    touch `Product.stock` itself — that stays `record_stock_in`'s job;
    `update_cost_from_adjustment` blends correctly and rejects `qty <= 0`;
    `get_cost_for_sale`/`get_cost_for_return` never write a movement row;
    the defensive lazy-fetch path for a product with no `InventoryCost` row
    yet).
  - `superpos_backend/pos/tests.py` — +1 integration test:
    `test_sequential_purchases_compound_correctly_via_costing_service` on
    `PurchaseInvoicePostingTests` — the owner's worked example exercised
    end-to-end through the real `POST /api/purchase-invoices/` API (not
    just the pure function), asserting `Product.stock`/`Product.cost`,
    `InventoryCost.avg_unit_cost`, and both `InventoryCostMovement` rows
    (correct `source_document_id` linkage to each invoice) all match.
- **Migration number:** none — pure service-layer refactor, `InventoryCost`/
  `InventoryCostMovement` already exist from Batch 1.
  `makemigrations --check` clean before and after.
- **API changes:** none — no serializer/view/url touched; every purchase-
  invoice request/response shape is byte-identical to before this batch.
- **Tests executed:** `pos.test_costing` + `pos.tests.PurchaseInvoicePostingTests`
  (36/36 green) + full suite (598/598 green — 584 baseline + 14 new).
  `manage.py check` clean. All 12 pre-existing purchase-posting tests pass
  **with unchanged assertion values**, including
  `test_cash_purchase_increases_stock_updates_cost_decreases_cashbox`'s
  literal `Decimal('7.00')` and the atomic-rollback test (confirming the
  nested `@transaction.atomic` in `apply_purchase_receipt` correctly rolls
  back via Django's savepoint mechanism when the outer transaction fails).
- **Live verification (beyond the automated suite):** posted two real
  purchases through `post_purchase_invoice` against the dev DB's existing
  seeded "Apple 1kg" product (pre-existing stock=50/cost=9.00, not a fresh
  fixture) — 10 @ 12.00 → 9.50, then 10 @ 16.00 → 10.4286 (`InventoryCost`)
  / 10.43 (`Product.cost` mirror), matching the hand-computed weighted
  average exactly; `InventoryCostMovement` audit trail correctly linked
  both entries to their respective purchase-invoice IDs.
- **Risks:** none identified — `update_cost_from_adjustment` is fully
  implemented and tested but has zero callers today (Batch 3's job to
  wire it up), so it carries no behavior-change risk in this batch.
- **Not touched this batch:** `serializers.py`, `views.py`, `urls.py`,
  the stock-adjustment endpoint, frontend, GL, recipes.
- **Next:** Batch 3 — wire `update_cost_from_adjustment` into the stock
  adjustment endpoint, add the manual cost-override flow (`cost` becomes
  read-only on `PATCH /products/{id}/` for an existing product, a new
  audited `POST /products/{id}/cost-adjustment/` endpoint takes its place,
  CSV-import cost changes route through the same audited path), close the
  three previously-uncoordinated `Product.cost` write paths down to one.

### Batch 3 — close the three uncoordinated `Product.cost` write paths

Branch: `s3/batch-3-manual-cost-adjustment` (off `s3/batch-2-costing-service`).

**Design note — deviates from the Batch 2 "Next" preview above.** That
preview envisioned a dedicated new `POST /products/{id}/cost-adjustment/`
endpoint taking an arbitrary `new_cost` + `reason`. Implementing that would
have reintroduced exactly the thing Batch 2's confirmed golden rule
forbids: an arbitrary cost override with no quantity basis is not one of
the two events allowed to move the average (purchase receipt, positive
inventory count). So Batch 3 does **not** add a third write path — it
routes the "manual cost adjustment" through the *existing*
`POST /inventory/adjust/` (`stock_adjustment`) endpoint instead, which
already models a physical count. No new URL was added.

- **Files changed:**
  - `superpos_backend/pos/serializers.py`:
    - `StockAdjustmentSerializer` — added optional `unit_cost`
      (`Decimal(14,4)`, `min_value=0.0001`). Only meaningful when the count
      is an *increase* (`actual_qty > previous stock`); documented in the
      class docstring as the second AVCO-updating event.
    - `ProductSerializer.update()` — raises `ValidationError` if `'cost' in
      validated_data`, pointing the caller at a purchase invoice or the
      adjustment endpoint. `ProductSerializer.create()` now calls
      `costing.initialize_inventory_cost(product=product,
      opening_cost=product.cost)` after `super().create()` — CREATE keeps
      `cost` freely editable as the opening value (unchanged behavior);
      only UPDATE is locked.
  - `superpos_backend/pos/views.py`:
    - Added a top-level `costing` import alongside `barcode_resolution`/
      `idempotency`.
    - `stock_adjustment` — now wrapped in `transaction.atomic()`. When
      `diff > 0` (a positive count) **and** `unit_cost` was given, calls
      `costing.update_cost_from_adjustment(product=product, qty=diff,
      adjustment_cost=unit_cost, source_document_type='stock_adjustment',
      actor_user=request.user, note=reason)` — computed *before*
      `Product.stock` is overwritten, so the blend correctly uses the
      pre-count stock (same ordering discipline `apply_purchase_receipt`
      already established in Batch 2). Shrinkage, an unchanged count, or a
      positive count with no `unit_cost` given never touch the average —
      they consume it as-is, per the golden rule. Response gained a
      `unit_cost` echo field (`null` when not applicable).
    - `_import_row` (CSV import) — the **update** branch no longer writes
      `existing.cost` directly. It computes `stock_diff = stock -
      existing.stock`; if positive, calls
      `costing.update_cost_from_adjustment(product=existing,
      qty=Decimal(stock_diff), adjustment_cost=cost,
      source_document_type='csv_import', note='CSV import upsert')` before
      saving the new `stock` value — the row's `cost` column is honored
      only when it comes with a stock increase (a purchase-shaped event);
      an update row that doesn't raise stock has no quantity basis to
      blend against, so its `cost` column is now silently ignored instead
      of overwriting the AVCO-derived average (a deliberate behavior
      change, consistent with the golden rule — flagged here since no
      test previously covered this path either way). The **create** branch
      now calls `costing.initialize_inventory_cost(product=new_product,
      opening_cost=cost)` after `Product.objects.create(...)` (it bypasses
      `ProductSerializer.create()` entirely, so needed its own call).
  - `superpos_backend/pos/services/costing.py` — docstrings updated (module
    header + `update_cost_from_adjustment`) to record the two call sites
    now wired up; no logic change.
  - `superpos_backend/pos/test_costing.py` — +10 tests:
    `ProductCostLockdownApiTests` (PATCH `cost` on an existing product →
    400 with the field unchanged; PATCH of other fields still succeeds;
    POST create with `cost` → `InventoryCost` initialized, zero movement
    rows), `StockAdjustmentCostApiTests` (positive count + `unit_cost` →
    blends exactly like Batch 2's `update_cost_from_adjustment` unit test,
    now through the real endpoint; positive count without `unit_cost` →
    average untouched, zero movement rows; shrinkage ignores `unit_cost`
    even if sent; non-Manager caller → 403), `CsvImportCostRoutingApiTests`
    (update row raising stock → cost blends, one `csv_import` movement row;
    update row not raising stock → `cost` column ignored, average
    unchanged; create row → `InventoryCost` initialized, zero movement
    rows — all three assert `resp.json()['errors'] == []` so a swallowed
    per-row exception can't masquerade as a pass).
- **Migration number:** none — pure serializer/view wiring, no model
  change. `makemigrations --check` clean before and after.
- **API changes:** `StockAdjustmentSerializer` gained one optional field
  (`unit_cost`) and the response gained one echo field (`unit_cost`) — both
  additive, existing callers unaffected. `PATCH`/`PUT /products/{id}/` now
  rejects a `cost` key with 400 for an **existing** product only — `POST
  /products/` (create) is unaffected. No new URL route.
- **Tests executed:** `pos.test_costing` (33/33 green) + full suite
  (608/608 green — 598 baseline + 10 new). `manage.py check` and
  `makemigrations --check` both clean.
- **Pre-existing coverage gap noted, not regressed:** neither
  `stock_adjustment` nor `products_import` had *any* test before this
  batch (confirmed via repo-wide grep) — every assertion in the three new
  test classes above is net-new coverage, not a preserved regression
  check, since there was nothing to preserve.
- **Risks:** the CSV-import behavior change (cost column ignored on a
  same/decreased-stock update row) is a real, deliberate behavior change
  from the pre-Batch-3 CSV import, which always overwrote `cost`
  unconditionally. No CSV import documentation/UI currently advertises a
  "correct cost without changing stock" workflow, and no test existed for
  the old behavior either, so this is assessed as low-risk — flagged here
  for visibility rather than silently changed.
- **Not touched this batch:** any model/migration, `PurchaseInvoiceLine`
  costing (Batch 2's territory, unchanged), COGS/GL/dashboard reporting
  (Batch 4's job), frontend.
- **Next:** Batch 4 — COGS / gross profit / margin reporting, wiring the
  now-fully-audited `Product.cost`/`InventoryCost.avg_unit_cost` into
  `dashboard_summary` and a new per-product cost-movement read endpoint.

### Batch 4 — COGS / Gross Profit / Margin / Dashboard / Reports (backend-only)

Branch: `s3/batch-4-cogs-reporting` (off `s3/batch-3-manual-cost-adjustment`).
Backend-only, matching every prior Sprint 3 batch — frontend surfacing of
these new fields is deferred to Batch 6.

Consumes `SaleItem.unit_cost` (written on every sale since Batch 5a, read
by nothing in production code until now) for read/reporting-only COGS and
gross-profit figures. Zero GL posting: `FinancialAccountMovement
.MovementType` gains no new value, enforced by a dedicated negative-
assertion test suite, not just a comment.

**Formulas used (verified against the live models, not GL-derived):**
- `net_revenue = Sale.total − Sale.tax_amount`. `Sale` has no stored
  `discount_amount` field — only `subtotal`/`tax_amount`/`total`
  (`total = subtotal + tax_amount − discount_amount`) — so this
  algebraically recovers `subtotal − discount_amount` (tax-exclusive,
  discount-inclusive revenue) without a new field. Matches
  `TARGET_BOUNDARIES.md`'s "net revenue" convention (menu price net of
  VAT; glossary `:436-439`).
- `cogs = Σ(SaleItem.unit_cost × SaleItem.qty)` over the window's
  `SaleItem` rows (both already base-unit-denominated regardless of which
  unit a line was sold in — no `ProductUnit` join needed; no Recipe model
  exists yet, so a directly-sold product's own cost snapshot *is* its
  "recipe COGS").
- `gross_profit = net_revenue − cogs`. `gross_margin_pct = gross_profit ÷
  net_revenue × 100` (0 when `net_revenue <= 0`).
- Per-`top_products[i]` row: denominated against `line_total` (confirmed
  pre-tax at `pos/serializers.py:1476`, same tax basis as `net_revenue`).
  Known, pre-existing limitation carried forward unchanged: invoice-level
  discount isn't allocated back across individual lines — already true of
  `top_products.revenue` before this batch, not introduced by it.
- **R-L naming discipline:** `cogs` / `gross_profit` / `gross_margin_pct` /
  `net_revenue` only — never `net_profit`/`profit` (reserved for a future
  GL-level figure after operating expenses).

- **Files changed:**
  - `superpos_backend/pos/views.py`:
    - `dashboard_summary` — merged `tax_total=Sum('tax_amount')` into the
      existing top-level `agg` aggregate (zero extra queries); hoisted
      `window_items` above the `items_sold` computation and merged a COGS
      `Sum(ExpressionWrapper(F('unit_cost')*F('qty'), ...))` into that same
      call via a `_cogs_sum()` helper (a **fresh** expression per call —
      reusing one `ExpressionWrapper` instance across two aggregate calls,
      or naming an aggregate output alias `qty` in the same call as an
      expression that references the `qty` field, both raise a spurious
      `FieldError: 'qty' is an aggregate`; hit both while implementing,
      fixed by a factory function and renaming the alias to `total_qty`).
      Added four additive `kpis` keys (`net_revenue`, `cogs`,
      `gross_profit`, `gross_margin_pct`) — **`kpis['revenue']` is
      completely unchanged** (still `Sum('total')`, tax-inclusive; a
      regression test asserts this explicitly so it's never confused with
      the new `net_revenue`). `top_products` gained `cogs`/`gross_profit`/
      `gross_margin_pct` per row from the same `window_items` queryset
      (still one query family, no N+1).
    - New `ProductCostMovementListView(TenantMixin, generics.ListAPIView)`
      — mirrors `ProductWarehouseStockView` (a plain tenant+product-scoped
      `ListAPIView`), **not** `ProductStockMovementListView` (a much
      heavier hand-rolled statement-summary `APIView` — overkill for a
      pure audit-ledger read). Relies on `InventoryCostMovement.Meta
      .ordering` for newest-first; global `StandardPageNumberPagination`
      applies automatically. Returns an empty list (not 404) for a
      cross-tenant or nonexistent product id, matching that same
      precedent.
  - `superpos_backend/pos/serializers.py`:
    - New `InventoryCostMovementSerializer` (`read_only_fields = fields`
      — every row is written exclusively by `pos.services.costing`).
    - `SaleItemSerializer` gained `line_cogs`
      (`SerializerMethodField`, `quantize_money(unit_cost * qty)`,
      returned as a string to match `unit_cost`/`price_each`'s DRF
      `DecimalField` string-serialization convention). Inherently
      read-only — not listed in `read_only_fields` (DRF raises an
      `AssertionError` if a non-model field is listed there).
  - `superpos_backend/pos/urls.py` — one new route:
    `products/<int:pk>/cost-movements/` → `product-cost-movements`.
  - `superpos_backend/pos/test_costing.py` — +16 tests:
    `DashboardCogsGrossProfitTests` (hand-computed `kpis` correctness
    against the owner-style worked example; `kpis['revenue']` unchanged
    regression guard; zero-sales-in-window → all-zeros not a crash;
    per-product `top_products` cost fields; a `line_total == 0` edge case
    guarding the divide-by-zero fallback; a voided sale excluded from both
    `cogs` and `top_products`), `ProductCostMovementsApiTests` (tenant
    isolation → empty list not leaked data; newest-first ordering;
    pagination beyond `PAGE_SIZE=20`; write verbs → 405; Cashier → 403),
    `SaleItemLineCogsApiTests` (correct value on read; `unit_cost=0`
    legacy row → `'0.00'`, no crash), `Batch4NoGlPostingTests` (zero new
    `FinancialAccountMovement` rows from `dashboard_summary`, the new
    cost-movements endpoint, and a `SaleItemSerializer` read; a static
    assertion that `MovementType.values` grew no COGS-shaped member).
- **Migration number:** none — reuses `InventoryCostMovement` (Batch 1),
  `SaleItem.unit_cost`/`qty` (Batch 5a), `Sale.total`/`tax_amount`
  (pre-existing). `makemigrations --check` clean before and after.
- **API changes (additive only):** `GET /api/dashboard/summary/` gains
  `kpis.net_revenue`/`cogs`/`gross_profit`/`gross_margin_pct` +
  per-`top_products[i]` `cogs`/`gross_profit`/`gross_margin_pct`; new
  `GET /api/products/{pk}/cost-movements/` (Manager+, paginated,
  tenant-scoped); `SaleItemSerializer` (used by `GET /api/sales/` and
  `/api/sales/{id}/`) gains read-only `line_cogs`. No existing key removed
  or renamed.
- **Tests executed:** `pos.test_costing` (49/49 green) + full suite
  (624/624 green — 608 baseline + 16 new). `manage.py check` and
  `makemigrations --check` both clean.
- **Risks:** the `top_products[i].gross_margin_pct` discount-allocation
  caveat above (documented, pre-existing, not new). No other risk
  identified — this batch touches zero existing write paths.
- **Not touched this batch:** any model/migration, `accounts/models.py`,
  any GL-adjacent code, `SaleSerializer.create()`'s stock-deduction flow,
  frontend.
- **Next:** Batch 5 — backend regression + documentation checkpoint, then
  Batch 6 — frontend surfacing of everything Sprint 3 shipped.

### Batch 5 — regression + documentation checkpoint

Branch: `s3/batch-5-regression-checkpoint` (off `s3/batch-4-cogs-reporting`).
Mirrors the mandatory checkpoint Sprint 2 used between its backend batches
and its frontend batch. Preceded by a full read-only architecture review
("Pre-Batch-5 Architecture Review", plan file, benchmarked against SAP B1/
Business Central/NetSuite/Odoo/ERPNext/Lightspeed/KORONA/Toast) — its
findings and this checkpoint's actions are summarized here.

**The review surfaced one live, P0 regression, fixed separately and first:**
`superpos/src/components/products/ProductFormModal.tsx`'s `buildPayload()`
unconditionally sent `cost` in every edit-save `PATCH`. Batch 3 made `cost`
reject any write on `PATCH /products/{id}/` for an *existing* product — so
every "Edit Product" save in the deployed app had been 400ing since Batch 3
landed, even when only an unrelated field (e.g. name) changed, and nothing
in the automated suite caught it because there is no frontend-integration
test exercising the real deployed payload shape. Fixed on its own branch,
`s3/hotfix-product-cost-edit-lockdown` (commit `1d057e2`): `buildPayload()`
now omits `cost` when editing (still sends it on create, as the opening
cost); the Cost input is disabled during edit so the omission is visible,
not a silent drop. **Verified with a real end-to-end click-through** (not
just a unit test) — logged in as the seeded Owner user, opened the products
admin UI in a real Chromium instance, edited a product's name via the row
action menu, confirmed the `PATCH` returned `200` (not `400`), the name
change persisted, and `cost` stayed at its prior value in the response.
This fix should land (or be cherry-picked) before/alongside this checkpoint
— the acceptance gate below could not have honestly passed without it.

**Checklist (per the Sprint 3 plan's Batch 5 section):**
- **Full backend test suite green:** 625/625 (624 baseline through Batch 4
  + 1 new regression test this batch, see below). `manage.py check` clean.
  `manage.py makemigrations --check --dry-run` clean.
- **Manual migration review:** Sprint 3 added exactly one migration —
  `pos/migrations/0027_inventory_cost.py` (Batch 1) — confirmed by
  inspection to contain only two `CreateModel` operations (`InventoryCost`,
  `InventoryCostMovement`). Zero `AlterField`/`RemoveField`/`RunPython` on
  any pre-existing table. Batches 2-4 added no migrations at all (verified
  clean at each batch's own checkpoint already).
- **`Product.cost` / `SaleItem.unit_cost` / `Product.margin` wire-shape
  compatibility for callers that haven't opted into the new endpoints:**
  read shapes are unchanged everywhere (Batch 4 only *added* fields —
  `line_cogs`, new `kpis` keys — never removed or renamed one). The one
  **write**-side compatibility break (`Product.cost` on `PATCH`, Batch 3)
  is the P0 finding above — grepped every frontend call site that PATCHes
  `/products/{id}/` (`ProductFormModal.tsx`, `ScalePage.tsx` ×2, plus
  `api/erp.ts`'s `productUnitsApi.update` which targets a different
  sub-resource) and confirmed `ProductFormModal.tsx` was the *only* one
  sending `cost`, now fixed. With that fix in place, this gate holds.
- **Explicit scope check** (grep, this session): zero matches for `COGS`
  anywhere in `accounts/models.py` or the rest of the `accounts` app; zero
  `Recipe`/`BOM`/`ProductionOrder` model anywhere in `pos/models.py` or
  `accounts/models.py`. Confirms Batch 4 stayed inside its stated
  read/reporting-only boundary.
- **New regression test** (closing a real gap the architecture review
  named): `CostingServiceTests.test_multi_step_negative_stock_recovery` in
  `pos/test_costing.py` — the existing negative-stock test only proved the
  single-step fallback formula; this walks oversell → purchase (still
  net-negative, fallback fires) → oversell again → a bigger purchase that
  pulls stock back positive (a **real** weighted blend netting a negative
  pre-purchase stock against a positive purchase quantity, not the
  fallback) → confirms the average lands on the mathematically correct
  value (`225.0000`, hand-verified) at the end, not an intermediate
  fallback value, with the audit trail correctly recording both steps.
- **Backlog items identified, deliberately not actioned this batch** (per
  the review's own recommendation — low-urgency, no reason to bundle into
  a regression checkpoint): a composite `(tenant, product, -occurred_at)`
  index for `InventoryCostMovement` (currently relies on Django's
  automatic single-column FK indexes only); the pre-existing
  `payment_methods` N-queries-in-a-loop pattern in `dashboard_summary`
  (predates Sprint 3, untouched by Batch 4). Neither is urgent at current
  data volume.
- **Explicitly not attempted, per the review's recommendation:** Purchase
  Returns, Sales Returns, a pure cost-correction/revaluation tool, Recipe/
  BOM, GL wiring — every one stays correctly gated behind its own future
  decision, forcing any into this checkpoint would repeat exactly the
  scope creep this project's governance has consistently avoided.
- **Tests executed:** full suite 625/625 green. `manage.py check` and
  `makemigrations --check` both clean.
- **Not touched this batch:** any model/migration (checkpoint-only, plus
  one new test), `accounts/models.py`, any GL-adjacent code.
- **Next:** Batch 6 — frontend surfacing of Sprint 3's cost/margin/COGS
  data (the P0 hotfix already covers the one urgent frontend compatibility
  fix; Batch 6 is the deliberate, designed frontend work — new dashboard
  tiles, a cost-history drawer, `PurchaseDetailPage` before/after cost
  display — not a second hotfix pass).

---

## Sprint 3 Hotfix Pack — post-review stabilization (no new features)

**Branch:** `s3/hotfix-pack` (off `s3/batch-5-regression-checkpoint`).
**Scope discipline:** this pack fixes only the 5 verified blocking issues
named by the business owner's own architecture/adversarial review — no
Recipe/BOM, no FIFO, no GL postings, no Purchase/Sales Return costing, no
inventory revaluation, no public-API redesign beyond what each bug fix
required. Every hotfix below was **verified against the real, current code
first** — not assumed from the review's problem description — which
surfaced that one "bug" (Hotfix 1) was already fixed on a separate branch
and needed a cherry-pick, not a re-implementation, and that another
(Hotfix 3) had a deeper root cause than its description implied.

### Hotfix 1 — Product Edit Regression (already fixed, cherry-picked)

**Verification finding:** this exact regression — `ProductFormModal`
unconditionally sending `cost` on every edit-save `PATCH`, 400ing against
Batch 3's cost-immutability rule — was already diagnosed and fixed on
`s3/hotfix-product-cost-edit-lockdown` (commit `1d057e2`, documented under
Sprint 3 Batch 5 above). Cherry-picked cleanly onto `s3/hotfix-pack`
instead of re-implementing. No new code, no new tests needed — the
existing fix (`buildPayload()` omits `cost` on edit; the Cost input is
disabled during edit) already stands on its own commit.

### Hotfix 2 — Stock Adjustment Race Condition

**Problem confirmed:** `stock_adjustment` (`POST /inventory/adjust/`) read
`Product.stock` *before* acquiring any row lock, then computed
`diff = actual_qty - previous_stock` and wrote the new stock and a
`StockMovement` row from that stale read — a classic lost-update race
under concurrent adjustments on the same product.

**Fix — `pos/views.py`, `stock_adjustment`:** fully rewritten to a single
`transaction.atomic()` block that (1) `Product.objects.select_for_update()`
locks the row first, (2) reads `previous_stock` only *after* the lock is
held, (3) computes `diff` from that locked read, (4) applies the cost
blend via `costing.update_cost_from_adjustment()` for positive diffs with
an explicit `unit_cost`, (5) updates `Product.stock`, (6) writes exactly
one `StockMovement` row (`quantity_before`/`quantity_after` populated,
matching the "hardened ledger" convention `record_stock_in`/
`record_stock_out` already use elsewhere) — all inside the one atomic
transaction, so `InventoryCostMovement`'s quantity always matches the
locked `diff`, never a stale one.

**Tests added** (`pos/test_hotfix_pack.py::StockAdjustmentConcurrencyTests`):
a real two-thread concurrency test using `TransactionTestCase` (the only
Django test base that runs against the real DB without wrapping the test
in a rolled-back transaction, required to exercise genuine cross-thread
row locking) — two real HTTP requests fired from two threads against the
same product, asserting the two resulting `StockMovement` rows form an
unbroken `quantity_before`→`quantity_after` chain regardless of which
thread's lock wins, and that final `Product.stock` matches the
last-applied movement's `quantity_after`. Verified stable across 3
consecutive runs (not just a single lucky pass).

### Hotfix 3 — Adjustment Direction Bug

**Verification finding — deeper than the review's own description:** two
*incompatible* pre-existing conventions were both writing `ADJUSTMENT`
rows. Path (a), the `stock_adjustment` view, wrote `qty=diff` directly via
a raw `.create()`, preserving the sign. Path (b), the generic
`StockMovementSerializer.create()` → `record_stock_in`/`record_stock_out`
dispatch (used by direct `POST /api/stock-movements/`), always stored
`qty` as a positive *magnitude* (`_coerce_qty` requires `qty > 0`),
**losing the sign entirely**. This meant direction could not be recovered
at read time by inspecting `qty`'s sign for path-(b)-created historical
rows — a read-side "fix" based on sign inspection would have been silently
wrong for half of the system's adjustment-creation paths. This confirmed
the review's own preferred solution (explicit `ADJUSTMENT_IN`/
`ADJUSTMENT_OUT` values) was correct, not just one option among several.

**Fix:**
- `pos/models.py` — `StockMovement.MovementType` gained two new values,
  `ADJUSTMENT_IN`/`ADJUSTMENT_OUT`, alongside the existing `ADJUSTMENT`
  (kept, relabeled "Adjustment (legacy)", for historical rows already in
  the DB — never backfilled, per the "no risky data migrations" rule).
  New additive-only migration `pos/migrations/0028_alter_stockmovement_movement_type.py`
  (a single `AlterField` on the choices list — confirmed no DB-level CHECK
  constraint exists on this plain `CharField`, so this is pure Python
  metadata with zero schema/data risk).
- `pos/services/stock_movements.py` + `pos/serializers.py` — `_IN_TYPES`/
  `_OUT_TYPES` sets (both copies) extended with the two new values.
  `StockMovementSerializer.create()`'s routing block now translates a
  client-sent legacy `ADJUSTMENT` + a signed `qty` into the correct
  explicit direction before dispatch (`signed_qty < 0` → `record_stock_out`
  with `movement_type=ADJUSTMENT_OUT`; else `record_stock_in` with
  `ADJUSTMENT_IN`) — so path (b) now also produces unambiguous rows going
  forward.
- `pos/views.py` — the rewritten `stock_adjustment` (Hotfix 2) writes
  `ADJUSTMENT_IN` for `diff >= 0`, `ADJUSTMENT_OUT` otherwise, directly
  (no legacy value ever written by this path anymore).

**Tests added/fixed:**
- `pos/test_hotfix_pack.py::StockAdjustmentDirectionApiTests` — 3 tests:
  positive adjustment → `ADJUSTMENT_IN` with correct `quantity_in`/
  `quantity_out`; negative → `ADJUSTMENT_OUT`; a statement-summary
  reconciliation check across both directions in sequence.
- `pos/test_stock_direct_post.py::test_post_adjustment_positive_qty_increases_stock`
  — this test had previously *asserted the bug as correct behavior*
  (a positive adjustment mis-storing as an outflow); updated to assert the
  fix (`movement_type == ADJUSTMENT_IN`, correct `quantity_in`/`_out`).
- Balance-reconciliation assertions use
  `get_product_stock_statement_summary(product)['closing_quantity']`, not
  `get_product_stock_balance()` — the latter is a pure ledger-only sum that
  does not account for a product's un-ledgered opening `stock` value (a
  real trap for fixtures created with `Product.objects.create(stock=...)`
  directly); the former correctly anchors off `Product.stock` when no
  prior ledger row exists, so it's the correct tool for these assertions.

### Hotfix 4 — Purchase Discount AVCO

**Problem confirmed:** `purchase_invoices.py`'s moving-average computation
used the gross `line_subtotal` (qty × unit_cost) as the acquisition value
fed into `moving_average_cost()`, while the same line's accounting/AP
effect already correctly netted out `discount_amount`. Inventory
valuation and the supplier liability were being computed from two
different economic values for the same purchase.

**Fix — `pos/services/purchase_invoices.py`:** the moving-average
computation was restructured so both the unit-aware and legacy line
branches feed into one shared calculation:
`net_line_value = line_subtotal - discount`, then
`moving_avg_unit_cost = net_line_value / qty` (quantized). Tax is
deliberately **not** netted out — confirmed by reading the model layer
that this system has no VAT-recovery ledger account, so tax was never
part of the cost basis before this fix and the owner's own policy
("if taxes are non-recoverable, preserve existing behavior") means it
stays that way; only the discount term is new.

**Test added** (`pos/tests.py::PurchaseInvoicePostingTests::test_purchase_discount_nets_out_of_moving_average_cost`)
— exactly the pack's own worked example: 1000 gross, 100 supplier
discount, 10 units → asserts blended cost is `90.00`/unit (not
`100.00`), `InventoryCost.avg_unit_cost == 90.0000`, inventory value
added (`stock × cost`) reconciles exactly with the supplier AP balance
actually posted (`900.00` both sides).

**Regression check:** existing discount=0 tests are mathematically
unaffected (`net_line_value == line_subtotal` when `discount == 0`),
confirmed by the full suite staying green.

### Hotfix 5 — Mandatory Idempotency

**Problem confirmed:** `POST /api/purchase-invoices/` accepted an optional
`Idempotency-Key` header — a retried request with no key, or a dropped-then-
retried request, could duplicate the posted stock, AP, and cash/bank
effects. The `idempotency.lookup()`/`.save()` service functions already
existed and were already correct (their own docstring is explicit that a
missing key is the *caller's* responsibility to reject, not the service's),
they just weren't being enforced at the view layer for this endpoint.

**Fix — `pos/views.py`, `PurchaseInvoiceListCreateView.create()`:** now
requires a non-blank `Idempotency-Key` header (400
`IDEMPOTENCY_KEY_REQUIRED` if missing), replays the original response on a
key reuse with an identical payload (`idempotency.lookup()`), returns 409
`IDEMPOTENCY_CONFLICT` on a key reused with a *different* payload, and
additionally rejects (409 `SUPPLIER_REFERENCE_DUPLICATE`) a fresh request
whose `(tenant, supplier, reference)` triple already exists — the
"business uniqueness" requirement, guarding the case where a client
retries with a *new* idempotency key but the same real-world supplier
invoice number.

**Tests added** (`pos/test_hotfix_pack.py::PurchaseInvoiceIdempotencyRequiredApiTests`,
7 tests): missing key rejected, blank key rejected, an exact retry
produces zero duplicate `PurchaseInvoice`/`StockMovement`/
`InventoryCostMovement`/AP-balance effects and returns the original
response, a different key legitimately creates a second invoice, same key
with a different payload → 409 conflict, a duplicate supplier reference is
rejected even with a fresh idempotency key, a blank reference never
triggers the uniqueness guard, and the same reference under two different
suppliers is allowed.

**Fallout — every existing test that POSTs to `purchase-invoice-list` now
needs a real key:** systematically fixed ~20 call sites across
`pos/tests.py`, `pos/test_pos_integration.py`, each given a genuinely
unique key (not a shared/repeated one, which would trigger unintended
replay instead of the intended fresh create). Kept keys even on tests
expecting a 400 for an *unrelated* validation reason (e.g. non-stock line
type, over-paid amount, zero/negative qty, cross-tenant refs) — those
would have "accidentally" still passed with a 400 from the new
`IDEMPOTENCY_KEY_REQUIRED` check for the wrong reason, silently no longer
testing what they claim to test. One `ERROR` (not `FAIL`) was uncovered
this way: `PurchaseInvoiceReadScopingTests.setUp()` called
`resp.json()['id']` on what had become a 400 body, raising `KeyError` —
fixed by adding the header to `setUp()`'s own POST call.

### Test Coverage Summary

| Area | File | Count |
|---|---|---|
| Product edit (Hotfix 1, pre-existing fix, no new tests this pack) | — | — |
| Concurrent stock adjustment | `test_hotfix_pack.py::StockAdjustmentConcurrencyTests` | 1 |
| Adjustment direction (in/out) | `test_hotfix_pack.py::StockAdjustmentDirectionApiTests` + `test_stock_direct_post.py` fix | 4 |
| Product edit field coverage (name/barcode/price/category/units, cost untouched) | `test_hotfix_pack.py::ProductEditFieldCoverageApiTests` | 5 |
| Purchase discount AVCO | `tests.py::PurchaseInvoicePostingTests` | 1 |
| Idempotent purchase retries + business-uniqueness | `test_hotfix_pack.py::PurchaseInvoiceIdempotencyRequiredApiTests` | 7 |
| **New tests, this pack** | `pos/test_hotfix_pack.py` (new file) + 1 in `tests.py` | **18** |

### Before / After Behavior

| Scenario | Before | After |
|---|---|---|
| Edit product name only | 400 (rejected `cost`) | 200, `cost` untouched |
| Two concurrent adjustments on same product | lost update possible (stale-read race) | serialized via row lock, unbroken quantity chain |
| Positive stock adjustment | stored ambiguously as `ADJUSTMENT`, misread as outflow by some readers | stored as `ADJUSTMENT_IN`, unambiguous everywhere |
| Negative stock adjustment | stored ambiguously as `ADJUSTMENT` | stored as `ADJUSTMENT_OUT`, unambiguous |
| Purchase with a supplier discount | moving-average cost computed from gross price | computed from `subtotal - discount` (tax still excluded, unchanged policy) |
| Retried purchase POST (network retry, double-click) | could duplicate stock/AP/cash effects | replays the original response, zero duplication |
| Two purchases with the same supplier reference | allowed (silent duplicate risk) | second one rejected with `SUPPLIER_REFERENCE_DUPLICATE` |

### Architectural Decisions Made

1. **Hotfix 3 solved via new enum values, not a read-side sign-inspection
   fix** — the only correct option once the two incompatible historical
   write conventions were discovered; matches the pack's own stated
   preferred solution.
2. **Legacy `ADJUSTMENT` value kept, not removed** — historical rows using
   it are never backfilled (no `RunPython` data migration), consistent
   with this project's established R-F discipline (additive-only
   migrations, no risky data mutation). `_IN_TYPES` still recognizes it so
   old rows continue to read correctly under the pre-existing (ambiguous
   for that value only) convention; only *new* rows get the unambiguous
   direction.
3. **Idempotency business-uniqueness scoped to `(tenant, supplier,
   reference)`, only enforced when `reference` is non-blank** — matches
   the pack's own instruction ("without breaking existing behavior");
   invoices with no supplier reference supplied are unaffected.
4. **Tax intentionally excluded from Hotfix 4's discount netting** — this
   system has no VAT-recovery ledger account, so including tax in the cost
   basis would misstate inventory value; explicitly preserved per the
   pack's own stated policy.

### Final Verification

- `python3 manage.py test` — **643/643 passed**, 0 failures, 0 errors
  (baseline 625 from the Sprint 3 Batch 5 checkpoint + 18 new tests this
  pack). All pre-existing tests remain green, including every test touched
  only to add an `Idempotency-Key` header (their original assertions are
  unchanged).
- `StockAdjustmentConcurrencyTests` (the one genuine multi-threaded test)
  re-run 3 additional times in isolation to confirm it isn't flaky — all 4
  runs (this run + 3 extra) passed.
- `python3 manage.py check` — clean (1 pre-existing silenced warning,
  unrelated to this pack).
- `python3 manage.py makemigrations --check --dry-run` — clean, no pending
  migrations. Exactly one new migration this pack
  (`0028_alter_stockmovement_movement_type.py`), confirmed additive-only
  (`AlterField` on choices metadata, no `RemoveField`, no `RunPython`, no
  DB-level constraint affected).
- No remaining HIGH severity issue from the review is open: all 5 named
  hotfixes are implemented and covered by regression tests; Hotfix 1 was
  confirmed already fixed rather than re-implemented.
- Confirmed out of scope, untouched: Recipe/BOM, FIFO, GL postings,
  Purchase/Sales Return costing, inventory revaluation — zero references
  to any of these added by this pack (grep-confirmed against the diff).

---

*(Later sprints get their own sections here after their pre-sprint audits.)*
