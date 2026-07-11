# IMPLEMENTATION_PROGRESS.md

> Living tracker for the controlled implementation of the ratified architecture
> package. One section per sprint. Updated after every audit and every
> implementation batch. Governance: a slice's code lands only when its gate has
> exited per [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)
> §3.0 (R-M), except components the register explicitly leaves ungated.

---

## Sprint 1 — Foundation (roadmap Slice 1 + Slice 2)

**Status: IN PROGRESS — Batch 1 (GA-1, GA-6, GA-8) executed 2026-07-12 on
branch `s1/gate-a-foundation`; suite 370 green.** Remaining: steps 4–8
(provisioning command, sales idempotency, GA-7, GA-9, GA-2) pending the next
authorized batch; steps 9–10 (GA-3/GA-4) blocked on G0 exit.
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
| 4 | `provision_default_payment_routing` management command (`--dry-run` default / `--apply [--tenant]`) | — | **Replaces GA-5.** No financial rows created inside `migrate`; idempotent; logs every created/reused/demoted row. |
| 5 | Sales idempotency (Slice 2) | — | Wire existing `idempotency.lookup/save` into `SaleListCreateView.create` exactly as purchase invoices; replay → one Sale, conflict → 409. |
| 6 | GA-7 financially-correct void | — | Compensating `FinancialAccountMovement`/`CustomerARMovement` reversal entries under `select_for_update`, `Idempotency-Key` replay; reversal follows the compensating-document pattern (R-C). |
| 7 | GA-9 test pack | — | Port + re-point backfill tests at the step-4 command; add void-reversal + sales-idempotency tests; full suite green. |
| 8 | GA-2 strict routing | Step 4 **applied & verified for every active tenant** | Ordering guarantee: no live branch stops selling. |
| 9 | GA-3 credit-limit guard | **D-14 answered + G0 exit** | If D-14 → "null = unlimited", requires an additive nullable migration on `Customer.credit_limit`. |
| 10 | GA-4 negative-stock guard | **G0 exit** (D-15 already selected: branch toggle only, no per-sale override) | Blocked oversell → structured 400 + full rollback. |

Steps 9–10 ship in a Sprint-1 follow-up batch the moment G0 exits; everything
else is implementable now.

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

1. **User authorization to execute Sprint 1** (execution rule: sprint must be
   explicitly authorized).
2. **D-14 answer + G0 sign-off/promotion** — blocks steps 9–10 only.
3. Access to a production-like tenant list for the step-8 provisioning
   verification (dev DB only has test data).

---

*(Later sprints get their own sections here after their pre-sprint audits.)*
