# Frontend Slice — Prototype Design System + ERP Lite Screens

**Date:** 2026-07-04
**Branch:** `mvp/counter-cafe-demo-readiness` (7 commits, `superpos/` only — no backend changes)
**Scope:** Convert the approved SuperPOS.dc.html visual system into native React + TypeScript + Tailwind components, refactor existing screens, and add the backend-ready Counter Sales ERP Lite modules.

---

## 1. Acceptance-criteria status

| Criterion | Status |
|---|---|
| No support.js / DC runtime / iframe in the app or bundle | ✅ verified by grep over `src/`, `index.html`, and the built `dist/assets` |
| No prototype mock data in production routes | ✅ `src/data/mock.ts` remains orphaned (not imported); no prototype fixtures copied |
| Existing screens preserve functionality | ✅ all existing API calls and routes intact; only dishonest UI removed |
| New screens use real verified APIs | ✅ every call maps to a route in the backend URLconf / OpenAPI schema |
| Prototype visual identity | ✅ same token set (neutral bg, white cards, 64px header, blue primary, compact badges, dense tables) |
| Desktop + tablet layouts | ✅ sidebar collapses to overlay `<lg`, POS stacks on portrait, KPI grids responsive |
| Arabic RTL | ✅ logical properties (`start/end`) throughout new components; nav/header keys added to `ar.json` |
| Forms have validation + loading states | ✅ client-side validation + DRF field-error mapping via `parseApiError` |
| Lists handle real backend pagination | ✅ DataTable + Pagination on DRF page numbers (20/page); Sales page cap removed |
| `npm run build` passes | ✅ `tsc && vite build`, 1031 modules, main bundle 510 kB (new modules lazy-split) |
| Screenshots | ⚠️ require a running backend + seeded tenant — not capturable in this environment; see §6 |
| Automated tests | ⚠️ the project has no test framework (audit P1-21); adding one was out of slice scope; see §6 |

---

## 2. Commits (review in order)

1. `frontend: extract prototype design system + role guards foundation`
2. `frontend: Customers module (AR)`
3. `frontend: Suppliers module (AP)`
4. `frontend: Purchase invoices module (stock items only)`
5. `frontend: Warehouse inventory screens (read-only Slice J balances)`
6. `frontend: Finance module (accounts, methods, branch routing, settlements)`
7. `frontend: POS UX on real backend behavior (Part D)`
8. `frontend: refactor existing screens — honest states + real pagination (Part B)`
9. (this document + label-only terminal hint wording)

---

## 3. Route map

| Route | Page | Min role | Notes |
|---|---|---|---|
| `/login` | LoginPage | — | fake claims removed; honors requested destination |
| `/pos` | POSPage | Cashier | customer selector, F2 discount, F8 payment, credit |
| `/receipt` | ReceiptPage | Cashier | in-memory fallback |
| `/receipt/:saleUuid` | ReceiptPage | Cashier | durable — refetches `/sales/{uuid}/` |
| `/sales` | SalesPage | Cashier | server pagination + method filter |
| `/dashboard` | DashboardPage | Manager | |
| `/products` | ProductsPage | Manager | |
| `/inventory` | InventoryPage | Manager | movement ledger |
| `/warehouses` | WarehousesPage | Manager | **new** — warehouses + per-warehouse stock |
| `/scale` | ScalePage | Manager | |
| `/customers` | CustomersPage | Manager | **new** |
| `/suppliers` | SuppliersPage | Manager | **new** |
| `/purchases` | PurchasesPage | Manager | **new** |
| `/purchases/new` | PurchaseCreatePage | Manager | **new** |
| `/purchases/:id` | PurchaseDetailPage | Manager | **new** — read-only when posted |
| `/finance` | FinancePage | Manager | **new** — accounts / methods / routing / settlements |
| `/users` | UsersPage | Manager | |
| `/settings` | SettingsPage | Manager | blocked-load state added |

Guarding: `RequireRole` renders an explicit access-denied screen (not a redirect) for direct-URL attempts below the floor; the sidebar also hides those links, and every backend 403 renders a `PermissionDeniedState`. Role floors mirror the backend permission classes (`IsCashierOrAbove` / `IsManagerOrAbove`).

## 4. API map (new frontend consumers)

| Endpoint | Used by |
|---|---|
| `GET/POST/PATCH /api/customers/`, `POST …/deactivate/`, `GET …/balance/`, `GET …/statement/` | Customers |
| `GET/POST/PATCH /api/suppliers/` + same sub-routes | Suppliers |
| `GET/POST /api/customer-receipts/`, `GET …/{id}/` (Idempotency-Key **required** — always sent) | Customer drawer, Finance→Settlements |
| `GET/POST /api/supplier-payments/`, `GET …/{id}/` (Idempotency-Key) | Supplier drawer, Finance→Settlements |
| `GET/POST /api/purchase-invoices/`, `GET …/{id}/` (Idempotency-Key, stable per form) | Purchases |
| `GET/POST/PATCH /api/finance/accounts/` + `deactivate/ balance/ movements/` | Finance→Accounts |
| `GET /api/finance/movements/` | (available; account statements used instead) |
| `GET/POST/PATCH /api/finance/payment-methods/` + `deactivate/` | Finance→Methods, PaymentModal, settlement forms |
| `GET/POST/PATCH /api/branches/{id}/payment-methods/` + `deactivate/` | Finance→Routing, PaymentModal (403-tolerant for cashiers) |
| `GET /api/inventory/warehouses/` | Warehouses, PurchaseCreate |
| `GET /api/inventory/warehouse-stocks/` (`warehouse/product/has_stock/low_stock` filters) | Warehouses→Stock |
| `GET /api/inventory/warehouses/{id}/stock/` | Warehouses (via filter) |
| `GET /api/products/{id}/warehouse-stocks/` | product breakdown drawer |
| `POST /api/sales/` now also sends `customer`, `discount_type`, `discount_value`, `method: credit` | POS |
| `GET /api/sales/?page&page_size&method&start_date&end_date` | Sales list |
| `GET /api/sales/{uuid}/` / `{uuid}/receipt/` | durable receipt |

Method → destination-account compatibility (mirrors backend validation):
cash → cashbox / main_safe · card → card_settlement · wallet → wallet · credit → customer_ar · custom → any.

## 5. Key honest-UX corrections carried in this slice

- Wallet posts as `wallet` (P0-01 was already fixed; preserved) and credit posts as `credit`.
- Card/wallet are manual confirmations with explicit "not connected to the terminal/provider" copy; terminal type in Settings is now labeled "label only".
- Offline simulation removed: connectivity pill/banner reflect `navigator.onLine` only and state that nothing is saved locally.
- Receipt is a durable document route (`/receipt/:saleUuid`); no fake printer/drawer/QR claims.
- Sale POST failures never clear the cart; routing errors say the sale was **not** recorded and point to Finance → Branch routing.
- Negative stock is a distinct danger state everywhere it appears.

## 6. Deferred items

- **Automated tests** — no framework exists in the project; recommend Vitest + RTL starting with `parseApiError`, discount math mirror, PaymentModal enable/labels, RequireRole.
- **Screenshots** — need `npm run dev` + seeded backend; capture list: POS (customer+discount+credit), Payment modal routing labels, Customers drawer statement, Purchase create/detail, Finance routing tab, Warehouses stock, RTL spot-checks.
- **Users page 100-row cap** (P2-13) — server pagination not yet applied there.
- **Cashier-side statement views** — balances/statements are Manager+ on the backend; cashiers see a clean denied state.
- **Arabic coverage of new module screens** — shell/nav are translated; new ERP page bodies are English pending a translation pass (P1-20).
- **Cart lock while payment modal is open / modal-aware barcode focus** (P1-06).
- **Sales cashier filter** is a page-local refinement (backend accepts `cashier=<id>`; UI uses names — wire IDs later).
- **Split/mixed payments, price tiers, sales returns, void reason/approval flow, shifts, recipes, tables/KDS** — out of scope by contract (excluded modules stay off the nav).
