# END_TO_END_WORKFLOW_STATUS.md

> **Read-only architecture audit — 2 of 7.** Which workflows actually complete
> end-to-end, which are partial, and which are absent — with the concrete code
> path and the exact stopping point. No runtime code changed;
> `safety/backend-gate-a-wip-2026-07-04` **not** merged.
>
> Status legend: ✅ **Works E2E** · ⚠️ **Partial** (works but has a material gap) ·
> ❌ **Absent** (spec'd, not built). "Gate A" = the quarantined safety branch.

---

## 1. Sales / POS

| # | Workflow | Status | Code path & stopping point |
|---|---|---|---|
| 1.1 | Barcode/weight scan → cart | ✅ | `product_scan` / `product_by_barcode` ([pos/views.py:142](superpos_backend/pos/views.py#L142)); weight-encoded barcode parsed by `_parse_weight_encoded_barcode`. |
| 1.2 | Counter checkout → Sale + SaleItem + Payment | ✅ | `SaleListCreateView` → `SaleSerializer.create` ([pos/serializers.py](superpos_backend/pos/serializers.py)); atomic. |
| 1.3 | Stock deduction on sale | ⚠️ | `SaleSerializer._apply_stock` → `Product.deduct_stock` + `StockMovement`. Deducts **global `Product.stock`**; `WarehouseStock` updated only when the line carries a warehouse. **Oversell allowed by default** on mvp (warning only). Gate A blocks oversell unless `BranchSettings.allow_negative_stock`. |
| 1.4 | Financial routing of sale proceeds | ⚠️ | `sale_posting.post_sale_ledgers` posts one `FinancialAccountMovement` (cash/card/wallet) or `CustomerARMovement` (credit). **mvp = best-effort:** a branch with *no* `BranchPaymentMethod` rows completes the sale **without** a GL row (logged WARNING). **Gate A = strict:** every completed sale must resolve an active route or the whole sale rolls back (400). |
| 1.5 | Revenue / output-VAT / COGS legs | ❌ | Only the **funding side** posts. No revenue account, no output-VAT ledger, no COGS. `SaleItem.unit_cost` is snapshotted but never posted. → no balanced trial balance. |
| 1.6 | Credit sale → Customer AR + credit-limit check | ⚠️ | AR posts via `customer_ar`. **Credit-limit enforcement exists only on Gate A** (`SaleSerializer.create` blocks if `balance + total > credit_limit`). mvp does not enforce the limit. |
| 1.7 | Sale idempotency (double-submit safety) | ❌ | `POST /sales/` does **not** call `idempotency.lookup/save` (only settlements + purchase-invoices do). A retried checkout creates a second Sale. |
| 1.8 | Durable receipt | ✅ | `sale_receipt` by uuid/pk; frontend `/receipt/:saleUuid` refetches `GET /sales/{uuid}/`. |
| 1.9 | Void sale | ⚠️ | `void_sale` flips `Sale.status=voided`. **No** line-level void, **no** manager-approval gate, **no** compensating ledger reversal wired to it. |
| 1.10 | Sales return | ❌ | `ReturnStatus` enum + AR/AP `SALES_RETURN`/`PURCHASE_RETURN` movement types exist, but **no return document / endpoint / posting**. |
| 1.11 | Split / mixed payment | ❌ | `Payment.MIXED` enum only; no `PaymentLine[]`, no multi-tender capture. |

## 2. Purchasing / AP

| # | Workflow | Status | Code path & stopping point |
|---|---|---|---|
| 2.1 | Purchase invoice create-and-post (stock items) | ✅ | `PurchaseInvoiceListCreateView` → `purchase_invoices.post_purchase_invoice` (atomic): document + lines + AVCO cost update + `StockMovement PURCHASE_IN` + cash/bank credit (if paid) + Supplier AP credit (if credit). Idempotency-Key honored. |
| 2.2 | Inventory-value GL debit on purchase | ❌ | Documented deferral: inventory tracked by `StockMovement` qty + `Product.cost` only; **no Inventory GL account / debit leg** → purchase does not balance in double-entry terms. |
| 2.3 | Input-VAT on purchase | ❌ | `tax_amount`/`tax_total` **stored but not posted** (v3.6 leaves purchase-tax undefined). |
| 2.4 | Non-stock/expense/fixed-asset/service purchase lines | ❌ | `PurchaseInvoiceLine.LineType` has them, but the service **rejects anything but `stock_item`**. |
| 2.5 | Purchase draft → post lifecycle / unpost / reversal | ⚠️ | `PostingStatus.DRAFT` exists but the service **always create-and-posts** (`POSTED`). No usable draft, no unpost, no purchase return. |
| 2.6 | Supplier payment settlement | ✅ | `SupplierPaymentListCreateView` → `create_supplier_payment` (atomic: doc + AP debit + FinAcct credit). Idempotency-Key required. |
| 2.7 | Supplier payment allocation to specific invoices | ❌ | Documented deferral: payment records amount only; **no FIFO/manual allocation / ageing against named invoices**. |

## 3. Treasury / Finance / Party ledgers

| # | Workflow | Status | Code path |
|---|---|---|---|
| 3.1 | Financial account CRUD + deactivate | ✅ | `FinancialAccount*View`. |
| 3.2 | Payment method + branch routing config | ✅ | `PaymentMethod*` + `BranchPaymentMethod*`; method↔account-type compatibility enforced in serializer. Gate A adds "at most one active default per (branch, method_type)". |
| 3.3 | Customer receipt settlement | ✅ | `create_customer_receipt` (atomic: doc + AR credit + FinAcct debit). Idempotency-Key required. |
| 3.4 | Account / customer / supplier statements | ✅ | `*StatementView` read from movement rows with `balance_before/after` — reports never read UI state. |
| 3.5 | Opening balances → auditable posting | ⚠️ | `opening_balance` on FinancialAccount/Customer/Supplier is **stored, never posted** as a movement. Balances derived from movements therefore ignore it. |
| 3.6 | Card commission / settlement-to-bank posting | ❌ | `commission_percent`/`fixed_fee`/`commission_expense_account` + `SETTLEMENT_TO_BANK`/`SETTLEMENT_FROM_CARD` movement types modeled, **not posted**. |

## 4. Inventory / warehouses

| # | Workflow | Status | Code path & stopping point |
|---|---|---|---|
| 4.1 | Warehouse + branch-warehouse CRUD | ✅ | `Warehouse*` / `BranchWarehouse*`; role-based defaults with DB uniqueness. |
| 4.2 | Per-warehouse balance (read) | ✅ | `WarehouseStock` cache; `warehouse-stocks/`, `warehouses/{id}/stock/`, `products/{id}/warehouse-stock/`. |
| 4.3 | Authoritative on-hand quantity | ⚠️ | **`Product.stock` (global) is authoritative**; `WarehouseStock` is a cache maintained only for movements that carry a warehouse. Legacy/unconfigured movements bypass it → per-warehouse truth is not guaranteed complete. |
| 4.4 | Warehouse transfer | ❌ | `WarehouseTransfer` in the contract only; no model/endpoint. |
| 4.5 | Direct stock edit (unsafe) | ⚠️ | `PATCH products/{id}/stock/`, `POST stock-movements/`, `POST inventory/purchase/`, `POST inventory/adjust/` mutate stock **without an auditable business document**. Works, but violates the "no direct correction" principle. |
| 4.6 | Batch / expiry tracking | ❌ | `InventoryBatch` modeled but not driven by any posting path. |

## 5. Table service / kitchen / shifts (F&B core)

| # | Workflow | Status | Notes |
|---|---|---|---|
| 5.1 | Tables / sections | ❌ | Contract + `TableStatus` enum only; no model/API. |
| 5.2 | Open order / lines (draft vs sent) | ❌ | `OpenOrderStatus`/`OpenOrderLineStatus` enums only. |
| 5.3 | Send-to-kitchen / kitchen tickets | ❌ | `KitchenTicketStatus` enum only. |
| 5.4 | Request bill / pay-converts-to-invoice | ❌ | API contract §3.7–3.8 unbuilt. |
| 5.5 | Shifts (open/close, close-block) | ❌ | `ShiftStatus` enum + `shift_id` placeholder ints only. |
| 5.6 | Wastage / complimentary / inventory-loss | ❌ | Contract only. |

## 6. Catalog richness (F&B)

| # | Capability | Status |
|---|---|---|
| 6.1 | Nested/POS `ProductCategory` (station, sort, show_on_pos, revenue link) | ❌ (flat `Category` only) |
| 6.2 | Sales-category vs Inventory-category split | ❌ |
| 6.3 | UnitGroup/Unit/ProductUnit/ProductBarcodeUnit | ❌ (fixed `Product.unit` + `pack_qty`) |
| 6.4 | Price tiers + `ProductUnitTierPrice` | ❌ (`price_tier_id` is a BigInt placeholder) |
| 6.5 | `product_type` (stock/recipe/ingredient/service/bundle) | ❌ |
| 6.6 | Recipes / BOM / modifiers / size variants / RECIPE_CONSUME | ❌ |

## 7. Compliance / channels

| # | Capability | Status |
|---|---|---|
| 7.1 | ZATCA Phase 2 e-invoicing (hash chain, CSID, TLV QR, clearance/reporting) | ❌ — **zero** presence; `vat_number` + QR-on-receipt notion only. |
| 7.2 | Delivery-platform accounting (gross revenue vs commission) | ❌ — no channel/commission model; only in-store methods. |
| 7.3 | Document numbering sequences | ❌ — contract only. |

## 8. Platform / non-functional

| # | Concern | Status |
|---|---|---|
| 8.1 | Tenant/branch isolation | ✅ every queryset tenant-scoped; subscription middleware gate. |
| 8.2 | RBAC + access-denied UX | ✅ backend permission classes mirrored by `RequireRole`. |
| 8.3 | Secrets / prod config | ⚠️ mvp hard-codes `SECRET_KEY`/DB pw/`DEBUG`/`ALLOW_ALL`. **Gate A** makes them env-driven (`.env.example`). |
| 8.4 | Automated tests — backend | ✅ substantial `pos`/`accounts` suites (Gate A adds +535 L). |
| 8.5 | Automated tests — frontend | ❌ no runner installed. |

---

## 9. Gate A behavior delta (if the safety branch is later landed)

| Behavior | mvp (current) | Gate A (safety, unmerged) |
|---|---|---|
| Sale with unrouted branch | Completes, **no GL row** (warning) | **400, sale rolls back** |
| Route resolution | default-or-any | deterministic `(-is_default, -id)` |
| Duplicate active default route | possible | serializer rejects; migration `0017` demotes |
| Legacy branches without routing | best-effort skip | migration `0017` provisions default cashbox/card/wallet routing |
| Credit sale over limit | allowed | **blocked** (`credit_limit_exceeded`) |
| Oversell | allowed (warning) | **blocked** unless `allow_negative_stock` (`insufficient_stock`) |
| Prod secrets/config | hard-coded | env-driven |
| Error shape | `{field: msg}` | `{field:[msg], code, detail}` |

> **Constraint honored:** this comparison is analysis only — the safety branch is
> **not** merged. Its landing plan is in
> [TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) §Gate A.

---

## 10. Headline reliability blockers for an F&B/accounting system
1. **No balanced double-entry GL** — sales post funding only; no revenue/COGS/VAT;
   purchases post no inventory debit → no trial balance (§1.5, §2.2–2.3).
2. **Inventory authority on a global counter** — `Product.stock`, not per-warehouse
   (§4.3), with **direct-mutation bypasses** (§4.5).
3. **Flat catalog** — no ProductUnit, no category split, no recipes/modifiers/
   variants (§6) → no F&B costing or menu engineering.
4. **Sales idempotency gap** (§1.7) on the highest-volume endpoint.
5. **Returns / line-void / manager-approval / shifts / tables** absent (§1.9–1.11,
   §5).
6. **Delivery + ZATCA** absent (§7).

These are sized and sequenced in
[KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md) and
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md).
