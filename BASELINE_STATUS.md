# Baseline Status — Phase 0 Stabilization

This is a **read-only baseline report**. No runtime code, migrations, or business
logic were changed while producing it. It captures the current verified state of
the backend and frontend before any v3.6 implementation work begins.

Date captured: 2026-06-27
Git branch at capture: `main` (working tree effectively clean — only an untracked
`superpos_backend/accounts/__pycache__/*.pyc` build artifact present).

---

## 1. Confirmed Project Structure

```
pos cashir/
├── superpos_backend/        # Django + DRF backend (implementation baseline)
│   ├── manage.py
│   ├── requirements.txt
│   ├── seed_data.py
│   ├── run_phase1_tests.py  # live-server smoke script (NOT a unittest suite)
│   ├── superpos_backend/    # project config (settings.py, urls.py, wsgi/asgi, pagination.py)
│   ├── accounts/            # tenants, branches, users, terminals, auth, middleware
│   └── pos/                 # products, inventory, sales, payments, dashboard
├── superpos/                # React + Vite + TypeScript frontend (implementation baseline)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json / tsconfig.node.json
│   └── src/                 # pages, components, store (zustand), api/client.ts, i18n, types
├── enhacment_new_version/   # v3.6 product docs (PRD/FLOW/DOMAIN/DESIGN) + UX prototype
├── SOURCE_OF_TRUTH.md       # decision hierarchy
├── API_CONTRACT.md          # Table Service / Open Orders MVP contract (planning)
├── MASTER_DATA_CONTRACT.md  # master-data foundation contract (planning)
├── IMPLEMENTATION_BACKLOG.md # phased backlog (Phase 0 → Phase 6)
└── legacy docs / prototypes (PRD_old_v.md, FLOW_old_v.md, etc. — historical only)
```

All four required planning files were read and exist: `SOURCE_OF_TRUTH.md`,
`API_CONTRACT.md`, `MASTER_DATA_CONTRACT.md`, `IMPLEMENTATION_BACKLOG.md`.

---

## 2. Backend Confirmation

- **Framework:** Django 4.2.30 + Django REST Framework, JWT auth
  (`rest_framework_simplejwt`), `django-filter`, `drf-spectacular`,
  `corsheaders`. Python 3.12.4.
- **Apps:** `accounts` (custom `AUTH_USER_MODEL = accounts.User`, Tenant, Branch,
  Terminal, subscription middleware) and `pos` (Category, Product, InventoryBatch,
  StockMovement, Sale, Payment, AuditLog, DiscountCode).
- **Database:** PostgreSQL (`NAME=superpos`, localhost:5432). DB credentials are
  **hard-coded in `settings.py`** and `DEBUG = True` with a committed `SECRET_KEY`.
- **Settings:** `superpos_backend/superpos_backend/settings.py`. System check:
  `python manage.py check` → "no issues (1 silenced)". The 1 silenced check is
  `auth.E003` (intentional — username is unique per-tenant, not globally).
- **Tests present:**
  - `pos/tests.py` — 11 real `APITestCase` tests (barcode/weight, checkout, receipt).
  - `accounts/tests.py` — placeholder only (no tests).
  - `run_phase1_tests.py` — a live-server smoke script that hits a running
    `127.0.0.1:8000` and requires seeded users (`karim`/`mohamed`/`ziad`). It is
    **not** part of `manage.py test` and needs a running server + seed data.
- **Migrations:** present and applied-capable.
  - `accounts/migrations/` → `0001` … `0009`
  - `pos/migrations/` → `0001` … `0013`
  - No unmade-migration warnings surfaced during `manage.py test`.
- **Routes:** `accounts/urls.py` (auth/login, token refresh, me, users, branches,
  tenant settings/translations) and `pos/urls.py` (categories, products,
  inventory, stock-movements, sales by pk + uuid, dashboard). **No** table-service
  / open-order / shift / kitchen-ticket endpoints exist yet (those are net-new per
  the API contract).

---

## 3. Frontend Confirmation

- **Framework:** React 18.3 + TypeScript 5.6 + Vite 5.4, Tailwind 3.4,
  `react-router-dom` 6, `zustand` 5, `axios`, `i18next`. Node v24.11.1, npm 11.7.0.
- **Routes (`src/App.tsx`):** `/login`, `/pos`, `/receipt`, `/dashboard`,
  `/products`, `/inventory`, `/sales`, `/users`, `/settings`, `/scale`; `/` and `*`
  redirect to `/pos`. Auth-gated via `ProtectedRoute`; subscription block screen
  short-circuits the whole shell.
- **API client (`src/api/client.ts`):** axios instance, base
  `http://127.0.0.1:8000/api` (hard-coded; `media.ts` reads `VITE_API_URL` but no
  `.env` is committed). Bearer token from `localStorage`, single-flight 401 refresh,
  subscription-block + auth-expired global events.
- **State:** zustand stores (`authStore`, `appStore`, `posStore`).
- **Build scripts (`package.json`):** `dev` = `vite`; `build` = `tsc && vite build`;
  `preview` = `vite preview`. **No test script / no test runner installed.**
- `node_modules` is already installed.

---

## 4. Exact Commands

### Backend tests
```bash
cd "superpos_backend"
python manage.py test
```
Requires a reachable PostgreSQL at localhost:5432 with the credentials in
`settings.py` and permission to create the test database.

Optional live smoke script (needs a separately running server + seeded users):
```bash
cd "superpos_backend"
python manage.py runserver        # in one terminal
python run_phase1_tests.py        # in another
```

### Frontend install / build / test
```bash
cd "superpos"
npm install                       # node_modules already present; run if missing
npm run build                     # tsc typecheck + vite build  — CURRENTLY FAILS (see §5)
npm run dev                       # vite dev server (works; no typecheck gate)
# npm test                        # NOT AVAILABLE — no test script / runner configured
```

---

## 5. Current Pass/Fail Status

| Check | Command | Result |
|---|---|---|
| Backend system check | `python manage.py check` | **PASS** — no issues (1 silenced) |
| Backend test suite | `python manage.py test` | **PASS** — Ran 11 tests, `OK` |
| Frontend typecheck+build | `npm run build` | **FAIL** — 9 TypeScript errors at the `tsc` step |
| Frontend dev server | `npm run dev` | Expected to work (esbuild does not typecheck) |
| Frontend tests | `npm test` | **N/A** — no test tooling configured |

### Existing errors (frontend `npm run build`)

All 9 are pre-existing **type-check** errors; `vite build` (esbuild) itself does not
typecheck, so they only block the `tsc` gate of `npm run build`, not the dev server.

1. `src/utils/media.ts(14,34)` — `Property 'env' does not exist on type 'ImportMeta'`.
   Root cause: there is **no `src/vite-env.d.ts`** (`/// <reference types="vite/client" />`
   is missing), so `import.meta.env` is untyped.
2. `src/data/mock.ts(43–50, col 85)` — 8× `Type 'string' is not assignable to type
   'number'`. The `USERS` fixture sets `branch: 'All branches'` (string) while
   `AppUser.branch?` is now typed `number | null`. `mock.ts` is stale demo/fixture
   data that drifted from the evolved `src/types/index.ts`.

### Backend warning (non-fatal)
- PostgreSQL prints a **collation version mismatch** warning when creating/dropping
  the test DB (OS provided 1541.2 vs DB created with 1540.3). Tests still pass; this
  is an environment/DB maintenance note, not a code defect.

---

## 6. Risky Areas (handle with care before/while implementing)

- **Hard-coded secrets/config in `settings.py`** — DB password, `SECRET_KEY`,
  `DEBUG=True`, `ALLOWED_HOSTS=['*']`, `CORS_ALLOW_ALL_ORIGINS=True`. Not Phase 0's
  job to fix, but do not propagate this pattern; new config should be env-driven.
- **Custom user / per-tenant uniqueness** (`auth.E003` silenced). Any user or login
  change must preserve tenant-scoped username uniqueness.
- **`SubscriptionCheckMiddleware`** hard-blocks `/api/*` for inactive/expired
  tenants and peeks at the JWT manually — new endpoints automatically fall under it.
- **Sales identity duality** — sales are addressable by both `int pk` and `uuid`.
  The Open Order → SalesInvoice conversion (Phase 5) must respect this.
- **Stale `mock.ts` fixtures** drift from `types/index.ts`; they currently break the
  production build. Treat as fixture cleanup, not a runtime-logic change.
- **No frontend tests at all** — UI changes have no automated safety net.
- **`run_phase1_tests.py` depends on seeded users + a running server**; it is not a
  hermetic CI test and should not be wired into an automated gate as-is.

---

## 7. Current Reusable Backend Parts

- **Tenant / Branch / Terminal / User model + JWT auth + RBAC** (`accounts/`) — solid
  multi-tenant foundation; branch concept already exists for Phase 1.5 branch work.
- **Product / Category / InventoryBatch / StockMovement** (`pos/models.py`) — catalog
  and inventory-ledger primitives to extend for units/categories/price tiers.
- **Sale / Payment + void + receipt** flows — reference for the Pay → SalesInvoice
  conversion and payment-line routing.
- **Dashboard aggregation endpoints**, **DRF pagination/filter scaffolding**,
  **AuditLog model**, **`drf-spectacular` schema** — reusable cross-cutting infra.

## 8. Current Reusable Frontend Parts

- **`api/client.ts`** — token refresh, subscription/auth event handling. Add an
  `Idempotency-Key` header path here for Phase 1 (per API contract §2).
- **App shell + `ProtectedRoute` + routing** in `App.tsx` — extend with table-service
  routes without restructuring.
- **zustand stores** (`authStore`, `appStore`, `posStore`) — pattern to follow for an
  open-order/table store.
- **UI kit** (`components/ui/*`: Button, Modal, Keypad, Input, Card, Badge, Icon) and
  **POS components** (`BarcodeInput`, `CartLine`, `PaymentModal`, `QuickProductCard`).
- **i18n setup** (`i18n/`, tenant translation overrides) and **`types/index.ts`** as
  the shared contract surface to grow for order/line/ticket status fields.

---

## 9. Recommended First Safe Implementation Branch

```bash
git checkout -b phase0/stabilization-baseline
```
Then for the first real slice:
```bash
git checkout -b phase1/foundation-status-and-idempotency
```
Rationale: keep Phase 0 (baseline + docs) isolated from any code change, and start
implementation from a clearly named feature branch off `main`. Backlog Phase 0 also
calls for a dedicated safe branch before implementation begins.

---

## 10. Files That Should NOT Be Touched Yet

- `enhacment_new_version/*` and all v3.6 docs — source of truth, planning-only.
- `SOURCE_OF_TRUTH.md`, `API_CONTRACT.md`, `MASTER_DATA_CONTRACT.md`,
  `IMPLEMENTATION_BACKLOG.md` — change only via deliberate planning updates.
- Legacy docs/prototypes (`*_old_v.md`, `SuperPOS_old_prototybe.html`) — historical.
- `superpos_backend/pos/migrations/*` and `accounts/migrations/*` — no new migrations
  in Phase 0 (per task constraints).
- `superpos_backend/superpos_backend/settings.py` business config — no Phase 0 edits.
- Backend business logic in `pos/views.py`, `pos/models.py`, `accounts/views.py`,
  `accounts/models.py` — read-only in Phase 0.
- Frontend runtime logic in `superpos/src/**` (stores, pages, `api/client.ts`) —
  read-only in Phase 0.

---

## 11. Exact Next Recommended Implementation Slice

**Slice:** Backlog **Phase 1 — Foundation Lite**, first item:
*"Define and document the shared document status fields for orders, lines, tickets,
and payment lifecycle."*

Concretely, the smallest safe first move after this baseline:

1. On `phase1/foundation-status-and-idempotency`, define the shared **status enums**
   (order: `draft → sent → needs_bill → paid_clearing → … `; line: `draft/unsent →
   sent → voided`; payment lifecycle; kitchen-ticket states) in planning + as
   backend choices and in `superpos/src/types/index.ts`, with **status-transition
   unit tests** and **serializer contract tests** — without creating table/order
   tables yet.
2. In parallel, add **`Idempotency-Key` support scaffolding** (model + middleware/
   mixin design and the client header path) since every critical POST in
   `API_CONTRACT.md §2` depends on it. This unblocks all Phase 3 endpoints.

Defer table/order/ticket models (Phase 2) and any endpoints (Phase 3) until the
status model and idempotency mechanism are agreed and tested.

> Pre-slice hygiene (optional, low-risk, **not** runtime logic): add
> `src/vite-env.d.ts` and reconcile/remove the stale `src/data/mock.ts` fixtures so
> `npm run build` passes — this restores the frontend build gate before feature work.

---

## Stop

Per Phase 0 scope, work stops here. No implementation, migrations, or runtime
changes were made. Awaiting approval of this baseline before starting the slice in §11.
