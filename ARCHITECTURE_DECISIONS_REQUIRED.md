# ARCHITECTURE_DECISIONS_REQUIRED.md

> **The ratification instrument (deliverable 8 of the architecture audit).**
> Every unresolved business/architecture decision (D-01…D-35), with the current
> behavior it affects, options, a recommendation with trade-offs, an owner, and
> the roadmap slices it blocks. **A decision may carry a *selected option* (with
> consultation provenance in its Status cell and §3.5) while its *gate remains
> Open* — selection ≠ gate exit. Nothing in the proposed target architecture is
> ratified, and no implementation is unblocked, until the gate exits: all
> required approvals recorded here AND its decisions promoted to ADRs + the next
> source-of-truth docs version (R-M).** Decisions are
> grouped into **gates G0–G4 plus the independent future sub-gates G5a/G5b/G5c**
> (§3.0); implementation of a slice unblocks only when *its* gate's **sign-off
> is recorded AND the approved decisions have been promoted to ADRs and the
> next source-of-truth docs version** —
> a future gate never blocks an unrelated earlier slice, and four decisions are
> **scoped single-decision blockers** that gate only one narrowly-defined
> capability. IDs are append-only: new decisions are added after the highest
> existing ID and **existing IDs are never renumbered**.
> Documentation only — no runtime code, migrations, DB, tests, or frontend were
> changed; `safety/backend-gate-a-wip-2026-07-04` remains unmerged.
>
> Companions: [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) (conflict register
> CR-1…CR-8 ↔ D-01…D-08) · [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)
> (slice numbers referenced in "Blocks") ·
> [TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) (Gate A
> per-component verdicts GA-1…GA-10).

## 1. Owner roles

| Code | Role |
|---|---|
| **BO** | Business Owner (product/priorities) |
| **FA** | Finance / Accounting advisor (policy correctness) |
| **EN** | Engineering lead (feasibility, migration) |
| **RC** | Regulatory / Compliance (tax authority requirements) |

## 2. Already-ratified directives (recorded 2026-07-04 — for traceability, no signature needed)

| ID | Ratified rule |
|---|---|
| R-A | **Egypt is the primary market.** Primary compliance slice = **Egypt ETA eReceipt/eInvoice adapter**; ZATCA (KSA) is kept only as an optional future-market adapter. |
| R-B | **`WarehouseStock` stores quantity in the product base unit only.** `ProductUnit` represents conversions; separate stock balances per conversion unit are never stored. (MASTER_DATA_CONTRACT §5 wording to be aligned.) |
| R-C | **Posted documents are never "unposted."** Undo = cancellation (pre-post) or reversal/return document (post) with compensating entries. |
| R-D | **FinancialAccount ≠ ChartOfAccount.** FinancialAccount = operational cash/bank/wallet/card-clearing account; ChartOfAccount = the full accounting ledger; every FinancialAccount links to a GL account (`gl_account`). |
| R-E | **Reconciliation identities** ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §1): balanced journals; AR/AP controls = subledger totals; inventory control = valuation; cash/bank GL = operational subledgers. |
| R-F | **Gate A is reviewed component-by-component; migration `0017` is NOT approved as-is** — replaced by a dry-run provisioning command + admin review ([TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) §3.2). |
| R-G | **Recipes depend on units/inventory-authority/costing/GL — not on tables/KDS.** Table service stays deferred. |
| R-H | **DocumentSequence precedes compliance and final return/invoice workflows.** |
| R-I | **Frontend test framework starts early as a parallel quality slice (P1).** |
| R-J | **Category-default inheritance + snapshot-on-post.** SalesCategory/InventoryCategory are hierarchical (self-parent «تندرج من»); defaults resolve `product override → child category → nearest parent → tenant default`; the resolved tax/account values are snapshotted on posted documents — later category or recipe/cost edits never alter historical transactions ([TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.2/§6.7). |
| R-K | **Variants are menu/PLU-first; barcode-free.** Pizza/menu recipe products require no barcode; the primary POS flow is category/menu selection (optional PLU). SizeVariant is never forced through ProductBarcodeUnit, which exists only for packaged/purchase/retail units (§6.5/§6.6). |
| R-L | **Gross profit is never called "net profit."** Period net profit exists only at the GL level after rent, salaries, utilities, marketing, depreciation, and other operating expenses (§6.8/§6.13). |
| R-M | **Decision-gate governance + ADR promotion.** Decisions are grouped into **gates G0–G4 plus the independent future sub-gates G5a/G5b/G5c** (§3.0) so future choices never block unrelated earlier slices. **Promotion is part of each gate's exit criteria:** a gate exits — and implementation of its slices unblocks — only when sign-off is recorded **and** the approved decisions are promoted into ADR documents and folded into the next PRD/FLOW/DOMAIN/DESIGN version. **v3.6 remains the authoritative business source of truth until that promotion happens** — an approved-but-unpromoted decision governs implementation planning only, never overrides v3.6 silently. |

## 3. Open decisions — signed per gate

> Columns: current behavior/context (with code refs) · options · recommendation
> **with trade-offs** · owner · blocking slices · status.

### 3.0 Decision gates (R-M) — which decisions block which slices

| Gate | Name | Decision IDs | Unblocks slices |
|---|---|---|---|
| **G0** | Sales integrity (immediate) | D-14, D-15 | 1 (Gate A GA-3/GA-4), 2 |
| **G1** | Catalog & category | D-01 | 4 (and feeds 11) |
| **G2** | Units & inventory | D-13 | 3, 5 |
| **G3** | Costing & GL | D-02, D-07, D-08, D-09, D-10, D-11, D-12, D-16, D-17, D-22, **D-31** (cross-referenced by G4), **D-35** (decided with D-07) | 6, 7, 8, 9, 10, and the **financial-statement part of 16** — costing (Slice 6) never waits for the recipe/production gate |
| **G4** | Recipe / variants / production | D-06, D-23, D-24, D-26, D-27, D-28, D-29, D-30, D-33, D-34 | 11, 11b (and the **recipe-profitability part of 16**) |
| **G5a** | Future: Delivery | D-03 | 12 only |
| **G5b** | Future: ETA / Compliance | D-05 (D-18 relevant **only if** service charge is enabled; D-25 remains the scoped credit-note blocker) | 13 only |
| **G5c** | Future: Tables / Payments | D-20, D-18 | 14 only |
| — | Confirmation-only | D-04 (card stays manual in MVP) | blocks **no** slice; scoped to future card-terminal work |

**Scoped single-decision blockers** (block exactly one narrowly-defined
capability, nothing else):

| ID | Blocks only |
|---|---|
| D-19 | **Deferred** batch/expiry/FEFO decision — blocks only a future batch-tracking slice; `InventoryBatch` stays dormant meanwhile. G2 is NOT blocked by it. |
| D-21 | Route-deprecation removals (Slice 15) only. |
| D-25 | Sales Returns (Slice 10) and the ETA credit-note flow inside Slice 13 only. |
| D-32 | The contribution-margin report inside Slice 16 only — GL, numbering, purchases, and returns proceed without it. (Decided alongside G3; informs Slice 12.) |

**Rule (gate exit criteria, R-M):** a gate exits — and implementation of its
slices starts — only when **(1) sign-off is recorded in §4 AND (2) the approved
decisions are promoted to ADRs and folded into the next PRD/FLOW/DOMAIN/DESIGN
version**. Exiting G0 alone unblocks the entire sales-integrity track; the G5x
sub-gates are mutually independent — **Delivery (G5a) never waits for split
payments (G5c), and ETA (G5b) never waits for table service (G5c)** — and none
of them can block anything in G0–G4. **v3.6 stays authoritative until each
gate's promotion completes** (R-M).

### 3.1 Structural (from conflict register CR-1…CR-8)

| ID | Decision | Current behavior / context | Options | Recommendation + trade-offs | Owner | Blocks | Status |
|---|---|---|---|---|---|---|---|
| D-01 | Category split: Sales vs Inventory trees + GL links | Flat `Category(tenant,name)` ([pos/models.py:25](superpos_backend/pos/models.py#L25)); v3.6 has one POS category; F&B doc splits menu vs stock categories with revenue/asset account links | (a) keep single tree; (b) **split SalesCategory + InventoryCategory** | **(b)** — separates menu grouping from stock/GL classification; additive; admin reclassifies (no auto-map). Trade-off: reclassification effort per tenant. | BO+FA | 4, 7, 11 | Open |
| D-02 | GL depth for "ERP-lite" | v3.6: full GL = Phase 2; subledgers only today; F&B doc: full USAR chart now | (a) subledgers only; (b) **phase GL forward-only per Slice 7**; (c) full USAR now | **(b)** — trial balance capability without blocking MVP; opening journal, no retro-explosion. Trade-off: historical periods stay subledger-only. **Consultation (2026-07-05):** accountant confirmed the need for P&L, assets, liabilities, journals and complete financial movements; introduce the complete GL **forward-only as a separate phased slice, beside** the existing treasury/AR/AP subsidiary ledgers. **Do not hardcode a USAR chart or account numbering yet — the restaurant chart/template stays subject to later accountant review.** | FA | 7 | **Selected: Option B (2026-07-05 consultation). Gate G3 Open.** |
| D-03 | Delivery platforms: gross vs net + commission classification | Nothing modeled; F&B doc mandates gross revenue + separate commission | (a) book net payout; (b) **gross revenue, commission separate** (contra-revenue or expense) | **(b)** — correct VAT base + honest revenue; requires platform receivable + payout reconciliation (cadence/tolerance to define here). Trade-off: more posting complexity. | FA+BO | 12 | Open |
| D-04 | Card handling stays manual in MVP | v3.6: card recorded manually; terminal integration Phase 2 | (a) confirm manual; (b) pull integration forward | **(a)** — keep v3.6; automate settlement/commission with GL slice. | BO | — (confirm) | Open |
| D-05 | Egypt ETA scope/timeline/ownership | Zero e-invoicing today; Egypt ratified as primary market (R-A) | Scope: eReceipt only vs eReceipt+eInvoice; onboarding owned by tenant vs platform; timeline | **eReceipt (B2C POS) first**, eInvoice (B2B) second; platform-assisted onboarding with tenant-owned credentials. Trade-off: platform-assisted = support burden; tenant-owned = onboarding friction. | RC+BO | 13 | Open |
| D-06 | Recipe consumption mode + yield governance | No recipes; F&B doc: kit (instant depletion) vs manufacturing order (WIP) + yield factor | (a) kit-only MVP; (b) kit + MO for sub-recipes; (c) MO-only | **(b)** — kit for made-to-order items, MO for batch prep (dough) matches café reality. Trade-off: MO adds WIP accounting. Yield factors owned by Ops with FA review. | BO+FA | 11 | Open |
| D-07 | Moving-average cost field location | AVCO currently on `Product.cost` ([purchase_invoices.py:68](superpos_backend/pos/services/purchase_invoices.py#L68)); ProductUnit doesn't exist yet | (a) stay on Product.cost; (b) move the base-unit average cost off `Product.cost` | **(b)** — cost must live where quantity truth lives (the base unit). **Refined by D-35**, which decides the exact home (base ProductUnit vs a dedicated valuation record); either way `ProductUnit` remains primarily a conversion definition and `Product.cost` is kept as a mirror during transition. | EN+FA | 6 | Open |
| D-08 | Inventory valuation accounts | No inventory GL; purchase posts no inventory debit (documented deferral) | (a) one inventory account per tenant; (b) **per InventoryCategory asset account** | **(b)** — F&B-doc pattern (food/beverage/packaging split) enables cost-percentage reporting; requires D-01. Trade-off: more mapping upkeep. | FA | 7 (with 4) | Open |

### 3.2 Accounting policy (stakeholder-required additions)

| ID | Decision | Current behavior / context | Options | Recommendation + trade-offs | Owner | Blocks | Status |
|---|---|---|---|---|---|---|---|
| D-09 | **Moving-average cost scope** | Single tenant-wide average implied by `Product.cost`; no transfers exist yet | (a) **tenant-wide**; (b) branch-wide; (c) warehouse-specific | **(a) tenant-wide for MVP** — matches current mechanics, zero transfer-pricing complexity, one average to audit. Trade-offs: (a) blurs branch P&L when purchase prices differ per branch; (b) branch P&L accuracy but needs inter-branch transfer costing; (c) most precise (damage/production bins) but thin per-warehouse data → volatile averages + heavy transfer logic. **Upgrade trigger:** revisit to (b) when WarehouseTransfer documents land. **Consultation (2026-07-05):** one tenant/company-wide moving-average per product for MVP; **branch profitability must still be reported separately**, and the consolidated company report combines all branches **without hiding a losing branch inside company totals**. Upgrade trigger to branch-level costing remains WarehouseTransfer maturity. | FA | 6, 7, 11 | **Selected: Option A for MVP (2026-07-05 consultation). Gate G3 Open.** |
| D-10 | Tax inclusive vs exclusive pricing | **Exclusive today**: `total = subtotal + tax − discount` ([pos/serializers.py:675-693](superpos_backend/pos/serializers.py#L675-L693)); `Product.tax_rate` default 10% (Egypt standard VAT is 14%) | (a) exclusive storage + exclusive display; (b) **exclusive storage + optional inclusive display**; (c) inclusive storage | **(b)** — keeps ledger math clean while menus can show inclusive prices (Egyptian retail norm). Trade-off: display-rounding reconciliation. Also fix default tax rate per tenant. **Consultation (2026-07-05):** store net/tax-exclusive values separately and allow customer-facing menu/display prices to be tax-inclusive; **do not hardcode 14% globally — tax stays configurable through tax profiles.** | FA+BO | 7, 13 | **Selected: Option B (2026-07-05 consultation). Gate G3 Open.** |
| D-11 | Discount before or after tax | **After tax today** — percent discount computed on subtotal and subtracted from `subtotal + tax`, so the **tax base is NOT reduced by the discount** ([pos/serializers.py:686-693](superpos_backend/pos/serializers.py#L686-L693)) | (a) keep discount-after-tax; (b) **discount-before-tax (reduce taxable base)** | **(b)** — VAT should be levied on the actual consideration; current behavior over-collects VAT on discounted sales and would fail ETA validation. Trade-off: behavior change needs a dated cutover + FE mirror update. **Consultation (2026-07-05):** discount reduces the taxable base **first**, then tax is calculated on the net amount — **Finance-approved by the accountant. Regulatory/ETA (RC) confirmation remains pending; do NOT treat D-11 as fully ratified until RC approval is recorded.** | FA+RC | 7, 13 | **Selected: Option B — Finance-approved (2026-07-05); Regulatory/ETA (RC) approval PENDING → NOT fully ratified. Gate G3 Open.** |
| D-12 | Rounding policy | Inconsistent: purchases quantize `ROUND_HALF_UP` to 0.01 ([purchase_invoices.py:56](superpos_backend/pos/services/purchase_invoices.py#L56)); sale math carries raw Decimals to the DB layer | (a) round at line level then sum (**HALF_UP**); (b) round only totals; (c) banker's rounding | **(a)** — line-level HALF_UP 2dp, totals = Σ rounded lines; matches purchase service and e-invoice line-item validation. Trade-off: 1-piaster differences vs current sale outputs at cutover. | FA+EN | 6, 7, 13 | Open |
| D-13 | Decimal precision standard | Money mostly 2dp (10/2, 14/2); qty 3dp (8/3–14/3); `Product.cost` 2dp | (a) money 2dp / qty 3dp everywhere; (b) **money 2dp, qty 3dp, internal unit-cost 4dp** | **(b)** — 4dp avg-cost avoids drift on small base units (gram-level recipes) while presenting 2dp. Trade-off: one more internal column convention; `Product.cost` (2dp) stays a display mirror. | EN+FA | 3, 6, 7 | Open |
| D-14 | Credit-limit semantics: null vs zero. **Pending question (2026-07-05):** Should NULL mean unlimited credit, zero mean no credit sales, and a positive number mean the maximum customer credit limit? | Gate A treats `credit_limit <= 0` as **unlimited** (field defaults 0, not nullable) | (a) keep `<=0 = unlimited`; (b) **null = unlimited, 0 = no credit** (make nullable) | **(b)** — a zero limit that *grants* unlimited credit is a trap; explicit null expresses "no limit". Trade-off: nullable migration + FE handling; Gate A GA-3 guard adjusted before landing. **Consultation (2026-07-05): remains Open** — no option confirmed; the pending question above must be answered before G0 can exit. | BO+FA | 1 (GA-3) | Open |
| D-15 | Negative-stock override model | `BranchSettings.allow_negative_stock` branch toggle (enforced only in Gate A WIP) | (a) **branch toggle only**; (b) toggle + per-sale manager override with approval audit | **(a) for MVP** — deterministic and already built; add (b) with the approvals slice (10) if ops demand it. Trade-off: a blocked sale needs a manager to flip the branch setting. **Consultation (2026-07-05):** branch-level `allow_negative_stock` controlled by management; disabled → insufficient stock blocks the sale; enabled → negative stock permitted, **recorded honestly and exposed for later reconciliation. No per-sale manager override in MVP.** | BO | 1 (GA-4) — governs negative-stock *behavior/policy* only; does **not** block construction of Slice 5 (inventory authority), only the oversell-policy configuration within it | **Selected: Option A for MVP (2026-07-05 consultation). Gate G0 Open.** |
| D-16 | Fiscal periods & close | None — any date is postable forever | (a) no periods (status quo); (b) **monthly soft-close** (block posting into closed periods; reopen = privileged) | **(b)** after GL lands — reports become stable and auditable. Trade-off: back-dated corrections must go through reversal documents in the open period. | FA | 7, 16 | Open |
| D-17 | Opening cutover date | Opening balances stored-but-never-posted on FinancialAccount/Customer/Supplier | Per-tenant cutover date for the GL opening journal + opening-balance documents | Pick one dated cutover per tenant; all opening docs dated to it; subledger↔GL identities verified same day. Trade-off: requires a stock count + balance confirmation per tenant. | FA+BO | 7 (with D-22) | Open |
| D-18 | Tips / service charge / complimentary | Nothing modeled; complimentary named in API contract only | Service charge: **disabled by default, tenant/branch configurable, no hardcoded percentage** — order-level charge with its own revenue/liability account; **tax treatment requires Finance + Regulatory approval**; tips: pass-through liability; complimentary: removal-action document | Decide **accounts + tax treatment** with FA+RC before any service-charge feature ships; build later (Slice 14; affects Slice 13 payloads only for tenants that enable it). Trade-off: deferring the decision would force rework of receipt + ETA payloads for enabled tenants. | FA+RC+BO | 14 (13 only if enabled) | Open |
| D-19 | Batch/expiry scope (**deferred — scoped blocker, no gate**) | `InventoryBatch` modeled, unused by any posting path ([pos/models.py:141](superpos_backend/pos/models.py#L141)) | (a) drop; (b) keep + wire into purchase/consumption (FEFO); (c) **DEFER/DORMANT** — keep the model in code, unused, untouched | **(c)** — do **not** delete now; `InventoryBatch` stays dormant until batch/expiry/FEFO scope is explicitly approved, then becomes (b) wire-in or a deliberate removal slice. Blocks **only** a future batch-tracking slice — never G2, Slice 5, or purchasing. Trade-off: dormant code carries small maintenance weight but zero data risk. | BO | future batch slice only | Open |

### 3.3 Carried-over open items

| ID | Decision | Context | Recommendation | Owner | Blocks | Status |
|---|---|---|---|---|---|---|
| D-20 | Split/mixed payments as `PaymentLine[]` | `Payment.MIXED` enum exists with no implementation | Implement PaymentLine[] at the pay flow (Slice 14 for table service; optionally counter POS earlier); then drop `MIXED` (X-2) | BO+EN | 14, X-2 | Open |
| D-21 | Route-deprecation cutover window | Duplicate `/api/auth`+`/api/accounts`, triple branch surface, sale int-pk, direct-mutation POSTs | Fixed window (e.g. 2 release cycles) + zero-traffic audit before removal | EN | 15 | Open |
| D-22 | Opening-balance-as-document conversion | `opening_balance` fields are stored hints, never posted | Convert each non-zero hint into a proposed opening document at D-17's cutover; retire fields after | FA+EN | 7 | Open |
| D-23 | Modifier price & cost ownership | No modifier model; price could live on Modifier, per-size matrix, or per parent item | Price on Modifier with per-size override in the Size Mapping Matrix; cost always derived from recipe components | BO+FA | 11 | Open |
| D-24 | Size variants: one product vs separate SKUs | No variant model; separate SKUs would explode the catalog (F&B doc warns against it) | **Variant-of-one-product** (parent + SizeVariant) with optional SKU/PLU; **no barcode required and never routed through ProductBarcodeUnit** (R-K) — primary POS flow is category/menu selection or optional PLU; an optional variant-barcode mapping may be added separately in the future if a real use case appears | BO+EN | 11 | Open |
| D-25 | Sales-return scope for MVP (**scoped blocker**) | No return document; refund could be cash-out, AR credit note, or exchange-only | Return document with refund via original method (cash-out movement) or AR credit note; ETA credit-note emission required once Slice 13 lands | FA+BO | 10; 13 (credit-note flow only) | Open |

### 3.4 Recipe, production & costing decisions (appended after D-25 — gate per §3.0; never renumbered)

| ID | Decision | Context | Options | Recommendation + trade-offs | Owner | Blocks | Status |
|---|---|---|---|---|---|---|---|
| D-26 | Maximum sub-recipe nesting depth | Prep items (dough, sauce) can themselves contain prep items; unbounded nesting complicates costing + cycle checks | (a) depth 1; (b) **depth 2**; (c) unlimited | **(b) 2 levels for MVP** (recipe → prep → raw), enforced as a validated hard cap at RecipeVersion approval. Trade-offs: (a) too tight for sauces-with-bases; (c) unbounded cost-explosion recursion and harder audits. Raise later if a real case appears. | BO+EN | 11, 11b | Open |
| D-27 | Circular-recipe prevention | A recipe referencing itself (directly or via a prep chain) would loop cost calculation | (a) runtime recursion guard only; (b) **DAG validation at RecipeVersion approval** | **(b)** — reject the version at approval time when the component graph has a cycle; cheap (depth ≤ D-26) and keeps posted paths safe without runtime cost. | EN | 11, 11b | Open |
| D-28 | Theoretical vs actual consumption | Depletion at sale can only be theoretical (recipe quantities); actual usage differs (waste, over-portioning) | (a) theoretical-only; (b) **theoretical at sale + periodic counts → period-level ingredient variance**; (c) actual weigh-in per order | **(b)** — theoretical depletion posts in real time from immutable recipe snapshots; periodic stock counts determine **ingredient-level usage variance per product/warehouse/period — they can NOT identify actual consumption per individual pizza** (that would require (c) or an explicit allocation method, both out of scope). (c) is operationally unrealistic; (a) hides variance forever. | FA+BO | 11, 16 | Open |
| D-29 | Production yield & variance handling | Batch output rarely equals planned output | (a) ignore (cost drifts); (b) **normal loss absorbed into good-output unit cost; abnormal wastage expensed separately; variance only vs an approved standard** | **(b)** with strict role separation: **normal loss** (within the recipe's yield factor) is absorbed into the good-output unit cost; **abnormal wastage** (beyond it) is expensed separately; **production variance is used only when comparing actual output/cost against an approved standard/planned basis** — and **the same loss is never double-counted** in both output cost and a variance/wastage expense. Trade-off: needs actual-output capture at posting. | FA | 11b | Open |
| D-30 | Normal loss vs abnormal wastage classification (**production/recipe loss only**) | Production loss must split into expected (cost of doing business) vs exceptional (investigated) | Threshold %, approval flow, account mapping | Define a per-recipe/production normal-loss threshold; within threshold → normal (absorbed into good-output/COGS cost); beyond → **abnormal wastage expense requiring manager approval** and its own GL account. A given loss quantity is classified **exactly once** — never inside output cost *and* as an expense (no double-count, per D-29). **Scope: D-30 governs production/recipe loss only — standalone operational wastage (e.g. shelf spoilage) is NOT classified by D-30; it follows a separate tenant wastage policy via the Wastage Document.** Trade-off: threshold tuning per tenant. | FA+BO | 11b, 10 | Open |
| D-31 | Snapshot representation on posted documents (**gate G3** — cross-referenced by G4) | R-J requires immutable recipe/cost + tax/account snapshots | (a) JSON blob per line; (b) **normalized snapshot rows** | **(b)** — normalized rows (snapshot header + component lines) keep variance/food-cost reporting queryable without JSON parsing; slightly more schema. JSON acceptable only for the tax/account resolution snapshot (small, rarely queried). Decided with G3 so Slice 6's snapshot mechanics never wait for the full recipe/production gate. | EN | 6 (snapshot mechanics), 11 | Open |
| D-32 | Contribution-margin variable-fee set (**scoped blocker**) | §6.8/§6.13: which fees sit between gross profit and contribution margin | Packaging-not-in-recipe · payment/card fees · delivery commission · loyalty costs | Include payment fees + delivery commission + non-recipe packaging; exclude fixed costs (those are period net-profit items). Decided alongside G3 but **blocks only the contribution-margin report within Slice 16 — never GL, numbering, purchases, or returns**; informs Slice 12. | FA | 16 (contribution-margin report only) | Open |
| D-33 | Prep-item output dating / shelf-life | Produced dough/sauce has a usable life; ties to batch/expiry decision D-19 | (a) no dating (MVP); (b) production-date + shelf-life on ProductionOrder output | **(a) for MVP** unless D-19 resolves to keep batch tracking — then (b) rides on the same mechanism. Trade-off: (a) relies on kitchen discipline for FIFO of prep items. | BO | 11b | Open |
| D-34 | Free/complimentary modifier COGS treatment | A zero-price modifier (e.g. free extra sauce) still consumes inventory | (a) consumption into normal COGS; (b) route to complimentary/marketing expense | **(a) for MVP** — consumption is part of the item's COGS and shows up in food-cost %; (b) only when a formal complimentary policy (D-18) lands. | FA+BO | 11 | Open |
| D-35 | **Average-cost ownership: base ProductUnit vs dedicated valuation record** (**gate G3** — costing, decided with D-07) | `ProductUnit` is primarily a **conversion definition** and stock lives in the base unit (R-B); the average cost needs an unambiguous home — it must never imply that every conversion unit maintains an independent average cost | (a) `avg_cost` **only on the base ProductUnit**; all other units derive cost purely by conversion; (b) **separate InventoryCost/valuation record** per product (scope per D-09) storing the avg cost per base unit | **(b)** — keeps ProductUnit purely a conversion table; migration is a trivial copy of `Product.cost` into the valuation record; reporting/valuation queries join one purpose-built table; and the record extends naturally if D-09 later upgrades scope (tenant → branch). Trade-offs: (b) adds one table; (a) avoids the table but overloads ProductUnit semantics and invites the false per-conversion-unit-cost reading. Either way, **conversion units never carry independent averages**. | EN+FA | 6 (with D-07) | Open |

### 3.5 Consultation log (append-only)

> Records who selected which option and when. **Decision selections here are
> decision-level only — they do NOT exit any gate.** No gate exits without all
> required approvals recorded in §4 **and** ADR/next-source-of-truth promotion
> (R-M).

**2026-07-05 — Business/accounting consultation**
- Participants: **Business Owner**; **External accountant / financial advisor**.
- Selections recorded:
  - **D-02 (GL depth): Option B** — complete GL forward-only as a separate phased
    slice, beside the treasury/AR/AP subsidiary ledgers (P&L, assets,
    liabilities, journals, complete movements). No USAR chart / account numbering
    hardcoded yet; restaurant chart/template subject to later accountant review.
  - **D-09 (moving-average cost scope): Option A (MVP)** — one tenant/company-wide
    moving-average per product; branch profitability still reported separately and
    the consolidated report must not hide a losing branch; branch-level upgrade
    trigger = WarehouseTransfer maturity.
  - **D-10 (tax inclusive/exclusive): Option B** — store net/tax-exclusive
    separately; allow tax-inclusive customer-facing display; no hardcoded 14%,
    configurable via tax profiles.
  - **D-11 (discount vs taxable base): Option B** — discount reduces the taxable
    base first, then tax on the net amount. **Finance-approved; Regulatory/ETA
    (RC) approval PENDING → not fully ratified.**
  - **D-15 (negative-stock override): Option A (MVP)** — branch-level
    `allow_negative_stock` under management control; disabled blocks the sale;
    enabled records negative stock honestly for later reconciliation; no per-sale
    manager override in MVP.
- **D-14 (credit-limit semantics): remains Open** — pending question: *"Should
  NULL mean unlimited credit, zero mean no credit sales, and a positive number
  mean the maximum customer credit limit?"*
- **Gate impact: NONE.** **G0 remains Open** (D-14 still Open) and **G3 remains
  Open** (D-07, D-08, D-12, D-16, D-17, D-22, D-31, D-35 still Open; D-11 pending
  RC). No ADRs created; no promotion; implementation remains blocked.

## 4. Sign-off — per gate (R-M)

> **Decision selections recorded 2026-07-05 (§3.5) are NOT gate sign-off.**
> **G0 and G3 remain Open.** No gate exits until all its required approvals are
> recorded in this table **and** its decisions are promoted (ADRs → next
> source-of-truth docs version, R-M). Signature/date cells below stay blank
> until then.

| Gate | Scope | Business Owner | Finance / Accounting | Engineering | Regulatory / Compliance | Date |
|---|---|---|---|---|---|---|
| G0 | Sales integrity (D-14, D-15) | | | | n/a | |
| G1 | Catalog & category (D-01) | | | | n/a | |
| G2 | Units & inventory (D-13) | | | | n/a | |
| G3 | Costing & GL (D-02, D-07…D-12, D-16, D-17, D-22, D-31, D-35) | | | | | |
| G4 | Recipe / variants / production (D-06, D-23, D-24, D-26…D-30, D-33, D-34) | | | | n/a | |
| G5a | Delivery (D-03) | | | | | |
| G5b | ETA / Compliance (D-05; + D-18 only if service charge enabled) | | | | | |
| G5c | Tables / Payments (D-20, D-18) | | | | n/a | |
| — | Confirmation-only (D-04 — card manual in MVP) | | | | n/a | |
| — | Scoped blockers, signed individually (D-19 deferred · D-21 · D-25 · D-32) | | | | | |

> A gate **exits** only when its signature is recorded here **and** its
> decisions are promoted (ADR documents → next PRD/FLOW/DOMAIN/DESIGN version,
> per R-M). Only then are the slices in §3.0 unblocked and the corresponding
> freeze in [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §5 lifted.
