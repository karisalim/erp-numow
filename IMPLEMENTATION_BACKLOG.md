# Implementation Backlog

## Purpose

This backlog defines the planned implementation phases for the Table Service / Open Orders MVP Core slice.

This file is planning-only. It does not implement code, create migrations, or alter runtime behavior yet.

---

## Phase 0 — Stabilize

- [ ] Run the current backend and frontend test suite and capture baseline results.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/run_phase1_tests.py](superpos_backend/run_phase1_tests.py), [superpos_backend/pos/tests.py](superpos_backend/pos/tests.py), [superpos_backend/accounts/tests.py](superpos_backend/accounts/tests.py)
  - Affected frontend files/components: [superpos/package.json](superpos/package.json)
  - Tests required: backend regression suite, frontend build check, smoke test plan
  - Dependencies: none
  - Acceptance criteria: test baseline is documented and any existing failures are known before new work begins

- [ ] Create a backup branch or safe working branch before any implementation begins.
  - Priority: P0
  - Affected backend files/apps: none
  - Affected frontend files/components: none
  - Tests required: git branch verification
  - Dependencies: Git repository state
  - Acceptance criteria: a dedicated branch exists and is documented for this work

- [ ] Freeze the legacy docs as historical reference and keep only the v3.6 docs as active product guidance.
  - Priority: P0
  - Affected backend files/apps: none
  - Affected frontend files/components: none
  - Tests required: documentation review only
  - Dependencies: source-of-truth confirmation
  - Acceptance criteria: the planning docs clearly mark legacy files as historical only

- [ ] Confirm the source-of-truth hierarchy for product, workflow, domain, and UX decisions.
  - Priority: P0
  - Affected backend files/apps: none
  - Affected frontend files/components: none
  - Tests required: review of planning docs
  - Dependencies: [SOURCE_OF_TRUTH.md](SOURCE_OF_TRUTH.md)
  - Acceptance criteria: the team agrees on the precedence order for all future decisions

---

## Phase 1 — Foundation Lite

- [ ] Define and document the shared document status fields for orders, lines, tickets, and payment lifecycle.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/serializers.py](superpos_backend/pos/serializers.py)
  - Affected frontend files/components: [superpos/src/types/index.ts](superpos/src/types/index.ts)
  - Tests required: status transition unit tests, serializer contract tests
  - Dependencies: Phase 0 source-of-truth confirmation
  - Acceptance criteria: a shared status model exists in planning and is ready for implementation

- [ ] Define tenant settings for table-service behavior, shift blocking, and payment routing defaults.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/accounts/serializers.py](superpos_backend/accounts/serializers.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: settings validation tests, serializer tests
  - Dependencies: source-of-truth and status model
  - Acceptance criteria: settings are documented and ready for implementation

- [ ] Define the idempotency key model and request handling rules for critical POST operations.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/api/client.ts](superpos/src/api/client.ts)
  - Tests required: idempotency replay tests, conflict tests
  - Dependencies: API contract definition
  - Acceptance criteria: critical POST endpoints support deterministic replay behavior

- [ ] Define financial account basics for payment routing.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: routing rules tests, account mapping tests
  - Dependencies: API contract and tenant settings
  - Acceptance criteria: cash, card, wallet, and credit routing paths are defined clearly

- [ ] Define the Cashbox and Card Settlement account structure.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: account creation tests, default configuration tests
  - Dependencies: financial account basics
  - Acceptance criteria: each payment route has a clear account target

- [ ] Define the Wallet Account and Customer AR basics.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: account routing tests, credit-mode validation tests
  - Dependencies: financial account basics
  - Acceptance criteria: wallet and credit flows have explicit target accounts

- [ ] Define the Shift basics, including active shift state and close-block rules.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: shift-open/shift-close state tests
  - Dependencies: status model and tenant settings
  - Acceptance criteria: shift open/close behavior and close blockers are defined clearly

---

## Phase 1.5 — Master Data & Configuration Foundation

- [ ] Implement Dynamic Branch Management for tenant-defined branches and branch-specific configuration.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: branch CRUD tests, deactivation tests, branch-scoping tests
  - Dependencies: foundation account and settings basics
  - Acceptance criteria: branches can be created, configured, deactivated, and filtered by branch without hard-coded behavior

- [ ] Implement BranchSettings for branch-level defaults and operational rules.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: settings CRUD tests, default-account linkage tests
  - Dependencies: Dynamic Branch Management
  - Acceptance criteria: each branch can expose its own defaults for warehouse, cashbox, price tier, receipt footer, and shift rules

- [ ] Implement BranchTerminal for POS terminal/device registration and branch association.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: terminal CRUD tests, branch linkage tests
  - Dependencies: Dynamic Branch Management
  - Acceptance criteria: each branch can register and manage terminals independently

- [ ] Implement BranchUserAssignment for user-to-branch permissions and default branch behavior.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py)
  - Affected frontend files/components: [superpos/src/pages/UsersPage.tsx](superpos/src/pages/UsersPage.tsx)
  - Tests required: assignment tests, permission-scope tests
  - Dependencies: Dynamic Branch Management
  - Acceptance criteria: users can be assigned to one branch, multiple branches, or all branches with clear access rules

- [ ] Implement BranchDocumentSequence for branch-specific numbering when enabled.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: sequence generation tests, branch-specific numbering tests
  - Dependencies: Dynamic Branch Management
  - Acceptance criteria: transactional documents can use branch-aware numbering rules

- [ ] Add branch-based reporting and filtering support for sales, inventory, finance, and movement views.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py)
  - Affected frontend files/components: [superpos/src/pages/DashboardPage.tsx](superpos/src/pages/DashboardPage.tsx), [superpos/src/pages/SalesPage.tsx](superpos/src/pages/SalesPage.tsx)
  - Tests required: branch filter tests, report aggregation tests
  - Dependencies: movement and posting foundation
  - Acceptance criteria: reports and statements can be filtered by branch and use branch_id in all records

- [ ] Implement the FinancialAccount model and APIs for cashboxes, main safe, bank, card settlement, wallet, customer AR, supplier AP, and expense accounts.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/accounts/urls.py](superpos_backend/accounts/urls.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx), [superpos/src/components/ui](superpos/src/components/ui)
  - Tests required: account CRUD tests, tenant scoping tests, branch-aware routing tests
  - Dependencies: Phase 0 stabilization, source-of-truth confirmation
  - Acceptance criteria: a tenant can create and manage financial accounts dynamically from the UI and API

- [ ] Implement PaymentMethod and BranchPaymentMethod models and APIs for tenant-defined payment routing.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/accounts/views.py](superpos_backend/accounts/views.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: payment-method CRUD tests, branch-link tests, routing tests
  - Dependencies: FinancialAccount model and API
  - Acceptance criteria: branches can enable/disable payment methods and each method resolves to a destination account without hard-coded assumptions

- [ ] Implement UnitGroup, Unit, ProductUnit, and ProductBarcodeUnit models and APIs.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py)
  - Affected frontend files/components: [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx), [superpos/src/components/products](superpos/src/components/products)
  - Tests required: unit-group CRUD tests, conversion-factor tests, product-unit linking tests
  - Dependencies: product and catalog foundations
  - Acceptance criteria: the tenant can create unit groups, units, and product unit conversions dynamically

- [ ] Implement ProductCategory model and APIs with POS visibility and routing metadata.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx), [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: category CRUD tests, product assignment tests, POS filter behavior tests
  - Dependencies: product catalog foundation
  - Acceptance criteria: categories can be nested, ordered, and used for POS filtering and kitchen/bar routing

- [ ] Implement PriceTier, Customer, and ProductUnitTierPrice models and APIs.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py)
  - Affected frontend files/components: [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx), [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: price-tier CRUD tests, customer tier assignment tests, price resolution tests
  - Dependencies: product unit model and customer concept
  - Acceptance criteria: a product can have different sale prices per unit and per tier, and POS resolves price server-side

- [ ] Update the product master contract and product creation/update payloads.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/serializers.py](superpos_backend/pos/serializers.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx)
  - Tests required: product payload validation tests, unit/category/tier assignment tests
  - Dependencies: category, unit, and price-tier models
  - Acceptance criteria: product creation supports category, unit, price tier, routing, and POS visibility configuration

- [ ] Add tests for dynamic configuration behaviors and UI planning for settings/catalog screens.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/tests.py](superpos_backend/pos/tests.py), [superpos_backend/accounts/tests.py](superpos_backend/accounts/tests.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx), [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx)
  - Tests required: configuration CRUD tests, validation tests, UI route planning checks
  - Dependencies: all master-data foundation features
  - Acceptance criteria: dynamic configuration can be tested through API contract and planned through UI screens before table-service implementation begins

---

## Phase 2 — Table Service Models

- [ ] Add the DiningSection model and supporting relationships.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/migrations](superpos_backend/pos/migrations)
  - Affected frontend files/components: [superpos/src/components/pos](superpos/src/components/pos)
  - Tests required: model creation tests, tenant scoping tests
  - Dependencies: Foundation Lite models
  - Acceptance criteria: sections can be created and scoped to a tenant/branch

- [ ] Add the DiningTable model with table state and occupancy rules.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/components/pos](superpos/src/components/pos)
  - Tests required: table state tests, occupancy tests
  - Dependencies: DiningSection
  - Acceptance criteria: a table can be opened, occupied, and marked for billing

- [ ] Add the OpenOrder model and its status lifecycle.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/types/index.ts](superpos/src/types/index.ts)
  - Tests required: order lifecycle tests, status transition tests
  - Dependencies: status model and table model
  - Acceptance criteria: an open order can be created, edited, billed, and paid without being a SalesInvoice

- [ ] Add the OpenOrderLine model for draft and sent lines.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/types/index.ts](superpos/src/types/index.ts)
  - Tests required: line state tests, line totals tests
  - Dependencies: OpenOrder and product model
  - Acceptance criteria: lines can be added, updated, sent, and voided according to the contract

- [ ] Add the KitchenTicket model and its lifecycle references.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/components/pos](superpos/src/components/pos)
  - Tests required: ticket creation tests, ticket state tests
  - Dependencies: OpenOrderLine
  - Acceptance criteria: sent lines produce a ticket record with clear status semantics

---

## Phase 3 — Table Service APIs

- [ ] Implement the table listing and table open endpoints from the API contract.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py), [superpos_backend/pos/serializers.py](superpos_backend/pos/serializers.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: GET /api/pos/tables/ tests, POST /api/pos/tables/{table_id}/open/ tests
  - Dependencies: table models and status model
  - Acceptance criteria: tables can be listed and opened successfully with valid payloads

- [ ] Implement the OpenOrder detail and line creation/update endpoints.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py), [superpos_backend/pos/serializers.py](superpos_backend/pos/serializers.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: GET /api/pos/open-orders/{id}/ tests, POST /api/pos/open-orders/{id}/lines/ tests, PATCH /api/pos/open-orders/{id}/lines/{line_id}/ tests
  - Dependencies: OpenOrder and OpenOrderLine models
  - Acceptance criteria: orders can be read and updated through the contract

- [ ] Implement the send-to-kitchen and request-bill endpoints.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: send-to-kitchen tests, request-bill tests
  - Dependencies: KitchenTicket and order status rules
  - Acceptance criteria: only unsent lines are sent and bill requests change order state without creating an invoice

- [ ] Implement pay, void-line, shift-open, shift-close, and current-shift endpoints.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py), [superpos_backend/pos/urls.py](superpos_backend/pos/urls.py)
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: pay tests, void-line tests, shift tests, block-on-open-tables tests
  - Dependencies: financial accounts, shift basics, and order lifecycle rules
  - Acceptance criteria: pay converts one OpenOrder to one SalesInvoice and routing rules are honored

- [ ] Add endpoint tests for every contract route and error condition.
  - Priority: P0
  - Affected backend files/apps: [superpos_backend/pos/tests.py](superpos_backend/pos/tests.py), [superpos_backend/accounts/tests.py](superpos_backend/accounts/tests.py)
  - Affected frontend files/components: none
  - Tests required: contract-level API tests for success and failure cases
  - Dependencies: all table-service APIs
  - Acceptance criteria: every endpoint has explicit test coverage for happy path and contract rule failures

---

## Phase 4 — React Integration

- [ ] Connect the Table Grid view to the API contract.
  - Priority: P1
  - Affected backend files/apps: none
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx), [superpos/src/components/pos](superpos/src/components/pos)
  - Tests required: UI state tests, table-list integration tests
  - Dependencies: table API
  - Acceptance criteria: tables load from the API and reflect occupancy state

- [ ] Add the Open Table modal and create-order flow.
  - Priority: P1
  - Affected backend files/apps: none
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: modal interaction tests, API payload tests
  - Dependencies: open-table API
  - Acceptance criteria: the user can create a new open order from a table

- [ ] Add the Open Order screen for line management.
  - Priority: P1
  - Affected backend files/apps: none
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx), [superpos/src/components/pos](superpos/src/components/pos)
  - Tests required: add-item flow tests, update-line flow tests
  - Dependencies: order detail and line APIs
  - Acceptance criteria: users can add, edit, and review order lines

- [ ] Add send-to-kitchen and request-bill flows in the UI.
  - Priority: P1
  - Affected backend files/apps: none
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: UI action tests, API contract tests
  - Dependencies: send-to-kitchen and request-bill APIs
  - Acceptance criteria: the UI triggers the correct API actions and updates state

- [ ] Add the Pay flow for finalizing the order.
  - Priority: P1
  - Affected backend files/apps: none
  - Affected frontend files/components: [superpos/src/pages/POSPage.tsx](superpos/src/pages/POSPage.tsx)
  - Tests required: payment method selection tests, pay submission tests
  - Dependencies: pay API
  - Acceptance criteria: the UI can finalize and convert an order to a sales invoice

---

## Phase 5 — SalesInvoice Posting

- [ ] Implement the conversion of one OpenOrder into one final SalesInvoice.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/SalesPage.tsx](superpos/src/pages/SalesPage.tsx)
  - Tests required: invoice creation tests, one-order-to-one-invoice tests
  - Dependencies: OpenOrder and payment routing
  - Acceptance criteria: a finalized order produces a single posted sales invoice

- [ ] Add payment line records and routing to the correct financial destination.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/ReceiptPage.tsx](superpos/src/pages/ReceiptPage.tsx)
  - Tests required: payment route tests by method
  - Dependencies: financial account basics
  - Acceptance criteria: each payment method routes correctly to the defined account target

- [ ] Add movement and posting records for inventory and finance changes.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/InventoryPage.tsx](superpos/src/pages/InventoryPage.tsx)
  - Tests required: posting tests, stock movement tests
  - Dependencies: OpenOrder conversion and payment lines
  - Acceptance criteria: posting records are created consistently for completed orders

- [ ] Add audit log entries for table-service actions and payment finalization.
  - Priority: P1
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: none
  - Tests required: audit record tests
  - Dependencies: unified audit model
  - Acceptance criteria: important actions are logged with actor, action, and target context

---

## Phase 6 — Later ERP Lite Modules

- [ ] Add purchase flow and purchase invoice support.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/InventoryPage.tsx](superpos/src/pages/InventoryPage.tsx)
  - Tests required: purchase invoice tests, supplier linkage tests
  - Dependencies: financial account basics and inventory ledger model
  - Acceptance criteria: purchase documents can be created and linked to inventory movement

- [ ] Add customers and suppliers, including AR and AP basics.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/accounts/models.py](superpos_backend/accounts/models.py), [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/UsersPage.tsx](superpos/src/pages/UsersPage.tsx), [superpos/src/pages/SalesPage.tsx](superpos/src/pages/SalesPage.tsx)
  - Tests required: customer/supplier balance tests, payment posting tests
  - Dependencies: financial account basics
  - Acceptance criteria: customer credit and supplier obligations are represented in the system

- [ ] Add wastage, complimentary handling, and inventory-loss workflows.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py), [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/InventoryPage.tsx](superpos/src/pages/InventoryPage.tsx)
  - Tests required: wastage routing tests, inventory-loss tests
  - Dependencies: removal-action contract and inventory movement model
  - Acceptance criteria: removed prepared items are routed and posted consistently

- [ ] Add recipes and modifiers for kitchen-ready product composition.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/ProductsPage.tsx](superpos/src/pages/ProductsPage.tsx)
  - Tests required: recipe composition tests, modifier tests
  - Dependencies: product model and inventory ledger basics
  - Acceptance criteria: complex products can be configured and used in orders

- [ ] Add reporting and ledger-based analytics for sales, inventory, and finance.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/pos/views.py](superpos_backend/pos/views.py)
  - Affected frontend files/components: [superpos/src/pages/DashboardPage.tsx](superpos/src/pages/DashboardPage.tsx)
  - Tests required: report aggregation tests, ledger summary tests
  - Dependencies: posting and movement records
  - Acceptance criteria: reports are generated from posted data rather than transient UI state

- [ ] Add fixed assets support and lifecycle tracking.
  - Priority: P2
  - Affected backend files/apps: [superpos_backend/pos/models.py](superpos_backend/pos/models.py)
  - Affected frontend files/components: [superpos/src/pages/SettingsPage.tsx](superpos/src/pages/SettingsPage.tsx)
  - Tests required: asset lifecycle tests
  - Dependencies: financial account basics
  - Acceptance criteria: fixed assets can be tracked from acquisition to disposal

---

## Implementation Order Recommendation

1. Phase 0 — Stabilize
2. Phase 1 — Foundation Lite
3. Phase 1.5 — Master Data & Configuration Foundation
4. Phase 2 — Table Service Models
5. Phase 3 — Table Service APIs
6. Phase 4 — React Integration
7. Phase 5 — SalesInvoice Posting
8. Phase 6 — Later ERP Lite Modules

---

## Definition of Done for the MVP Slice

The MVP slice is ready for implementation when:

- no duplicate backlog tasks remain
- API payment status flow is consistent
- paid_clearing → clear → available is the official table lifecycle

- the source-of-truth and API contract are approved
- table and order models are defined
- open-order APIs exist and are tested
- the React UI can open a table, add items, send to kitchen, request a bill, and pay
- payment conversion creates a final SalesInvoice without violating the contract
