# API_AND_MODEL_INVENTORY.md

> **Read-only architecture audit — 3 of 7.** Exhaustive inventory of the current
> API surface and data models, each tagged for disposition, plus a dedicated
> duplication / unsafe-surface register. No runtime code changed;
> `safety/backend-gate-a-wip-2026-07-04` **not** merged.
>
> Disposition tags (rationale in
> [KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md)):
> **K**=Keep · **E**=Extend · **R**=Rework · **D**=Deprecate · **X**=Drop.
> Endpoint claims mirror [SuperPOS API.yaml](SuperPOS%20API.yaml) and the URLconf.

---

## 1. Endpoint inventory

Idempotency column: ✔ = `Idempotency-Key` honored via `pos.services.idempotency`;
✘ = not wired.

### 1.1 `accounts` — auth / identity (mounted **twice**: `/api/auth/` + `/api/accounts/`)

| Method | Path (relative to both mounts) | View | Min role | Idem | Tag |
|---|---|---|---|---|---|
| POST | `login/` | `LoginView` | — | ✘ | K |
| POST | `token/refresh/` | `TokenRefreshView` | — | ✘ | K |
| GET | `me/` | `MeView` | auth | — | K |
| GET/POST | `users/` | `UserListCreateView` | Manager | ✘ | K |
| GET/PATCH/DELETE | `users/{pk}/` | `UserDetailView` | Manager | ✘ | K |
| GET/POST | `branches/` | `BranchListCreateView` (legacy serializer) | Manager | ✘ | **D** |
| GET/PATCH/DELETE | `branches/{pk}/` | `BranchDetailView` (legacy) | Manager | ✘ | **D** |
| GET/PATCH | `tenant/settings/` | `TenantSettingsView` | Manager | — | K |
| GET | `tenant/translations/{lang}/` | `TenantTranslationsView` | auth | — | K |

> **The entire block above is served at BOTH `/api/auth/…` and `/api/accounts/…`.**
> The whole `/api/auth/` mount is tagged **D** (converge on one prefix).

### 1.2 `accounts` — v3.6 branch surface (`/api/branches/`)

| Method | Path | View | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `` | `BranchV2ListCreateView` | ✘ | K |
| GET/PATCH | `{pk}/` | `BranchV2DetailView` | ✘ | K |
| POST | `{pk}/deactivate/` | `BranchDeactivateView` | ✘ | K |
| GET/PATCH | `{pk}/settings/` | `BranchSettingsView` | ✘ | E (default_*_id → FK) |
| GET/POST | `{pk}/users/` | `BranchUsersView` | ✘ | K |
| GET/POST | `{branch}/payment-methods/` | `BranchPaymentMethodListCreateView` | ✘ | K/E |
| GET/PATCH | `{branch}/payment-methods/{pk}/` | `BranchPaymentMethodDetailView` | ✘ | K/E |
| POST | `{branch}/payment-methods/{pk}/deactivate/` | `BranchPaymentMethodDeactivateView` | ✘ | K |
| GET/POST | `{branch}/warehouses/` | `BranchNestedWarehouseListCreateView` (pos) | ✘ | K |

### 1.3 `accounts` — finance / parties / settlements

| Method | Path | View | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `/api/finance/accounts/` | `FinancialAccountListCreateView` | ✘ | K/E |
| GET/PATCH | `/api/finance/accounts/{pk}/` | `FinancialAccountDetailView` | ✘ | K |
| POST | `/api/finance/accounts/{pk}/deactivate/` | `FinancialAccountDeactivateView` | ✘ | K |
| GET | `/api/finance/accounts/{pk}/movements/` | `FinancialAccountStatementView` | ✘ | K |
| GET | `/api/finance/accounts/{pk}/balance/` | `FinancialAccountBalanceView` | ✘ | K |
| GET | `/api/finance/movements/` | `FinancialAccountMovementListView` | ✘ | K |
| GET/POST | `/api/finance/payment-methods/` | `PaymentMethodListCreateView` | ✘ | K |
| GET/PATCH | `/api/finance/payment-methods/{pk}/` | `PaymentMethodDetailView` | ✘ | K |
| POST | `/api/finance/payment-methods/{pk}/deactivate/` | `PaymentMethodDeactivateView` | ✘ | K |
| GET/POST/… | `/api/customers/` (+`{pk}/`,`deactivate/`,`statement/`,`balance/`) | `Customer*View` | ✘ | K/E |
| GET/POST/… | `/api/suppliers/` (+ same sub-routes) | `Supplier*View` | ✘ | K/E |
| GET | `/api/customer-ar/movements/` | `CustomerARMovementListView` | ✘ | K |
| GET | `/api/supplier-ap/movements/` | `SupplierAPMovementListView` | ✘ | K |
| GET/POST | `/api/customer-receipts/` (+`{pk}/`) | `CustomerReceipt*View` | **✔** | K |
| GET/POST | `/api/supplier-payments/` (+`{pk}/`) | `SupplierPayment*View` | **✔** | K |

### 1.4 `pos` — catalog / inventory / sales (`/api/`)

| Method | Path | View / fn | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `categories/` | `CategoryListCreateView` | ✘ | **R** (split Sales/Inventory) |
| GET/POST | `products/` | `ProductListCreateView` | ✘ | E |
| GET | `products/export/` , `products/barcode/{bc}/` , `products/scan/{bc}/` | fns | ✘ | K |
| POST | `products/import/` | `products_import` | ✘ | E |
| GET/PATCH/DELETE | `products/{pk}/` | `ProductDetailView` | ✘ | E |
| **PATCH** | `products/{pk}/stock/` | `product_stock_update` | ✘ | **D** (direct mutation) |
| GET | `products/{pk}/stock-movements/` , `stock-balance/` , `warehouse-stock/` | views | ✘ | K |
| GET/POST | `inventory/batches/` (+`{pk}/`) | `InventoryBatch*View` | ✘ | X or E (batch decision) |
| **POST** | `inventory/purchase/` | `purchase_receipt` | ✘ | **D** (legacy ad-hoc) |
| **POST** | `inventory/adjust/` | `stock_adjustment` | ✘ | **D** (undocumented adjust) |
| GET | `inventory/alerts/` | `inventory_alerts` | ✘ | K |
| GET/**POST** | `stock-movements/` | `StockMovementListCreateView` | ✘ | **D** for POST / K for GET |
| GET/POST/… | `inventory/warehouses/` (+`{pk}/`,`deactivate/`,`{pk}/stock/`) | `Warehouse*View` | ✘ | K |
| GET/POST/… | `inventory/branch-warehouses/` (+`{pk}/`,`deactivate/`) | `BranchWarehouse*View` | ✘ | K |
| GET | `inventory/warehouse-stocks/` | `WarehouseStockListView` | ✘ | K |
| GET/POST | `purchase-invoices/` (+`{pk}/`) | `PurchaseInvoice*View` | **✔** | E |
| GET/POST | `sales/` | `SaleListCreateView` | **✘ (gap)** | E (add idempotency) |
| GET | `sales/export/` | `sales_export` | ✘ | K |
| GET | `sales/{int:pk}/` (+`void/`,`receipt/`) | `SaleDetailView`/`void_sale`/`sale_receipt` | ✘ | **D** (int id) |
| GET | `sales/{uuid}/` (+`void/`,`receipt/`) | same views | ✘ | K/E |
| GET | `dashboard/summary|top-products|low-stock|daily-stats/` | fns | — | K |
| GET | `/api/schema/` , `/api/docs/` | drf-spectacular | — | K |

---

## 2. Model inventory (disposition)

| App | Model | Tag | One-line disposition |
|---|---|---|---|
| accounts | `Tenant` | K | Solid SaaS root. |
| accounts | `Branch` | K/E | Keep; converge routes; consider `default_*` FKs. |
| accounts | `Terminal` | K | Keep; used by sale context. |
| accounts | `User` | K | Keep per-tenant-unique RBAC user. |
| accounts | `BranchSettings` | E | Swap `default_*_id` BigInt placeholders → real FKs. |
| accounts | `BranchUserAssignment` | K | Keep multi-branch mapping. |
| accounts | `FinancialAccount` | K/E | Keep; add `inventory` + tax + revenue account types for GL. |
| accounts | `PaymentMethod` | K | Keep. |
| accounts | `BranchPaymentMethod` | K/E | Keep routing; activate commission posting later. |
| accounts | `FinancialAccountMovement` | K | Keep as **subsidiary** ledger; **not** the GL. |
| accounts | `Customer` / `Supplier` | K/E | Keep; `price_tier_id` BigInt → FK when PriceTier lands. |
| accounts | `CustomerARMovement` / `SupplierAPMovement` | K | Keep subsidiary AR/AP ledgers. |
| accounts | `CustomerReceipt` / `SupplierPayment` | K/E | Keep; add invoice allocation later. |
| pos | `Category` | **R** | Split into SalesCategory + InventoryCategory. |
| pos | `Product` | E/R | Extend (`product_type`, recipe/POS flags); rework unit/pack_qty → ProductUnit; demote `stock`. |
| pos | `InventoryBatch` | X/E | Drop if batch out of scope, else wire into posting. |
| pos | `Sale` / `SaleItem` | K/E | Keep; extend posting with revenue/VAT/COGS; add idempotency. |
| pos | `StockMovement` | K | Keep universal ledger; make it the per-warehouse authority source. |
| pos | `Payment` | K/E | Keep; `MIXED` → real `PaymentLine[]`. |
| pos | `AuditLog` | K | Keep. |
| pos | `DiscountCode` | K | Keep. |
| pos | `IdempotencyRecord` | K | Keep; extend coverage to `POST /sales/`. |
| pos | `Warehouse` / `BranchWarehouse` | K | Keep; `BranchWarehouse` = canonical default home. |
| pos | `WarehouseStock` | K/R | Keep; **promote to authoritative** per-warehouse balance. |
| pos | `PurchaseInvoice` / line | E | Keep; extend lifecycle, non-stock lines, GL/VAT legs, returns. |
| pos | `pos/domain/statuses.py` enums | K | Keep; **wire** when table/order/shift models land. |

---

## 3. Duplication & unsafe-surface register  ⚠️

| # | Item | Where | Risk | Disposition |
|---|---|---|---|---|
| DUP-1 | `accounts.urls` mounted at **both** `/api/auth/` and `/api/accounts/` | [urls.py:18-19](superpos_backend/superpos_backend/urls.py#L18-L19) | Two public identities for every auth/user/branch/tenant route; drift + doc noise. | **D** — pick one prefix, 301/deprecate the other after client cutover. |
| DUP-2 | **Triple branch surface**: legacy `BranchSerializer` at `/api/auth/branches/` + `/api/accounts/branches/`, v3.6 `BranchV2*` at `/api/branches/` | urls.py + `accounts/urls.py` + `accounts/branches_urls.py` | Two serializer shapes for one model; clients may write to the wrong one. | **D** legacy; converge on `/api/branches/`. FE already uses v2. |
| DUP-3 | **Sale dual identity**: `sales/<int:pk>/` and `sales/<uuid>/` (detail/void/receipt) | [pos/urls.py:57-65](superpos_backend/pos/urls.py#L57-L65) | Two ways to address one sale; int-pk leaks internal id. | **D** int-pk (public = UUID) with a compat window. |
| UNSAFE-1 | `PATCH products/{pk}/stock/` sets stock directly | `product_stock_update` | Balance change with **no auditable document**. | **D** → replace with adjustment document. |
| UNSAFE-2 | `POST stock-movements/` creates a raw movement | `StockMovementListCreateView` | Ledger row without a governing document/reason. | **D** for POST; keep GET. |
| UNSAFE-3 | `POST inventory/purchase/` (ad-hoc receive) | `purchase_receipt` | Parallel to real `purchase-invoices/`; no AP/finance posting. | **D** → funnel to `purchase-invoices/`. |
| UNSAFE-4 | `POST inventory/adjust/` | `stock_adjustment` | Undocumented stock adjustment. | **D** → adjustment document w/ reason + approval. |
| IDEM-1 | `POST /sales/` has **no** idempotency | `SaleListCreateView` | Double-submit = duplicate sale + duplicate ledger effects. | **E** — wire `idempotency.lookup/save`. |
| IDEM-2 | Idempotency coverage uneven | receipts/payments/purchases ✔ ; sales ✘ ; table-service POSTs (future) ✘ | Inconsistent guarantee across critical POSTs. | **E** — standardize per API_CONTRACT §2. |
| PLACE-1 | `BranchSettings.default_*_id` BigInt placeholders vs canonical `BranchWarehouse(role,is_default)` | accounts/models.py | Two "default warehouse" truths → drift. | **E** — reconcile; FK swap. |
| PLACE-2 | `Customer.price_tier_id` BigInt placeholder | accounts/models.py | Forward-declared FK; unenforced. | **E** — FK when PriceTier lands. |
| DEAD-1 | `mock.ts` orphaned | superpos/src/data/ | Stale fixtures; drifts from types. | **X** — remove. |
| DEAD-2 | `Payment.MIXED` enum, no split impl | pos/models.py | Enum value with no behavior. | **X/E** — implement `PaymentLine[]` or drop value. |
| DEAD-3 | `InventoryBatch` not in posting | pos/models.py | Modeled, unused. | **X/E** — decide batch/expiry scope. |

---

## 4. Idempotency coverage matrix

| Critical POST | Currently guarded? | Should be (API_CONTRACT §2) |
|---|---|---|
| customer-receipts | ✔ | ✔ |
| supplier-payments | ✔ | ✔ |
| purchase-invoices | ✔ | ✔ |
| **sales** | **✘** | **✔ (gap)** |
| table open / clear, order lines, send-to-kitchen, request-bill, pay, void-line, shift open/close, retry-print | n/a (unbuilt) | ✔ when built |

See [KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md) for the
rationale, blast radius, and migration/compat needs behind every tag above.
