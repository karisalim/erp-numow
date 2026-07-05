# KEEP_EXTEND_REWORK_DEPRECATE.md

> **Read-only architecture audit — 4 of 7.** Disposition verdict for every
> existing concept — **KEEP / EXTEND / REWORK / DEPRECATE / DROP** — with
> rationale, blast radius, and the migration/compat + isolation/history guardrail
> each carries. No runtime code changed; `safety/backend-gate-a-wip-2026-07-04`
> **not** merged.
>
> **Bias: prefer extension over rewrite.** Nothing here requires a full rewrite.
> Every posted table is append-only and tenant-scoped, so new capability slots in
> *beside* existing tables.

---

## Legend
- **KEEP** — correct as-is; build on it.
- **EXTEND** — additive fields/tables/endpoints; existing shape survives.
- **REWORK** — internal redesign needed, but **still additive at schema level**
  (new authoritative table beside the old, old demoted to cache/read-only).
- **DEPRECATE** — keep serving behind a compat window; stop building on it; sunset
  after client cutover.
- **DROP** — safe to remove after explicit confirmation.

Guardrails applied to every row: preserve tenant/branch isolation; preserve posted
history (deactivate, never delete; reverse via compensating document); **no direct
balance/stock correction without an auditable document**.

---

## 1. KEEP

| Concept | Why | Guardrail |
|---|---|---|
| Tenant / Branch / Terminal / User + RBAC + `SubscriptionCheckMiddleware` | Clean, isolated multi-tenant spine; per-tenant username; role floors mirrored FE↔BE. | Any auth change must preserve per-tenant username uniqueness (auth.E003). |
| `FinancialAccount` / `PaymentMethod` / `BranchPaymentMethod` routing | Routing is config-driven, never guessed; method↔account-type compatibility enforced. | Keep the "no hardcoded routing" invariant. |
| Movement ledgers (`FinancialAccountMovement`, `CustomerARMovement`, `SupplierAPMovement`) | Correct append-only **subsidiary** ledgers with locked running balances. | **Never call these a GL.** They become the subledgers under a new GL. |
| Settlement docs (`CustomerReceipt`, `SupplierPayment`) + atomic posting services | Tri-ledger atomic post; reversal-by-compensating-doc is the right pattern. | Keep POSTED-immutable + compensating reversal. |
| `Warehouse` / `BranchWarehouse` | Role-based default home is the canonical branch↔warehouse link. | Keep as the single default-warehouse truth (retire `BranchSettings.default_*`). |
| `StockMovement` (universal `source_document_type/id`, running qty) | Append-only, warehouse-aware, document-agnostic. | It is the audit source; caches derive from it. |
| `IdempotencyRecord` + `pos/services/idempotency.py` | Correct `(tenant,key)` scoping, payload-hash replay, 409 on conflict. | Extend coverage (see §2). |
| `pos/domain/statuses.py` enums | Contract-aligned status vocab, centralized. | Wire to models when table/order/shift land. |
| `AuditLog`, DRF pagination/filter scaffolding, drf-spectacular schema | Reusable cross-cutting infra. | — |
| Frontend design system + honest-state UX + `api/client.ts` (401 refresh, idempotency header) | Real-API consumers, no fake claims, RTL logical props. | Keep honest-state discipline. |

## 2. EXTEND (additive)

| Concept | Extension | Blast radius | Migration/compat |
|---|---|---|---|
| `Product` | Add `product_type` per MASTER_DATA_CONTRACT §11 — **Ingredient · Stock/Resale · Prep/Sub-Recipe · Recipe Product · Packaging · Service/Non-Stock · Bundle/Combo · Fixed Asset (purchase-only)** — plus mandatory flags `sellable` / `purchasable` / `track_inventory` / `base_unit`, `sales_category` (when sellable), `inventory_category` (when stock-controlled), default station. Component sale price only when independently sellable. | Serializer + product form; [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.4. | Additive nullable fields; default `stock_item`; backfill per TRANSITION §2.10. |
| `Sale` / `SaleItem` posting | Add revenue + output-VAT + COGS legs at post time (into the new GL) **and immutable snapshot fields** (R-J): resolved tax/account mapping, recipe version, component quantities + avg costs, total recipe cost (shape per D-31). | `sale_posting` service. | Forward-only; no retro-post of historical sales; legacy rows carry null snapshots. |
| `PurchaseInvoice` | Non-stock/expense/fixed-asset/service lines; input-VAT leg; inventory-GL debit; draft→post lifecycle with **cancellation (pre-post) + reversal/return documents (post)** — a posted document is never "unposted"; purchase return. | `purchase_invoices` service, serializer. | Additive; `posting_status` already present; undo follows the existing compensating-document pattern (DOMAIN §5.3/§5.5/§5.6). |
| `BranchPaymentMethod` | Activate commission/settlement-to-bank posting. | Posting services + finance movement types (already modeled). | Additive posting only. |
| `CustomerReceipt`/`SupplierPayment` | Allocation against named invoices + ageing. | Settlement services + a link table. | New link table; existing docs unaffected. |
| `IdempotencyRecord` coverage | Wire `POST /sales/` (and future table-service POSTs). | `SaleListCreateView`. | Behavioral only; requires FE to send `Idempotency-Key` on sales (client already has the helper). |
| Customer/Supplier | `price_tier_id` BigInt → FK when PriceTier lands; opening-balance-as-document. | serializer + new PriceTier model. | FK swap migration; opening balance becomes a posted doc. |
| `FinancialAccount` → GL link | Add a `gl_account` FK mapping each **operational treasury account** (cash/bank/wallet/card-clearing) to its ChartOfAccount ledger account. GL-only accounts — inventory, revenue, VAT output/input, commission expense — are **ChartOfAccount rows, never FinancialAccount types**. Operational additions stay limited to genuine treasury accounts (e.g. a platform-receivable clearing account). Existing GL-ish types (`customer_ar`/`supplier_ap`/`expense`/`opening_balance`) map to GL control accounts (cleanup item). | New FK + ChartOfAccount (R-5). | Additive FK; mapping reviewed at GL cutover. |
| Reporting | Branch filters across sales/inventory/finance/movements. | views. | Read-only. |

## 3. REWORK (redesign, additive at schema level)

| # | Concept | Current | Target | Why additive | Guardrail |
|---|---|---|---|---|---|
| R-1 | Inventory authority | Global `Product.stock` counter; `WarehouseStock` a partial cache. | **`WarehouseStock` (per product×warehouse) authoritative, quantity denominated in the product base unit ONLY** — never separate balances per conversion unit; `Product.stock` demoted to derived cache. | New table already exists (Slice J); promote it, backfill from `StockMovement`. | No stock "correction" — backfill is a derivation + reconciliation report, not a manual set. Recorded directive R-B (2026-07-04): base-unit-only balances. |
| R-2 | Category | Flat `Category(tenant,name)`. | **Hierarchical SalesCategory** (self-parent «تندرج من»; inheritable tax profile, revenue GL, COGS GL, kitchen station, POS visibility, sort) **+ hierarchical InventoryCategory** (ingredients/prep/packaging/resale; inventory-asset/wastage/adjustment/variance GL defaults) — never merged. Inheritance: `product → child → nearest parent → tenant default`; resolved values **snapshotted on posted documents** (R-J). Full spec: [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.2/§6.3. | New tables beside `Category`; legacy retained read-only until reclassified. | **No automatic mapping** — reclassification is an admin decision (CR-1/D-01, gate G1); category edits never alter posted history. |
| R-3 | Units | Fixed `Product.unit` enum + `pack_qty`. | **UnitGroup / Unit / ProductUnit / ProductBarcodeUnit** — `ProductUnit` represents **conversion definitions only**; stock balances stay in the product base unit (R-1), never stored per conversion unit. `ProductBarcodeUnit` exists **only for packaged/purchase/retail units that need scanning** — menu recipe products and their variants are barcode-free (R-K: menu/PLU-first; variants never via ProductBarcodeUnit). | New tables; `Product.unit`/`pack_qty` seed *proposals*. | Seed values are proposals requiring confirmation, not silent conversion. |
| R-4 | Costing | Moving-average on `Product.cost`; COGS never posted. | **Base-unit moving-average cost** — home per **D-35** (base ProductUnit vs a dedicated InventoryCost/valuation record; recommendation = valuation record); `ProductUnit` stays primarily a conversion definition and **conversion units never carry independent averages**; COGS leg on sale. | Depends on R-3; new home beside `Product.cost`. | Historical cost snapshots on `SaleItem.unit_cost` preserved. |
| R-5 | General Ledger | Subsidiary movement ledgers only; no journal → no trial balance. | Add **ChartOfAccount (full accounting ledger) + JournalEntry + balanced JournalLine** *alongside* the subledgers; posting engine writes both atomically. **`FinancialAccount` stays a separate operational treasury account** that links to its ledger account via `gl_account` — the two concepts are never merged. | GL is a **new** layer; subledgers stay as subledgers. | Historical subledger balances enter GL via an **opening journal**, not retro-explosion. Reconciliation identities in [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §1 must hold at and after cutover. |

> R-1…R-5 are the "replacement-shaped" items. None discards a table; each adds an
> authoritative structure beside the existing one. This is why the overall verdict
> is **ADDITIVE EVOLUTION**, not partial replacement.

## 4. DEPRECATE (compat window, then sunset)

| # | Item | Converge on | Compat plan |
|---|---|---|---|
| D-1 | `/api/auth/*` duplicate mount | `/api/accounts/*` (+ resource prefixes) | Keep both; announce; FE audit; remove `/api/auth/` after cutover (login stays reachable at chosen prefix). |
| D-2 | Legacy branch surfaces (`/api/auth|accounts/branches/`, legacy `BranchSerializer`) | `/api/branches/` v2 | FE already on v2; keep legacy read-only during window. |
| D-3 | Sale int-pk routes (`sales/<int:pk>/…`) | UUID routes | Public id = UUID; keep int-pk resolving during window. |
| D-4 | `PATCH products/{pk}/stock/` | Adjustment **document** | Replace with a reason+approval adjustment doc that posts a `StockMovement`. |
| D-5 | `POST stock-movements/` (raw) | Governing documents | Keep GET; block POST behind a document. |
| D-6 | `POST inventory/purchase/` | `purchase-invoices/` | Redirect ad-hoc receive into the posted purchase path. |
| D-7 | `POST inventory/adjust/` | Adjustment document | Same as D-4. |
| D-8 | `BranchSettings.default_*_id` placeholders | `BranchWarehouse(role,is_default)` | FK swap; stop reading the placeholders. |

> All D-items keep serving until clients cut over — no route is removed in this
> audit. Removal is a scheduled roadmap slice, not implied here.

## 5. DROP (after confirmation)

| # | Item | Condition |
|---|---|---|
| X-1 | `superpos/src/data/mock.ts` | Confirmed orphaned; remove + fixture cleanup. |
| X-2 | `Payment.MIXED` enum value | Drop **iff** split-payment lands as `PaymentLine[]` instead (else EXTEND). |

### 5.1 DEFER / DORMANT (kept in code, unused — not a DROP)

| # | Item | Condition |
|---|---|---|
| X-3 | `InventoryBatch` | **DEFER/DORMANT — do NOT drop now.** Keep the model in code, unused, until batch/expiry/FEFO scope is approved (deferred decision D-19, a scoped blocker that gates only a future batch slice). Wiring into posting or a deliberate removal slice comes only after that approval. |

---

## 6. Roll-up

| Tag | Count (headline items) | Character |
|---|---|---|
| KEEP | ~11 groups | The multi-tenant + master-data + subsidiary-ledger + settlement spine is sound. |
| EXTEND | ~9 | Additive fields/endpoints/posting legs. |
| REWORK | 5 (R-1…R-5) | Bounded, additive-at-schema redesign of catalog/units/costing/inventory-authority/GL. |
| DEPRECATE | 8 (D-1…D-8) | Duplicate routes + direct-mutation endpoints, behind compat windows. |
| DROP | 2 (X-1, X-2) | Dead/placeholder code, decision-gated. |
| DEFER/DORMANT | 1 (X-3) | Kept in code, unused, until batch/expiry/FEFO scope (D-19) is approved. |

**Verdict feeding [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) and
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md): ADDITIVE EVOLUTION** — no
module is replaced; the GL is *added*, catalog/units/inventory-authority are
*reworked additively*, and duplicate/unsafe surfaces are *deprecated behind compat
windows*. Freeze all REWORK + catalog/GL EXTEND items until the accounting/product
architecture is ratified (see roadmap slice 0).
