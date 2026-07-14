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

**Status: IN PROGRESS — Batch 1 (Units Core Foundation) executed 2026-07-14 on
branch `s2/master-data-foundation`; suite 431 green.** Design authority: the
approved Sprint 2 design (plan approved 2026-07-13) + MASTER_DATA_CONTRACT §2.
Remaining: Batch 0 governance (owner action — see flag below), Batches 2–5.

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

---

*(Later sprints get their own sections here after their pre-sprint audits.)*
