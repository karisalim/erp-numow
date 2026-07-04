# IMPLEMENTATION_ROADMAP.md

> **Read-only architecture audit — 7 of 7.** The sequenced, freeze-gated slice plan
> to reach a reliable F&B/accounting system, plus the architecture-level treatment
> of the three specially-requested topics. **No code, migrations, or final API
> schemas in this pass** — this is the ordering and the decision gates only.
> `safety/backend-gate-a-wip-2026-07-04` is **not** merged.

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
*subsidiary*, not a balanced double-entry **GL** (no revenue/COGS/VAT legs → no
trial balance); (2) the **catalog is too flat** for F&B (single category, fixed
unit, no ProductUnit, no recipes/modifiers/size variants); (3) **inventory
authority** lives on a global `Product.stock` counter with direct-mutation
bypasses; (4) the three requested capabilities — recipe size/modifier scaling,
delivery-platform gross-vs-commission, ZATCA Phase 2 — range from unbuilt to
entirely absent (ZATCA is unmentioned in v3.6). Low-risk hygiene debt (duplicate
`/api/auth`+`/api/accounts`, triple branch surface, sale int/uuid duality, direct
stock endpoints) is real but bounded.

Because every posted table is append-only and tenant-scoped and every new capability
slots in **beside** existing tables, the system evolves additively — **provided the
accounting/product architecture is ratified and frozen first, and no historical
balance is corrected without a document.**

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
freeze-gated): ratify the target chart of accounts and the subledger-vs-GL boundary,
the Sales/Inventory category split, the ProductUnit/UnitGroup model, and the
COGS/inventory-GL/VAT posting rules — resolving conflict register CR-1…CR-8 in
[TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md). Nothing downstream is safe until this
is frozen. The first **safe code** slice immediately after is **Slice 1 — land Gate
A** (self-contained, already implemented).

### Freeze until ratified
`Product`/catalog schema changes; Category rework; COGS/GL/VAT posting; recipe/
modifier/variant models; delivery + ZATCA; and removal of duplicate/direct-mutation
endpoints. Master-data CRUD, reporting reads, route-dedup planning, and the Gate A
review may proceed in parallel.

---

## 2. Slice sequence

Each slice: **Goal · Depends on · Additive? · Key risk · Guardrail · Exit test.**
"Additive?" = does it only add tables/fields/endpoints (Y) vs promote/deprecate (P).

| # | Slice | Goal | Depends on | Add? | Key risk | Guardrail / exit test |
|---|---|---|---|---|---|---|
| 0 | **Architecture ratification** | Freeze chart of accounts, subledger↔GL boundary, category split, ProductUnit, COGS/VAT rules (CR-1…CR-8) | — | doc | wrong north star | Signed decisions per conflict; no code. |
| 1 | **Land Gate A** | Strict sales routing, credit limit, negative-stock policy, env config, backfill `0017` | 0 (routing rules) | P | backfill provisions wrong accounts | Review per-tenant naming; full test suite green; trial: unrouted branch → 400. |
| 2 | **Sales idempotency** | Wire `idempotency.lookup/save` on `POST /sales/` | 1 | Y | FE must send key | Replay test = one Sale; conflict = 409. |
| 3 | **Catalog units** | UnitGroup/Unit/ProductUnit/ProductBarcodeUnit; product base unit | 0 | Y | silent conversion | Seeded units are *proposals*; conversion tests. |
| 4 | **Category split** | SalesCategory + InventoryCategory (+ revenue/asset account links) | 0 | Y | auto-map GL accounts | Admin classifies; legacy `Category` read-only. |
| 5 | **Inventory authority** | Promote `WarehouseStock` to authoritative; demote `Product.stock` to cache; deprecate direct-mutation endpoints → adjustment documents | 3 | P | derived ≠ global | Reconciliation report; mismatches → adjustment doc, never silent set. |
| 6 | **COGS + moving-average on ProductUnit** | `ProductUnit.avg_cost`; COGS leg at sale post | 3,5 | Y | historical COGS | Forward-only; `SaleItem.unit_cost` snapshots preserved. |
| 7 | **General Ledger** | ChartOfAccount + JournalEntry + balanced JournalLine; posting engine writes GL + subledgers atomically; revenue/output-VAT/inventory/input-VAT legs | 0,4,6 | Y | imbalance | Forward-only + opening journal; trial balance = Σ subledgers. |
| 8 | **Purchase lifecycle** | Non-stock lines, draft/unpost, purchase return, input-VAT + inventory-GL debit, payment allocation/ageing | 7 | Y | double-count | Reversal via compensating doc; allocation tests. |
| 9 | **Returns / line-void / manager approval** | Sales-return document, line-level void, approval gate (`ApprovalStatus`) | 7 | Y | orphan reversals | Compensating ledger + GL; approval audit. |
| 10 | **Table service + shifts + KDS (MVP)** | DiningTable/Section, OpenOrder(+Line), send-to-kitchen, request-bill, pay→SalesInvoice, Shift, KitchenTicket; wire `pos/domain/statuses.py` | 2,7 | Y | scope creep | API_CONTRACT §3 coverage; idempotency on all POSTs. |
| 11 | **Recipes / modifiers / size variants** | Parent item + SizeVariant + ModifierGroup/Modifier + Recipe(BOM) + size×modifier depletion matrix; RECIPE_CONSUME + COGS | 3,6,7,10 | Y | matrix complexity | See §3.1; yield-factor tests. |
| 12 | **Delivery / channel revenue** | DeliveryChannel + commission model; gross revenue + separate commission posting; platform receivable/settlement | 7 | Y | gross-vs-net | See §3.2; VAT base = gross. |
| 13 | **ZATCA Phase 2 e-invoicing** | Compliant invoice (UUID, hash chain, CSID, TLV QR, counter), clearance/reporting, VAT ledger | 7 | Y | regulatory | See §3.3; scope gated on market/timeline. |
| 14 | **Route dedup + deprecation removals** | Remove `/api/auth` dup, legacy branch, sale int-pk, direct-mutation POSTs | 5 | P | unknown client | Zero-traffic audit; separate slice. |
| 15 | **Reporting on GL** | Trial balance / P&L / balance sheet + branch/channel/category analytics | 7,12 | Y | perf | Reads posted data only. |
| 16 | **Document numbering + lookups** | DocumentSequence/BranchDocumentSequence; tenant lookups | 7 | Y | uniqueness | Per-tenant/type sequence tests. |
| 17 | **Frontend test framework + i18n + cleanups** | Vitest+RTL; Arabic for ERP pages; drop `mock.ts`; users pagination | parallel | Y | — | First tests green. |

**Ordering rationale:** ratify → secure the money path (Gate A + idempotency) →
build the catalog foundation (units, categories) → make inventory truthful (per-
warehouse + COGS) → stand up the GL → then everything financial-correctness-
dependent (purchases, returns, table service, recipes, delivery, ZATCA, reporting)
flows from the GL. Deprecation removals come only after clients have cut over.

---

## 3. Special topics (architecture-level, per stakeholder template)

> For each: **current-state gap · target-state conceptual model · affected existing
> models/APIs · accounting + inventory impact · migration considerations ·
> unresolved business decisions.** No code / migrations / final API schemas.
> v3.6 remains authority; F&B doc is candidate research (conflicts CR-3/CR-6).

### 3.1 Dynamic recipe scaling by size variant + modifier (Slice 11)
- **Current-state gap:** none built. `Product` is flat (no `product_type`, no
  ProductUnit, no recipe/BOM/modifier/variant). `StockMovement` names no
  RECIPE_CONSUME writer. COGS not posted. v3.6 scopes recipes/modifiers to Phase 2;
  DOMAIN §1.2/§7.2 name modifiers + RECIPE_CONSUME as concepts only.
- **Target-state conceptual model:** ParentMenuItem (a `Product` of
  `product_type=recipe`) → SizeVariant (small/medium/large) → ModifierGroup →
  Modifier. A **Recipe/BOM** links each (variant, modifier) to raw `ProductUnit`
  quantities via a **Size Mapping Matrix** (extra-cheese = 40 g small / 80 g large).
  Two consumption modes (F&B doc): **kit / instant depletion** at sale time, or
  **manufacturing order (WIP)** for pre-prepared sub-recipes. Apply a **yield/
  wastage factor** per line; value via AVCO.
- **Affected existing models/APIs:** `Product` (+`product_type`, recipe flags),
  `SaleItem` (variant/modifier selection), `StockMovement` (RECIPE_CONSUME),
  `Category` (→ SalesCategory menu grouping), POS product/scan endpoints, the pay/
  checkout flow.
- **Accounting + inventory impact:** sale of a recipe item depletes raw ProductUnit
  stock (per warehouse) and posts COGS = Σ(component qty × avg_cost × yield); menu
  margin computed from gross price − COGS − VAT.
- **Migration considerations:** depends on ProductUnit (Slice 3), inventory
  authority (5), COGS (6), GL (7). No back-population of historical sales into
  recipes.
- **Unresolved business decisions:** kit vs manufacturing-order per product; sub-
  recipe depth; where modifier **price** and **cost** live; yield-factor governance;
  whether size is a variant of one product or separate SKUs.

### 3.2 Delivery-platform accounting: gross sales vs commission (Slice 12)
- **Current-state gap:** none. Only in-store payment methods exist; no channel,
  platform, commission, or receivable model. v3.6 does not specify delivery
  accounting (card fees/commission = Phase 2).
- **Target-state conceptual model:** DeliveryChannel/Platform (Jahez/HungerStation/
  Talabat…) with a commission config (percent/fixed). Per F&B doc: **book the full
  invoice as gross taxable revenue**, then post the platform **commission separately**
  as contra-revenue or direct marketing expense; recognize a **platform receivable**
  cleared on payout **settlement/reconciliation**.
- **Affected existing models/APIs:** `Sale` (channel + platform link), `PaymentMethod`/
  `BranchPaymentMethod` (a platform "method" routing to a platform-receivable
  account), `FinancialAccount` (new receivable + commission-expense types),
  movement types + GL.
- **Accounting + inventory impact:** VAT base = **gross** (not net) — this is the
  correctness fix the F&B doc calls out; commission reduces margin, not revenue;
  inventory depletes normally at sale time.
- **Migration considerations:** depends on GL (Slice 7). Additive; no change to
  historical in-store sales.
- **Unresolved business decisions:** gross-vs-net policy confirmation (F&B mandates
  gross); commission as contra-revenue vs expense; per-platform commission tiers;
  payout reconciliation cadence + tolerance; VAT treatment of the commission itself.

### 3.3 ZATCA Phase 2 e-invoicing compliance (Slice 13)
- **Current-state gap:** **zero.** No literal ZATCA anywhere; only `vat_number`
  (tenant/branch/party) and a QR-on-receipt notion. v3.6 does not mention ZATCA;
  the F&B doc addresses VAT (output/input) and IFRS but not the Phase-2 cryptographic
  requirements.
- **Target-state conceptual model:** a compliant invoice representation carrying the
  ZATCA Phase 2 essentials — invoice **UUID**, **previous-invoice-hash (PIH) chain**,
  **cryptographic stamp / CSID** (device onboarding), **TLV QR**, monotonic
  **invoice counter (ICV)** — plus **clearance** (B2B) / **reporting** (B2C)
  integration and an **output/input-VAT ledger**.
- **Affected existing models/APIs:** `Sale`/SalesInvoice (compliance fields +
  immutable numbering), `Tenant`/`Branch` (VAT registration + device credentials),
  GL (VAT accounts), a **new compliance context** + integration client.
- **Accounting + inventory impact:** output-VAT posted at sale; input-VAT at purchase
  (closes the deferred purchase-tax gap); no direct inventory impact.
- **Migration considerations:** forward-only; historical sales are not retro-stamped.
  Large; depends on GL (7) and immutable document numbering (16).
- **Unresolved business decisions:** **is KSA/ZATCA in scope at all**, and by when?
  Phase (generation vs full clearance/reporting integration)? Certificate/device
  onboarding ownership (tenant vs platform)? Which markets beyond KSA? — **regulatory,
  unresolved; gates the slice.**

---

## 4. Consolidated unresolved business decisions
Category split model + revenue/asset account mapping (CR-1) · GL depth for
"ERP-lite" (CR-2) · COGS timing + inventory valuation account (CR-8) · input/output-
VAT posting rules · returns/line-void/manager-approval model · split/mixed payment
(`PaymentLine[]`) · opening-balance-as-document conversion · recipe kit-vs-MO +
sub-recipes + yield policy (CR-6) · delivery gross-vs-net + per-platform commission
+ payout reconciliation (CR-3) · ZATCA scope/market/timeline/ownership (CR-5) ·
route-deprecation cutover window · `InventoryBatch`/batch-expiry keep-or-drop.

---

## 5. Confirmation — no runtime code changed
This audit read the current branch, git history, the OpenAPI schema
([SuperPOS API.yaml](SuperPOS%20API.yaml)), the frontend, the backend, the tests,
and the `mvp/counter-cafe-demo-readiness...safety/backend-gate-a-wip-2026-07-04`
diff, and produced **only** the seven Markdown deliverables. **No** runtime code,
migrations, database, tests, or frontend were modified, and
**`safety/backend-gate-a-wip-2026-07-04` was not merged.**

Companion docs: [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) ·
[END_TO_END_WORKFLOW_STATUS.md](END_TO_END_WORKFLOW_STATUS.md) ·
[API_AND_MODEL_INVENTORY.md](API_AND_MODEL_INVENTORY.md) ·
[KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md) ·
[TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) ·
[TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md)
