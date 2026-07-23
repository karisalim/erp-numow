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

### Batch 6 — Frontend: cost/margin/COGS visibility (Sprint 3 Costing UI)

**Scope discipline:** 100% frontend, zero backend files touched (verified
via `git diff --stat` scoped to `superpos_backend/` returning empty).
Preceded by a full pre-implementation analysis: three parallel research
passes (frontend current-state audit, backend contract verification,
governance/conventions audit) plus a design pass, spot-verified against
the real files before any code was written. Two design questions were put
to the business owner and resolved before implementation: Top-10 table
gets 2 new columns (Gross Profit + Margin %, not a 3rd COGS column); the
Cost History drawer uses full real server-side pagination (not a
first-page-only cap), matching how SAP B1/Odoo/Dynamics treat cost
history as a proper audit ledger.

**Files changed:**
- `superpos/src/types/erp.ts` — new `InventoryCostMovement` interface
  (mirrors `InventoryCostMovementSerializer` exactly). Moved
  `DashboardPage.tsx`'s page-local `KPIs`/`TopProduct`/etc. interfaces
  here as `DashboardKPIs`/`DashboardTopProduct`/`DashboardPaymentMethodSummary`/
  `DashboardLowStockEntry`/`DashboardSummaryResponse`, extended with
  `net_revenue, cogs, gross_profit, gross_margin_pct` (KPIs) and
  `cogs, gross_profit, gross_margin_pct` (top-product rows) — needed so
  the new typed API wrapper isn't forced to import from a page.
- `superpos/src/api/erp.ts` — new `inventoryCostApi.listMovements(productId, params?)`
  → `GET /products/<id>/cost-movements/`; new `dashboardApi.summary(params?)`
  → `GET /dashboard/summary/`, replacing `DashboardPage.tsx`'s previous
  inline `apiClient.get(...)` call (pure refactor, same behavior, brings
  Dashboard in line with every sibling page's typed-wrapper convention).
- `superpos/src/components/products/ProductCostHistoryDrawer.tsx` (new)
  — `Drawer` (`max-w-[920px]`, widened from an initial 760px after manual
  testing showed the 6-column table needed more room) + `DataTable<InventoryCostMovement>`
  + `useQuery`, real server-side pagination (20/page). Columns: Date,
  Source (`source_document_type` + `#id`), Qty received, Unit cost
  received, Avg cost before → after (colored delta — amber when cost
  rose, green when it fell), Note. Empty state explains cost only moves
  on purchase receipts or positive stock-count adjustments with a unit
  cost entered.
- `superpos/src/components/products/ProductActionsMenu.tsx` +
  `superpos/src/pages/ProductsPage.tsx` — new `'costHistory'` row action
  (grouped directly after "Stock movements"), `costHistoryProduct` state,
  drawer render — mirrors the existing `unitsProduct`/`ProductUnitsDrawer`
  wiring already in that file.
- `superpos/src/components/products/ProductFormModal.tsx` — the local
  `Field` component's `hint` prop widened from `string` to `React.ReactNode`;
  when the Cost field is disabled (edit/view mode), it now shows an inline
  hint explaining cost is AVCO-derived plus a "View cost history" button
  opening the same drawer, closing a real UX gap (the field was
  previously just silently greyed out with zero explanation). Zero
  payload/submit-logic change — the P0 hotfix already omits `cost` from
  edit PATCHes; this batch only adds presentation + one `useState`.
- `superpos/src/pages/purchases/PurchaseDetailPage.tsx` — after the
  invoice loads, fetches cost-movements (page 1 only — a targeted lookup,
  not a browse) for the distinct stock-item product ids on the invoice,
  filters client-side for `source_document_type === 'purchase_invoice' && source_document_id === invoice.id`.
  When a match exists, the `MovementEffectsCard`'s previously-hardcoded
  "quantities received and moving-average cost updated" sentence is
  replaced with the real per-product `avg_cost_before → avg_cost_after`
  numbers; when no match (still loading, error, or a genuinely old/buried
  movement beyond page 1), it falls back to the generic sentence — this
  falls out naturally from the `useMemo` derivation with no explicit
  error-handling code needed.
- `superpos/src/pages/DashboardPage.tsx` — two new KPI tiles added to the
  existing `statCards` array: **Gross profit** (`#8B5CF6`/`chart` icon)
  and **Gross margin** (`#EC4899`/`tag` icon). Both deliberately render
  **no trend badge** — every `*_trend` key the backend sends is hardcoded
  `0.0` (no real trend math exists for any KPI, old or new), so a fake
  "0% vs prev" badge would assert data that doesn't exist; `trend` was
  widened to optional on the stat-card type and the trend row is now
  conditionally rendered. Top-10 products table gained two columns
  (Gross profit, Margin %) using the per-row fields the backend already
  returns; `colSpan` adjusted 4→6 on the loading/empty rows. KPI grid
  widened from `xl:grid-cols-4` to `xl:grid-cols-3` (2 rows of 3) to
  accommodate the 4→6 tile count cleanly.

**Why each change was required:** Sprint 3's AVCO engine (Batches 1-5,
backend-only) had zero frontend consumer anywhere — a full grep across
`superpos/src/` for every costing term returned zero matches before this
batch. The Dashboard showed no COGS/margin data despite the backend
computing it since Batch 4; a purchase invoice's detail page said "cost
updated" with no numbers despite `InventoryCostMovement` existing since
Batch 1; nobody could see why a product's cost changed at all. This batch
closes exactly that visibility gap — surfacing already-built,
already-tested backend capability, nothing more.

**Tests added:** none (frontend automated tests remain unconfigured
project-wide — governance rule R-I tracks this as a separate, not-yet-
started initiative, consistent with every prior frontend batch).
Verification was `npm run build` (clean `tsc` + `vite build`) plus a real
end-to-end browser click-through (Playwright + headless Chromium) against
the actual local stack (Django + Postgres + Vite dev server) logged in as
the seeded Owner user, exercising real existing data (2 products, 2
posted purchase invoices, 2 `InventoryCostMovement` rows):
- Dashboard: 6 tiles render (4 original + Gross profit + Gross margin),
  the two new tiles show no trend badge, Top-10 table shows the two new
  columns.
- Products page → row menu → "Cost history" → drawer opens showing both
  real cost movements for "Apple 1kg (verified)" with correct
  before→after values and colored deltas.
- Products page → row menu → "Edit" → Cost field is disabled/greyed with
  the new hint text and a working "View cost history" link that opens the
  same drawer.
- Purchases → an existing posted invoice (`PUR-2`) → detail page shows
  "AVCO cost for Apple 1kg (verified) moved EGP 9.50 → EGP 10.43 (received 10)"
  in place of the old generic sentence.
- Zero console errors introduced (3 pre-existing 404s unrelated to this
  batch, confirmed present before these changes too).

**Before/after behavior:** see the click-through results above — every
change is additive (new tiles, new columns, new drawer, new hint); no
existing screen's prior behavior for non-costing data changed.

**Architectural decisions made:**
1. No "adjust cost" button/flow was built — there is categorically no
   backend mechanism to correct a wrong average cost without also
   increasing recorded stock (confirmed during the pre-implementation
   research), so a UI for it would need new backend work first.
2. `ProductsPage.tsx`'s client-side margin recompute (`(price-cost)/price*100`)
   was left untouched — mathematically identical to the backend's
   `Product.margin` now that cost is AVCO-locked (Batch 3), zero benefit
   to swapping.
3. No i18n keys were added — every sibling admin/detail page shipped this
   sprint (`UnitsPage.tsx`, `PriceTiersPage.tsx`, `CategoriesPage.tsx`,
   `ProductUnitsDrawer.tsx`) is 100% hardcoded English with zero `t()`
   calls; adding translation for only this one feature would be
   inconsistent, not more complete.
4. Cost History drawer placed in `components/products/` (not
   `pages/products/` alongside `ProductUnitsDrawer.tsx`) so that
   `ProductFormModal.tsx` — itself a `components/` file — can import it
   without reaching into `pages/`; matches where `StockMovementsModal.tsx`/
   `ReceiveStockModal.tsx` already live.
5. The `PurchaseDetailPage` cost-movement lookup intentionally uses only
   page 1 of the endpoint's results (a targeted "does this invoice show
   up" search), while the drawer uses full real pagination (a deliberate
   full-history browse) — different tools for different jobs, both
   confirmed with the business owner before implementation.

**Final verification:**
- `npm run build` (in `superpos/`) — clean, both before and after the
  drawer-width adjustment discovered during manual testing.
- `git diff --stat` scoped to `superpos_backend/` — empty, confirming zero
  backend files changed.
- Manual end-to-end browser verification (see Tests added above) against
  the real local stack with real existing data — not a mock, not a dry
  run.
- Not touched: `PurchaseCreatePage.tsx` (already correct from 5b-4), any
  recipe/BOM/GL-adjacent code, any backend file.

---

### Sprint 4 — Advanced Reporting & Analytics

Requested by the business owner as 5 candidate features (charts for
Margin/COGS, branch/warehouse filtering, Cost History export to
Excel/PDF, average-cost-over-time comparison, deeper Dashboard
drill-down), preceded by an explicit full-analysis-before-implementation
request. Three parallel research passes (backend data model, frontend
patterns, governance docs) found none of the 5 features gated by any open
decision — **no Phase 0 governance closure was needed this sprint**,
unlike Sprint 2/3. The one real constraint is **D-09** (moving-average
cost is tenant-wide for MVP, upgrade trigger = WarehouseTransfer
maturity, not yet built) — respected throughout by keeping the branch
filter scoped to *sales/margin reporting* only, never to cost data
itself. Three scope decisions were confirmed with the owner before
coding: export formats = CSV + real Excel (.xlsx) + PDF (all three);
Dashboard drill-down reuses the existing `ProductCostHistoryDrawer`
in-place (no new `/products/:id` route); branch filter = branch-only, on
Dashboard/sales reporting only (no warehouse filter, no cost-side
filter). Full plan: `/root/.claude/plans/snuggly-sparking-noodle.md`
(Sprint 4 section).

#### Batch 1 + 2 — Dashboard trend endpoint, branch filter, top-products product-id fix

**Scope:** backend-only, additive. Batch 1 ships a new grouped-by-day
endpoint (the raw series the future Margin/COGS chart needs). Batch 2
adds optional branch scoping to the dashboard reporting surface and fixes
a real gap found during research: `top_products` grouped by the free-text
`product_name` snapshot only, with no product id at all — meaning
nothing could be drilled into from a Top-10 row.

**Files changed:**
- `superpos_backend/pos/views.py`:
  - New `dashboard_trend` view (`GET /api/dashboard/trend/`,
    `IsManagerOrAbove`) — same `start_date`/`end_date` window semantics as
    `dashboard_summary`, but grouped by `TruncDate('created_at')` /
    `TruncDate('sale__created_at')` into one row per calendar day:
    `net_revenue`, `cogs`, `gross_profit`, `gross_margin_pct`. Daily
    granularity only this sprint — no weekly/monthly downsampling
    (deliberate, not a gap; a year range is 365 points, fine for a line
    chart).
  - `dashboard_summary` and `dashboard_trend` both accept an optional
    `?branch_id=` — tenant-scoped `get_object_or_404(Branch, ...)`
    validation, then filters the base `Sale` queryset by
    `branch_id=branch_id`. Cost/COGS math needed zero changes:
    `SaleItem.unit_cost` is already a per-line snapshot independent of
    which branch sold it, so filtering `Sale` is sufficient.
  - `dashboard_summary`'s `top_products` block and the standalone
    `dashboard_top_products` view both now `.values('product',
    'product_name')` instead of `.values('product_name')` alone, and
    return an `id` field per row (the real product pk). Since
    `SaleItem.product` is `on_delete=SET_NULL`, rows with a since-deleted
    product are excluded via `.exclude(product__isnull=True)` — a ranking
    entry with nothing to drill into is simply omitted rather than
    surfaced with a dead link.
- `superpos_backend/pos/urls.py` — one new line:
  `path('dashboard/trend/', views.dashboard_trend, name='dashboard-trend')`.
- `superpos_backend/pos/test_reporting.py` (new file, matching this
  repo's per-feature test-file convention) — 13 tests across
  `DashboardTrendTests`, `DashboardBranchFilterTests`,
  `TopProductsProductIdTests`: per-day series correctness across 3 days
  including a zero-sales day (must appear as a zero row, not a gap),
  voided-sale exclusion, Cashier → 403, invalid date → 400; branch filter
  narrows `dashboard_summary`/`dashboard_trend` correctly, no-`branch_id`
  regression (unfiltered exactly as before), invalid/unknown/cross-tenant
  `branch_id` → 400/404/404; `top_products` now carries the real product
  id on both endpoints, and a since-deleted product's line is excluded
  without crashing.

**Migrations:** none — pure view/URL additions, confirmed via
`makemigrations --check --dry-run` (`No changes detected`).

**Tests:** 656 passed (643 baseline + 13 new), 0 failures.
`manage.py check` clean.

**Architectural decisions:**
1. No governance gate touched — D-09 stays exactly as ratified (cost
   itself never gains a branch dimension); the branch filter only narrows
   which `Sale` rows are aggregated, matching D-09's own consultation note
   that "branch profitability must still be reported separately."
2. Daily-only granularity for the trend endpoint, and no aggregation
   table — computed live from `Sale`/`SaleItem` per request, same as
   every other dashboard figure. Explicitly deferred, not missed: no user
   has asked for weekly/monthly rollups yet.
3. Excluding (not nulling) deleted-product rows from `top_products` was
   chosen over showing `id: null` — a ranking entry a user can't click
   into is worse than one less row.

**Not touched:** any model/migration, `InventoryCost`/
`InventoryCostMovement` (no branch/warehouse field added to either — a
deliberate D-09 compliance check), frontend.

**Next:** Batch 3 (cost-movement date-range filter) + Batch 4 (Cost
History export to CSV/Excel/PDF), then Batches 5-8 (frontend: chart,
branch selector, drawer enhancements, drill-down), then Batch 9
(regression checkpoint).

#### Batch 3 + 4 — Cost-movement date-range filter, CSV/Excel/PDF export

**Scope:** backend-only, additive. Batch 3 wires `?start_date=&end_date=&
source_document_type=` filtering onto the existing `GET
/products/{pk}/cost-movements/` list, mirroring `StockMovementFilter`'s
shape exactly. Batch 4 adds a new export endpoint returning the same
audit trail as a downloadable CSV, real Excel (`.xlsx`), or PDF file —
all three formats, per the owner's confirmed choice.

**Files changed:**
- `superpos_backend/pos/filters.py` — new `InventoryCostMovementFilter`
  (`start_date`/`end_date` → `occurred_at` range, `source_document_type`
  exact match), same field-naming convention as `StockMovementFilter`.
  Cost data has no branch/warehouse dimension (D-09), so no such filter
  exists here — there's nothing to filter by.
- `superpos_backend/pos/views.py`:
  - `ProductCostMovementListView` gets `filterset_class =
    InventoryCostMovementFilter`.
  - New `product_cost_movements_export` view (`GET
    /products/{pk}/cost-movements/export/`, `IsManagerOrAbove`) — reuses
    `InventoryCostMovementFilter` for the same date/type filtering,
    streams rows via `.iterator(chunk_size=500)` (same memory-safety
    pattern as `products_export`/`sales_export`), and renders one of
    three formats based on `?export_format=csv|xlsx|pdf`:
    - **CSV**: byte-for-byte the same `csv.writer` + UTF-8 BOM pattern as
      the existing product/sales exports.
    - **`.xlsx`**: `openpyxl.Workbook()`, one sheet, bold header row.
    - **PDF**: `reportlab.platypus.SimpleDocTemplate` + `Table`, landscape
      letter, bold dark header row — a plain tabular report, no charts
      embedded (matches what "export cost history" literally asked for).
    - Cross-tenant/nonexistent product ids yield an empty (but still
      valid, openable) file rather than a 404 — same "empty list, not
      404" precedent `ProductCostMovementListView` already established.
  - **Discovered mid-implementation and corrected:** the export's format
    selector is named `?export_format=`, not `?format=` — DRF reserves
    `format` as its own content-negotiation query param
    (`URL_FORMAT_OVERRIDE`) and raises `Http404` internally when the
    value doesn't match a registered renderer's format string. The first
    implementation used `?format=` and every export request 404'd; caught
    by the new tests, fixed by renaming the param rather than fighting
    DRF's renderer machinery for one endpoint.
- `superpos_backend/requirements.txt` — added `openpyxl>=3.1` (real
  `.xlsx` generation) and `reportlab>=4.0` (PDF generation), the project's
  first new dependencies since the original `requirements.txt`. Both
  install as pure-Python wheels with no system-level dependency (part of
  why `reportlab` was chosen over `weasyprint`, which needs
  Pango/Cairo/GTK) — confirmed via a clean `pip install`.
- `superpos_backend/pos/test_reporting.py` — 11 new tests across
  `CostMovementDateFilterTests` (4: date-range narrowing, source-type
  filter, no-filter regression, combined with pagination) and
  `CostHistoryExportTests` (7: each of the 3 formats returns 200 with the
  correct content type/filename and real content, an empty result still
  returns a valid file per format rather than crashing, date-range
  narrows the export, an invalid `export_format` value → 400, Cashier →
  403).

**Migrations:** none — pure view/filter/dependency additions, confirmed
via `makemigrations --check --dry-run` (`No changes detected`).

**Tests:** 667 passed (656 baseline + 11 new), 0 failures.
`manage.py check` clean.

**Architectural decisions:**
1. `reportlab` over `weasyprint`/`xhtml2pdf` for PDF generation — pure
   Python, no system-level rendering dependency, sufficient for a plain
   tabular report (no HTML/CSS layout needed for this use case).
2. The export endpoint reuses the exact same filter class as the list
   endpoint rather than duplicating filtering logic — what a user sees on
   screen (paginated table) and what they download (full filtered set)
   are governed by identical query semantics.
3. `?export_format=` instead of `?format=` — a real constraint discovered
   during implementation (DRF's reserved query param), not a stylistic
   choice; documented in both the view's docstring and the URL comment so
   it isn't accidentally "fixed" back to `format` later.

**Not touched:** any model/migration, `InventoryCost`/
`InventoryCostMovement` (no branch/warehouse field added), frontend.

**Next:** Batches 5-8 (frontend: Margin/COGS trend chart via Recharts,
Dashboard branch-filter selector, Cost History drawer enhancements
[date filter + trend chart + export button], Dashboard drill-down into
the existing drawer), then Batch 9 (regression checkpoint).

#### Batch 5-8 — Frontend: Margin/COGS chart, branch filter, drawer enhancements, drill-down

**Scope:** 100% frontend, zero backend files changed (confirmed via
`git diff --stat` scoped to `superpos_backend/`). Consumes the four
backend batches above.

**Files changed:**
- `superpos/package.json` — added `recharts` (the project's first chart
  library; no chart of any kind existed anywhere in the codebase before
  this).
- `superpos/src/components/dashboard/MarginCogsChart.tsx` (new) — a
  `ComposedChart` (Recharts): bars for net revenue vs. COGS per day
  (left axis), a line for gross margin % (right axis, 0-100). Directly
  visualizes the two figures the owner named ("Margin و COGS").
- `superpos/src/api/erp.ts` — `dashboardApi.trend()` wrapper for the new
  Batch 1 endpoint; `inventoryCostApi.exportMovements()` (blob response,
  `export_format` param) for the new Batch 4 endpoint.
- `superpos/src/types/erp.ts` — `DashboardTrendDay`/`DashboardTrendResponse`;
  added `id: number` to `DashboardTopProduct` (mirrors the Batch 2 backend
  fix, closes the frontend half of the drill-down gap).
- `superpos/src/pages/DashboardPage.tsx`:
  - New trend-fetching effect + `MarginCogsChart` card, reusing the page's
    existing `startDate`/`endDate` state — no new date inputs needed.
  - Branch filter: a `<select>` in the `Header`'s `right` slot (styled to
    match the existing date inputs, not `SelectField`, to stay visually
    consistent with that compact control row), populated from
    `branchesApi.list()`, feeding `branch_id` into both `summary()` and
    `trend()` calls. Subtitle now prefers the *selected filter's* branch
    name over the logged-in user's own home branch once a filter is
    active — they're different concepts (e.g. an Owner filtering into a
    branch that isn't their own).
  - Drill-down: Top-10 rows and low-stock rows are now `role="button"`,
    keyboard-accessible (`tabIndex`, `Enter` key), opening
    `ProductCostHistoryDrawer` for that product — the existing drawer
    reused in place, per the owner's confirmed choice, not a new
    `/products/:id` route.
- `superpos/src/components/products/ProductCostHistoryDrawer.tsx`:
  - Widened `product` prop from the full `Product` type to
    `{ id: number | string; name: string }` — the only two fields it
    actually reads — so Dashboard drill-down (which only has a
    `DashboardTopProduct`/`DashboardLowStockEntry` row, not a full
    `Product`) can open it without fabricating dummy field values for
    unrelated required fields. Both existing callers (`ProductFormModal`,
    `ProductsPage`) already pass full `Product` objects, which satisfy
    the narrower shape structurally — no call-site change needed.
  - New date-range filter (two `<input type="date">`, matching the same
    inline pattern already used on `DashboardPage`/`SalesPage` — a third,
    explicitly-accepted occurrence of the same ~15-line pattern rather
    than a premature shared component), narrowing both the table and the
    new trend chart together.
  - New "Average cost over time" chart (`CostTrendChart.tsx`, new file) —
    fetched as a separate query at `page_size=500` (Batch 3's documented
    ceiling) rather than reusing the table's paginated `page_size=20`
    response, since the table needs true pagination (an audit-ledger
    principle from Sprint 3 Batch 6) and the chart needs the fuller series.
  - New Export row (CSV/XLSX/PDF buttons), wired to
    `inventoryCostApi.exportMovements()` via the same
    `Blob`/`createObjectURL`/synthetic-`<a>`-click download pattern
    `SalesPage.tsx`'s CSV export already established.
- `superpos/src/components/products/CostTrendChart.tsx` (new) — a small
  `LineChart` of `avg_cost_after` over `occurred_at`; re-sorts to
  chronological order itself since the drawer's own data stays
  newest-first (an audit-ledger convention); shows an explicit "need at
  least 2 points" empty state rather than a broken/degenerate chart.

**Tests:** none (matches this project's consistent, already-tracked
zero-frontend-test-framework precedent — governance rule R-I).

**Verification performed (not just a build check):**
1. `npm run build` clean after every batch (5, 6, 7, 8 individually and
   combined).
2. Real end-to-end browser click-through (Playwright + headless Chromium,
   per the `/run` skill) against a live local stack (Postgres + Django +
   Vite) with real data — not mocked:
   - Created a second branch ("Downtown Branch") and one sale scoped to
     it, and one intentionally-low-stock product, purely to exercise the
     branch filter and low-stock drill-down paths with real, meaningful
     data (both additive, on the same local dev database prior batches
     already used for verification — not production).
   - Dashboard: confirmed the trend chart renders with a correct tooltip
     (COGS/net revenue/gross margin values cross-checked against the
     fixture sale's numbers), the branch selector narrows the KPI
     tiles/chart/top-products table correctly, and reverts cleanly to
     "All branches".
   - Confirmed clicking a Top-10 row AND a low-stock row both open the
     Cost History drawer for the correct product.
   - Confirmed the drawer's date-range inputs render and are wired; the
     "Average cost over time" chart renders a correct 2-point line
     matching the two real purchase-invoice movements already in the
     database (9.00→9.50→10.43).
   - Confirmed all three export buttons (CSV/XLSX/PDF) trigger a real
     browser download each, with non-zero, plausible file sizes
     (221 / 5188 / 1967 bytes respectively) — not just that the button
     exists or that the request doesn't 404.
3. Both dev servers stopped cleanly after verification.

**Architectural decisions:**
1. `MarginCogsChart` is a single combined chart (bars + line), not two
   separate charts — keeps "Margin and COGS" scannable together, matching
   how the owner phrased the original request.
2. The Cost History drawer's trend chart is a second, separate fetch at a
   higher page size rather than reusing the table's paginated response —
   the table's own real-pagination requirement (Sprint 3 Batch 6) and the
   chart's need for a fuller series are different jobs.
3. No shared `DateRangePicker` component extracted despite this being the
   third occurrence of the same inline date-input pattern — an explicit,
   accepted duplication rather than a premature abstraction; worth
   revisiting only if a fourth occurrence appears.
4. `ProductCostHistoryDrawer`'s prop type is now structurally minimal
   (`{id, name}`) rather than the full `Product` type — a deliberate
   widening to unblock drill-down from non-Product data shapes, not a
   sign the drawer needs more product data than before.

**Not touched:** any backend file (confirmed via `git diff --stat`), any
new route (`/products/:id` still doesn't exist — intentional per the
owner's confirmed choice), `SalesPage.tsx`'s own date-range inputs (branch
filter stays Dashboard-only this sprint, per the owner's confirmed scope).

**Next:** Batch 9 — regression + documentation checkpoint (full suite +
build green across the whole sprint, then this section's final closeout).

#### Batch 9 — Regression + documentation checkpoint (Sprint 4 close-out)

**Checklist (mirrors Sprint 2/3's own closing-batch format):**
- [x] `manage.py check` clean.
- [x] `manage.py makemigrations --check --dry-run` clean — `No changes
  detected`. **Zero migrations across the entire sprint**, confirmed by
  the migrations directory itself still ending at `0028_alter_stockmovement
  _movement_type.py` (the last Sprint 3 Hotfix Pack migration) —
  everything in Sprint 4 was new endpoints, filters, dependencies, and
  frontend UI on top of already-shipped schema.
- [x] `manage.py test` — **667/667 passed**, 0 failures (baseline 643 +
  24 new Sprint 4 tests: 13 in Batch 1+2, 4 in Batch 3, 7 in Batch 4).
- [x] `npm run build` clean for the full accumulated frontend diff
  (Batches 5-8 combined).
- [x] Manual, real-browser, end-to-end verification of all 5 features
  together (not just per-batch) against a live local stack — see the
  Batch 5-8 entry above for the full walkthrough (chart tooltip values
  cross-checked, branch filter narrowing, both drill-down paths, all 3
  export formats downloading real files).
- [x] Drift check: `InventoryCost`/`InventoryCostMovement` gained no
  branch/warehouse field anywhere in this sprint — grepped both files,
  confirmed unchanged since Sprint 3. D-09 stays exactly as ratified.

**Sprint 4 summary — all 5 originally-requested features shipped:**

| # | Feature (as requested) | Delivered as |
|---|---|---|
| 1 | Charts/graphs for Margin and COGS | `MarginCogsChart` on the Dashboard (net revenue/COGS bars + margin line), fed by the new `/dashboard/trend/` endpoint |
| 2 | Filter by Branch or Warehouse | Branch filter on Dashboard reporting (`?branch_id=`), scoped to sales/margin — cost stays tenant-wide per D-09; warehouse filter explicitly descoped by the owner this sprint |
| 3 | Export Cost History to Excel/PDF | CSV + real `.xlsx` (openpyxl) + PDF (reportlab), all three, from the Cost History drawer |
| 4 | Compare average cost change over time | `CostTrendChart` inside the Cost History drawer, plus the new date-range filter on the movements endpoint |
| 5 | Deeper drill-down from Dashboard to related documents | Top-10 products and low-stock rows now open the Cost History drawer; `InventoryCostMovement.source_document_type/id` remains the generic pointer for any future document-level drill-down |

**No governance gate was reopened this entire sprint** — every feature
read/presented data whose owning decisions (D-07, D-09, D-12, D-13, D-31,
D-35) were already closed in Sprint 3's Phase 0. This is the first sprint
in the project's history that needed no Phase 0 of its own.

**New backend dependencies introduced:** `openpyxl>=3.1`, `reportlab>=4.0`
— both pure-Python wheels, no system-level rendering dependency, confirmed
via a clean install.

**New frontend dependency introduced:** `recharts` — the project's first
charting library, used by both `MarginCogsChart` and `CostTrendChart`.

**Branches (all local, not yet pushed as of this checkpoint):**
`s4/batch-1-dashboard-trend-endpoint` → `s4/batch-3-cost-movement-date-filter`
→ `s4/batch-4-cost-history-export` → `s4/batch-5-margin-cogs-chart`
(carries Batches 5-8's combined frontend commit) →
`s4/batch-9-regression-checkpoint` (this checkpoint).

**Not touched:** any GL/`FinancialAccountMovement` code, Recipe/BOM,
warehouse-level filtering (descoped by the owner), any new database
migration.

Sprint 4 is complete.

---

#### Batch 10 — Cost History drawer + Dashboard polish (post-Sprint-4)

The business owner shared a reference mockup of a more elaborate Cost
History drawer (product-summary header, quick-range presets, real
document links, area chart with a trend badge, sortable/paginated table)
and asked for it to be matched. This batch closes the gap on everything
feasible from existing data; a few mockup elements were explicitly
descoped with a stated reason rather than faked.

**Backend (`superpos_backend/pos/serializers.py`, additive, no migration):**
- `InventoryCostMovementSerializer` gained `actor_user_username` (mirrors
  the existing `LedgerMovementSerializer.actor_user_username` pattern),
  read via the view's already-existing `select_related('actor_user')` — no
  extra query. Confirmed sortable-column support (`?ordering=`) was
  already live with zero backend change: DRF's global `OrderingFilter`
  defaults to every readable serializer field when a view doesn't set
  `ordering_fields`, and `ProductCostMovementListView` never did.

**Frontend:**
- `components/products/ProductCostHistoryDrawer.tsx` — rewritten:
  - Product-summary header (icon, name, SKU, Current avg cost, Current
    stock, Last cost update) — fetches the product directly
    (`GET /products/:id/`) so every caller (Products page, Dashboard
    drill-down) gets full fidelity regardless of what it had on hand.
    "Last cost update" reads the latest `InventoryCostMovement` row
    specifically (unfiltered, page_size=1), not `Product.updated_at` —
    that field also bumps on unrelated edits (name, category, …) and
    would misrepresent cost history.
  - Quick-range chips (All/7D/30D/90D/This Month/This Year/Custom) replace
    the bare date inputs as the primary interaction; Custom reveals them.
    "All" was added beyond the owner's literal list to preserve the
    drawer's existing "full audit ledger, must support full browsing"
    default rather than silently narrowing it.
  - Table gained **Movement type** (friendly label of
    `source_document_type`) and **User** (`actor_user_username`) columns;
    **Source** is now a live link to `/purchases/:id` when the row is a
    purchase receipt (React Router `Link`, using the existing route).
  - Date/Qty received/Avg cost columns are sortable (`?ordering=`, click
    toggles asc/desc); a page-size selector (10/20/50/100) sits under the
    table.
  - Empty state (no date filter active) now offers a "Create purchase"
    button linking to `/purchases/new`.
  - Drawer width widened `520px → 1200px` default → to fit the new
    columns without relying on the table's horizontal scroll at normal
    screen widths.
- `components/products/CostTrendChart.tsx` — swapped `LineChart` for a
  gradient-filled `AreaChart`; added a client-computed
  "±X% vs start of period" badge (first vs last point in the currently
  loaded, already-filtered series — not a genuine prior-period comparison,
  labeled accordingly to stay honest about its basis).
- `pages/DashboardPage.tsx`:
  - Gross profit / Gross margin tiles gained client-computed trend badges,
    since the backend has no real trend math for them (every `*_trend` key
    it sends elsewhere is hardcoded `0.0`). Computed from the same
    `/dashboard/trend/` series already driving the chart — anchored on the
    first and last *non-zero* day rather than strict first/last index, so
    a range that happens to start or end on a zero-sales day doesn't
    divide by zero or hide the badge for no reason. Labeled "vs start of
    period" (not "vs prev") to distinguish it from the 4 other tiles'
    genuine (if currently zeroed) backend trend concept.
  - Top-10 products table gained a **COGS** column between Revenue and
    Gross profit (data already existed server-side since Sprint 3 Batch 4
    — this was a pure display gap).

**Explicitly descoped, with reason (not silently dropped):**
- **Warehouse / Supplier columns** on the cost-movements table —
  `InventoryCostMovement` tracks neither dimension (D-09 keeps cost
  tenant-wide; supplier would need an extra join per row this drawer
  doesn't perform). Flagged to the owner rather than fabricated.
- **Drill-down from a Stock Adjustment row** — purchase-invoice rows link
  out correctly; adjustment rows have no dedicated page to link to (stock
  adjustments are posted via an inline modal, not a routed document), so
  they stay plain text, same as before this batch.
- **Real "vs previous period" trend badges on the 4 non-costing KPI
  tiles** (Revenue, Transactions, Avg. basket, Items sold) — no matching
  daily series exists for these (the trend endpoint only carries
  net_revenue/cogs/gross_profit/gross_margin_pct), and fabricating one
  from a different tax basis would misrepresent the number. Left as the
  backend's own (currently zeroed) `*_trend` keys.

**Tests:** `manage.py test` — 667/667 passed (unchanged from the Sprint 4
close-out baseline — this batch added a read-only serializer field and
frontend-only changes, no new backend behavior to test). `manage.py check`
/ `makemigrations --check --dry-run` clean — zero migrations.

**Verification:** `npm run build` clean. Full real-browser click-through
via Playwright against the live local stack: product-summary header
renders correct SKU/avg cost/stock/last-update; all 6 quick-range chips
and Custom exercised; Date-column sort toggled; page-size changed to 10;
purchase-invoice Source links confirmed present and navigating to the
correct `/purchases/:id`; area-chart trend badge rendered correctly for
both a >2-day range (real percentage) and a single-day range (no badge,
correctly suppressed); Dashboard Gross profit/Gross margin trend badges
verified against a real multi-day range (−71.4% / +44.5%); empty state's
"Create purchase" button verified for a product with zero cost movements.

**Not touched:** any GL/`FinancialAccountMovement` code, D-09 (no
branch/warehouse dimension added anywhere to `InventoryCost`/
`InventoryCostMovement`), any new database migration, Recipe/BOM.

---

## Sprint 5 — Recipes, Size Variants, Dynamic Modifiers & Branch-Scoped Costing

Full plan (Context, Scope, Phase 0, Batches 1-11) recorded in the session's
planning artifact before implementation began. Recipes/Variants/Modifiers
land in a new, separate `recipes` Django app (registered in
`INSTALLED_APPS`); changes to already-existing models (`InventoryCost`,
`StockMovement`, `SaleItem`, the sale-posting path) stay in `pos`, since
they're extensions of that app's own models, not new domain concepts.

### Phase 0 — Governance closure (2026-07-22)

`ARCHITECTURE_DECISIONS_REQUIRED.md`: **D-09 reopened** from "Selected:
Option A (tenant-wide)" to "Selected: Option B (branch-wide)" — the
Business Owner authorized the branch-level upgrade directly, ahead of the
original "WarehouseTransfer maturity" trigger (WarehouseTransfer stays
explicitly out of scope this sprint). Closed the **G4 MVP subset**
(D-23, D-24, D-26, D-27, D-28-theoretical-half, D-34) via a new sign-off
row, distinct from the still-fully-Open `G4` row. D-06/D-29/D-30/D-33
(Production Orders / MO / WIP / yield-loss) confirmed **explicitly out of
scope** by the owner's own words, not silently deferred — remain Open.
No code, no migrations — §3.5 (append) and §4 (append one row + update the
D-09 row's status cell) only.

### Batch 1 — Branch-scoped AVCO costing upgrade (backend)

**Goal:** implement the D-09 upgrade — `InventoryCost` becomes one row per
`(product, branch)` instead of one per product — with zero behavior change
for any call site that doesn't resolve a branch.

**Files changed:**
- `pos/models.py` — `InventoryCost.product`: `OneToOneField` →
  `ForeignKey` (`related_name` `inventory_cost` → `inventory_costs`,
  confirmed unused as a reverse accessor anywhere in the codebase before
  renaming). New nullable `branch` FK. Replaced the implicit one-per-product
  uniqueness with two constraints: `UniqueConstraint(product, branch)` +
  a partial `UniqueConstraint(product)` where `branch IS NULL` (same paired
  pattern `SalesCategory`/`InventoryCategory` already use for their
  "unique root name where parent IS NULL" rule) — `branch=NULL` stays the
  single tenant-wide fallback row.
- `pos/migrations/0029_branch_scoped_inventory_cost.py` — `AddField` +
  `AlterField` (cardinality only, no data) + 2 `AddConstraint`s. Every
  pre-existing row keeps `branch=NULL` — zero backfill needed for existing
  data to keep working exactly as before.
- `pos/services/costing.py` — every function gained an optional
  `branch=None` keyword: `get_or_create_inventory_cost`,
  `apply_purchase_receipt`, `update_cost_from_adjustment`,
  `get_cost_for_sale`, `get_cost_for_return`. `branch=None` behaves
  byte-for-byte as before (same query, blends against `Product.stock`). A
  real `branch` blends against
  `stock_movements.get_branch_stock_balance(product, branch)` instead and
  reads/writes that branch's own row; a branch's first-ever write seeds
  from the tenant-wide row's average (or `Product.cost` if neither exists)
  instead of starting blind at zero. `Product.cost` (2dp mirror) still
  syncs unconditionally on every call — documented as "mirrors whichever
  branch/tenant-wide row last transacted," not a partitioned per-branch
  truth. `initialize_inventory_cost` (product-CREATE time) now explicitly
  scopes its `get_or_create` to `branch=None` — without that fix it would
  raise `MultipleObjectsReturned` once a product has any branch-scoped rows
  alongside its tenant-wide one.
- `pos/services/stock_movements.py` — new
  `get_branch_stock_balance(product, branch) -> Decimal`: sums
  `WarehouseStock.quantity` across every warehouse actively linked to the
  branch (any `BranchWarehouse` role), defaults to 0 for an untouched
  branch.
- `pos/services/purchase_invoices.py` — `post_purchase_invoice` now passes
  `branch=branch` into `costing_svc.apply_purchase_receipt` (the function
  already had `branch` in scope — one-line change). Every purchase invoice
  from here on blends into its own branch's average, not a tenant-wide one.
  Module docstring updated to describe this.
- `pos/management/commands/seed_inventory_costs.py` — fixed for the new FK
  shape: dropped the now-invalid `select_related('inventory_cost')`
  (reverse accessor renamed and no longer to-one), scoped its
  `get_or_create` to `branch=None` explicitly (same
  `MultipleObjectsReturned` fix as `initialize_inventory_cost`).
- New `pos/management/commands/backfill_branch_inventory_cost.py` — mirrors
  `seed_inventory_costs`'s `--dry-run`/`--apply`/`--tenant` shape. For every
  product with a tenant-wide row and every active branch, seeds a
  branch-scoped row from the tenant-wide average (skips products with no
  tenant-wide row yet, skips inactive branches, never overwrites an
  existing branch row). Not required for correctness (the lazy
  `get_or_create_inventory_cost` fallback already handles a branch's first
  transaction) — exists so a "cost by branch" view has visible data
  immediately after upgrading, before any new purchase happens.

**Regression found and fixed (not a design flaw — the exact "unassigned-
warehouse legacy stock" risk flagged in the plan before writing code):**
`PurchaseInvoicePostingTests`'s shared fixture creates `Product(stock=100)`
directly with no matching `WarehouseStock` row (simulating pre-existing
stock recorded before any warehouse-aware movement). Branch-scoped costing
correctly reads that as 0 branch stock, changing
`test_cash_purchase_increases_stock_updates_cost_decreases_cashbox`'s
expected moving average from `7.00` to `9.00`. Fixed by seeding a matching
`WarehouseStock` row **locally in that one test** (not in the shared
class fixture — an earlier attempt to fix it at the class level broke a
sibling test, `WarehouseStockPurchaseTests`, that specifically asserts a
warehouse balance starts at zero). No other test's assertions changed.

**Tests:** extended `pos/test_costing.py` — `InventoryCostModelTests`'s
uniqueness test rewritten for the new `(product, branch)` constraint shape
plus a new test proving a product can hold a `branch=None` row and N
per-branch rows simultaneously; new `GetBranchStockBalanceTests` (4 tests:
zero for untouched branch, sums two warehouses on one branch, excludes a
warehouse linked to a different branch, excludes an inactive
`BranchWarehouse` link); new `BranchScopedCostingServiceTests` (6 tests:
two branches blend independently and don't leak into each other or the
tenant-wide row, first-purchase seeding from the tenant-wide row when
present vs. from `Product.cost` when absent, the `branch=None` path proven
byte-for-byte unchanged, `update_cost_from_adjustment` and
`get_cost_for_sale` branch-scoped); new
`BackfillBranchInventoryCostCommandTests` (6 tests: dry-run/apply,
active-branches-only, skip-no-base-row, idempotency, never-overwrite,
tenant scoping).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the one expected migration, additive
only — zero `RemoveField`, zero data mutation). Full suite: **684/684
passed** (up from the Sprint 4 close-out baseline of 667 + this batch's 17
new tests). `backfill_branch_inventory_cost` dry-run verified against the
real local dev database (correctly proposed one row per active branch per
already-tracked product, skipped nothing unexpectedly).

**Not touched:** `recipes` app (created and registered this batch as an
empty scaffold only — no models/migrations yet, that starts at Batch 2),
sale-posting path, any frontend file, any GL code.

### Batch 2 — `ProductVariant` model + CRUD (backend)

**Goal:** size variants (Small/Medium/Large) as their own model, matching
D-24's "variant-of-one-product" decision — each variant is an independent
row with its own sell price, not a computed scale of the parent product's
price, and deliberately carries no barcode.

**Files changed:**
- `recipes/models.py` (new app, first real model) — `ProductVariant`:
  `tenant`, `product` FK (string ref `'pos.Product'`, CASCADE,
  `related_name='variants'`), `name`, `sku`, `plu`, `price` (own sell
  price), `sort_order`, `is_active`, timestamps. `Meta`:
  `unique(tenant, product, name)` + `CHECK price >= 0`.
- `recipes/migrations/0001_initial.py` — `CreateModel` + 2 constraints,
  the app's first migration.
- `recipes/serializers.py` (new) — `ProductVariantSerializer`, mirrors
  `PriceTierSerializer`'s friendly-400 duplicate-name validation pattern.
- `recipes/views.py` (new) — `_ProductScopedMixin` (a deliberate, small
  duplicate of `pos.views._ProductScopedMixin` — that one is module-local
  to `pos.views`, and re-implementing ~15 lines was cheaper than exporting
  a new cross-app contract for it) + `ProductVariantListCreateView`/
  `DetailView`/`DeactivateView`, reusing `pos.views.TenantMixin` (generic,
  no `pos`-model dependency, safe to import across apps) and
  `accounts.permissions`. Same `IsCashierOrAbove` read / `IsManagerOrAbove`
  write split as every other catalog-admin endpoint.
- `recipes/urls.py` (new) — `products/<product_pk>/variants/` (+detail/
  deactivate), same nested-resource shape as `pos`'s
  `products/<pk>/units/`.
- `superpos_backend/urls.py` — mounted `recipes.urls` at `api/`, alongside
  `pos.urls` (no path collisions — `recipes` only owns the `variants/`
  sub-path under `products/<pk>/`).

**Tests:** new `recipes/tests.py` — `ProductVariantModelTests` (create,
per-`(tenant, product, name)` uniqueness enforced at the DB level, the
same name allowed on two different products, negative price rejected,
confirms no `barcode` field exists on the model at all) and
`ProductVariantApiTests` (manager can create, cashier forbidden to
write but can list, duplicate name → friendly 400, negative price →
friendly 400, PATCH updates price, deactivate + deactivate forbidden for
cashier, cross-tenant product → 404, no DELETE verb — mirrors the
`ProductUnit`/`PriceTier` API test conventions exactly).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the one expected `recipes` migration).
Full suite: **699/699 passed** (684 baseline + 15 new).

**Not touched:** `pos` app's models/migrations, sale-posting path, Recipe/
Modifier models (Batches 3-4), any frontend file, any GL code.

### Batch 3 — `Recipe` / `RecipeVersion` / `RecipeLine` models + cost calculation service (backend)

**Goal:** the core BOM structure — a container (`Recipe`) holding
versioned, statused snapshots (`RecipeVersion`) of component quantities
(`RecipeLine`), plus a service that rolls the cost up live from each
component's current branch-scoped average cost — with D-26 (max nesting
depth 2) and D-27 (no circular references) enforced at save time.

**Files changed:**
- `recipes/models.py` — `Recipe` (`product` FK + nullable `variant` FK,
  paired unique constraints mirroring `InventoryCost.branch`'s
  `(product, branch)` + partial-`branch IS NULL` pattern from Batch 1, just
  applied to `(product, variant)`); `RecipeVersion` (`draft`/`active`/
  `archived` status, partial unique constraint capping at most one
  `active` version per recipe — same "one default" shape as
  `ProductUnit.is_base`); `RecipeLine` (`component_product` **PROTECT**ed,
  `component_unit` + `entered_qty` → `qty_base` following the exact
  "entered + unit → base" pattern `SaleItem`/`PurchaseInvoiceLine` already
  established, `CHECK entered_qty > 0`). Recipe *cost* is never stored —
  only quantities are versioned; cost is always computed fresh from live
  component costs (the owner's own requirement: the recipe stays the
  same, but a sale's cost moves automatically when an ingredient's price
  moves).
- `recipes/migrations/0002_recipe_recipeversion_recipeline_and_more.py` —
  `CreateModel` × 3 + 5 constraints, no data.
- New `recipes/services/costing.py` — mirrors `pos/services/costing.py`'s
  house style (pure functions, `RecipeError`, `__all__`):
  `get_active_recipe(product, variant=None)`,
  `compute_recipe_cost(recipe_version, branch=None)` (rolls up via
  `pos.services.costing.get_cost_for_sale` per line, D-12 line-level 2dp
  rounding, total = Σ already-rounded lines), `validate_recipe_lines`
  (walks each candidate component's own sub-recipe chain — depth capped at
  `MAX_RECIPE_DEPTH = 2`, raises on a chain revisiting an ancestor
  product), `activate_recipe_version` (atomically archives whatever was
  previously active on the same recipe).
- `recipes/serializers.py` — `RecipeSerializer`, `RecipeLineSerializer`
  (tenant + same-product validation for `component_product`/
  `component_unit`, `entered_qty > 0`), `RecipeVersionSerializer` (nested
  line writes — pops `lines` from `validated_data`, calls
  `validate_recipe_lines` before creating anything, resolves
  `component_unit` to the component's base unit via
  `units_svc.get_base_product_unit` when omitted, computes `qty_base` via
  `units_svc.convert_to_base` per line — always created as `DRAFT`).
- `recipes/views.py` — `RecipeListCreateView`/`DetailView` (nested under
  `products/<pk>/`, `IsCashierOrAbove` read / `IsManagerOrAbove` write, same
  split as every other catalog endpoint), `RecipeVersionListCreateView`/
  `DetailView`/`ActivateView` (Manager+-only for both read and write — a
  recipe's exact quantities are a sensitive editorial detail, not a
  routine catalog read, unlike Variants/Units/Price-Tiers).
- `recipes/urls.py` — `products/<pk>/recipes/` (+detail), `.../versions/`
  (+detail/activate) — two-level nesting, mirrors `pos`'s
  `products/<pk>/units/<pk>/tier-prices/` shape.

**Tests:** new `recipes/test_recipes.py` (17 tests) —
`RecipeCostCalculationTests` (the owner's own worked example: Chicken
180g/Lettuce 120g/Caesar Sauce 40g/Parmesan 20g/Bread 60g → 38.00 total;
branch-scoped cost differs per branch from the same recipe definition; a
later ingredient purchase changes the computed cost without touching the
recipe's own rows); `RecipeDepthCycleValidationTests` (depth-2 sub-recipe
allowed, depth-3 rejected, self-reference rejected, indirect/circular
reference rejected); `RecipeVersionModelTests` (one-active-version DB
constraint, `activate_recipe_version` atomically archives the prior
active version, `get_active_recipe` returns `None` for a draft-only
recipe, `component_product` PROTECT blocks deletion, `(product, variant)`
uniqueness, a product's base recipe and its variant's recipe are fully
independent rows); `RecipeApiTests` (create recipe → create draft version
with nested lines → activate, empty-lines rejected with 400, cashier
forbidden to write versions, a self-referencing line rejected with a
friendly 400 not a 500).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the one expected migration). Full suite:
**716/716 passed** (699 baseline + 17 new).

**Not touched:** `pos` app's sale-posting path (Batch 5's job), Modifier
models (Batch 4), any frontend file, any GL code. `Product.cost`/
`InventoryCost` untouched by this batch — recipe cost is a pure read.

### Batch 4 — Modifiers (`ModifierGroup` / `ModifierOption` / consumption deltas) (backend)

**Goal:** dynamic extras/removals (Extra Cheese, No Onion) that change
both price and per-variant ingredient consumption, matching D-23
(price on the option, cost always derived from consumption) and D-34
(a free option still consumes inventory and counts as COGS).

**Files changed:**
- `recipes/models.py` — `ModifierGroup` (tenant-scoped, flat, `single`/
  `multiple` selection type + optional `min_select`/`max_select`);
  `ProductModifierGroup` (the product↔group attach link, unique per pair);
  `ModifierOption` (`price_delta`, can be 0 or negative); `ModifierOptionConsumption`
  (`variant` nullable — NULL means "applies regardless of variant", same
  paired-unique-constraint pattern as `Recipe.variant`/`InventoryCost.branch`;
  `entered_qty`/`qty_base` are **signed**, unlike `RecipeLine` which only
  ever adds — a modifier may also *remove* an ingredient, e.g. -20g onion;
  `CHECK entered_qty != 0` instead of `> 0`).
- `recipes/migrations/0003_modifiergroup_modifieroption_productmodifiergroup_and_more.py`
  — `CreateModel` × 4 + 6 constraints, no data.
- `recipes/services/costing.py` — new `compute_modifier_deltas(modifier_option,
  variant=None, branch=None)`: matches consumption rows scoped to the exact
  variant OR variant-agnostic, preferring the variant-specific row when
  both exist for the same component; **a negative delta contributes zero
  cost** (removing an ingredient must never produce negative COGS — a
  dedicated test locks this in); a free option (`price_delta=0`) still
  contributes its full consumption cost (D-34).
- `recipes/serializers.py` — `ModifierGroupSerializer` (duplicate-name
  400, mirrors `PriceTierSerializer`), `ModifierOptionSerializer`,
  `ProductModifierGroupSerializer`, `ModifierOptionConsumptionSerializer`
  (accepts a signed `entered_qty`, resolves `component_unit` to the
  component's base unit when omitted, computes signed `qty_base` via
  `convert_to_base(abs(entered_qty))` re-signed — `convert_to_base` itself
  only accepts positive input).
- `recipes/views.py` / `recipes/urls.py` — `catalog/modifier-groups/`
  (+options nested one level, +deactivate), `catalog/modifier-options/<pk>/consumptions/`
  (+detail), `products/<pk>/modifier-groups/` (attach/detach — the one
  Sprint-5 resource that supports a real `DELETE`, since it's a pure link
  table with no historical data worth soft-deleting, unlike everything
  else in this catalog).

**Tests:** extended `recipes/test_recipes.py` (+10) —
`ModifierDeltaCalculationTests` (positive delta cost, negative delta →
zero cost, free modifier still counts as COGS, variant-specific
consumption preferred over variant-agnostic for the same component);
`ModifierApiTests` (full create-group→option→consumption→attach-to-product
flow, negative `entered_qty` accepted, zero `entered_qty` rejected,
cashier forbidden to create a group, duplicate group name rejected,
detach via DELETE).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the one expected migration). Full suite:
**726/726 passed** (716 baseline + 10 new).

**Not touched:** `pos` app's sale-posting path (Batch 5's job — this is
where `RECIPE_CONSUME` and the actual per-line modifier selection at sale
time land), any frontend file, any GL code.

### Batch 5 — Sale-posting integration: `RECIPE_CONSUME`, variant/modifier selection, cost snapshot (backend)

**Goal:** the centerpiece of the sprint — a POS sale of a recipe product
with a chosen variant and modifiers correctly consumes every component's
stock at the branch's kitchen warehouse, snapshots the cost immutably, and
feeds the existing Sprint 3/4 COGS pipeline with **zero changes to that
pipeline**. Highest regression risk in the sprint — touches the shared
`SaleSerializer.create()`/`_apply_stock()` path every sale in the system
goes through.

**Files changed:**
- `pos/models.py` — `StockMovement.MovementType.RECIPE_CONSUME` added;
  `SaleItem.variant` FK (string ref `'recipes.ProductVariant'`, SET_NULL,
  nullable — which size was actually sold, snapshot-safe).
- `pos/migrations/0030_saleitem_variant_alter_stockmovement_movement_type.py`
  — additive only, correctly depends on `recipes.0003` for the
  cross-app FK.
- `recipes/models.py` — `SaleItemModifier` (frozen `option_name`/
  `price_delta` per selected modifier), `SaleItemRecipeCostSnapshot`
  (`total_recipe_cost`, mirrored onto `SaleItem.unit_cost` itself — see
  below), `SaleItemRecipeCostSnapshotLine` (per-D-31-Option-B normalized
  rows: one per base-recipe ingredient or modifier consumption delta,
  frozen `component_name`/`unit_cost`/`line_cost` independent of the
  component's live average by the time anyone reads it later).
- `recipes/migrations/0004_saleitemrecipecostsnapshot_and_more.py` —
  `CreateModel` × 3, no data; depends on `pos.0030` (needs `SaleItem` for
  the OneToOne/FK).
- `recipes/services/costing.py` — new `resolve_kitchen_warehouse(tenant,
  branch)`: mirrors `purchase_invoices._resolve_line_warehouse`'s exact
  pattern — prefers the branch's default `role=KITCHEN` `BranchWarehouse`,
  falls back to `role=SALES`, raises `RecipeError` (now caught in
  `_apply_stock` and converted to a clean 400) if neither exists.
- `pos/serializers.py` — the integration itself:
  - `SaleItemSerializer` gains `variant` (writable FK) and
    `modifier_option_ids` (write-only list, not a model field — resolved
    into `SaleItemModifier` rows), plus a read-only `modifiers` summary
    field for receipts/detail views.
  - `SaleSerializer.validate()`: a recipe-eligible line (`not
    affects_stock and can_have_recipe` — i.e. `RECIPE_PRODUCT`/
    `PREP_ITEM`/`BUNDLE`) gets its `price_each` **server-computed** —
    `variant.price` (or the base product's price) plus every selected
    modifier's `price_delta` — never accepted from the client, same
    discipline as the existing `product_unit` line's server-computed
    price.
  - `SaleSerializer.create()`: for a recipe line, resolves the active
    `Recipe`/`RecipeVersion` for `(product, variant)`, rolls up cost via
    `compute_recipe_cost` + `compute_modifier_deltas` (both branch-scoped,
    at `sale.branch`), writes `SaleItem.unit_cost` = that total, and
    writes the `SaleItemModifier`/`SaleItemRecipeCostSnapshot`(+lines)
    rows. A recipe product with no active recipe configured raises a
    clean 400 rather than silently selling at zero cost.
  - `_apply_stock()`: branches on `not affects_stock and can_have_recipe`
    — for a recipe line, walks the snapshot's frozen component lines (not
    a re-computation) and writes one `RECIPE_CONSUME` `StockMovement` per
    component at the resolved kitchen warehouse, reusing the exact same
    oversell fallback (`deduct_stock` → `InsufficientStockError` → retry
    `allow_oversell=True`) as the legacy path. Every other line
    (including a plain stock-item line) falls through to the **byte-for-
    byte original** `deduct_stock`/`SALE_OUT` code, unchanged.

**Regression found and fixed (the one real bug this batch's full-suite
run caught):** `_apply_stock`'s first draft branched on
`not product.type_behavior.affects_stock` alone. `SERVICE` and
`FIXED_ASSET` product types *also* carry `affects_stock=False` — they're
Sprint 2's deliberately-dormant classification flags, not recipe-eligible.
`pos.test_product_foundation.LegacyCompatibilityTests
.test_sale_flow_untouched_by_new_classification` (which explicitly sells a
`SERVICE`-typed product and asserts stock still deducts exactly like
legacy) caught this immediately — my new branch was silently skipping
stock deduction for that product with no recipe to fall back to. Fixed by
narrowing the condition to `not affects_stock **and** can_have_recipe`
(only `RECIPE_PRODUCT`/`PREP_ITEM`/`BUNDLE`), matching `create()`'s
already-correct condition exactly. No other test's behavior changed.

**Deliberate scope decision (deviates from the original plan text, made
during implementation once the real risk was visible in the code, not
assumed):** the plan's Batch 5 description also proposed switching
*every* sale line's `unit_cost` — not just recipe lines — from
`product.cost` to the new branch-scoped `costing.get_cost_for_sale
(branch=sale.branch)`, as a general correctness improvement. Verified by
reading `pos/tests.py`'s fixtures that several existing sale tests
manually override `Product.cost` mid-test (`self.product.cost = X; save()`)
*after* an `InventoryCost` row already exists from an earlier step in the
same test — under the branch-scoped read, that manual override would be
silently ignored (the stale `InventoryCost.avg_unit_cost` would win),
diverging from every existing assertion. This is real, avoidable risk for
zero benefit the owner actually asked for, so **non-recipe lines keep
reading `product.cost` directly, exactly as before Sprint 5** — only
recipe-product lines (which never had a trustworthy cost source before
this batch) get the new branch-scoped roll-up.

**Tests:** new `recipes.test_recipes.RecipeSalePostingTests` (9 tests,
posted through the real `/api/sales/` endpoint, not just service calls) —
full end-to-end recipe sale (2-ingredient recipe, correct `unit_cost`,
correct `RECIPE_CONSUME` movements per component, correct snapshot rows,
zero `SALE_OUT` on the recipe product itself); with a modifier (cost and
price both include the modifier, its own `RECIPE_CONSUME` movement fires);
with a variant (uses the variant's own independent recipe and price, the
base recipe's lettuce line does NOT fire); branch-scoped cost in a real
sale (two branches, two different ingredient costs, two different
`unit_cost` results from the identical recipe); snapshot immutability (a
later purchase moves the ingredient average sharply — the already-sold
item's `unit_cost`/snapshot are provably unchanged); oversell fallback for
a recipe ingredient (still 201, warning surfaced, negative stock
recorded); no-active-recipe → clean 400; the Sprint 3/4 dashboard COGS
pipeline reflects a recipe sale's COGS with the dashboard view's own code
untouched; a plain stock-item sale is unaffected. Before writing any of
these, `pos.tests`/`pos.test_pos_integration`/`pos.test_costing`/
`pos.test_hotfix_pack` (213 tests) were re-run unmodified and stayed
green, then the *entire* suite was run twice more (once surfacing the
`SERVICE`-type regression above, once clean after the fix).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the two expected migrations — one in
`pos`, one in `recipes`, additive only). Full suite: **735/735 passed**
(726 baseline + 9 new).

**Not touched:** recipe/food-cost reporting (Batch 6's job), any frontend
file, any GL code. `Product.cost`/non-recipe `SaleItem.unit_cost` sourcing
unchanged (see the deliberate scope decision above).

---

### Batch 5 Hotfix — pre-Batch-6 architecture review (2026-07-22, `s5/batch-5-hotfix-review`)

**Goal:** the Business Owner reviewed Batch 5's design before authorizing
Batch 6 and raised 6 concrete confirmation/cleanup points (verbatim
request preserved in the branch's commit history). Two of the six
surfaced real bugs (points 1 and 6); the rest were legitimate
documentation/snapshot-completeness gaps. All six are closed in this
batch — Batch 6 (reporting) has not started yet.

**Point 1 — `PREP_ITEM`/`BUNDLE` ambiguity.** `can_have_recipe=True` is
shared by three types: `RECIPE_PRODUCT`, `PREP_ITEM`, and `BUNDLE`.
`PREP_ITEM` belongs in the recipe path (it's consumed directly via a
recipe in this MVP — no Production Orders exist). `BUNDLE` does **not** —
it's a Sprint 2 placeholder for a future, different "bundle explosion"
feature (combos of already-stocked finished goods, consumed as whole-unit
multiples), not a recipe. Before this fix, the inline condition
`not affects_stock and can_have_recipe` silently included `BUNDLE` too.
Fixed by adding `recipes/services/costing.py`'s `is_recipe_eligible(product)`
— a single centralized predicate (`not affects_stock and can_have_recipe
and product_type != BUNDLE`), fully documented in its own docstring, and
wired into all three call sites that used to re-derive the rule inline:
`SaleSerializer.validate()`, `SaleSerializer.create()`, and
`SaleSerializer._apply_stock()`.

**Point 2 — Variant snapshot fields.** `SaleItem.variant` was a bare FK;
a later variant rename/reprice/delete would silently alter how an old
sale line reads. Added `SaleItem.variant_name` (CharField, blank default
`''`, matching `product_name`'s convention) and `SaleItem.variant_price`
(nullable Decimal — `NULL` means "no variant on this line", distinct from
a legitimate `0`), populated in `create()` whenever `variant is not None`.
Migration `pos/migrations/0031_saleitem_variant_name_saleitem_variant_price.py`
— additive only.

**Point 3 — Modifier snapshot completeness.** `SaleItemModifier` already
froze `option_name`/`price_delta` but not which `ModifierGroup` the option
belonged to. Added `SaleItemModifier.group_name` (CharField, blank
default `''`), populated from `option.modifier_group.name` at the same
point `option_name` is written. Migration
`recipes/migrations/0005_saleitemmodifier_group_name.py` — additive only.

**Point 4 — Costing-decision documentation.** The "why does only a
recipe-eligible line use branch-scoped cost, and every other line keep
reading `Product.cost`" decision was previously explained only in this
progress doc (see the Batch 5 entry above), not in the code itself.
Strengthened the inline comment at the `create()` call site to state
explicitly: this is a deliberate, permanent design choice to avoid
breaking the Sprint 3/4 COGS test fixtures, not an oversight or a TODO.

**Point 5 — Snapshot as sole source of truth.** Added an explicit
contract to `SaleItemRecipeCostSnapshot`'s docstring: once written, this
row (and its `.lines`) is the **only** thing any later operation — void,
refund, or any future feature — may read for this sale item's recipe cost
and ingredient consumption. Nothing may call `compute_recipe_cost()`,
`compute_modifier_deltas()`, or `compute_recipe_sale_lines()` again for an
already-posted sale item; those functions read *live* recipe/cost state,
which is only correct at the moment of sale. Verified true in code: the
new `compute_recipe_sale_lines()` (point 6) is called exactly once, in
`create()`; `_apply_stock()` reads `snapshot.lines` only; the new
recipe-aware `void_sale` (below) reads the `StockMovement` ledger only —
neither recomputes anything.

**Point 6 — Negative-consumption netting bug (real bug, not just a
documentation gap).** `compute_modifier_deltas()` (Batch 4/5 design)
correctly *drops* a negative-delta consumption line from its returned
`lines` for cost purposes (D-34: a removal doesn't create negative COGS)
— but Batch 5's `create()` was reusing that same filtered list for actual
**stock consumption** too. Net effect: a "No Onion" modifier's `-20g`
line was silently dropped before ever being netted against the recipe's
own `+20g` onion line, so the onion was **never actually removed from
stock** — the modifier affected cost/price bookkeeping but not real
consumption. Fixed with a new function,
`recipes/services/costing.py::compute_recipe_sale_lines()`, which is now
the *only* function `create()` calls for a recipe line's cost/consumption:
it nets recipe-line quantities against every selected modifier's delta
**per component** (summing signed quantities across both sources), then:
- raises `RecipeError` (→ clean 400) if any component's net would go
  negative — a modifier can never remove more of an ingredient than the
  recipe (plus other selected modifiers) actually provides;
- treats an exact net of zero as valid and normal (fully, legitimately
  removed) — no error, no `RECIPE_CONSUME` movement, no cost for that
  component;
- otherwise consumes/costs the net positive quantity, correctly reduced
  by the modifier.

`compute_modifier_deltas()` itself is kept unchanged (still used for
per-modifier cost previews elsewhere) — `_resolve_modifier_consumptions()`
was extracted as a shared helper so both functions resolve
variant-specific-vs-agnostic consumption rows identically.

**Additional fix surfaced during point 5's review, not in the original 6
points but directly blocking a correct "sole source of truth" story:
`void_sale` was not recipe-aware.** Before this fix, voiding a recipe-
product sale item would (a) bump the recipe product's own `Product.stock`
— meaningless, since it was never decremented at sale time
(`affects_stock=False`) — and (b) do nothing at all to restore the
ingredients actually consumed via `RECIPE_CONSUME`, silently leaking
stock forever on every recipe-sale void. This is a correctness gap
introduced by Batch 5 itself (before Batch 5, every sale item went
through the same uniform `SALE_OUT`/stock-bump path, so the old void loop
was correct for everything it saw). Fixed in `pos/views.py::void_sale`:
the per-item loop now skips the direct stock bump for a recipe-eligible
item (via the same `is_recipe_eligible()` predicate), and a new block
reverses every `RECIPE_CONSUME` `StockMovement` the sale posted — read
directly from the ledger (`StockMovement.objects.filter(sale=sale,
movement_type=RECIPE_CONSUME)`), never recomputed from the recipe/modifier
definitions (which may have changed since the sale). Each reversed
movement restores `Product.stock` + the cached `WarehouseStock` balance at
the exact warehouse the ingredient left from, and writes a compensating
`RETURN_IN` row.

**Files changed:**
- `recipes/services/costing.py` — `is_recipe_eligible()`,
  `_resolve_modifier_consumptions()` (extracted), `compute_recipe_sale_lines()`
  (new); `__all__` updated.
- `recipes/models.py` — `SaleItemModifier.group_name` field;
  `SaleItemRecipeCostSnapshot` docstring strengthened (point 5 contract).
- `pos/models.py` — `SaleItem.variant_name`/`variant_price` fields.
- `pos/migrations/0031_saleitem_variant_name_saleitem_variant_price.py`,
  `recipes/migrations/0005_saleitemmodifier_group_name.py` — both
  additive-only (`AddField`), no data mutation.
- `pos/serializers.py` — `SaleSerializer.validate()`/`create()` use
  `is_recipe_eligible()`; `create()` calls `compute_recipe_sale_lines()`
  instead of separate `compute_recipe_cost()` +
  per-option `compute_modifier_deltas()` calls, catches `RecipeError` as a
  400, populates `variant_name`/`variant_price`/`group_name`;
  `_apply_stock()` uses `is_recipe_eligible()`.
- `pos/views.py` — `void_sale` is now recipe-aware (see above).

**Tests:** 8 new tests added to `recipes/test_recipes.py`'s
`RecipeSalePostingTests` (now 17 tests in that class, 42 in the file):
BUNDLE-with-a-Recipe-attached still sells through the legacy `SALE_OUT`
path, never `RECIPE_CONSUME` (point 1); variant snapshot fields survive a
rename + outright deletion of the `ProductVariant` (point 2); modifier
`group_name` survives a `ModifierGroup` rename (point 3); a removal
modifier taking more than the recipe provides → clean 400, zero
`RECIPE_CONSUME` movement, zero snapshot line (point 6, the "reject"
half); a removal modifier taking exactly the recipe's own quantity → 201,
net-zero, zero `RECIPE_CONSUME` movement, zero cost/snapshot line for
that component, base recipe cost unaffected (point 6, the "net correctly"
half — this is the test that would have caught the original bug: before
the fix, this modifier would leave the onion's `+20g` `RECIPE_CONSUME`
movement firing unchanged); voiding a recipe sale restores both
ingredients' stock by their exact original quantities via `RETURN_IN`,
with zero movement recorded against the recipe product itself (void
fix).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean (exactly the two expected additive migrations).
`recipes.test_recipes` alone: 42/42 passed. Full suite: **741/741
passed** (735 baseline + 8 new — the two new migrations added zero net
test-count change beyond the 8 new test methods, since no prior test
needed updating).

**Not touched:** Batch 6 (recipe/food-cost reporting) not started — this
batch is exclusively the pre-Batch-6 confirmation/cleanup the owner asked
for. No frontend file. No GL code. `compute_modifier_deltas()`'s own
signature/behavior unchanged (still used standalone elsewhere); only
`create()`'s call site switched to `compute_recipe_sale_lines()`.

---

### Batch 5 Hotfix Follow-up — split snapshot lines for audit (2026-07-22, `s5/batch-5-hotfix-review`)

**Goal:** owner follow-up question after the Batch 5 hotfix landed: does
`compute_recipe_sale_lines()` keep base-recipe lines and modifier lines
separate in `SaleItemRecipeCostSnapshotLine` (better for audit/debugging),
or does it merge them into one netted row per component? It merged them
whenever a component was touched by both the base recipe and a selected
modifier. Owner's decision: split them — `SaleItemRecipeCostSnapshotLine`
must keep every base recipe line and every modifier line as its own row
(`is_modifier_line` as before), with **no netting inside the snapshot**.
Netting happens **only** at the `RECIPE_CONSUME` stock-deduction stage,
still rejecting any negative net exactly as before. A negative modifier
delta keeps its real (negative) sign in the snapshot. Final rounding
happens once on the total cost, not per line.

**Files changed:**
- `recipes/services/costing.py` — `compute_recipe_sale_lines()` rewritten:
  - Still nets every component's quantity (base recipe lines + every
    selected modifier's resolved consumption) to validate that no
    component's net ever goes negative (`RecipeError` → 400), exactly as
    before — this part of the netting logic is unchanged.
  - The returned `.lines` are no longer built from that netted dict. They
    are now built directly from the **unnetted sources**: one
    `RecipeCostLine` per active `RecipeLine` (`is_modifier_line=False`)
    and one per selected modifier's resolved `ModifierOptionConsumption`
    row (`is_modifier_line=True`, `source_modifier_option_id` set) — even
    when two lines share the same `component_product_id`. A modifier's
    negative `qty_base` (and the resulting negative `line_cost`) is kept
    as-is, never zeroed or dropped.
  - `RecipeCostResult.total_cost` is now computed by summing every line's
    **raw, unrounded** `qty_base * unit_cost` first, then quantizing to
    money (2dp) exactly once — replacing the previous "quantize each line,
    sum the rounded lines" approach, which could silently drift the total
    on components whose raw cost wasn't already a clean 2dp value.
  - Added a small per-call `unit_cost_cache` so a component appearing in
    both a base line and a modifier line only triggers one
    `get_cost_for_sale()` lookup, not two.
  - `RecipeCostLine`'s dataclass docstring updated to state `line_cost` is
    now the raw per-source value, not a pre-rounded one.
- `pos/serializers.py` — `SaleSerializer._apply_stock()`'s recipe branch:
  since `snapshot.lines` can now hold multiple rows for the same
  component (one base + one or more modifier rows), the loop that used to
  read `line.qty_base` directly (assuming one row per component) now nets
  `snapshot.lines` by `component_product_id` first (`net_qty`/
  `component_by_id` dicts), then writes exactly one `RECIPE_CONSUME`
  movement per net-positive component — a `<=0` net is skipped (fully,
  validly removed by a modifier), matching the prior single-movement
  behavior. This net can never be negative in practice: `compute_recipe_
  sale_lines()` already rejected that at sale-creation time and the
  snapshot is immutable afterward. `create()` itself needed no change —
  it already just persists whatever `RecipeCostLine`s the service returns.
- `recipes/models.py` — `SaleItemRecipeCostSnapshotLine`'s docstring
  rewritten to describe the new "one row per source, never netted" contract
  and point at `_apply_stock` as the one place a net is derived, on read,
  from the stored lines.
- `recipes/test_recipes.py` — `test_modifier_reduces_recipe_line_to_valid_
  zero_net` updated: previously asserted the onion component had **zero**
  snapshot lines when its net was zero; now asserts **two** lines exist
  (base `+20`, modifier `-20`, both with their real cost sign), matching
  the new split-line design. Added a new test,
  `test_recipe_and_modifier_lines_for_same_component_stay_separate_and_
  total_rounds_once`: a component touched by both a base recipe line and a
  modifier (each contributing a raw 0.126/g cost) proves (a) the snapshot
  keeps two separate rows for that component rather than merging them, (b)
  the item's total cost is `16.25` (sum-raw-then-round-once), not `16.26`
  (what round-per-line-then-sum would have produced — an explicit
  regression guard for the rounding-order fix), and (c) exactly one
  `RECIPE_CONSUME` movement for the combined `2g` is written at the
  stock-deduction stage.

**Migrations:** none — pure service/serializer logic change, no model
field added or removed. `manage.py makemigrations --check --dry-run`
confirmed clean before and after.

**Tests:** `recipes.test_recipes` grown by 1 new test method (43 in the
file); one existing test's assertions updated to match the new contract
(not a behavior regression — the old assertion tested the *old*
merged-line design, which is exactly what this change replaces). Full
suite: **742/742 passed** (741 baseline + 1 net new test).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean. Full suite green. Manual read-through confirmed
`void_sale` (`pos/views.py`) needed no change — it already reverses
`RECIPE_CONSUME` movements read directly from the `StockMovement` ledger,
never from `SaleItemRecipeCostSnapshotLine`, so it is unaffected by the
snapshot's internal row granularity either way.

**Not touched:** Batch 6 (recipe/food-cost reporting) — still not
started. No frontend file. No GL code. `compute_recipe_cost()` (the
recipe-cost *preview* function, unrelated to a posted sale) and
`compute_modifier_deltas()` (single-modifier preview) both keep their
existing per-line-rounded behavior unchanged — this change is scoped to
`compute_recipe_sale_lines()`, the one function that ever writes an
immutable sale-item snapshot.

---

### Batch 6 — Recipe & food-cost reporting (2026-07-23, `s5/batch-6-recipe-reporting`)

**Goal:** the two backend reports named in the Sprint 5 plan — "best/worst
margin" per recipe product, and "most-consumed ingredients" — as pure
reads over data Batch 5 already writes. No new write-side code, no GL
posting, no frontend file (backend-only batch, matching the sprint's own
"backend batches 1-6, frontend batches 8-10" discipline).

**Files changed:**
- `pos/views.py`:
  - `_parse_report_window(request, tenant)` — small private helper shared
    by the two views below: identical `start_date`/`end_date`/`branch_id`
    parsing semantics to `dashboard_summary`'s own inline logic (range
    defaults to today, an inverted range is swapped, `branch_id` is
    tenant-scoped and 404s if unknown). Factored out only because both new
    views need it verbatim.
  - `recipe_profitability(request)` (`GET /reports/recipe-profitability/`,
    `IsManagerOrAbove`) — groups `SaleItem` rows for
    `product__product_type=RECIPE_PRODUCT` sales in the window by
    `(product, product_name, variant, variant_name)` (the name snapshot
    fields, so a row reflects names as they were sold — same known
    limitation `top_products` already has for mid-window renames). Reads
    `SaleItem.unit_cost` (the branch-scoped recipe cost snapshot Batch 5
    already writes) for `food_cost` — never recomputes a recipe's cost.
    Returns `units_sold`, `revenue`, `food_cost`, `gross_profit`,
    `gross_margin_pct`, `food_cost_pct` per row. `?ordering=` (with an
    optional `-` prefix) sorts by any of those five fields in Python,
    defaulting to `-revenue`; an unrecognized value falls back to the
    default rather than 400ing.
  - `ingredient_consumption_report(request)`
    (`GET /reports/ingredient-consumption/`, `IsManagerOrAbove`) — reads
    the `RECIPE_CONSUME` `StockMovement` ledger directly (never recomputes
    from a live recipe definition — the same "the ledger is the source of
    truth" rule `void_sale`'s own `RECIPE_CONSUME` reversal already
    follows), grouped by `product`. Since a stock movement carries no cost
    snapshot of its own (unlike `SaleItem.unit_cost`), `cost_consumed` is
    derived per movement from that movement's own `(product, branch)`
    branch-scoped `InventoryCost` (D-09) — read fresh, not frozen at
    consumption time, so this is a live report, not an immutable snapshot.
    A small per-request `unit_cost_cache` avoids one `InventoryCost`
    lookup per movement row when many rows share the same `(product,
    branch)`. Per-product totals accumulate the *raw* `qty * unit_cost`
    across movements and quantize to money once at the end — the same
    "sum raw, round once" discipline the split-snapshot-line change above
    just established, applied here for the identical reason.
  - Both views clear `SaleItem`/`StockMovement`'s default `Meta.ordering`
    (`.order_by()` / iterating raw rows instead of `.values().annotate()`)
    to avoid Django folding an ordering column into `GROUP BY` — the same
    gotcha every other aggregation view in this file already works around.
  - New import: `from .services.product_types import ProductType`.
- `pos/urls.py` — two new routes:
  `reports/recipe-profitability/` (`recipe-profitability`),
  `reports/ingredient-consumption/` (`ingredient-consumption-report`).
- `pos/test_reporting.py` — 15 new tests across two new classes
  (`RecipeProfitabilityReportTests`, `IngredientConsumptionReportTests`),
  both built on a new `_Batch6ReportingTestBase(_Sprint4ReportingTestBase)`
  fixture (two `RECIPE_PRODUCT`-typed products, one raw ingredient, a
  `_make_recipe_movement()` helper that writes a `RECIPE_CONSUME`
  movement + its branch-scoped `InventoryCost` row directly, bypassing a
  real recipe sale — the recipe *posting* flow itself is already covered
  end-to-end in `recipes/test_recipes.py`). Coverage: hand-computed
  aggregate figures for both reports; stock-item products excluded from
  `recipe_profitability`; branch filter narrows both reports; D-09
  branch-scoped cost is read per movement, not one global figure, when
  the same ingredient has different average costs per branch; voided
  sales excluded; a non-`RECIPE_CONSUME` movement excluded from the
  ingredient report; zero-results-in-window returns an empty list, not an
  error; `?ordering=` sorts correctly and an invalid value falls back
  cleanly; Cashier → 403 on both.

**Migrations:** none — pure view/URL addition, no model change.
`manage.py makemigrations --check --dry-run` confirmed clean before and
after.

**Tests:** `pos.test_reporting` alone: 39/39 passed (24 baseline + 15
new). Full suite: **757/757 passed** (742 baseline + 15 new).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean. Full suite green.

**Not touched:** Batch 7 (backend regression/documentation checkpoint)
and Batches 8-10 (frontend) — not started. No GL code (no
`FinancialAccountMovement` write, matching Batch 4's own negative-GL-
assertion discipline, though this batch didn't add a dedicated test for
it since it writes nothing at all — read-only views). No change to
`recipes/services/costing.py`, `SaleSerializer`, or any recipe-posting
code — this batch is a pure consumer of data those already produce.

---

### Batch 7 — Production-readiness & architecture validation gate (2026-07-23, `s5/batch-7-production-readiness-gate`)

**Goal:** a validation gate before Sprint 5 frontend starts — not a feature
batch. Reviewed the full recipe lifecycle (Sale → Snapshot →
RECIPE_CONSUME → Void) across 10 axes: data integrity, concurrency/ACID,
idempotency, snapshot completeness, inventory/cost ledger consistency,
performance (N+1/caches), migration safety, API contract, and test gaps.
Fixed only justified defects; documented the rest. Full findings, the
coverage matrix, the ACID analysis, and every Sprint 5 architectural
decision live in the new **`SPRINT5_ARCHITECTURE_DECISIONS.md`** (repo
root).

**Defects fixed (justified by correctness / production risk / perf):**
- **F-1 (P1, correctness):** `RECIPE_CONSUME` was in neither
  `_IN_TYPES`/`_OUT_TYPES` in `pos/services/stock_movements.py`, so the
  movement-derived balance (`get_product_stock_balance`) and the stock-
  statement summary silently ignored recipe-ingredient consumption —
  overstating an ingredient's on-hand on `/products/<pk>/stock-balance/`
  and `/products/<pk>/stock-movements/` (the authoritative
  `Product.stock`/`WarehouseStock` were always correct). Fixed by adding
  `RECIPE_CONSUME` to `_OUT_TYPES`; a consume-then-void nets to zero since
  the void posts a `RETURN_IN` (an IN type).
- **F-2 (P1, data integrity / client-trust):** the sale path accepted any
  tenant `modifier_option_id` without checking the option's group is
  attached to the product via `ProductModifierGroup` — a buggy/hostile
  client could apply an arbitrary price delta (incl. a negative
  "discount") and arbitrary ingredient consumption to any recipe product.
  Fixed in `SaleSerializer.validate()` (rejects modifiers not offered for
  the product; tenant isolation was already enforced by the field
  queryset).
- **F-3 (P2, perf hot path):** recipe cost-snapshot lines were written one
  `INSERT` per component in the revenue path → switched to a single
  `bulk_create` per recipe sale line.

**Files changed:**
- `pos/services/stock_movements.py` — `RECIPE_CONSUME` added to `_OUT_TYPES`
  (with rationale comment).
- `pos/serializers.py` — `SaleSerializer.validate()` now enforces
  `ProductModifierGroup` membership for selected modifiers;
  `SaleSerializer.create()` writes snapshot lines via `bulk_create`.
- `recipes/test_recipes.py` — 2 new regression tests
  (`test_recipe_consume_counts_as_outflow_in_movement_derived_balance`,
  `test_modifier_not_offered_for_product_is_rejected`); Batch 5 fixtures
  updated to attach modifier groups via `ProductModifierGroup` (previously
  they relied on the now-closed validation gap).
- `SPRINT5_ARCHITECTURE_DECISIONS.md` (new) — the gate's full deliverable.

**Documented (not fixed — pre-existing or scale-dependent, with
recommendations):** F-4 the idempotency check-then-act race (pre-existing,
cross-cutting across all POST endpoints — recommend a reservation-row
rewrite in its own batch, R-1); F-5 per-component cost lookups (bounded by
recipe size, cached per-call, R-2); F-6 a future `StockMovement(tenant,
movement_type, created_at)` index for the ingredient report (R-3); F-7
`RECIPE_CONSUME`/void `RETURN_IN` rows not populating
`quantity_before`/`quantity_after` (consistent with the legacy sale/void
paths; the ledger chain tolerates NULLs). Rationale for each is in the
architecture doc.

**Migrations:** none — all fixes are logic/validation-only.
`makemigrations --check --dry-run` clean before and after.

**Tests:** full suite **759/759 passed** (757 baseline + 2 new). ACID
review confirmed: the whole sale posts in one `transaction.atomic()`
(sale + items + modifiers + snapshots + stock + ledgers roll back
together); locking uses `select_for_update`/atomic `F()` updates; no
lock-order inversion between concurrent sales and purchases (sale locks
Product-only, purchase locks Product→InventoryCost).

**Gate decision:** Sprint 5 backend cleared for the frontend batches
(8–10). All P1 defects fixed + regression-tested; migrations additive;
API additive; residual risks documented with recommendations.

**Not touched:** Batches 8-10 (frontend) — not started. No GL code. No
change to the AVCO math, recipe cost roll-up, or snapshot semantics — only
the ledger classification, one input validation, and one insert batching.

---

### Batch 7 Verification Pass — measured, not reasoned (2026-07-23, `s5/batch-7-production-readiness-gate`)

**Goal:** the owner asked for a second pass over Batch 7's gate with real
measurements instead of reasoning: a real regression audit, actual query-
count measurement (N+1), an end-to-end data-integrity test from sale to
every report, a documentation/API-contract sync check, and a
`coverage.py`-measured (not guessed) test-gap review. Full results are
appended as **Part E** of `SPRINT5_ARCHITECTURE_DECISIONS.md`; this entry is
the execution-record summary.

**Findings and fixes:**
- **F-8 (P2, perf — new, found by measurement):** `costing.get_or_create_
  inventory_cost` unconditionally ran a "tenant-wide seed" query before
  ever checking whether the `(product, branch)` row it wants already
  exists — 2 queries every call, even in the common case (a branch's
  ingredient after its first purchase) where the row is already there.
  Called once per recipe component on every recipe sale (the revenue hot
  path). **Fixed:** try the plain lookup first; only pay the seed-
  resolution queries on the genuine cold-start path. Measured effect: a
  sale with 3 distinct components (2 recipe lines + 1 modifier line) went
  from 63 to 60 queries. Confirms the first pass's F-5/R-2 reasoning was
  right in spirit; the actual fix was smaller ("look before you seed")
  than the batch-resolve rewrite originally proposed.
- **Two real coverage gaps closed** (found via `coverage run`, not
  reasoned about): `resolve_kitchen_warehouse`'s `RecipeError` path (a
  branch with no configured kitchen/sales warehouse — a plausible
  "new branch not fully set up" production scenario) had zero test
  coverage of the exception reaching a clean 400 and the whole sale
  rolling back; `_parse_report_window`'s error branches had zero coverage
  as reached through the two Batch 6 report endpoints specifically (only
  `dashboard-summary`/`dashboard-trend` were tested). Both closed with new
  tests.
- **End-to-end reconciliation proven, not assumed:** a new test posts two
  real recipe sales (via the actual `/sales/` API) across two branches with
  different branch-scoped ingredient costs, then verifies the exact same
  number (59.00) falls out of five independently-computed layers:
  `SaleItem.unit_cost`, the `RECIPE_CONSUME` ledger, `dashboard_summary`'s
  COGS, `recipe_profitability`'s `food_cost`, and `ingredient_consumption_
  report`'s summed `cost_consumed` (the last one reads a completely
  different table — `StockMovement`, not `SaleItem`).
- **Documentation sync:** confirmed `IMPLEMENTATION_PROGRESS.md` and
  `ARCHITECTURE_DECISIONS_REQUIRED.md` (the two living docs) are current.
  Confirmed `API_CONTRACT.md`/`API_AND_MODEL_INVENTORY.md`/
  `TARGET_BOUNDARIES.md`/`IMPLEMENTATION_ROADMAP.md`/`SOURCE_OF_TRUTH.md`/
  `INDEX.md` are a frozen, numbered "read-only architecture audit — N of 7"
  series predating Sprint 1 — point-in-time snapshots by design, not living
  trackers; editing them would misrepresent what they are, so none were
  touched. Compared the actual Sprint 5 schema against `TARGET_BOUNDARIES.md`
  §6's proposed target model: confirmed §6.13's profitability terminology
  matches Batch 6's report fields exactly (term-for-term), and confirmed
  every schema divergence found (`RecipeVersion`'s simpler 3-stage status
  vs. the target's 4-stage + date-effective window; `RecipeLine` missing a
  per-line yield/loss factor and per-line warehouse) is the direct,
  already-documented consequence of the "no Production Orders this sprint"
  scope decision — not a new gap.
- **Query-count regression guards added** (measured ceilings, not
  estimates) for all four Sprint-5 hot/report paths: recipe sale creation
  (≤60 queries), recipe sale void (≤35), `recipe-profitability` (≤5
  regardless of row count — confirmed DB-side aggregation, not per-row
  Python work), `ingredient-consumption-report` (≤5 regardless of row
  count — confirmed the per-request cost cache actually prevents the N+1
  the view's own docstring warns about).

**Files changed:**
- `pos/services/costing.py` — `get_or_create_inventory_cost` tries the
  plain `(product, branch)` lookup before the seed-resolution queries.
- `recipes/test_recipes.py` — 6 new tests on `RecipeSalePostingTests`:
  the no-kitchen-warehouse rejection, the recipe-sale and recipe-void
  query-count guards, and the end-to-end reconciliation test (plus a new
  `branch_c`/`manager_c` fixture with no configured warehouse).
- `pos/test_reporting.py` — 6 new tests across `RecipeProfitabilityReportTests`
  / `IngredientConsumptionReportTests`: invalid-date/branch_id validation
  (×2 endpoints) and the two query-count-doesn't-scale-with-rows guards.
- `SPRINT5_ARCHITECTURE_DECISIONS.md` — new **Part E** with the full
  measured results; the stale F-5 row in the original findings table now
  points to Part E instead of restating superseded reasoning.

**Migrations:** none — logic and tests only. `makemigrations --check
--dry-run` clean before and after.

**Tests:** full suite **771/771 passed** (759 baseline + 12 new). Coverage
(via `coverage.py`, added to the dev venv only — not `requirements.txt`,
since it's a measurement tool, not a runtime dependency): Sprint-5-relevant
modules (`recipes/`, `pos/services/costing.py`, `pos/services/stock_
movements.py`) stayed at 91% with both real gaps closed and every
remaining uncovered branch verified to be defensive/unreachable or
consistent with the rest of the codebase's own CRUD-boilerplate coverage
level (not a Sprint-5-introduced risk).

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean. Full suite green.

**Gate decision (reaffirmed):** Sprint 5 backend stays cleared for the
frontend batches (8–10). The verification pass found one additional real
perf issue (fixed) and closed two real coverage gaps — no new correctness
defect surfaced, and the end-to-end reconciliation test is the strongest
data-integrity guarantee this gate can offer short of production traffic.

**Not touched:** Batches 8-10 (frontend) — still not started. No GL code.
No change to the AVCO formula, recipe cost roll-up, or snapshot semantics.

---

### Sprint 5 — Pre-close-out owner review (2026-07-22)

Before signing off on Sprint 5, the Business Owner asked six specific
questions about the verification pass's own claims. Each was answered by
re-running real code (not re-reasoning from existing prose); three led to
genuine, now-closed gaps. Full answers with evidence are in
`SPRINT5_ARCHITECTURE_DECISIONS.md`'s new **Part F**.

- **Coverage measurement correction:** the previously-reported 91% figure
  was measured by running only `recipes pos.test_costing
  pos.test_reporting` under `coverage.py`, not the full suite — that
  undercounted `pos/services/stock_movements.py` (49% in the scoped run,
  since most of its coverage comes from `pos/tests.py`, which the scoped
  run never executed). Re-measured against the full 781-test suite: the
  honest baseline was **95%**, not 91%.
- **Three real gaps found and closed with new tests:**
  1. `update_cost_from_adjustment`'s cold-start branch (a stock-count cost
     adjustment on a `(product, branch)` pair with no prior `InventoryCost`
     row) had zero coverage — every existing test seeded the row via
     `apply_purchase_receipt` first. `pos/services/costing.py` is now
     **100%** covered.
  2. Every GET/PATCH/deactivate admin endpoint for Recipe, RecipeVersion,
     ModifierGroup, and ModifierOption had never been called by a single
     test (only their POST/create paths were exercised, needed for the
     sale-integration tests). 7 new tests took `recipes/views.py` from 83%
     to 96%.
  3. Void was never tested with a variant, a modifier, and an oversold
     ingredient combined — each was only proven independently at sale
     time. New test `test_void_recipe_sale_with_variant_modifier_and_
     oversell_combined` proves the combined reversal is exact.
- **AR/GL isolation proven, not just asserted:** new test
  `test_credit_recipe_sale_posts_correct_ar_charge_unaffected_by_recipe_logic`
  posts a real credit sale of a recipe product with a modifier and asserts
  the `CustomerARMovement` charge matches `sale.total` exactly and zero
  `FinancialAccountMovement` rows are created — closing what was
  previously only a code-reading inference into a direct proof.
- **Two scale-dependent gaps identified and explicitly left open** (real,
  not hidden): no load/stress test exists anywhere in Sprint 5 at
  production-realistic data volume; `ingredient_consumption_report`
  aggregates in Python (not SQL) over every matching `RECIPE_CONSUME` row,
  so its *response size* stays catalog-bounded but its *request cost*
  scales with movement-row count on a long date range. Both are recorded
  as scoped Sprint 6 backlog items, not blockers.
- A real 60-query recipe-sale breakdown (by table, not estimated) found a
  further ~16-query (27%) opportunity — 4 redundant `accounts_tenant`
  re-fetches and 12 nested-transaction savepoints from wrapping each
  component's stock-out call in its own `atomic()` block — deliberately
  **not** taken in this pass: the savepoints protect a real
  partial-failure correctness property, and touching lock-sensitive code
  right after a gate review for a single-digit-millisecond gain fails this
  project's own "no refactor without measurable benefit" rule. Flagged as
  a P3 backlog item.

**Files changed:**
- `pos/services/costing.py` — one new coverage-closing test target only
  (no production code change).
- `pos/test_costing.py` — 1 new test
  (`test_update_cost_from_adjustment_on_product_with_no_prior_inventory_cost_row`).
- `recipes/test_recipes.py` — 9 new tests: the combined void scenario, the
  credit-sale AR isolation proof, and 7 CRUD detail/deactivate/filter
  tests across Recipe/RecipeVersion/ModifierGroup/ModifierOption/
  ModifierOptionConsumption (new imports: `Customer`, `CustomerARMovement`,
  `FinancialAccountMovement`).
- `SPRINT5_ARCHITECTURE_DECISIONS.md` — E-5 corrected with the honest
  full-suite methodology and numbers; new **Part F** with all six answers;
  the Gate decision section updated with the corrected test/coverage
  counts and an explicit call-out of the two scale-dependent open items.

**Migrations:** none — tests and documentation only. `makemigrations
--check --dry-run` clean before and after.

**Tests:** full suite **781/781 passed** (771 baseline + 10 new).
Sprint-5-relevant coverage: **97%** (corrected 95% baseline → 97% after
closing the three real gaps above), `pos/services/costing.py` now 100%.

**Verification:** `manage.py check` clean. `manage.py makemigrations
--check --dry-run` clean. Full suite green.

**Gate decision (reaffirmed again):** Sprint 5 backend stays cleared for
the frontend batches (8–10). No new correctness defect surfaced at any
point in this review — every finding was either a documentation/
measurement correction or a genuine-but-non-blocking test-coverage gap,
all now closed.

**Not touched:** Batches 8-10 (frontend) — still not started. No GL code.
No change to the AVCO formula, recipe cost roll-up, or snapshot semantics.
No production code changed in this review at all — every fix was a test
or a documentation correction.

---

### Sprint 5 Batch 8 — Frontend: Recipe Management Application

New, fully independent React feature app at `superpos/src/apps/recipes/`
(api/components/hooks/pages/routes/services/store/types/utils), covering
Recipes/BOM, Size Variants, Modifiers, and food-cost reporting — the first
frontend consumer of every Sprint 5 Batch 1-6 backend endpoint.

- **Routing:** `/recipes`, `/recipes/new`, `/recipes/:id`,
  `/recipes/:id/edit`, `/recipes/:id/versions`, `/recipes/modifiers`,
  `/recipes/reports`, mounted into `App.tsx` as a single
  `/recipes/*` route (`RecipesApp` from `apps/recipes/routes/index.tsx`) —
  the only integration point; POS/Inventory/Sales routing untouched.
- **Reusable editor:** `RecipeProductForm` (component, not a page) owns all
  ingredient-editing behavior, taking `productId`/`variantId` — designed so
  a future batch can embed it directly inside `ProductFormModal` when
  `product_type === 'recipe_product'`, with no rewrite.
- **Zero business logic in React** (grep-verified): no cost/margin
  computed client-side anywhere; `CostPreview.tsx` explicitly explains why
  no live cost preview exists (see Gap G-1 below) instead of faking one;
  every save just POSTs the Sprint 5 request shape and renders whatever
  the server returns.
- **Independent state:** `recipesStore` (zustand) holds only the Recipe
  Editor's in-progress draft lines — nothing Recipes-specific was added to
  `posStore`/`appStore`.
- **Design system:** reuses `DataTable`/`Drawer`/`Modal`/`ConfirmDialog`/
  `FormField`/`Badge`/`Icon`/`Tabs`/`useQuery` etc. verbatim — no new
  design tokens.

**4 real gaps found and documented (not worked around):**
- G-1: no backend endpoint computes a recipe's cost before it's sold —
  `CostPreview` shows an honest explanation + a link to Recipe Reports
  instead of reimplementing the AVCO lookup in React.
- G-2: `GET /products/` has no `product_type` filter — the Recipe list
  fetches a larger page and filters client-side for display.
- G-3: no tenant-wide "recipe completeness"/variant-count endpoint —
  `RecipeSummary` only shows the 2 stats derivable from data already
  fetched, rather than N+1-looping to fake the rest.
- G-4: `ModifierGroup.selection_type`/`min_select`/`max_select` have no
  edit UI yet (low priority — POS doesn't consume them yet either).

Full file/component/route/API/gap inventory:
`SPRINT5_BATCH8_ARCHITECTURE_REVIEW.md`.

**Files changed outside `apps/recipes/`:** `App.tsx` (+2 lines), `Sidebar.tsx`
(+1 nav entry), `auth/permissions.ts` (+1 line, cosmetic role floor).
**Also fixed (environment, unrelated to this feature but blocking any
build verification):** `tsconfig.json` — added `"ignoreDeprecations":
"6.0"` (the TypeScript 6.0.2 now installed here deprecated `baseUrl`,
which made `tsc` fail before any code could be checked); the compiler's
own suggested fix, behavior-neutral.

**Verification:** `npm run build` clean (`tsc` + `vite build`). Full
real-browser click-through (Playwright + real Django/Postgres backend, not
mocked): seeded a demo tenant/ingredients/recipe product, then created a
recipe (search → pick ingredient → unit/qty → save draft → activate),
verified version history, created a size variant, created a modifier group
+ option (including the backend's own duplicate-name validation surfacing
correctly through the UI on a repeat attempt), and loaded the Reports page
with its branch/date filters against both report endpoints. No console
errors beyond a pre-existing, app-wide `favicon.ico` 404.

**Not touched:** any backend file, any POS/Sales/Inventory frontend page,
`ProductFormModal.tsx` (the future embed point for `RecipeProductForm` —
deliberately deferred, not started this batch).

---

## Sprint 5 Batch 8 — Production Readiness Hardening (2026-07-23)

Follow-up to Batch 8's initial delivery: the user requested full
Production-Grade enforcement (SAP/Odoo/Dynamics-level) of every rule the
prior audits had found missing, plus a full OpenAPI/Swagger contract
verification against a user-supplied `SuperPOS_API_2.yaml`.

**Swagger verification method:** rather than a manual endpoint-by-endpoint
read, generated a fresh schema from the live codebase via
`manage.py spectacular` (the same tool that produced the uploaded file,
since this backend runs `drf-spectacular`) and diffed it byte-for-byte
against the uploaded YAML. Result: **0 path differences** (135/135
identical); the only content diffs (240 lines) were cosmetic
`drf-spectacular` version artifacts in unrelated auth/accounts email
fields — zero differences in any Products/Recipes/Variants/Modifiers/
Sales/Reports endpoint. Full findings: `SPRINT5_BATCH8_SWAGGER_COMPLIANCE_REPORT.md`.

**Backend — 6 new/strengthened validations, all backend-authoritative:**
1. `ProductSerializer.validate()` — `show_on_pos=True` now rejected for any
   `product_type` with `can_sell=False`.
2. `SaleSerializer.validate()` — `can_sell` now enforced per sale item
   (previously unchecked entirely).
3. `SaleSerializer._apply_stock()` — `affects_stock` now actually enforced
   on the legacy branch (previously referenced only in a comment); Service/
   Bundle/Fixed-asset sales no longer touch `Product.stock` or write any
   `StockMovement`.
4. `pos/services/units.py::product_unit_in_use()` (new) +
   `ProductUnitSerializer.validate()` — `conversion_to_base` now locked for
   any `ProductUnit` (not just the base one) once used in a real
   purchase/sale/recipe/modifier line.
5. `recipes/serializers.py::RecipeSerializer.validate()` (new) — Recipe
   creation/update rejected for `product_type=bundle` (previously silently
   accepted, functionally inert).
6. `recipes/services/costing.py::check_recipe_readiness()` (new) — a
   Dynamics-style "availability check" gate: Recipe exists → Active Version
   exists (2 queries, replaces the old `get_active_recipe()` at identical
   cost) → non-empty version + no discontinued ingredient (checked inside
   `compute_recipe_sale_lines`, which already fetches the lines with
   `select_related`, so **zero extra queries** on the success path — the
   split was deliberate to avoid a measured query-count regression, caught
   by `test_recipe_sale_query_count_regression_guard`).

**Frontend — Dynamic Product Form + Reports enhancement:**
- `ProductFormModal.tsx`: `fieldVisibility()` — a pure display mirror of
  `pos/services/product_types.py`'s behavior matrix (booleans only, no
  business logic) drives which inputs render per `product_type`. Verified
  in a real browser: Ingredient hides Price/Cost-is-shown/POS/Tax/Sales
  category, shows Stock/Unit/Pack qty/Inventory category; Recipe product
  shows Price/POS/Tax/Sales category, hides Stock/Cost/Unit/Pack qty.
- **"Build Recipe" journey**: a brand-new `recipe_product` gets a
  dedicated success screen (Later / Build Recipe) after save, landing
  directly on `/recipes/new?product_id=X` with the editor in draft mode —
  no re-search. A persistent "Build / edit recipe" button also appears when
  editing an existing recipe product. Full Product → Save → Build Recipe →
  Recipe Editor journey verified end-to-end via Playwright against the
  live stack.
- `RecipeReportsPage.tsx`: added a 4-tile KPI strip (Revenue/Food cost/
  Gross profit/Gross margin — client-side SUM over already-fetched rows,
  no re-aggregation) and 3 ranked-list cards (Top Recipes by profit, Worst
  Margin, Most Used Ingredient — client-side sort/slice of the same
  already-fetched server-computed rows).
- `CostPreview.tsx` — untouched, per explicit instruction (no backend
  endpoint exists yet; placeholder stays as designed).

**Verification:** 802/802 backend tests passing (0 regressions — 3
pre-existing tests that asserted the OLD, buggy behavior were rewritten to
assert the new, correct behavior, with each rewrite documented inline
explaining why the old assertion was itself the bug); `manage.py check`
clean; `makemigrations --check` — zero new migrations (pure logic changes,
no schema changes); `npm run build` clean; real-browser Playwright
click-through of the full Dynamic Form + Build Recipe + Reports KPI flow.

**Deliverables:** `SPRINT5_BATCH8_PRODUCTION_READINESS_REPORT.md` (bugs
fixed, validations added, validations deliberately not implemented + why,
architecture conflicts — none found, before/after comparison,
enterprise-grade assessment) and `SPRINT5_BATCH8_SWAGGER_COMPLIANCE_REPORT.md`
(contract verification + endpoint dependency graph).

---

### Sprint 5 Batch 8 — Architectural Improvements Pass (2026-07-23)

**Scope:** explicit follow-up request — architectural improvements only,
not a re-implementation of the validations already shipped in the
Production Readiness pass above. Six items:

1. **Single Source of Truth.** New `GET /api/catalog/product-types/`
   (`pos.services.product_types.product_type_metadata()`) reads straight
   off `PRODUCT_TYPE_BEHAVIOR` — value/label/behavior flags/`required_fields`/
   `recommended_fields` per type, zero duplication. `ProductFormModal.tsx`'s
   local `TYPE_BEHAVIOR` const and hardcoded `PRODUCT_TYPE_OPTIONS` array
   are deleted; the form now fetches this endpoint once per session (cached
   in `hooks/useProductTypeMetadata.ts`, a module-level singleton fetch —
   static reference data, changes only when a developer adds a new type)
   and renders purely from the response via `findTypeMetadata()`. The
   frontend is now genuinely a renderer, not a second copy of the rule set.
2. **Dynamic Form Architecture — evaluated, not rebuilt.** A full Tabs/
   Sections redesign was assessed and intentionally NOT done this pass: the
   form is short enough (≤20 fields) that a tab split would add navigation
   cost without reducing real complexity, and every other admin form in
   this codebase (Units, Price Tiers, Categories) uses the same flat-card
   pattern — switching only this one form would break consistency. What
   *was* done is the workflow-driven piece the request's own example was
   really pointing at (steps 3-4 below): the Recipe Status stepper and the
   Derived Cost field turn "hide fields you can't use" into "show you where
   you are in the process" for the one product type (`recipe_product`)
   that actually has a multi-step lifecycle. Recorded as a conscious
   decision, not a skipped one — see the ERP UX Review reply for detail.
3. **Recipe Workflow.** New `RecipeStatusStepper.tsx` — reads real backend
   state (`GET /products/{id}/recipes/` + its versions) and renders
   `(No Recipe) → Build Recipe → Manage Versions → Activate Version →
   POS Ready`, only ever shown for an *existing* Recipe product in edit
   mode (never on create, since there's no product id yet to query).
   "POS Ready" only lights up when ALL of {active version exists, `can_sell`,
   `show_on_pos`} are true — a built-and-activated recipe that isn't shown
   on POS correctly stays short of the last step, with an inline reason.
4. **Derived Cost.** New backend endpoint
   `GET /products/{id}/recipes/{recipe_id}/versions/{version_id}/cost-preview/`
   (`recipes.services.costing.compute_recipe_cost`, exposed for the first
   time over the API — previously sale-only) plus `?branch_id=`. Replaces
   the previous `CostPreview.tsx` "not available yet" placeholder with a
   real, live, branch-scoped total + per-ingredient line list. New
   `DerivedCostField.tsx` shows this same number read-only inside
   `ProductFormModal` in place of the (now correctly still-hidden) editable
   Cost input for Recipe products, closing the "hide the whole section"
   gap named in the request.
5. **Required Fields Audit.** Two real, honest findings, both fixed:
   - **Purchase-side type enforcement was missing** — `can_sell` is
     enforced on `SaleSerializer` (prior batch) but `can_purchase` was
     never checked on `PurchaseInvoiceLineSerializer`; a Recipe
     product/Prep item/Service/Bundle could be purchased via a purchase
     invoice, which is architecturally wrong. Fixed with the exact mirror
     check.
   - **`sales_category`/`inventory_category` "required" claim was
     re-scoped, not force-enforced.** Both FKs stay `null=True, blank=True`
     at the model level deliberately — hard-requiring them would break the
     Quick Add fast-entry path and doesn't match how mainstream ERPs treat
     an "Uncategorized" product (a permanent valid state, not an error).
     `product_type_metadata()` now splits `required_fields` (backend
     rejects a write missing it — `name`/`barcode`/`price` when sellable/
     `cost` when cost-tracked) from `recommended_fields` (a real nudge, UI
     shows "(recommended)", never blocks submission). This keeps the new
     metadata endpoint honest — it never claims an enforcement the backend
     doesn't actually perform.
6. **ERP UX Review** — delivered as a direct chat reply (production-ready
   vs still-needs-improvement list), not a new document, matching the
   request's own "state only what's still needed / what's ready" framing.

**Files changed:**
- Backend: `pos/services/product_types.py` (`_required_fields`,
  `_recommended_fields`, `product_type_metadata`), `pos/views.py`
  (`ProductTypeMetadataListView`), `pos/urls.py`, `pos/serializers.py`
  (`PurchaseInvoiceLineSerializer.validate` — `can_purchase` check),
  `recipes/views.py` (`RecipeVersionCostPreviewView`), `recipes/urls.py`.
- Backend tests: `pos/test_units.py` (`ProductTypeMetadataTests`),
  `pos/tests.py` (`PurchaseInvoiceProductTypeEnforcementTests`),
  `recipes/test_recipes.py` (5 new cost-preview tests in `RecipeApiTests`).
- Frontend: `hooks/useProductTypeMetadata.ts` (new), `api/erp.ts`
  (`productTypesApi`), `types/erp.ts` (`ProductTypeMetadata`),
  `components/products/ProductFormModal.tsx` (metadata-driven visibility,
  `(recommended)` field tags, stepper + derived-cost wiring),
  `components/products/RecipeStatusStepper.tsx` (new),
  `components/products/DerivedCostField.tsx` (new),
  `apps/recipes/components/CostPreview.tsx` (real fetch, replacing the
  documented placeholder — includes a fix for a `useQuery` fetcher that
  must gate on `canPreview` itself, not just its render branch, since the
  hook's effect fires on every dependency change regardless of what gets
  rendered), `apps/recipes/api/recipesApi.ts` (`costPreview`),
  `apps/recipes/types/index.ts` (`RecipeCostPreview`).

**Verification:** 814/814 backend tests passing (up from 802 — 9 new
tests for the metadata endpoint + purchase enforcement + cost-preview
endpoint, 3 pre-existing tests updated where `required_fields` assertions
moved to `recommended_fields`); `manage.py check` clean;
`makemigrations --check` — zero new migrations (pure service/view/
serializer additions, no schema changes); `npm run build` clean;
real-browser Playwright verification of the metadata-driven Dynamic Form
(type switch correctly re-renders visibility from the server response),
the `(recommended)` tag, the Recipe Status stepper showing "No recipe" for
a product with none, and the Derived Cost field showing "No active recipe
yet" for the same product — all matching real backend state, not assumed.

---

*(Later batches of Sprint 5 get their own entries here as they land.)*
