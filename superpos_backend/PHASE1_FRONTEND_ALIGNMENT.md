# Phase 1 — React Frontend ↔ Backend API Alignment

**Date:** 2026-05-15
**Scope:** SuperPOS Phase 1 (Core POS — Auth, Products, Sales, Inventory, Receipt, Dashboard)
**Method:** Static cross-reference only. No HTTP calls executed.
**Companion doc:** `PHASE1_TEST_REPORT.md` (42/42 backend tests passing — trusted as baseline)

---

## 0. Headline Finding

The React app under `superpos/src/` is **100% mock-driven today**. A repository-wide search
(`fetch(`, `axios`, `http.`, `api.`) returns **zero matches** — there is no `src/api/`,
no `src/services/`, no HTTP wrapper, no JWT storage. Every page imports from
`superpos/src/data/mock.ts` (`PRODUCTS`, `TRANSACTIONS`, `USERS`, `PLU_DATA`,
`PERMISSIONS`). The Zustand auth store (`superpos/src/store/authStore.ts:11-19`) hard-codes
a `DEMO_USER` and resolves login after `setTimeout(700)`.

Therefore "alignment" here means: **does the backend already serve everything that
each existing React screen will need to call when the integration layer is added?**
The answer below is yes-with-minor-gaps: every Phase 1 screen has a corresponding
backend endpoint, but several field-naming and shape mismatches need a thin adapter.

---

## 1. Per-screen API mapping

Legend: ✅ provided · ⚠ provided but shape/naming differs · ❌ missing

### 1.1 LoginPage — `superpos/src/pages/LoginPage.tsx`
| UI element | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| email + password form (`:38-91`) | `POST /api/auth/login/` | ✅ `accounts/views.py:18` | Returns `{access, refresh, user:{…}}` via `CustomTokenObtainPairSerializer` |
| `AuthUser` populated after login | user object embedded in login response | ✅ `accounts/serializers.py:84` | Bundled into the token payload — frontend won't need a second `/me/` round trip |
| Initials / role / branch / terminal | `tenant_name`, `branch_name`, `terminal_name`, `role`, `full_name` | ✅ `accounts/serializers.py:8-32` | All four are exposed |

**Status:** ✅ Ready.

---

### 1.2 POSPage — `superpos/src/pages/POSPage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| Barcode submit lookup (`:46-67`) | `GET /api/pos/products/barcode/<barcode>/` | ✅ `pos/urls.py:11` | Returns full `Product` serializer |
| Scale barcode parsing (`utils/barcode.ts`) → PLU lookup | `GET /api/pos/plu/code/<plu>/` | ✅ `pos/urls.py:17` | Frontend needs to call this when `parseScaleBarcode` returns a `plu` |
| Quick-grid products | `GET /api/pos/products/?category=…` | ✅ `pos/urls.py:9` | Supports filters/search (DRF) |
| Categories tabs (`CATEGORIES` array hard-coded `:21`) | `GET /api/pos/categories/` | ✅ `pos/urls.py:6` | Frontend currently hard-codes 6 strings — should source from API |
| Complete sale (`completeSale`, `:70-90`) | `POST /api/pos/sales/` | ✅ `pos/urls.py:29` | See mismatches §3 |
| Offline mode queue (`incrementPendingSync`) | needs `offline=true` in POST body | ✅ `pos/serializers.py:142` | Field already accepted |

**Status:** ⚠ Ready, with field-shape adapter (see §3).

---

### 1.3 ReceiptPage — `superpos/src/pages/ReceiptPage.tsx`
| UI element | Source | Backend has it? | Notes |
|---|---|---|---|
| Receipt is rendered from `receiptTxn` in `posStore` | Built client-side after POST `/sales/` response | ✅ | All fields the UI reads (`subtotal`, `tax`, `total`, `paid`, `change`, `method`, `items[]`) are returned by `SaleSerializer` |
| `txn.terminal`, `txn.cashier` strings | `cashier_name`, `terminal_name` | ✅ `pos/serializers.py:153-162` | Naming differs (see §3) |
| Store name/address/VAT on the printed receipt (`:50-54`) | **No backend equivalent** | ❌ | Hard-coded today. Settings model does not exist |
| Reprint / email actions (`:155-160`) | No endpoints | ❌ | UI buttons are stubs; mark as Phase 2 |

**Status:** ⚠ Functional for receipt display; reprint/email endpoints missing (acceptable for Phase 1 since UI buttons are visual-only).

---

### 1.4 DashboardPage — `superpos/src/pages/DashboardPage.tsx`
| Card / widget | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| 4 STAT cards: Today's revenue, Txns, Avg basket, Items sold (`:32-37`) | `GET /api/pos/dashboard/summary/` | ✅ `pos/views.py:341` | Returns `today.{total,count,avg}`. **Items sold** is in `dashboard/daily-stats/` (`total_items`) |
| Sparkline `spark[]` arrays | **No endpoint** | ❌ | Frontend hard-codes 12-point arrays — Phase 2 work |
| `delta` "vs yesterday" % | **No endpoint** | ❌ | Could be derived client-side by calling `daily-stats?date=yesterday` |
| Top-10 products table (`:104-138`) | `GET /api/pos/dashboard/top-products/` | ⚠ `pos/views.py:403` | Backend returns `{product_name, qty_sold, revenue}`. UI expects `{name, qty, rev, mgn}`. **`margin` is missing** |
| Low-stock card (`:140-173`) | `GET /api/pos/dashboard/low-stock/` | ✅ `pos/views.py:428` | Returns `{name, current_stock, reorder_point, shortfall}` matches UI's `{stock, reorder}` shape after mapping |
| Payment-method breakdown (`:52-56`) | `dashboard/summary/.payment_methods` | ✅ `pos/views.py:364-372` | Returns `{cash:{count,total}, card:{…}, wallet:{…}}` — UI needs to compute `pct` client-side |
| Cashier shift card (Opened/Txns/Voided/Cash in drawer) | **No endpoint** | ❌ | No `Shift` model exists. Currently hard-coded. Phase 2 work |

**Status:** ⚠ Core data available; sparklines + cashier-shift + margin are gaps.

---

### 1.5 ProductsPage — `superpos/src/pages/ProductsPage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| Product list (`:107-143`) | `GET /api/pos/products/` | ✅ | `ProductSerializer` returns all visible columns: `sku`, `barcode`, `name`, `price`, `cost`, `stock`, `reorder`, `color`, `weighted` |
| Category filter | embed `category` param or fetch `/categories/` | ✅ | Filter by `category` PK supported by DRF FilterSet |
| Stock filter (All / In stock / Low / Out) | done client-side from `stock` value | ✅ | Backend exposes raw `stock`/`reorder` — UI compares locally |
| Search by name/SKU/barcode | `?search=…` | ✅ | DRF `search_fields` configured on view |
| "New product" button | `POST /api/pos/products/` | ✅ `pos/urls.py:9` | Endpoint exists; form modal not yet implemented in UI |
| "Import CSV" button | **No endpoint** | ❌ | Phase 2 work — UI button is a stub |
| Margin column (`margin = (price-cost)/price`) | `ProductSerializer.margin` | ✅ `pos/serializers.py:21` | Already provided as `float` |
| Category name as string | UI shows `p.category` as text; backend returns `category` (PK) + `category_name` | ⚠ | Frontend reads `category` as a string — should use `category_name` |

**Status:** ✅ Mostly ready. CSV import out of Phase 1 scope; field-rename adapter needed.

---

### 1.6 SalesPage — `superpos/src/pages/SalesPage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| Sales list table (`:172-198`) | `GET /api/pos/sales/` | ✅ | `SaleListSerializer` returns `id`, `cashier_name`, `method`, `total`, `status`, `item_count`, `created_at` |
| Date range filter (`From`/`To`, `:138-140`) | `?created_at__gte=…&created_at__lte=…` | ✅ | DRF `SaleFilter` in `pos/filters.py` |
| Method filter dropdown | `?method=cash|card|wallet` | ✅ | |
| Cashier filter (hard-coded names `:146`) | `?cashier=<id>` + needs cashiers list | ⚠ | Filter exists, but UI uses string names — needs to source the user list from `/api/auth/users/` |
| Search by Txn ID | `?search=…` | ✅ | |
| Stat cards: Today/Week/Month/Avg (`:90-94`) | `GET /api/pos/dashboard/summary/` | ✅ | Returns `today / this_week / this_month` aggregates |
| Transaction detail modal (`:18-87`) | `GET /api/pos/sales/<uuid>/` | ✅ `pos/urls.py:36` | UUID endpoint preferred |
| Void transaction button (`:79`) | `POST /api/pos/sales/<uuid>/void/` | ✅ `pos/urls.py:37` | Manager+ permission |
| Reprint receipt button (`:78`) | **No endpoint** | ❌ | Phase 2 — UI is a stub |
| "Daily report" / "Export CSV" buttons | **No endpoint** | ❌ | Phase 2 — UI is a stub |

**Status:** ✅ Ready for the table/detail/void flow. CSV export & reprint deferred.

---

### 1.7 UsersPage — `superpos/src/pages/UsersPage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| User table (`:158-183`) | `GET /api/auth/users/` | ✅ `accounts/urls.py:10` | `UserSerializer` exposes `full_name`, `email`, `role`, `branch_name`, `is_active` |
| Add user modal (`:23-108`) | `POST /api/auth/users/` | ✅ | `UserCreateSerializer` accepts `password`, `role`, `branch`, `terminal`, `pin_code` |
| Edit user modal | `PATCH /api/auth/users/<id>/` | ✅ | `UserUpdateSerializer` |
| Role permissions matrix (`PERMISSIONS`, `PERMISSION_LABELS`) | **No endpoint** | ❌ | Permission matrix is hard-coded client-side in `data/mock.ts`. Backend enforces via `IsManagerOrAbove` / `IsCashierOrAbove` permission classes, but doesn't expose the matrix to the UI. Phase 2 work |
| "Last login" column (`u.last`) | **No field** | ⚠ | `User` model inherits `last_login` from `AbstractUser` but it's NOT in `UserSerializer` fields list (`accounts/serializers.py:16-22`). Easy add |
| "Active now" stat (`:115`) | No equivalent | ❌ | No session/heartbeat tracking. Phase 2 |
| PIN code input | `pin_code` field on User | ✅ | Hashed via `set_pin()` — `UserCreateSerializer` accepts it raw |

**Status:** ⚠ CRUD ready; `last_login` field needs to be exposed; permission matrix and online-presence are gaps.

---

### 1.8 ScalePage — `superpos/src/pages/ScalePage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| PLU list table (`:160-205`) | `GET /api/pos/plu/` | ✅ `pos/urls.py:15` | Returns `plu`, `name`, `price`, `status`, `updated_at` |
| Inline price edit (`updatePrice`, `:69-75`) | `PATCH /api/pos/plu/<id>/` | ✅ `pos/urls.py:16` | |
| New / Edit / Delete PLU | `POST/PATCH/DELETE /api/pos/plu/<id>/` | ✅ | |
| `updated` / `status` columns | `updated_at`, `status` | ✅ | UI uses string `'Synced'`/`'Pending sync'`; backend uses lowercase `'synced'`/`'pending'` — see §3 |
| "Export to scale" button | **No endpoint** | ❌ | Phase 3 (per PRD roadmap — "scale integration" is Phase 3) |
| "Last export 08:00" stat | **No endpoint** | ❌ | Phase 3 |
| "Import CSV" / "Export CSV" | **No endpoint** | ❌ | Phase 2/3 |

**Status:** ✅ CRUD ready. Per PRD roadmap, scale integration is officially Phase 3 — no Phase 1 blocker.

---

### 1.9 SettingsPage — `superpos/src/pages/SettingsPage.tsx`
| UI feature | Endpoint needed | Backend has it? | Notes |
|---|---|---|---|
| Printer / Scale / Payment / Receipt / Localization sections | **No endpoint** | ❌ | No `Settings` / `TenantSettings` model exists. The page is purely cosmetic |
| Store name / VAT / address (for receipt) | should ideally be on `Tenant` or `Branch` | ⚠ | `Branch.address` exists, but no `vat_number`, `phone_footer`, etc. |

**Status:** ❌ Entirely cosmetic right now. Acceptable for Phase 1 since "settings" is not in the Phase 1 deliverable list of PRD §"Phase 1".

---

## 2. Gaps

### 2.1 Endpoints the frontend NEEDS but the backend lacks
| # | UI dependency | Severity | Note |
|---|---|---|---|
| 1 | Settings (`SettingsPage` entire page) | Low | Not a Phase 1 deliverable per PRD; UI is decorative |
| 2 | Cashier shift tracking (`DashboardPage` shift card) | Low | Hard-coded; not in PRD Phase 1 |
| 3 | Sparkline / "vs yesterday" delta data | Low | Hard-coded; not in PRD Phase 1 |
| 4 | Reprint receipt endpoint | Low | Reprint is a UI stub |
| 5 | CSV import/export (Products / PLU / Sales) | Low | UI stubs; explicitly Phase 2 |
| 6 | Permission matrix exposure (UsersPage) | Med | Backend enforces RBAC but frontend hard-codes the matrix — fine for Phase 1 |
| 7 | User `last_login` field in serializer | Low | One-line addition |
| 8 | Online-presence / "Active now" stat | Low | Not in PRD Phase 1 |

### 2.2 Fields the UI displays that the API doesn't return
| Field | Where in UI | Severity |
|---|---|---|
| `margin` on top-products dashboard | `DashboardPage.tsx:42-50` | Med — could be computed from cost on the backend or client side |
| `last_login` on UsersPage | `UsersPage.tsx:176` | Low |
| Sparkline arrays | `DashboardPage.tsx:32-37` | Low |
| Store-info (VAT, address, footer) on receipt | `ReceiptPage.tsx:50-54` | Low |

### 2.3 Backend endpoints with no frontend consumer (yet)
- `POST /api/pos/inventory/purchase/` — `pos/views.py:174` (purchase receipt). No UI screen.
- `POST /api/pos/inventory/adjust/` — `pos/views.py:215` (stock adjustment). No UI screen.
- `GET /api/pos/inventory/batches/` — no UI screen.
- `GET /api/pos/inventory/alerts/` — duplicates `dashboard/low-stock/`; only the dashboard variant is wired.
- `PATCH /api/pos/products/<id>/stock/` — direct stock edit; no UI screen yet (Products page doesn't allow stock edit).
- `GET /api/pos/categories/` — frontend currently hard-codes categories.

These are **not blockers** — they fulfil PRD inventory-module deliverables that no Phase 1
screen exposes. They will be consumed by the Phase 2/3 inventory pages.

---

## 3. Mismatches (shape / naming)

When the frontend wires its API layer, a thin adapter (or rename of `types/index.ts`) will be needed:

| Frontend (`types/index.ts`) | Backend (`*Serializer`) | Fix |
|---|---|---|
| `Product.tax: number` | `Product.tax_rate: Decimal` | Rename in TS type OR map in adapter |
| `Product.category: string` | `category: int (PK)` + `category_name: string` | Use `category_name` |
| `Product.id: string` | `id: int` | Coerce to string in adapter, or change TS |
| `CompletedTransaction.id: 'TXN-…' string` | `Sale.id: int` + `sale_uuid: UUID` | Use `sale_uuid` as the public identifier |
| `Transaction.cashier: string` | `cashier_name: string` | Adapter rename |
| `Transaction.method: 'cash'\|'card'\|'wallet'` | `method: same values` | ✅ matches |
| `Transaction.status: 'Completed'\|'Voided'\|'Refunded'` | `status: 'completed'\|'voided'\|'refunded'` | Case difference — convert to title-case in adapter |
| `PLUItem.status: 'Synced'\|'Pending sync'` | `'synced'\|'pending'` | Map in adapter |
| `AppUser.last: string` | not in serializer | Add `last_login` to `UserSerializer` |
| `AppUser.id: string` | `id: int` | Coerce |
| `AppUser.name` | `full_name` | Rename |
| `AuthUser.terminal: string` | `terminal_name` | Rename |
| `AuthUser.branch: string` | `branch_name` | Rename |
| Sale create — frontend builds `CompletedTransaction` with `subtotal/tax/total` locally | Backend recomputes from items — **frontend should trust the server response** | Replace `completeSale` (POSPage `:70-90`) with the server's returned `SaleSerializer` payload |
| Sale create — frontend `items` carry `tax: number` and weight as `qty` | Backend `SaleItemSerializer` accepts `{product, qty, price_each}` only | Drop client-side tax math when wiring; let backend compute |
| Login response location | `data.user` (UserSerializer) + `data.access` + `data.refresh` | Frontend currently uses `DEMO_USER` — replace wholesale |

---

## 4. Verdict

**Yes — Mostly Ready.** The Phase 1 backend (per `PHASE1_TEST_REPORT.md`, 42/42 tests green)
covers every operation the existing React Phase 1 screens actually need to perform:
authentication, product lookup (by id, barcode, PLU), category list, cart-to-sale POST,
sale list/detail/void by UUID, dashboard aggregates, user CRUD, and PLU CRUD. The remaining
gaps — sparklines, cashier-shift, settings, CSV import/export, reprint — are either explicitly
**Phase 2/3** work in `PRD.md §539-595` or are UI-only stubs (buttons without handlers).

The honest qualifier: the React app **today has no HTTP layer at all** (no `src/api/`, no
axios/fetch, hard-coded `DEMO_USER`). So "alignment" is in two senses:
- **Schema alignment** between what the UI shows and what the API serves: ⚠ ~12 small naming/shape mismatches (see §3), all fixable in a thin adapter or by tweaking `types/index.ts`.
- **Integration readiness**: the entire `src/api/` client + JWT storage + Zustand-store rewiring is still ahead. None of it is blocked by the backend.

### Direct answer to the Arabic question
**هل الـ APIs مناسبة للـ frontend في Phase 1؟**
نعم. كل صفحة من صفحات Phase 1 (Login, POS, Receipt, Dashboard, Products, Sales, Users)
لها endpoint كامل وجاهز في الباك إند. التحدّي المتبقّي ليس في تغطية الـ APIs، بل في كتابة طبقة الـ HTTP client في الفرونت إند نفسها + معالجة فروقات بسيطة في تسمية الحقول (`tax_rate` ↔ `tax`, `cashier_name` ↔ `cashier`, status بحروف صغيرة, الخ). صفحة Settings وأجزاء من Dashboard (sparklines, cashier shift) تعتمد على بيانات ثابتة في الواجهة ولا تمنع البدء بالربط لأنها أصلاً ليست ضمن أهداف Phase 1 حسب الـ PRD.

### Top 3 blockers to start React ↔ backend integration
1. **The React app has no API client.** Add `src/api/client.ts` (axios + JWT interceptor), refactor `authStore` to call `POST /api/auth/login/` and persist `access`/`refresh` tokens, replace mock imports in each page with real fetches.
2. **Field-name divergence in `superpos/src/types/index.ts`** (12 small mismatches in §3). Either rename TS interfaces or insert a serializer-to-DTO adapter at the boundary. Without this the components break on first integration.
3. **Sale-creation flow currently builds `CompletedTransaction` locally** (POSPage `:70-90`). The backend recomputes subtotal/tax/total/change authoritatively — the frontend must switch to consuming the POST `/sales/` response (and use `sale_uuid` instead of the generated `'TXN-…'` string) before receipt printing will be correct.

None of these three is a backend blocker. They are pure frontend integration tasks unblocked by the Phase 1 backend as it stands today.
