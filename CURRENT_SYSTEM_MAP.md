# CURRENT_SYSTEM_MAP.md

> **Read-only architecture audit — 1 of 7.** Captures the *as-built* state of
> SuperPOS (branch `mvp/counter-cafe-demo-readiness`) from database to API to
> frontend. No runtime code, migrations, DB, tests, or frontend were modified to
> produce this. `safety/backend-gate-a-wip-2026-07-04` is **not** merged.
>
> Companion docs: [END_TO_END_WORKFLOW_STATUS.md](END_TO_END_WORKFLOW_STATUS.md) ·
> [API_AND_MODEL_INVENTORY.md](API_AND_MODEL_INVENTORY.md) ·
> [KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md) ·
> [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) ·
> [TRANSITION_AND_MIGRATION_PLAN.md](TRANSITION_AND_MIGRATION_PLAN.md) ·
> [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)
>
> **Source-of-truth note:** v3.6 docs (`enhacment_new_version/*`) remain the
> approved business authority. The untracked `F&B Accounting System Design.md` is
> *candidate research only* (see [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md)
> conflict register).

---

## 1. Stack & top-level layout

| Layer | Tech | Location |
|---|---|---|
| Backend | Django 4.2.30 + DRF, SimpleJWT, django-filter, drf-spectacular, corsheaders; Python 3.12 | [superpos_backend/](superpos_backend/) |
| Database | PostgreSQL (`NAME=superpos`, localhost:5432); creds hard-coded in `settings.py` on base branch | — |
| Frontend | React 18 + TS 5.6 + Vite 5, Tailwind 3, react-router-dom 6, zustand 5, axios, i18next | [superpos/src/](superpos/src/) |
| Product docs | v3.6 PRD/FLOW/DOMAIN/DESIGN + UX prototype | [enhacment_new_version/](enhacment_new_version/) |

Two Django apps: **`accounts`** (tenancy, identity, finance master-data, AR/AP,
settlements) and **`pos`** (catalog, inventory, warehouses, sales, purchases,
dashboard). Cross-app rule observed in code: `pos` imports `accounts` *models/
permissions* (leaf modules) only, never `accounts` views/urls — so no circular
import (see [accounts/branches_urls.py:11-15](superpos_backend/accounts/branches_urls.py#L11-L15)).

---

## 2. Data model catalog

Scoping legend: **T** = tenant FK, **B** = branch FK/branch-aware, **A** =
append-only (no update/delete of posted rows in normal flow).

### 2.1 `accounts` app — [accounts/models.py](superpos_backend/accounts/models.py)

| Model | Scope | Key fields | Purpose / notes |
|---|---|---|---|
| `Tenant` | — | plan, active, currency/language/timezone, printer/scale/payment toggles, `translation_overrides` (JSON) | SaaS tenant + device/UX config. |
| `Branch` | T | `code`, `branch_type`, tax/currency/timezone, `is_main`, legacy `active` + `is_active` **property alias** | v3.6 master-data branch. `is_active` is a read-only alias over DB column `active`. |
| `Terminal` | B | name, serial (global unique) | POS device. |
| `User` (AbstractUser) | T,B | role (Owner/Admin/Manager/Cashier), `terminal`, hashed `pin_code`; username unique **per tenant** (auth.E003 silenced) | Custom auth user + RBAC. |
| `BranchSettings` | T,B | `default_*_id` **BigInt placeholders**, `allow_negative_stock`, `require_shift_for_pos`, `allow_shift_close_with_open_orders`, receipt header/footer | Per-branch operational defaults; created lazily on first GET. |
| `BranchUserAssignment` | T,B | `role_at_branch`, `is_default_branch` | Multi-branch user mapping (legacy `User.branch` = primary). |
| `FinancialAccount` | T,(B) | `account_type` (cashbox/main_safe/bank/card_settlement/wallet/customer_ar/supplier_ap/expense/opening_balance/other), `opening_balance` | Money destination. `opening_balance` **stored, not posted**. |
| `PaymentMethod` | T | `method_type` (cash/card/wallet/credit/custom), `requires_customer` (forced True for credit in `save()`) | Tenant payment method. |
| `BranchPaymentMethod` | T,B | `destination_account`, `settlement_bank_account`, `commission_percent`, `fixed_fee`, `commission_expense_account`, `is_default` | **Routing source of truth.** Commission fields modeled but not posted. |
| `FinancialAccountMovement` | T,(B),A | `debit`⊕`credit` (CHECK: exactly one > 0), `balance_before/after`, `movement_type` (20 types), `source_document_type/id`, `terminal_id`/`shift_id` (plain int) | **Subsidiary** cash/bank/wallet ledger with running balance. **Not** a journal. |
| `Customer` (_PartyBase) | T | `credit_limit`, `price_tier_id` (**BigInt placeholder**), `opening_balance` | Master data; opening balance not posted. |
| `Supplier` (_PartyBase) | T | `opening_balance` | Master data. |
| `CustomerARMovement` | T,(B),A | debit⊕credit, balance_before/after, movement_type, source_document_* | AR subsidiary ledger (asset-like). |
| `SupplierAPMovement` | T,(B),A | debit⊕credit, balance_before/after | AP subsidiary ledger (liability-like). |
| `CustomerReceipt` (_SettlementDocumentBase) | T,(B),A | amount, `payment_method`, `destination_account`, `posted_at`, `status=posted` | Settlement doc; posts AR credit + FinAcct debit atomically. Reversal = compensating doc. |
| `SupplierPayment` (_SettlementDocumentBase) | T,(B),A | amount, `source_account`, `posted_at` | Posts AP debit + FinAcct credit atomically. |

### 2.2 `pos` app — [pos/models.py](superpos_backend/pos/models.py)

| Model | Scope | Key fields | Purpose / notes |
|---|---|---|---|
| `Category` | T | `name` only (`unique_together (tenant,name)`) | **Flat** category. No nesting / POS flags / station / account link. |
| `Product` | T | `barcode`, `sku`, `category`, `price`, `cost`, `tax_rate`, **`stock` (global cached qty)**, `reorder`, `weighted`, **`unit` (fixed enum piece/kg/liter/carton)**, **`pack_qty` (fixed)**, `plu` | Catalog core + `deduct_stock()` row-locked helper. No `product_type`, no ProductUnit, no recipe. |
| `InventoryBatch` | T | batch_number, remaining_quantity, expiry, cost_price | Modeled; **not driven by any posting path**. |
| `Sale` | T,B | `sale_uuid` (public id), cashier, `customer`, subtotal/tax/total, `method`, `payment_method_hint`, discount, status (completed/voided/refunded) | Counter sale header. |
| `SaleItem` | (via Sale) | product, qty, price_each, line_total, **`unit_cost` snapshot**, `warehouse` (traceability) | Cost captured but **COGS never posted**. |
| `StockMovement` | T,B,A | qty, movement_type (sale_out/purchase_in/receive_in/return_in/adjustment), `warehouse`, `quantity_before/after`, `source_document_type/id`, `actor_user`, legacy `sale` FK | Append-only stock ledger; running qty null on legacy rows. |
| `Payment` | (1:1 Sale) | method (incl. `MIXED` placeholder), status, amount, amount_paid, change | Payment metadata. `MIXED` unused (no split impl). |
| `AuditLog` | T,A | action, model_name, object_id, old/new JSON, ip/ua, reason | Admin-change ledger via `log_change()`. |
| `DiscountCode` | T | code, type, value, validity, max_uses, applicable_products (M2M) | Coupons. |
| `IdempotencyRecord` | T | key, request_hash, response snapshot; `(tenant,key)` unique | Idempotency store (wired on some POSTs only — see §4). |
| `Warehouse` | T | `code`, `warehouse_type`, is_active | Tenant stock location (no direct branch FK). |
| `BranchWarehouse` | T,B | `role` (sales/purchase_receiving/kitchen/bar/returns/damaged), `is_default` | **Canonical** branch↔warehouse default home. |
| `WarehouseStock` | T | product, warehouse, `quantity` (signed) | **Cached** per-warehouse balance (Slice J). Invariant: Σ + unassigned == `Product.stock`. |
| `PurchaseInvoice` | T,B,A | supplier, totals, `paid_amount`/`credit_amount`, `payment_method`, `source_account`, `posting_status` (default POSTED), `payment_status` | Create-and-post purchase (stock-item only). |
| `PurchaseInvoiceLine` | T | product, warehouse, `line_type` (stock_item/expense/fixed_asset/service/non_stock — **only stock_item posts**), qty, unit_cost, discount, tax, line_total | Tax stored, not posted. |

### 2.3 Status vocabulary — [pos/domain/statuses.py](superpos_backend/pos/domain/statuses.py)
Full v3.6 enums exist as `TextChoices`: `PostingStatus`, `PaymentStatus`,
`ReturnStatus`, `ApprovalStatus`, `SyncStatus`, `OpenOrderStatus`,
`OpenOrderLineStatus`, `TableStatus`, `KitchenTicketStatus`, `ShiftStatus` +
`STATUS_REGISTRY`. **Defined but unwired** — no Table/OpenOrder/KitchenTicket/
Shift model references them yet.

---

## 3. Migration timeline (foundation slices)

| accounts | pos | Added |
|---|---|---|
| 0001–0009 | 0001–0011 | Base tenancy, branch/terminal, per-tenant username, tenant localization/hardware/payment toggles, receipt header; products, Sale rename, StockMovement, discount/tax, pack_qty, indexes, AuditLog/DiscountCode/Payment. |
| 0010 | — | Branch master-data foundation (BranchSettings, BranchUserAssignment). |
| 0011 | — | Finance payment foundation (FinancialAccount, PaymentMethod, BranchPaymentMethod). |
| 0012 | 0012 | accounts: FinancialAccountMovement. pos: backfill branches + enforce `Sale.branch` NOT NULL. |
| 0013 | 0013 | accounts: Customer/Supplier master data. pos: drop `Product.stock >= 0` constraint (oversell allowed). |
| 0014 | 0014 | accounts: AR/AP ledgers. pos: IdempotencyRecord. |
| 0015 | 0015 | accounts: CustomerReceipt/SupplierPayment. pos: StockMovement actor_user + source_document_*. |
| 0016 | 0016 | accounts: `balance_before` on movements. pos: StockMovement running_quantity. |
| — | 0017 | Warehouse + BranchWarehouse + StockMovement.warehouse. |
| — | 0018 | PurchaseInvoice + line. |
| — | 0019 | Sale.customer + SaleItem.unit_cost/warehouse. |
| — | 0020 | WarehouseStock. |
| **0017 (safety only)** | — | **`0017_backfill_branch_payment_routing`** — Gate A data migration (unmerged): provisions default cashbox/card/wallet accounts + methods + default `BranchPaymentMethod` for every branch with no routing; demotes duplicate active defaults. Reverse = noop. |

---

## 4. API route tree (mounted in [superpos_backend/urls.py](superpos_backend/superpos_backend/urls.py))

```
/admin/
/api/auth/        ─┐  ← SAME include('accounts.urls')  ── DUPLICATE MOUNT
/api/accounts/    ─┘     login, token/refresh, me, users, branches (legacy),
                         tenant/settings, tenant/translations
/api/branches/          BranchV2* + settings + users + payment-methods(+deactivate)
                        + nested warehouses               ← v3.6 branch surface
/api/finance/           accounts(+deactivate/movements/balance), movements,
                        payment-methods(+deactivate)
/api/customers/         CRUD + deactivate + statement + balance
/api/suppliers/         CRUD + deactivate + statement + balance
/api/customer-ar/movements/      flat AR stream
/api/supplier-ap/movements/      flat AP stream
/api/customer-receipts/          list/create (Idempotency-Key) + detail
/api/supplier-payments/          list/create (Idempotency-Key) + detail
/api/  (pos.urls):
    categories/
    products/ (+export/import/barcode/scan/{pk}/ {pk}/stock/ ← DIRECT PATCH
              {pk}/stock-movements/ {pk}/stock-balance/ {pk}/warehouse-stock/)
    inventory/batches/  inventory/purchase/ ← LEGACY  inventory/adjust/ ← LEGACY
    inventory/alerts/
    stock-movements/    ← RAW POST create
    inventory/warehouses/(+{pk}/ +deactivate +{pk}/stock/)
    inventory/branch-warehouses/(+{pk}/ +deactivate)
    inventory/warehouse-stocks/
    purchase-invoices/ (+{pk}/)   ← create-and-post (Idempotency-Key)
    sales/ (+export)
    sales/<int:pk>/(+void +receipt)     ← DUAL IDENTITY (legacy)
    sales/<uuid:sale_uuid>/(+void +receipt)  ← preferred public id
    dashboard/summary|top-products|low-stock|daily-stats
/api/schema/  /api/docs/   (drf-spectacular)
```

**Flagged duplications / legacy surfaces** (detailed in
[API_AND_MODEL_INVENTORY.md](API_AND_MODEL_INVENTORY.md) §Duplication register):
1. **`/api/auth/` and `/api/accounts/` are the identical include** → every
   auth/user/branch/tenant route is served twice.
2. **Triple branch surface:** legacy `BranchSerializer` under
   `/api/auth/branches/` *and* `/api/accounts/branches/`, plus v3.6 `BranchV2*`
   under `/api/branches/`.
3. **Sale dual identity:** `<int:pk>` and `<uuid:sale_uuid>` variants of detail/
   void/receipt.
4. **Direct-mutation endpoints (no auditable document):** `PATCH products/{pk}/
   stock/`, `POST stock-movements/`, `POST inventory/purchase/`, `POST inventory/
   adjust/`.
5. **Idempotency wired only** on customer-receipts, supplier-payments, and
   purchase-invoices — **not** on `POST /sales/`.

---

## 5. Frontend map — [superpos/src/App.tsx](superpos/src/App.tsx)

| Route | Page | Min role | Primary API consumers |
|---|---|---|---|
| `/login` | LoginPage | — | `POST /api/auth/login/` |
| `/pos` | POSPage | Cashier | `POST /sales/` (+customer/discount/credit), products/scan, PaymentModal routing |
| `/receipt` , `/receipt/:saleUuid` | ReceiptPage | Cashier | `GET /sales/{uuid}/` , `/receipt/` |
| `/sales` | SalesPage | Cashier | `GET /sales/?page&method&dates` (server pagination) |
| `/dashboard` | DashboardPage | Manager | dashboard/* |
| `/products` | ProductsPage | Manager | products CRUD, receive-stock, stock-movements modal |
| `/inventory` | InventoryPage | Manager | stock-movements, batches, alerts |
| `/warehouses` | WarehousesPage | Manager | inventory/warehouses, warehouse-stocks |
| `/customers` , `/suppliers` | Customers/Suppliers | Manager | parties CRUD + statement/balance + settlements |
| `/purchases` , `/new` , `/:id` | Purchases* | Manager | purchase-invoices (Idempotency-Key) |
| `/finance` | FinancePage | Manager | finance accounts/methods, branch routing, settlements |
| `/users` , `/settings` , `/scale` | Users/Settings/Scale | Manager | users, tenant settings |
| `/` , `*` | → `/pos` | — | — |

- **Guarding:** `RequireRole` renders an explicit access-denied screen (not a
  redirect); role floors mirror backend permission classes; every backend 403
  renders `PermissionDeniedState`.
- **API client:** [superpos/src/api/client.ts](superpos/src/api/client.ts) —
  axios base `http://127.0.0.1:8000/api`, Bearer from localStorage, single-flight
  401 refresh, subscription/auth global events; `Idempotency-Key` helper in
  [api/idempotency.ts](superpos/src/api/idempotency.ts).
- **Orphaned / debt:** [superpos/src/data/mock.ts](superpos/src/data/mock.ts)
  imported by nothing (not in production routes); **no test framework** installed;
  Users page 100-row cap; new ERP page bodies English-only pending i18n pass.

---

## 6. Branch topology

| Branch | Role |
|---|---|
| `main` | Phase-0 baseline. |
| `mvp/counter-cafe-demo-readiness` | **Current.** Frontend ERP-lite + honest POS on real backend (7 FE commits over the phase1_5 backend). |
| `phase1/foundation-status-and-idempotency` | Status enums + idempotency scaffolding. |
| `phase1_5/*` (14 branches) | Incremental backend foundations: dynamic branches, finance/payment, movement ledger, customer/supplier, AR/AP, receipts/payments, warehouses, per-warehouse stock, purchase posting, sales posting integration, stock hardening, build hygiene. |
| `safety/backend-gate-a-wip-2026-07-04` | **Quarantined, unmerged.** Gate A sales financial integrity (strict routing, credit limit, negative-stock policy, env config, backfill 0017, +535 L tests). Reviewed here, **not** merged. |

---

## 7. Cross-cutting infrastructure (reusable)

- **Tenant isolation:** every queryset filters by `request.user.tenant`; middleware
  `SubscriptionCheckMiddleware` hard-blocks `/api/*` for inactive/expired tenants.
- **RBAC:** `IsCashierOrAbove` / `IsManagerOrAbove` permission classes; per-branch
  assignment model exists.
- **Posting services** (atomic, reusable): `accounts/services/` (account_movements,
  customer_ar, supplier_ap, customer_receipts, supplier_payments, _party_ledger);
  `pos/services/` (sale_posting, purchase_invoices, stock_movements, idempotency).
- **Running-balance discipline:** movement writers use `select_for_update()` on
  prior rows so concurrent posts can't interleave the running balance.
- **OpenAPI:** `drf-spectacular` schema at `/api/schema/`, mirror committed as
  [SuperPOS API.yaml](SuperPOS%20API.yaml).

See [END_TO_END_WORKFLOW_STATUS.md](END_TO_END_WORKFLOW_STATUS.md) for which of
these actually complete a workflow, and where they stop.
