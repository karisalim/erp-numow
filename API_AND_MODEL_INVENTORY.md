# API_AND_MODEL_INVENTORY.md

> **Read-only architecture audit — 3 of 7.** Endpoint and model inventory of the
> current API surface **as derived from the URLconf (the runtime truth for this
> branch)**, each tagged for disposition, plus a dedicated duplication /
> unsafe-surface register. No runtime code changed;
> `safety/backend-gate-a-wip-2026-07-04` **not** merged.
>
> Disposition tags (rationale in
> [KEEP_EXTEND_REWORK_DEPRECATE.md](KEEP_EXTEND_REWORK_DEPRECATE.md)):
> **K**=Keep · **E**=Extend · **R**=Rework · **D**=Deprecate · **X**=Drop.
>
> **Authority note (schema accuracy):** endpoint claims follow the **URLconf**
> (runtime truth for this branch). The committed
> [SuperPOS API.yaml](SuperPOS%20API.yaml) was generated from **Gate A WIP
> code** and is ahead of the mvp runtime in places — it documents a
> financially-correct void with compensating ledger entries and an
> `Idempotency-Key` on `/sales/{id}/void/` that do **not** exist on this branch,
> and its descriptions contain path drift around `warehouse-stock(s)`: **this
> branch's actual route is the singular** `products/{pk}/warehouse-stock/`,
> while the plural `warehouse-stocks/` is what the frontend and the Gate A WIP
> use — a **current FE/BE mismatch (PATH-1/GA-10), not an existing plural route
> on mvp**. Regenerating the schema from the active branch is a
> post-ratification hygiene item.

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
| GET/PUT/PATCH/DELETE | `users/{pk}/` | `UserDetailView` | Manager | ✘ | K |
| GET/POST | `branches/` | `BranchListCreateView` (legacy serializer) | Manager | ✘ | **D** |
| GET/PUT/PATCH/DELETE | `branches/{pk}/` | `BranchDetailView` (legacy) | Manager | ✘ | **D** |
| GET/PUT/PATCH | `tenant/settings/` | `TenantSettingsView` | Manager | — | K |
| GET/PUT/DELETE | `tenant/translations/{lang}/` | `TenantTranslationsView` | auth | — | K |

> **The entire block above is served at BOTH `/api/auth/…` and `/api/accounts/…`.**
> The whole `/api/auth/` mount is tagged **D** (converge on one prefix).

### 1.2 `accounts` — v3.6 branch surface (`/api/branches/`)

| Method | Path | View | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `` | `BranchV2ListCreateView` | ✘ | K |
| GET/PUT/PATCH | `{pk}/` | `BranchV2DetailView` | ✘ | K |
| POST | `{pk}/deactivate/` | `BranchDeactivateView` | ✘ | K |
| GET/PATCH | `{pk}/settings/` | `BranchSettingsView` | ✘ | E (default_*_id → FK) |
| GET/POST | `{pk}/users/` | `BranchUsersView` | ✘ | K |
| GET/POST | `{branch}/payment-methods/` | `BranchPaymentMethodListCreateView` | ✘ | K/E |
| **PATCH only** (no GET detail) | `{branch}/payment-methods/{pk}/` | `BranchPaymentMethodDetailView` | ✘ | K/E |
| POST | `{branch}/payment-methods/{pk}/deactivate/` | `BranchPaymentMethodDeactivateView` | ✘ | K |
| GET/POST | `{branch}/warehouses/` | `BranchNestedWarehouseListCreateView` (pos) | ✘ | K |

### 1.3 `accounts` — finance / parties / settlements

| Method | Path | View | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `/api/finance/accounts/` | `FinancialAccountListCreateView` | ✘ | K/E |
| GET/PUT/PATCH | `/api/finance/accounts/{pk}/` | `FinancialAccountDetailView` | ✘ | K |
| POST | `/api/finance/accounts/{pk}/deactivate/` | `FinancialAccountDeactivateView` | ✘ | K |
| GET | `/api/finance/accounts/{pk}/movements/` | `FinancialAccountStatementView` | ✘ | K |
| GET | `/api/finance/accounts/{pk}/balance/` | `FinancialAccountBalanceView` | ✘ | K |
| GET | `/api/finance/movements/` | `FinancialAccountMovementListView` | ✘ | K |
| GET/POST | `/api/finance/payment-methods/` | `PaymentMethodListCreateView` | ✘ | K |
| GET/PUT/PATCH | `/api/finance/payment-methods/{pk}/` | `PaymentMethodDetailView` | ✘ | K |
| POST | `/api/finance/payment-methods/{pk}/deactivate/` | `PaymentMethodDeactivateView` | ✘ | K |
| GET/POST/… | `/api/customers/` (+`{pk}/`,`deactivate/`,`statement/`,`balance/`) | `Customer*View` | ✘ | K/E |
| GET/POST/… | `/api/suppliers/` (+ same sub-routes) | `Supplier*View` | ✘ | K/E |
| GET | `/api/customer-ar/movements/` | `CustomerARMovementListView` | ✘ | K |
| GET | `/api/supplier-ap/movements/` | `SupplierAPMovementListView` | ✘ | K |
| GET/POST | `/api/customer-receipts/` (+`{pk}/` GET) | `CustomerReceipt*View` | **✔** | K |
| GET/POST | `/api/supplier-payments/` (+`{pk}/` GET) | `SupplierPayment*View` | **✔** | K |

> Collapsed-row methods: party detail routes (`customers/{pk}/`,
> `suppliers/{pk}/`) are **GET/PUT/PATCH** (`RetrieveUpdateAPIView`); all
> `deactivate/` actions are **POST**; settlement `{pk}/` details are GET-only.

### 1.4 `pos` — catalog / inventory / sales (`/api/`)

| Method | Path | View / fn | Idem | Tag |
|---|---|---|---|---|
| GET/POST | `categories/` | `CategoryListCreateView` | ✘ | **R** (split Sales/Inventory) |
| GET/POST | `products/` | `ProductListCreateView` | ✘ | E |
| GET | `products/export/` , `products/barcode/{bc}/` , `products/scan/{bc}/` | fns | ✘ | K |
| POST | `products/import/` | `products_import` | ✘ | E |
| GET/PUT/PATCH/DELETE | `products/{pk}/` | `ProductDetailView` | ✘ | E |
| **PATCH** | `products/{pk}/stock/` | `product_stock_update` | ✘ | **D** (direct mutation) |
| GET | `products/{pk}/stock-movements/` , `stock-balance/` | views | ✘ | K |
| GET | `products/{pk}/warehouse-stock/` — ⚠️ **singular on this branch (the real current MVP runtime path)**; the **intended canonical/frontend-expected path** is the plural `products/{id}/warehouse-stocks/`, which the frontend already calls ([erp.ts:168](superpos/src/api/erp.ts#L168)) → **live 404 mismatch on mvp**; Gate A WIP contains the 1-line rename (GA-10) | `ProductWarehouseStockView` | ✘ | K (rename to plural) |
| GET/POST (list) · GET/PUT/PATCH/DELETE ({pk}) | `inventory/batches/` (+`{pk}/`) | `InventoryBatch*View` | ✘ | **DEFER/DORMANT** (D-19) |
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
| GET | `sales/{int:pk}/` , `sales/{int:pk}/receipt/` | `SaleDetailView` / `sale_receipt` | ✘ | **D** (int id) |
| **POST** | `sales/{int:pk}/void/` | `void_sale` | ✘ | **D** (int id) |
| GET | `sales/{uuid}/` , `sales/{uuid}/receipt/` | same views | ✘ | K/E |
| **POST** | `sales/{uuid}/void/` | `void_sale` | ✘ (Gate A WIP adds it) | K/E |
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
| accounts | `FinancialAccount` | K/E | Keep as **operational treasury account** (cash/bank/wallet/card-clearing); link to the GL via a `gl_account` FK. GL-only accounts (inventory, revenue, VAT) live on **ChartOfAccount** — never as FinancialAccount types. Existing GL-ish types (`customer_ar`/`supplier_ap`/`expense`/`opening_balance`) map to GL control accounts (cleanup item). |
| accounts | `PaymentMethod` | K | Keep. |
| accounts | `BranchPaymentMethod` | K/E | Keep routing; activate commission posting later. |
| accounts | `FinancialAccountMovement` | K | Keep as **subsidiary** ledger; **not** the GL. |
| accounts | `Customer` / `Supplier` | K/E | Keep; `price_tier_id` BigInt → FK when PriceTier lands. |
| accounts | `CustomerARMovement` / `SupplierAPMovement` | K | Keep subsidiary AR/AP ledgers. |
| accounts | `CustomerReceipt` / `SupplierPayment` | K/E | Keep; add invoice allocation later. |
| pos | `Category` | **R** | Split into **hierarchical SalesCategory** (self-parent «تندرج من», inheritable tax/GL/station/POS defaults, snapshot-on-post) + **hierarchical InventoryCategory** (asset/wastage/adjustment/variance GL defaults) — spec: [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.2/§6.3. |
| pos | `Product` | E/R | Extend: `product_type` (8 types per MASTER_DATA_CONTRACT §11) + `sellable`/`purchasable`/`track_inventory`/`base_unit` + category FKs; rework unit/pack_qty → ProductUnit (conversions only); demote `stock`. Spec: [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6.4. |
| pos | `InventoryBatch` | **DEFER/DORMANT** | Do **not** drop now — keep in code, unused, until batch/expiry/FEFO scope is approved (deferred decision D-19). |
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

### 2.1 Target net-new model register (proposed — pending gates G1–G4; no endpoints exist yet, none invented here)

Specified in [TARGET_BOUNDARIES.md](TARGET_BOUNDARIES.md) §6 as the proposed
target; listed so the model inventory is complete for ratification:

| Target model | Purpose | Spec | Slice |
|---|---|---|---|
| `SalesCategory` | Hierarchical menu tree («تندرج من»), inheritable tax/revenue-GL/COGS-GL/station/POS defaults | §6.2 | 4 |
| `InventoryCategory` | Hierarchical stock tree (ingredients/prep/packaging/resale), asset/wastage/adjustment/variance GL defaults | §6.3 | 4 |
| `UnitGroup` / `Unit` / `ProductUnit` | Data-driven conversions; base-unit stock rule | §6.5 | 3 |
| `ProductBarcodeUnit` | Barcodes for packaged/purchase/retail units only | §6.5 | 3 |
| `ProductVariant` | S/M/L variant: price, optional PLU, POS sort — barcode-free (R-K) | §6.6 | 11 |
| `Recipe` / `RecipeVersion` / `RecipeLine` | Per-variant dated/statused BOM with yield + loss factors | §6.7 | 11 |
| `ModifierGroup` / `ModifierOption` / `RecipeConsumptionDelta` | Price delta + per-variant consumption delta | §6.10 | 11 |
| `ProductionOrder` | Raw → prep conversion; normal loss / abnormal wastage / variance | §6.9 | 11b |
| Snapshot tables (recipe/cost + tax/account resolution) | Immutable posted-document snapshots (R-J; shape per D-31) | §6.7/§6.2 | 6/11 |
| `InventoryCost` / valuation record (**conditional — pending D-35 approval**) | Base-unit average cost per product (scope per D-09); keeps ProductUnit purely a conversion definition | §6.11 / D-35 | 6 |
| `ChartOfAccount` / `JournalEntry` / `JournalLine` | Full accounting ledger beside subledgers | §2.7 | 7 |

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
| DEAD-3 | `InventoryBatch` not in posting | pos/models.py | Modeled, unused. | **DEFER/DORMANT** — keep unused until batch/expiry/FEFO scope (D-19) is approved; no deletion now. |
| PATH-1 | **FE↔BE path mismatch:** frontend calls plural `products/{id}/warehouse-stocks/` ([erp.ts:168](superpos/src/api/erp.ts#L168)); this branch's URLconf serves singular `warehouse-stock/` ([pos/urls.py:21](superpos_backend/pos/urls.py#L21)) | pos/urls.py vs superpos/src/api/erp.ts | Product warehouse-breakdown drawer 404s on mvp. | Rename to plural via Gate A component **GA-10** (1-line, already in the safety WIP). |

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
