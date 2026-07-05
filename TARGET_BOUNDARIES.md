# TARGET_BOUNDARIES.md

> **Read-only architecture audit — 5 of 7.** The bounded-context (module) target
> for a reliable F&B/accounting system, what each context owns, what stays
> additive vs net-new, and the **v3.6 ↔ F&B-doc conflict register**. No runtime
> code changed; `safety/backend-gate-a-wip-2026-07-04` **not** merged.
>
> **Authority rule (per stakeholder decision):** v3.6 (`PRD/FLOW/DOMAIN/DESIGN`)
> is the **approved business source of truth**. `F&B Accounting System Design.md`
> is **candidate target-state research**, not an automatic replacement. Every
> conflict is logged below with (1) v3.6 rule, (2) F&B proposal, (3) recommended
> decision, (4) migration/scope impact — **v3.6 is never silently overridden**,
> and it **remains authoritative until a gate's approved decisions are promoted
> (ADRs → next PRD/FLOW/DOMAIN/DESIGN version, per R-M).**

---

## 1. Boundary principle

> **Movement ledgers = subsidiary ledgers. The General Ledger = balanced journal
> (double-entry). A single posting engine writes BOTH atomically for every posted
> document.** The current `FinancialAccountMovement` / `CustomerARMovement` /
> `SupplierAPMovement` become subledgers *under* a new GL; they are never renamed
> to "GL" and never removed.
>
> **Two account concepts, never merged:**
> - **FinancialAccount** = *operational* cash / bank / wallet / card-clearing
>   account (treasury; what the cashier and finance screens operate on).
> - **ChartOfAccount** = the *full accounting ledger* account (assets,
>   liabilities, equity, revenue, expenses).
> - Every FinancialAccount **links to** exactly one GL account (`gl_account` FK);
>   GL-only accounts (inventory, revenue, VAT) exist **only** in ChartOfAccount.
>
> **Reconciliation identities (must hold at GL cutover and continuously after):**
> 1. Σ GL debits = Σ GL credits (every journal balanced).
> 2. AR control account (GL) = Σ customer AR subledger (`CustomerARMovement`).
> 3. AP control account (GL) = Σ supplier AP subledger (`SupplierAPMovement`).
> 4. Inventory control account (GL) = inventory valuation
>    (Σ base-unit quantity × moving-average cost).
> 5. Each cash/bank GL account = its corresponding operational subledger
>    (`FinancialAccountMovement` running balance of the linked FinancialAccount).

---

## 2. Bounded contexts

For each: **Now** (current coverage) · **Target** (responsibility) · **Owns** ·
**Additive vs Net-new**.

### 2.1 Identity & Tenancy
- **Now:** Tenant, Branch, Terminal, User, RBAC, subscription gate — complete.
- **Target:** unchanged + BranchUserAssignment as the access boundary.
- **Owns:** Tenant, Branch, Terminal, User, BranchSettings, BranchUserAssignment.
- **Disposition:** KEEP (additive route dedup only).

### 2.2 Catalog & Units
- **Now:** flat `Category`, `Product` with fixed unit/pack_qty, `price`/`cost`.
- **Target:** typed `Product`; **UnitGroup/Unit/ProductUnit/ProductBarcodeUnit**;
  **hierarchical SalesCategory + hierarchical InventoryCategory**;
  **ProductVariant → RecipeVersion → RecipeLines**; price tiers +
  `ProductUnitTierPrice`. **The proposed F&B catalog/recipe/costing target model
  is specified in §6 below (pending gates G1–G4).**
- **Owns:** Product, ProductVariant, ProductUnit, UnitGroup/Unit, SalesCategory,
  InventoryCategory, Recipe/RecipeVersion/RecipeLine, ModifierGroup/ModifierOption,
  PriceTier, ProductUnitTierPrice, ProductBarcodeUnit.
- **Disposition:** REWORK (R-2, R-3) + EXTEND — additive tables beside `Product`/`Category`.

### 2.3 Inventory & Costing
- **Now:** global `Product.stock`, `StockMovement`, `WarehouseStock` cache,
  moving-average on `Product.cost`, direct-mutation endpoints.
- **Target:** **per-warehouse (`WarehouseStock`) authoritative** balance, with
  quantity denominated in the **product base unit only** (recorded directive
  R-B) — `ProductUnit` is primarily a conversion definition; separate stock
  balances per conversion unit are never stored; **base-unit moving-average
  cost** (home per **D-35**: base ProductUnit vs dedicated valuation record;
  scope per D-09 — conversion units never carry independent averages);
  **RECIPE_CONSUME** movements; warehouse transfers; adjustment/wastage
  **documents** replacing direct mutation.
- **Owns:** StockMovement (audit source), WarehouseStock (authority), WarehouseTransfer,
  StockAdjustmentDoc, WastageDoc, **InventoryCost/valuation record (conditional —
  pending D-35 approval)**.
- **Disposition:** REWORK (R-1, R-4) + EXTEND; DEPRECATE direct-mutation endpoints.

### 2.4 Sales / POS & Table Service
- **Now:** counter `Sale`/`SaleItem`/`Payment`, void, durable receipt; no
  idempotency; no tables/orders/shifts/split.
- **Target:** OpenOrder/OpenOrderLine/DiningTable/DiningSection, send-to-kitchen,
  request-bill, pay→one SalesInvoice, shifts, `PaymentLine[]`, sales idempotency,
  line-void + manager approval.
- **Owns:** Sale/SalesInvoice, SaleItem, PaymentLine, OpenOrder(+Line), DiningTable/
  Section, Shift, KitchenTicket.
- **Disposition:** EXTEND (Sale) + NET-NEW (tables/orders/shifts/KDS).

### 2.5 Purchasing & AP
- **Now:** create-and-post `PurchaseInvoice` (stock-item only), SupplierPayment.
- **Target:** all line types; draft→post lifecycle with **cancellation (pre-post)
  and reversal/return documents (post)** — posted documents are never unposted;
  purchase return; input-VAT + inventory GL legs; payment allocation/ageing.
- **Owns:** PurchaseInvoice(+Line), PurchaseReturn, SupplierPayment(+allocation).
- **Disposition:** EXTEND.

### 2.6 Treasury / Finance & Payment Routing
- **Now:** FinancialAccount, PaymentMethod, BranchPaymentMethod, cash/AR subledgers.
- **Target:** FinancialAccount stays strictly **operational** (cash/bank/wallet/
  card-clearing) and gains a `gl_account` FK to its ChartOfAccount ledger account;
  + cash drop / settlement-to-bank / commission posting; opening balance as
  document. Existing GL-ish FinancialAccount types (`customer_ar`, `supplier_ap`,
  `expense`, `opening_balance`) are mapped to GL control accounts — flagged as a
  reconciliation/cleanup item at GL cutover.
- **Owns:** FinancialAccount, PaymentMethod, BranchPaymentMethod, FinancialAccountMovement (subledger).
- **Disposition:** KEEP + EXTEND.

### 2.7 General Ledger  ⟵ **NET-NEW**
- **Now:** none (subledgers only; no trial balance possible).
- **Target:** **ChartOfAccount = the full accounting ledger** (assets/liabilities/
  equity/revenue/expenses — a separate concept from the operational
  FinancialAccount, which links to it); **JournalEntry + balanced JournalLine**;
  posting rules per document type; trial balance / P&L / balance sheet read from
  GL. The five reconciliation identities in §1 are the permanent contract between
  GL control accounts and the subledgers.
- **Owns:** ChartOfAccount, JournalEntry, JournalLine, PostingRule.
- **Disposition:** NET-NEW, **added beside** subledgers (R-5).

### 2.8 Party AR/AP
- **Now:** Customer/Supplier + AR/AP subledgers + statements.
- **Target:** unchanged + allocation + opening-balance documents; feed GL control accounts.
- **Disposition:** KEEP + EXTEND.

### 2.9 Compliance / e-Invoicing  ⟵ **NET-NEW**
- **Now:** `vat_number` + QR-on-receipt notion only; no e-invoicing integration
  of any kind.
- **Target:** a **pluggable compliance-adapter layer** with the **Egypt ETA
  adapter as the primary implementation** (Egypt is the primary market — Tenant
  defaults `EGP`/`Africa/Cairo`): **eReceipt** for B2C POS transactions and
  **eInvoice** for B2B — document UUID, ETA submission/notarization, POS
  serial/device registration, signing, receipt QR, plus the output/input-VAT
  ledger legs. **ZATCA (KSA) is retained only as an optional future-market
  adapter** behind the same interface; it is not the primary slice.
- **Owns:** ComplianceAdapter interface, ComplianceDocument (per-regime payload +
  submission state), InvoiceCounter/DocumentSequence linkage, VAT ledger accounts.
- **Disposition:** NET-NEW (regulatory; ETA scope/timeline per D-05).

### 2.10 Delivery / Channel Revenue  ⟵ **NET-NEW**
- **Now:** in-store payment methods only.
- **Target:** DeliveryChannel/Platform, commission model; **gross revenue booked,
  commission as separate contra-revenue/expense**, platform receivable + settlement.
- **Owns:** DeliveryChannel, PlatformCommission, ChannelSale linkage.
- **Disposition:** NET-NEW (see CR-3, CR-6).

### 2.11 Reporting
- **Now:** dashboard aggregates + movement statements.
- **Target:** GL-based financials + branch/channel/category analytics from posted data.
- **Disposition:** EXTEND (reads GL + subledgers).

---

## 3. Net-new vs additive summary

| Additive/Extend to existing | Net-new contexts |
|---|---|
| Catalog units, category split, price tiers; Sale posting legs; purchase lifecycle; inventory authority promotion; routing commission posting; sales idempotency; opening-balance documents | General Ledger (ChartOfAccount + journals); Table Service/Shifts/KDS; Compliance/e-Invoicing (**Egypt ETA primary**; ZATCA optional future adapter); Delivery/Channel Revenue; Warehouse Transfer; Recipes/Modifiers/Variants |

No context requires replacing an existing module. Every net-new context attaches to
the existing posting engine and tenant/branch scoping.

---

## 4. v3.6 ↔ F&B-doc conflict register

> Format per stakeholder: **(1) v3.6 rule · (2) F&B proposal · (3) recommended
> decision · (4) migration/scope impact.** Recommendations do **not** silently
> override v3.6; each is a decision to be ratified in roadmap slice 0.
>
> **Ratification instrument:** every CR row below — together with the accounting-
> policy decisions (tax, discount, rounding, costing scope, fiscal periods, …) —
> is consolidated as a signable register in
> [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md)
> (IDs D-01…D-08 map to CR-1…CR-8). Sign-off there is Slice 0's exit criterion.

| # | Topic | (1) v3.6 rule | (2) F&B proposal | (3) Recommended decision | (4) Migration / scope impact |
|---|---|---|---|---|---|
| CR-1 | Product categorization | Single `ProductCategory` (POS visibility + routing); one category tree. | **Two separate trees**: Sales Categories (menu/POS, revenue-account linked) **and** Inventory Categories (raw material, asset-account linked). | **Adopt the split** — F&B correctly separates menu grouping from stock/GL classification; it is additive and does not violate v3.6 (v3.6 is silent on inventory categories). Keep v3.6's POS-category semantics inside SalesCategory. **Proposed as hierarchical trees with inheritance + snapshot-on-post — see §6.2/§6.3 — pending Catalog gate G1.** | New `SalesCategory` + `InventoryCategory` tables; legacy `Category` read-only until reclassified; **no auto-mapping** (admin classifies). |
| CR-2 | Accounting depth | "ERP Lite — **not** a full double-entry system; full GL is **Phase 2**." Financial effects route to named accounts. | Full **USAR 5-level chart of accounts**, IFRS-aligned, true GL now. | **Phase it:** keep subledgers as the MVP truth (v3.6), **introduce GL forward-only** as a defined slice; do not block MVP on full USAR. Ratify the target chart before COGS/VAT work. | Net-new GL layer beside subledgers; opening journal for historical balances; no retro-explosion. |
| CR-3 | Delivery commission | Card fees / commission = **Phase 2**; delivery-platform accounting **not specified**. | Book **gross** invoice as taxable revenue; record delivery commission separately as contra-revenue / marketing expense; do **not** book net. | **Adopt the gross-vs-commission rule** as the target design (it is an accounting-correctness fix, not a v3.6 contradiction), scheduled as a Phase-2-aligned slice. | Net-new DeliveryChannel + commission accounts + VAT-base rule; depends on GL. |
| CR-4 | Card terminal | Card recorded **manually** in MVP; terminal integration = Phase 2. | Implies richer settlement/commission automation. | **Keep v3.6** (manual card in MVP); automate settlement/commission with GL slice. | None now; later additive. |
| CR-5 | e-Invoicing / compliance market | v3.6 does **not** specify an e-invoicing regime; QR-on-receipt + `vat_number` only. | F&B doc covers VAT output/input + IFRS-aligned chart, no specific regime. | **Egypt is the primary market** (stakeholder-ratified 2026-07-04; Tenant defaults `EGP`/`Africa/Cairo`) → primary compliance slice = **Egypt ETA eReceipt/eInvoice adapter** behind a pluggable compliance-adapter interface; **ZATCA (KSA) kept only as an optional future-market adapter**. ETA taxpayer profile / phase timeline remain open (D-05). | Net-new compliance context; depends on GL + DocumentSequence; ETA onboarding ownership TBD. |
| CR-6 | Recipes / size-variant depletion | Recipes & modifiers = **Phase 2** ("Restaurants Phase 2+"); RECIPE_CONSUME movement type named in DOMAIN §7.2. | Parent item + **Size Mapping Matrix** + modifier groups; per-size BOM depletion (extra cheese 40g small / 80g large); AVCO + yield factor; kit vs manufacturing-order modes. | **Adopt F&B as the target recipe model** for the Phase-2 recipe slice — it operationalizes v3.6's RECIPE_CONSUME without contradicting it. Ratify kit-vs-MO + sub-recipe policy first. **Proposed as Variant → RecipeVersion → RecipeLines with immutable snapshots — see §6.6–§6.10 — pending Recipe/Production gate G4.** | Net-new Recipe/BOM/Modifier/Variant tables; depends on ProductUnit (R-3) + COGS (R-4). |
| CR-7 | Costing field | v3.6 §7.1 moving-average; ProductUnit implied. | AVCO on stock unit + yield factor per recipe line. | **Align:** average cost moves **off `Product.cost` into the D-35-approved base-unit valuation home** (base ProductUnit or a dedicated valuation record — not hard-coded here); add yield factor on recipe lines. | Depends on ProductUnit (R-3) + D-35. |
| CR-8 | Inventory valuation account | v3.6 posting routes to named accounts; inventory-value debit deferred in code. | Inventory categories each linked to a current-asset account. | **Adopt** inventory-asset accounts as GL control accounts per InventoryCategory. | Depends on GL + CR-1. |

---

## 5. What must be frozen until this is ratified
The entire Catalog & Units rework (R-2, R-3), Costing (R-4), the GL layer (R-5),
and everything downstream of them (COGS, VAT legs, recipes, delivery, Egypt ETA
compliance) are **frozen** until the relevant **decision gate** in
[ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md) is
signed **and promoted** (gates G0–G4 plus the mutually independent future
sub-gates G5a/G5b/G5c and scoped blockers; a slice unblocks only when *its*
gate's sign-off is recorded **and its decisions are promoted to ADRs → next
source-of-truth docs version** — unrelated gates never block it). Master-data CRUD, reporting reads, route dedup planning, the
parallel frontend-test-framework slice, and the component-by-component Gate A
review may proceed in parallel. Sequencing in
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md); migration mechanics in
[TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md).

---

## 6. F&B Catalog, Recipe, Production & Costing Architecture (proposed target)

> The **proposed target architecture** for the F&B domain — **pending the
> relevant decision-gate approvals (G1–G4)** in
> [ARCHITECTURE_DECISIONS_REQUIRED.md](ARCHITECTURE_DECISIONS_REQUIRED.md);
> all D-rows remain Open/unsigned. The stakeholder directives R-A…R-M are
> *recorded* (register §2) and shape this proposal, but the model as a whole is
> not ratified until its gates sign — and per R-M, **v3.6 stays the
> authoritative business source of truth until approved decisions are promoted
> (ADRs → next PRD/FLOW/DOMAIN/DESIGN version)**. Architecture level only — no
> code, migrations, or final API schemas.

### 6.1 The conceptual chain

```
SalesCategory (hierarchical, self-parent «تندرج من»)
  └─ Product  (typed; e.g. product_type = recipe_product)
       └─ ProductVariant / SizeVariant  (Small / Medium / Large)
            └─ RecipeVersion  (dated, statused, per variant)
                 └─ RecipeLines  (component products, base-unit quantities)
```

Worked shape:

```
Pizza                       ← SalesCategory (root)
├── Italian Pizza           ← SalesCategory (parent = Pizza)
│     └── Margherita Pizza  ← Product (recipe_product), NOT a category
│           ├── Small / Medium / Large   ← ProductVariants
│           └── (per-variant RecipeVersion → RecipeLines:
│                dough, sauce, mozzarella, oil, box)
└── American Pizza          ← SalesCategory (parent = Pizza)
```

**Rules:** Margherita is a *Product* under Italian Pizza — never a child
category. Cheese, sauce, and dough are *RecipeLines* (component products) —
never categories. Components are independent inventory items with their own
base unit, purchase conversions, stock quantity, purchase cost, and
moving-average cost; a component carries a sale price **only** when it is
independently sellable (`sellable=True`).

### 6.2 SalesCategory (hierarchical)
- Self-referencing `parent` field (conceptually **«تندرج من»** — "descends
  from"); unlimited nesting for menu organization.
- **Inheritable defaults:** tax profile · revenue GL account · COGS GL account ·
  kitchen station · POS visibility · sort order.
- **Inheritance resolution (R-J):** `product override → child category →
  nearest parent category → tenant default`.
- **Snapshot-on-post (R-J):** the *resolved* tax/account values are snapshotted
  onto every posted document line. Renaming, re-parenting, or re-mapping a
  category later **never alters historical transactions**.

### 6.3 InventoryCategory (separate, hierarchical — never merged with SalesCategory)
- Trees for **ingredients · prep/sub-recipe items · packaging · resale stock**.
- **Inheritable GL defaults:** inventory asset account · wastage account ·
  adjustment account · production-variance account.
- All category account links point to **ChartOfAccount** (the accounting
  ledger), never to FinancialAccount (operational treasury) — per R-D.

### 6.4 Product types & mandatory flags
Types (aligned with MASTER_DATA_CONTRACT §11): **Ingredient Item · Stock/Resale
Item · Prep/Sub-Recipe · Recipe Product · Packaging Item · Service/Non-Stock ·
Bundle/Combo · Fixed Asset (purchase-only)**.

Every Product explicitly defines: `sellable` · `purchasable` ·
`track_inventory` · `base_unit` · `sales_category` (required when sellable) ·
`inventory_category` (required when stock-controlled).

| Type | sellable | purchasable | track_inventory | typical categories |
|---|---|---|---|---|
| Ingredient (mozzarella, oil) | only if also sold | ✔ | ✔ | InventoryCategory: Ingredients |
| Stock/Resale (canned drink) | ✔ | ✔ | ✔ | both |
| Prep/Sub-Recipe (dough, sauce) | rarely | ✘ (produced) | ✔ | InventoryCategory: Prep |
| Recipe Product (Margherita) | ✔ | ✘ | ✘ (components tracked) | SalesCategory |
| Packaging (pizza box) | ✘ | ✔ | ✔ | InventoryCategory: Packaging |
| Service / Non-Stock | ✔ | optional | ✘ | SalesCategory |
| Bundle/Combo | ✔ | ✘ | ✘ | SalesCategory |
| Fixed Asset | ✘ | ✔ (purchase-only) | ✘ (asset register) | — |

### 6.5 Units & conversions
- **UnitGroup** (Weight, Volume, Count) → **Unit** (g/kg · ml/L ·
  piece/carton/box/bag) → **ProductUnit** (per-product conversion +
  purchase/sale usage flags).
- **ProductBarcodeUnit exists only for packaged / purchase / retail units that
  actually need scanning** — it is not a general requirement.
- **WarehouseStock always stores quantity in the Product base unit only** (R-B).
  Never a kg balance *and* a g balance for the same item — `ProductUnit` is a
  conversion definition, not a stock bucket.

### 6.6 Variants (barcode-free by design — R-K)
- **ProductVariant/SizeVariant:** parent product · name (Small/Medium/Large) ·
  sale price · optional SKU/PLU · POS sort order · active flag.
- **A pizza does not require a barcode.** The primary POS flow is
  category/menu selection (or optional PLU). Barcode is optional and is never
  the foundation of variant identity; variants are **not** forced through
  `ProductBarcodeUnit`.
- Each variant may bind its **own RecipeVersion with its own component
  quantities** — ingredient scaling is per-size data, never a single global
  multiplier.

### 6.7 Recipe / RecipeVersion / RecipeLine
- **Recipe** — the container per (product, variant).
- **RecipeVersion** — `effective_from`/`effective_to`; status
  `draft → approved → active → retired`; **yield quantity + yield unit**.
- **RecipeLine** — component Product · quantity **in the component's base
  unit** · normal-loss / yield factor · source warehouse **or warehouse role**
  (kitchen/bar per BranchWarehouse roles) · optional preparation instructions.
- **Immutability (R-J):** posted sales/production store immutable snapshots of
  the recipe version, component quantities, component average costs, and the
  calculated total recipe cost. **Historical sales never change when a recipe
  or a cost changes later.**

### 6.8 Worked example — Margherita Medium
> **Illustrative example values only — NOT system defaults.** Currency EGP;
> menu price shown tax-exclusive (final policy = D-10/D-11).

Sales path: SalesCategory `Pizza > Italian Pizza` → Product `Margherita Pizza`
(recipe_product) → Variant `Medium` → active RecipeVersion:

| RecipeLine (component) | Qty (base unit) | Avg cost / unit (ex.) | Line cost |
|---|---|---|---|
| Pizza Dough (Prep) | 250 g | 0.06 /g | 15.00 |
| Pizza Sauce (Prep) | 120 g | 0.05 /g | 6.00 |
| Mozzarella (Ingredient) | 140 g | 0.14 /g | 19.60 |
| Olive Oil (Ingredient) | 10 g | 0.20 /g | 2.00 |
| Medium Pizza Box (Packaging) | 1 piece | 4.40 /piece | 4.40 |
| **Recipe COGS (theoretical)** | | | **47.00** |

With an example menu price of **160.00** (net of VAT):

| Metric | Formula | Example value |
|---|---|---|
| Recipe COGS | Σ(base-unit qty × avg-cost snapshot) | 47.00 |
| **Gross profit** | net revenue − recipe COGS | 160.00 − 47.00 = **113.00** |
| **Gross margin** | gross profit ÷ net revenue | **70.6 %** |
| **Food-cost %** | recipe COGS ÷ net revenue | **29.4 %** |
| **Contribution margin** (counter, card) | gross profit − variable fees (ex.: card fee 2.00) | 111.00 (**69.4 %**) |
| **Contribution margin** (delivery, ex. 18 % commission) | 113.00 − 28.80 | 84.20 (**52.6 %**) |

Packaging note: the box is a RecipeLine here, so it is inside COGS; variable
fees not in the recipe (payment fees, delivery commission) belong to
**contribution margin** (fee set = D-32).

> **Terminology rule (R-L): gross profit is never called "net profit."**
> **Period net profit** is computed only at the GL level after rent, salaries,
> utilities, marketing, depreciation, and other operating expenses
> (Slices 7/16).

### 6.9 Sub-recipes & ProductionOrder
Pizza Dough and Pizza Sauce are **Prep/Sub-Recipe** inventory items produced in
batches, then consumed by made-to-order pizzas at sale time.

**ProductionOrder:** warehouse · recipe version · planned output · actual
output · input components (consumed at avg cost) · output item · **normal
loss** (inside output cost via yield factor) · **abnormal wastage** (expensed
separately) · **production variance** · posted status · **immutable snapshots**
(same rule as sales).

Flow: production converts raw inventory → prepared inventory (valued at the
computed batch cost); the pizza's RecipeLines then consume prep + raw
components at sale.

**Cost-role clarification (no double-counting):**
- **Production normal loss** (within the recipe's yield factor) is **absorbed
  into the good-output unit cost with NO separate expense entry** — it never
  appears as a wastage line.
- **Standalone operational wastage** (outside production — e.g. shelf spoilage)
  is a separate **Wastage Document** with its own expense entry (§6.12).
- **Abnormal wastage** (beyond the normal-loss threshold) is **expensed
  separately** to the wastage account.
- **Production variance** is used **only** when comparing actual output/cost
  against an **approved standard/planned basis** — it is not a dumping ground
  for loss.
- A given loss quantity lives in **exactly one** of these places — never in
  output cost *and* a variance/wastage expense simultaneously.

Gated parameters (G4): nesting depth **D-26**, cycle prevention **D-27**,
theoretical-vs-actual consumption **D-28**, yield/variance **D-29**,
normal-vs-abnormal loss classification **D-30**.

### 6.10 Modifiers
- **ModifierGroup → ModifierOption**, each option carrying a **price delta**
  and a per-variant **RecipeConsumptionDelta**.
- Example — *Extra Cheese*: Small **+40 g** mozzarella (+price), Medium
  **+60 g** (+price), Large **+80 g** (+price).
- A modifier changes **both** the customer price **and** the component
  consumption/COGS (free/comp modifier COGS handling = D-34; modifier price/
  cost ownership = D-23).

### 6.11 Purchasing → costing → GL (kept separate)
1. **PurchaseInvoice lines** update: warehouse stock **in base units** →
   moving-average component cost → inventory valuation.
2. **Recipe cost** = Σ(component base-unit quantity × component
   **average-cost snapshot**).
3. **A recipe-product sale**: records net revenue/tax (per D-10/D-11) ·
   consumes recipe components (theoretical depletion per D-28) · stores the
   recipe + cost snapshots · posts **inventory/COGS journal lines only after
   the GL exists**.
4. **Boundary rule:** the **costing/valuation engine (Slice 6) is separate from
   GL posting (Slice 7)** — costing works and is reportable before a single
   JournalEntry exists; the GL adds the double-entry legs on top.

### 6.12 Conceptual accounting entries (ChartOfAccount concepts — illustrative)
> FinancialAccount = treasury only; every entry below is against ChartOfAccount
> ledger accounts (cash/bank GL accounts are the ones *linked* from treasury
> accounts via `gl_account`). Posted documents are **never unposted** (R-C) —
> undo = cancellation before posting, reversal/return documents after.

| Event | Dr | Cr |
|---|---|---|
| Ingredient purchase | Inventory–Ingredients (asset, per InventoryCategory) [+ VAT Input] | Cash/Bank GL or AP control |
| Prep production (dough batch) | Inventory–Prep (output qty × batch cost; normal loss inside via yield) | Inventory–Ingredients (inputs at avg cost) |
| — production abnormal wastage | Wastage Expense (abnormal) | Inventory–Ingredients |
| — production variance (only vs an approved standard/planned basis; never a loss already counted in output cost or wastage expense) | Production Variance (Dr or Cr) | counterpart Inventory |
| Recipe-product sale (payment leg) | Cash / Card-clearing / AR control (gross) | Revenue (per SalesCategory snapshot, net) + VAT Output |
| Recipe COGS (post-GL) | COGS (per SalesCategory snapshot) | Inventory–(component categories) at snapshot cost |
| Production normal loss (within yield factor) | **No separate entry** — absorbed into the good-output unit cost (already inside the prep-production entry above) | — |
| Standalone operational wastage — normal, within the **tenant wastage policy** (via **Wastage Document**, e.g. shelf spoilage outside production — NOT classified by production decision D-30) | Wastage–Normal (COGS section) | Inventory |
| Standalone operational wastage — abnormal (Wastage Document, approval req.) | Wastage–Abnormal Expense | Inventory |
| Sales return / reversal (document) | Revenue-Returns (contra) + VAT Output | Cash / AR control — and Dr Inventory / Cr COGS when restockable |

### 6.13 Profitability reporting definitions
| Metric | Definition |
|---|---|
| **Theoretical recipe cost (per sale)** | Active RecipeVersion quantities × avg-cost snapshots (what *should* have been consumed). Per-sale cost is always theoretical, from immutable recipe snapshots. |
| **Actual ingredient usage (period-level)** | Derived from periodic stock counts + production actuals, **per ingredient/product/warehouse/period** (D-28). Stock counts **cannot identify actual consumption per individual pizza/sale** — no per-sale "actual cost" exists unless an explicit allocation or actual-capture method is introduced. |
| **Ingredient usage variance (period, per ingredient/warehouse)** | Actual ingredient usage − theoretical usage for the period (waste, over-portioning, theft). |
| **Gross profit** | Net revenue − recipe COGS. |
| **Gross margin** | Gross profit ÷ net revenue. |
| **Food-cost %** | Recipe COGS ÷ net revenue. |
| **Contribution margin** | Gross profit − variable fees (packaging-not-in-recipe, payment fees, delivery commission — set per D-32). |
| **Period net profit** | GL-level only: after rent, salaries, utilities, marketing, depreciation, other operating expenses. Never conflated with gross profit (R-L). |
