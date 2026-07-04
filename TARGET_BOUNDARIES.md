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
> decision, (4) migration/scope impact — **v3.6 is never silently overridden.**

---

## 1. Boundary principle

> **Movement ledgers = subsidiary ledgers. The General Ledger = balanced journal
> (double-entry). A single posting engine writes BOTH atomically for every posted
> document.** The current `FinancialAccountMovement` / `CustomerARMovement` /
> `SupplierAPMovement` become subledgers *under* a new GL; they are never renamed
> to "GL" and never removed.

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
- **Target:** `product_type`; **UnitGroup/Unit/ProductUnit/ProductBarcodeUnit**;
  **SalesCategory + InventoryCategory**; price tiers + `ProductUnitTierPrice`.
- **Owns:** Product, ProductUnit, UnitGroup/Unit, SalesCategory, InventoryCategory,
  PriceTier, ProductUnitTierPrice, ProductBarcodeUnit.
- **Disposition:** REWORK (R-2, R-3) + EXTEND — additive tables beside `Product`/`Category`.

### 2.3 Inventory & Costing
- **Now:** global `Product.stock`, `StockMovement`, `WarehouseStock` cache,
  moving-average on `Product.cost`, direct-mutation endpoints.
- **Target:** **per-warehouse (`WarehouseStock`) authoritative** balance;
  `ProductUnit.avg_cost` moving-average; **RECIPE_CONSUME** movements; warehouse
  transfers; adjustment/wastage **documents** replacing direct mutation.
- **Owns:** StockMovement (audit source), WarehouseStock (authority), WarehouseTransfer,
  StockAdjustmentDoc, WastageDoc.
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
- **Target:** all line types, draft/unpost, purchase return, input-VAT + inventory
  GL legs, payment allocation/ageing.
- **Owns:** PurchaseInvoice(+Line), PurchaseReturn, SupplierPayment(+allocation).
- **Disposition:** EXTEND.

### 2.6 Treasury / Finance & Payment Routing
- **Now:** FinancialAccount, PaymentMethod, BranchPaymentMethod, cash/AR subledgers.
- **Target:** + cash drop / settlement-to-bank / commission posting; opening
  balance as document.
- **Owns:** FinancialAccount, PaymentMethod, BranchPaymentMethod, FinancialAccountMovement (subledger).
- **Disposition:** KEEP + EXTEND.

### 2.7 General Ledger  ⟵ **NET-NEW**
- **Now:** none (subledgers only; no trial balance possible).
- **Target:** ChartOfAccount, **JournalEntry + balanced JournalLine**, posting rules
  per document type; trial balance / P&L / balance sheet read from GL.
- **Owns:** ChartOfAccount, JournalEntry, JournalLine, PostingRule.
- **Disposition:** NET-NEW, **added beside** subledgers (R-5).

### 2.8 Party AR/AP
- **Now:** Customer/Supplier + AR/AP subledgers + statements.
- **Target:** unchanged + allocation + opening-balance documents; feed GL control accounts.
- **Disposition:** KEEP + EXTEND.

### 2.9 Compliance / e-Invoicing  ⟵ **NET-NEW**
- **Now:** `vat_number` + QR-on-receipt notion only; **no ZATCA**.
- **Target:** compliant invoice representation (UUID, hash chain/PIH, CSID stamp,
  TLV QR, invoice counter), clearance/reporting integration, output/input-VAT.
- **Owns:** ComplianceInvoice, InvoiceCounter, VAT ledger accounts.
- **Disposition:** NET-NEW (regulatory; scope unresolved — see CR-5).

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
| Catalog units, category split, price tiers; Sale posting legs; purchase lifecycle; inventory authority promotion; routing commission posting; sales idempotency; opening-balance documents | General Ledger; Table Service/Shifts/KDS; Compliance/e-Invoicing (ZATCA); Delivery/Channel Revenue; Warehouse Transfer; Recipes/Modifiers/Variants |

No context requires replacing an existing module. Every net-new context attaches to
the existing posting engine and tenant/branch scoping.

---

## 4. v3.6 ↔ F&B-doc conflict register

> Format per stakeholder: **(1) v3.6 rule · (2) F&B proposal · (3) recommended
> decision · (4) migration/scope impact.** Recommendations do **not** silently
> override v3.6; each is a decision to be ratified in roadmap slice 0.

| # | Topic | (1) v3.6 rule | (2) F&B proposal | (3) Recommended decision | (4) Migration / scope impact |
|---|---|---|---|---|---|
| CR-1 | Product categorization | Single `ProductCategory` (POS visibility + routing); one category tree. | **Two separate trees**: Sales Categories (menu/POS, revenue-account linked) **and** Inventory Categories (raw material, asset-account linked). | **Adopt the split** — F&B correctly separates menu grouping from stock/GL classification; it is additive and does not violate v3.6 (v3.6 is silent on inventory categories). Keep v3.6's POS-category semantics inside SalesCategory. | New `SalesCategory` + `InventoryCategory` tables; legacy `Category` read-only until reclassified; **no auto-mapping** (admin classifies). |
| CR-2 | Accounting depth | "ERP Lite — **not** a full double-entry system; full GL is **Phase 2**." Financial effects route to named accounts. | Full **USAR 5-level chart of accounts**, IFRS-aligned, true GL now. | **Phase it:** keep subledgers as the MVP truth (v3.6), **introduce GL forward-only** as a defined slice; do not block MVP on full USAR. Ratify the target chart before COGS/VAT work. | Net-new GL layer beside subledgers; opening journal for historical balances; no retro-explosion. |
| CR-3 | Delivery commission | Card fees / commission = **Phase 2**; delivery-platform accounting **not specified**. | Book **gross** invoice as taxable revenue; record delivery commission separately as contra-revenue / marketing expense; do **not** book net. | **Adopt the gross-vs-commission rule** as the target design (it is an accounting-correctness fix, not a v3.6 contradiction), scheduled as a Phase-2-aligned slice. | Net-new DeliveryChannel + commission accounts + VAT-base rule; depends on GL. |
| CR-4 | Card terminal | Card recorded **manually** in MVP; terminal integration = Phase 2. | Implies richer settlement/commission automation. | **Keep v3.6** (manual card in MVP); automate settlement/commission with GL slice. | None now; later additive. |
| CR-5 | e-Invoicing / ZATCA | v3.6 does **not** mention ZATCA; QR-on-receipt + `vat_number` only. | (F&B doc references VAT output/input + IFRS, not full ZATCA Phase 2 crypto.) | **Flag as an unresolved regulatory decision** — neither doc specifies ZATCA Phase 2; treat as net-new compliance context gated on market/timeline confirmation. | Net-new compliance context; large; scope/ownership TBD. |
| CR-6 | Recipes / size-variant depletion | Recipes & modifiers = **Phase 2** ("Restaurants Phase 2+"); RECIPE_CONSUME movement type named in DOMAIN §7.2. | Parent item + **Size Mapping Matrix** + modifier groups; per-size BOM depletion (extra cheese 40g small / 80g large); AVCO + yield factor; kit vs manufacturing-order modes. | **Adopt F&B as the target recipe model** for the Phase-2 recipe slice — it operationalizes v3.6's RECIPE_CONSUME without contradicting it. Ratify kit-vs-MO + sub-recipe policy first. | Net-new Recipe/BOM/Modifier/Variant tables; depends on ProductUnit (R-3) + COGS (R-4). |
| CR-7 | Costing field | v3.6 §7.1 moving-average; ProductUnit implied. | AVCO on stock unit + yield factor per recipe line. | **Align:** move moving-average to `ProductUnit.avg_cost`; add yield factor on recipe lines. | Depends on ProductUnit (R-3). |
| CR-8 | Inventory valuation account | v3.6 posting routes to named accounts; inventory-value debit deferred in code. | Inventory categories each linked to a current-asset account. | **Adopt** inventory-asset accounts as GL control accounts per InventoryCategory. | Depends on GL + CR-1. |

---

## 5. What must be frozen until this is ratified
The entire Catalog & Units rework (R-2, R-3), Costing (R-4), the GL layer (R-5),
and everything downstream of them (COGS, VAT legs, recipes, delivery, ZATCA) are
**frozen** until slice 0 (Accounting & Product Architecture Ratification) resolves
CR-1…CR-8. Master-data CRUD, reporting reads, route dedup planning, and the Gate A
review may proceed in parallel. Sequencing in
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md); migration mechanics in
[TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md).
