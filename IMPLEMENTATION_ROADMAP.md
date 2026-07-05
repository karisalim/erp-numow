# IMPLEMENTATION_ROADMAP.md

> **Read-only architecture audit — 7 of 7 (revised for ratification).** The
> sequenced, freeze-gated slice plan to reach a reliable F&B/accounting system,
> plus the architecture-level treatment of the three specially-requested topics.
> **No code, migrations, or final API schemas in this pass** — ordering and
> decision gates only. `safety/backend-gate-a-wip-2026-07-04` is **not** merged.
>
> **Ratification instrument:** every open decision referenced below lives in
> [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)
> (IDs `D-01`…`D-35`, grouped into **gates G0–G4 + the independent future
> sub-gates G5a (delivery) / G5b (ETA) / G5c (tables/payments)** plus scoped
> single-decision blockers). Slice 0 ratifies **per gate**: implementation of a
> slice unblocks only when *its* gate's **sign-off is recorded AND the approved
> decisions are promoted to ADRs and the next source-of-truth docs version** —
> a future sub-gate never blocks an unrelated earlier slice or a sibling
> sub-gate. All gates are currently **unsigned**; the
> **proposed** F&B catalog/recipe/costing target model lives in
> [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6, pending G1–G4 approval.
> Per R-M, **v3.6 stays authoritative until approved decisions are promoted**
> (ADRs → next PRD/FLOW/DOMAIN/DESIGN version).

---

## 1. Executive summary & verdict

SuperPOS is a **genuinely usable multi-tenant counter-POS with a credible ERP-lite
spine** (tenancy/RBAC, dynamic branches, warehouses with per-warehouse balances,
configurable payment routing, append-only AR/AP/cash **subsidiary** ledgers, atomic
settlement documents, create-and-post purchase invoices) — all tenant/branch-
isolated with append-only history, consumed by a React frontend on real APIs with
honest states.

The gaps to a reliable **F&B/accounting** system are additive net-new modules plus a
few bounded internal reworks, **not** a broken core: (1) the ledgers are
*subsidiary*, not a balanced double-entry **GL** — the target adds a
**ChartOfAccount** (full accounting ledger) as a separate concept from the
operational **FinancialAccount** (cash/bank/wallet/card-clearing), linked via
`gl_account`, with five permanent reconciliation identities
([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §1); (2) the **catalog is too flat**
for F&B (single category, fixed unit, no ProductUnit, no recipes/modifiers/size
variants) — the **proposed** target chain is **hierarchical SalesCategory
(«تندرج من») → typed Product → ProductVariant → RecipeVersion → RecipeLines**,
with a parallel hierarchical InventoryCategory
([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6, pending gates G1–G4); (3) **inventory authority** lives on a global
`Product.stock` counter with direct-mutation bypasses — the target authority is
per-warehouse `WarehouseStock` **denominated in the product base unit only**;
(4) the three requested capabilities — recipe size/modifier scaling,
delivery-platform gross-vs-commission, and e-invoicing compliance for the
**primary market, Egypt (ETA eReceipt/eInvoice)** — are unbuilt (ZATCA is kept
only as an optional future-market adapter). Low-risk hygiene debt (duplicate
`/api/auth`+`/api/accounts`, triple branch surface, sale int/uuid duality, direct
stock endpoints) is real but bounded.

Because every posted table is append-only and tenant-scoped and every new capability
slots in **beside** existing tables, the system evolves additively — **provided the
accounting/product architecture is ratified and frozen first, and no historical
balance is corrected without a document.** Posted documents are never "unposted":
undo is always a cancellation (pre-post) or a reversal/return document (post).

### Exact answer: **ADDITIVE EVOLUTION**
Not a rewrite; not a replacement of any bounded module. It carries a small, well-
contained set of REWORK items (catalog/units, inventory-balance authority,
GL-beside-subledgers) that remain additive at the schema level, plus controlled
DEPRECATION of duplicate/legacy routes and direct-mutation endpoints behind a
compatibility window. The only "replacement-shaped" area — the general ledger — is
satisfied by **adding** a double-entry layer over the existing posting engine, not
by discarding the subsidiary ledgers.

### First recommended implementation slice
**Slice 0 — Accounting & Product Architecture Ratification** (planning/decision,
freeze-gated): sign the decision gates in
[ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md) —
**G0 sales integrity → G1 catalog → G2 units/inventory → G3 costing/GL (incl.
D-31/D-35) → G4 recipe/production → G5a delivery · G5b ETA/compliance · G5c
tables/payments (three mutually independent future sub-gates)**. **A gate exits
— and its slices unblock — only when its sign-off is recorded AND its decisions
are promoted to ADRs and the next source-of-truth docs version** (not on
signature alone); the G5x sub-gates may stay open without blocking anything
earlier or each other.
Promoted decisions fold into the next
PRD/FLOW/DOMAIN/DESIGN version (R-M), so the audit never permanently conflicts
with v3.6. The first **safe code** slice immediately after is **Slice 1
— land Gate A component-by-component** (with migration `0017` replaced by the
dry-run provisioning workflow — see
[TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) §3), with the
**parallel quality slice P1 (frontend test framework)** starting at the same time.

### Freeze until ratified
`Product`/catalog schema changes; Category rework; COGS/GL/VAT posting; recipe/
modifier/variant models; delivery + Egypt ETA compliance work; and removal of
duplicate/direct-mutation endpoints. Master-data CRUD, reporting reads, route-dedup
planning, the P1 frontend-test slice, and the component-by-component Gate A review
may proceed in parallel.

---

## 2. Slice sequence

Each slice: **Goal · Depends on · Additive? · Key risk · Guardrail / exit test.**
"Add?" = only adds tables/fields/endpoints (Y) vs promote/deprecate (P).

| # | Slice | Goal | Depends on | Add? | Key risk | Guardrail / exit test |
|---|---|---|---|---|---|---|
| 0 | **Architecture ratification (per gate)** | Sign the gates in [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md) (D-01…D-35 grouped G0–G4 + G5a/b/c + scoped blockers): ChartOfAccount boundary, category split, ProductUnit, COGS/VAT rules, tax/discount/rounding policies, recipe/production parameters | — | doc | wrong north star | **Gate exit criteria = sign-off recorded AND decisions promoted to ADRs → next source-of-truth docs version**; only then are its slices (§3.0 of the register) unblocked — **v3.6 stays authoritative until that promotion**; no code. |
| 1 | **Land Gate A — component-by-component** | GA-1…GA-10 per the verdict table in [TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) §3.1; **migration `0017` replaced** by `provision_default_payment_routing --dry-run/--apply` + admin review (§3.2); strict routing lands only after all tenants are provisioned | 0 (D-14, D-15 for GA-3/GA-4) | P | blind provisioning; live branches stop selling | Dry-run reviewed per tenant before apply; full suite green; unrouted-branch sale → 400 only after provisioning verified. |
| **P1** | **Frontend test framework (parallel quality slice)** | Vitest + RTL; first tests: `parseApiError`, discount-math mirror, PaymentModal enable/labels, `RequireRole`; remove orphaned `mock.ts` | — (runs parallel with 1–2) | Y | none | `npm test` green in CI; `mock.ts` gone; build stays green. |
| 2 | **Sales idempotency** | Wire `idempotency.lookup/save` on `POST /sales/`; FE sends `Idempotency-Key` | 1 | Y | FE must send key | Replay test = one Sale; conflict = 409. |
| 3 | **Catalog units** | UnitGroup/Unit/ProductUnit/ProductBarcodeUnit; product base unit; **ProductUnit = conversion definitions only** — stock balances stay in base unit | 0 | Y | silent conversion | Seeded units are *proposals*; conversion tests. |
| 4 | **Category split (hierarchical)** | **Hierarchical SalesCategory** (self-parent «تندرج من») + **hierarchical InventoryCategory**; inheritable defaults (tax, revenue GL, COGS GL, station, POS visibility/sort · inventory-asset/wastage/adjustment/variance GL); resolution `product → child → nearest parent → tenant`; **snapshot-on-post** (R-J) | 0 (G1) | Y | auto-map GL accounts | Admin classifies; legacy `Category` read-only; category edits never alter posted history. |
| 5 | **Inventory authority** | Promote `WarehouseStock` (base-unit quantities) to authoritative; demote `Product.stock` to cache; replace direct-mutation endpoints with adjustment documents | 3 | P | derived ≠ global | Reconciliation report; mismatches → adjustment doc, never silent set. |
| 6 | **Costing/valuation engine (separate from GL)** | **Base-unit average cost** (home per **D-35** — base ProductUnit vs dedicated valuation record; scope per **D-09**; conversion units never carry independent averages); recipe cost = Σ(base-unit qty × avg-cost snapshot); costing + valuation reportable **before any JournalEntry exists** — COGS journal lines land only with Slice 7 | 3,5 (G3 — incl. D-31/D-35; never waits for G4) | Y | historical COGS | Forward-only; `SaleItem.unit_cost` snapshots preserved; snapshot shape per D-31. |
| 7 | **General Ledger** | **ChartOfAccount** (full ledger, separate from operational FinancialAccount) + JournalEntry + balanced JournalLine; `FinancialAccount.gl_account` mapping; posting engine writes GL + subledgers atomically; revenue/output-VAT/inventory/input-VAT legs | 0,4,6 | Y | imbalance / control drift | Forward-only + opening journal; **all five reconciliation identities hold** ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §1). |
| 8 | **Document numbering** | DocumentSequence / BranchDocumentSequence for all document types — **must precede compliance and the final return/invoice workflows** | 7 | Y | uniqueness | Per-tenant/type/branch sequence tests; gapless where a regime requires it. |
| 9 | **Purchase lifecycle** | Non-stock/expense/fixed-asset/service lines; input-VAT + inventory-GL legs; draft→post with **cancellation (pre-post) + reversal/return documents (post)** — never unpost; supplier-payment allocation/ageing | 7,8 | Y | double-count | Undo only via compensating documents; allocation tests. |
| 10 | **Sales returns / line-void / manager approval** | Sales-return document, line-level void, approval gate (`ApprovalStatus`) — all as reversal documents | 7,8 | Y | orphan reversals | Compensating ledger + GL entries; approval audit. |
| 11 | **Recipes / variants / modifiers** | ProductVariant (S/M/L, price, optional PLU — **no barcode**, R-K) + Recipe/RecipeVersion/RecipeLine (dated, statused, yield, per-variant quantities) + ModifierGroup/ModifierOption with price delta + per-variant **RecipeConsumptionDelta**; RECIPE_CONSUME depletion + immutable snapshots (R-J) | **3,5,6,7** (units, inventory authority, costing, GL — **not** table service) (G4) | Y | matrix complexity | See §3.1 + [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.6–§6.10; cycle check per D-27; snapshot tests. |
| 11b | **Production orders & sub-recipes** | ProductionOrder (warehouse, recipe version, planned/actual output, inputs, output item, **normal loss / abnormal wastage / production variance**, posted status + snapshots); raw → prep conversion for dough/sauce | 11 (G4: D-26…D-30, D-33) | Y | yield errors | Variance posts to production-variance account (D-29); loss classification per D-30. |
| 12 | **Delivery / channel revenue** | DeliveryChannel + commission model; gross revenue + separate commission posting; platform receivable/settlement | 7,8 (G5a — independent of G5b/G5c: **never waits for split payments or tables**) | Y | gross-vs-net | See §3.2; VAT base = gross. |
| 13 | **Egypt ETA eReceipt/eInvoice adapter** | Pluggable compliance-adapter layer; **primary adapter = Egypt ETA** (eReceipt B2C, eInvoice B2B); VAT ledger; ZATCA remains an optional future-market adapter only | **7,8 (eReceipt foundation); the return/credit/debit-note flow additionally requires Slice 10** (G5b — independent of G5a/G5c: **never waits for table service**) | Y | regulatory | See §3.3; gated on D-05 (ETA scope/timeline); credit-note part also gated on D-25; D-18 relevant only for service-charge-enabled tenants. |
| 14 | **Table service + shifts + KDS (deferred)** | DiningTable/Section, OpenOrder(+Line), send-to-kitchen, request-bill, pay→SalesInvoice, Shift, KitchenTicket; wire `pos/domain/statuses.py` | 2,7,8 (G5c: D-20 split payments + D-18) | Y | scope creep | API_CONTRACT §3 coverage; idempotency on all POSTs. Explicitly deferred — nothing else depends on it. |
| 15 | **Route dedup + deprecation removals** | Remove `/api/auth` dup, legacy branch surfaces, sale int-pk, direct-mutation POSTs | 5 | P | unknown client | Zero-traffic audit; separate slice. |
| 16 | **Reporting on GL + profitability** | Trial balance / P&L / balance sheet + branch/category analytics + the profitability set ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.13): theoretical recipe cost, period-level ingredient usage variance, gross profit/margin, food-cost %, contribution margin (fee set per scoped blocker D-32), **period net profit from the GL** | **Split deps: financial statements → 7; recipe profitability → 11/11b; channel analytics only → 12** (reporting never waits for delivery wholesale) | Y | perf | Reads posted data only; identities re-checked; gross profit never labeled net profit (R-L); per-sale cost stays theoretical (D-28). |
| 17 | **i18n + remaining cleanups** | Arabic for ERP pages; users pagination; schema regeneration from active branch | any | Y | — | Build + tests green. |

**Ordering rationale:** ratify per gate (G0 first — it alone unblocks the whole
sales-integrity track) → secure the money path (Gate A component-by-component +
sales idempotency, with the P1 test framework running in parallel from day one) →
build the catalog foundation (units, hierarchical categories) → make inventory
truthful (per-warehouse base-unit authority + the costing/valuation engine,
which is deliberately **separate from GL posting**) → stand up the GL →
**document numbering immediately after the GL and before anything that issues
formal documents** (returns, purchase lifecycle, compliance) → then the
financial-correctness-dependent modules (purchases, returns, **recipes/variants/
modifiers then production orders (11 → 11b) — which depend on
units/inventory/costing/GL, not on tables**, delivery, Egypt ETA, profitability
reporting). Table service/KDS stays deferred with no other slice depending on
it. Deprecation removals come only after clients have cut over.

---

## 3. Special topics (architecture-level, per stakeholder template)

> For each: **current-state gap · target-state conceptual model · affected existing
> models/APIs · accounting + inventory impact · migration considerations ·
> unresolved business decisions.** No code / migrations / final API schemas.
> v3.6 remains authority; the F&B doc is candidate research (conflicts D-03/D-06).

### 3.1 Dynamic recipe scaling by size variant + modifier (Slice 11)
- **Current-state gap:** none built. `Product` is flat (no `product_type`, no
  ProductUnit, no recipe/BOM/modifier/variant). `StockMovement` names no
  RECIPE_CONSUME writer. COGS not posted. v3.6 scopes recipes/modifiers to Phase 2;
  DOMAIN §1.2/§7.2 name modifiers + RECIPE_CONSUME as concepts only.
- **Target-state conceptual model (proposed — [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6, pending gate G4):**
  hierarchical SalesCategory («تندرج من») → Product (`product_type=recipe_product`)
  → **ProductVariant** (S/M/L, price, optional PLU — **no barcode**, never via
  ProductBarcodeUnit) → **RecipeVersion** (dated, statused, yield, one per
  variant — no single scale multiplier) → **RecipeLines** (component base-unit
  quantities + normal-loss/yield factor + source warehouse/role). ModifierGroup/
  ModifierOption carry a price delta + per-variant **RecipeConsumptionDelta**
  (extra cheese: S +40 g / M +60 g / L +80 g). Consumption modes: **kit / instant
  depletion** at sale, **ProductionOrder (WIP)** for prep items (Slice 11b).
  All depletion in the **product base unit** against per-warehouse balances;
  posted documents store **immutable recipe/cost snapshots** (R-J).
- **Affected existing models/APIs:** `Product` (+`product_type`, recipe flags),
  `SaleItem` (variant/modifier selection), `StockMovement` (RECIPE_CONSUME),
  `Category` (→ SalesCategory menu grouping), POS product/scan endpoints, the pay/
  checkout flow.
- **Accounting + inventory impact:** sale of a recipe item depletes raw ProductUnit
  base-unit stock (per warehouse) and posts COGS = Σ(component qty × avg_cost ×
  yield) to the GL; **gross profit = net revenue − COGS; gross margin = gross
  profit ÷ net revenue** (net revenue = selling price excluding VAT).
- **Migration considerations:** depends on ProductUnit (Slice 3), inventory
  authority (5), COGS (6), GL (7) — **and NOT on table service/KDS (Slice 14)**;
  recipes are fully buildable for counter sales. No back-population of historical
  sales into recipes.
- **Unresolved business decisions (gate G4):** kit vs manufacturing-order per
  product (D-06); sub-recipe nesting depth (D-26); circular-recipe prevention
  (D-27); theoretical vs actual consumption (D-28); production yield/variance
  (D-29); normal vs abnormal loss (D-30); snapshot representation (D-31);
  prep shelf-life (D-33); free-modifier COGS (D-34); modifier price/cost
  ownership (D-23); size = variant-of-one-product (D-24, recommended).

### 3.2 Delivery-platform accounting: gross sales vs commission (Slice 12)
- **Current-state gap:** none. Only in-store payment methods exist; no channel,
  platform, commission, or receivable model. v3.6 does not specify delivery
  accounting (card fees/commission = Phase 2).
- **Target-state conceptual model:** DeliveryChannel/Platform (Talabat, elmenus,
  Jahez, HungerStation, …) with a commission config (percent/fixed). Per the F&B
  doc: **book the full invoice as gross taxable revenue**, then post the platform
  **commission separately** as contra-revenue or direct marketing expense;
  recognize a **platform receivable** (operational clearing FinancialAccount
  linked to its GL account) cleared on payout **settlement/reconciliation**.
- **Affected existing models/APIs:** `Sale` (channel + platform link),
  `PaymentMethod`/`BranchPaymentMethod` (a platform "method" routing to the
  platform-receivable account), `FinancialAccount` (new operational receivable
  account linked via `gl_account`), movement types + GL journal legs.
- **Accounting + inventory impact:** VAT base = **gross** (not net) — the
  correctness fix the F&B doc calls out; commission reduces margin, not revenue;
  inventory depletes normally at sale time.
- **Migration considerations:** depends on GL (7) + DocumentSequence (8). Additive;
  no change to historical in-store sales.
- **Unresolved business decisions:** gross-vs-net confirmation (D-03); commission
  as contra-revenue vs expense; per-platform commission tiers; payout
  reconciliation cadence + tolerance; VAT treatment of the commission itself.

### 3.3 E-invoicing compliance — **Egypt ETA eReceipt/eInvoice (primary)** (Slice 13)
- **Current-state gap:** **zero.** No e-invoicing integration of any kind; only
  `vat_number` fields and a QR-on-receipt notion. Neither v3.6 nor the F&B doc
  specifies a regime. **Egypt is the primary market** (stakeholder-ratified;
  Tenant defaults `EGP`/`Africa/Cairo`).
- **Target-state conceptual model:** a **pluggable compliance-adapter layer** with
  the **Egypt ETA adapter** as the primary implementation:
  - **eReceipt** (B2C POS): receipt UUID, POS serial/device registration with ETA,
    signed receipt submission, customer-facing QR;
  - **eInvoice** (B2B): structured invoice submission, ETA UUID/long-ID,
    notarization/validation flow, credit/debit-note documents for returns;
  - shared: document UUID + hash, sequential numbering from DocumentSequence
    (Slice 8), signing/credential management, submission-state machine
    (pending/submitted/valid/invalid/cancelled), retry/outbox.
  **ZATCA (KSA — PIH hash chain, CSID, TLV QR, clearance/reporting) is retained
  only as an optional future-market adapter** behind the same interface; it is
  not scheduled.
- **Affected existing models/APIs:** `Sale`/SalesInvoice (compliance payload +
  immutable numbering + submission state), `Tenant`/`Branch` (ETA registration,
  POS serials, credentials), GL (output/input-VAT accounts), a **new compliance
  context** + integration client; returns (Slice 10) must emit credit notes.
- **Accounting + inventory impact:** output-VAT posted at sale; input-VAT at
  purchase (closes the deferred purchase-tax gap); VAT payable = output − input in
  the GL; no direct inventory impact.
- **Migration considerations:** forward-only; historical sales are not
  retro-submitted. The **eReceipt foundation depends on GL (7) + DocumentSequence
  (8)**; the **return/credit/debit-note flow additionally depends on Sales
  Returns (Slice 10)** — it cannot ship before a return document exists.
- **Unresolved business decisions (D-05):** ETA taxpayer profile + onboarding
  ownership (tenant vs platform); eReceipt vs eInvoice phase timeline for the
  target tenants; signing/HSM approach; which additional markets (ZATCA/KSA) ever
  get an adapter — **regulatory, gates the slice.**

---

## 4. Consolidated unresolved business decisions

**Moved to [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)**
— the single signable register (D-01…D-35, grouped into gates G0–G4 + the
independent G5a/G5b/G5c sub-gates and scoped blockers, per R-M)
covering: category split, GL depth, delivery gross-vs-commission, card terminal,
Egypt ETA scope, recipe model, costing field, inventory valuation accounts,
**moving-average cost scope**, tax inclusive/exclusive, discount-before/after-tax,
rounding, decimal precision, credit-limit null/zero, negative-stock override,
fiscal periods, opening cutover date, tips/service charge/complimentary,
batch/expiry, split payments, route cutover window, opening-balance conversion,
and the new recipe/production set (sub-recipe depth, cycle prevention,
theoretical-vs-actual, yield/variance, loss classification, snapshots,
contribution-margin fees, prep shelf-life, free-modifier COGS). Slice 0 =
per-gate sign-off of that file; signed gates promote to ADRs → next
PRD/FLOW/DOMAIN/DESIGN version.

---

## 5. Confirmation — no runtime code changed
This audit (and this ratification revision) read the current branch, git history,
the OpenAPI schema ([SuperPOS API.yaml](SuperPOS%20API.yaml) — noting it was
generated from Gate A WIP code and is ahead of the mvp runtime), the frontend, the
backend, the tests, and the
`mvp/counter-cafe-demo-readiness...safety/backend-gate-a-wip-2026-07-04` diff, and
produced **only** Markdown deliverables. **No** runtime code, migrations, database,
tests, or frontend were modified, and
**`safety/backend-gate-a-wip-2026-07-04` was not merged.**

Companion docs: [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) ·
[END_TO_END_WORKFLOW_STATUS.md](END_TO_END_WORKFLOW_STATUS.md) ·
[API_AND_MODEL_INVENTORY.md](API_AND_MODEL_INVENTORY.md) ·
[KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md) ·
[TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) ·
[TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) ·
[ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)
