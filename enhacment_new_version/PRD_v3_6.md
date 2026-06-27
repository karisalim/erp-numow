# 📋 SuperPOS ERP Lite — Product Requirements Document (PRD)

**Version:** 3.6  
**Last Updated:** June 2026  
**Status:** Draft — Pending Final Review  
**Supersedes:** PRD v2.0 (Cloud POS System)

---

## 📖 How to Read This Document

This document uses a consistent phase classification throughout:

| Label | Meaning |
|-------|---------|
| **[MVP Core]** | First live-usable release — must ship |
| **[MVP Extended]** | Ships shortly after MVP Core |
| **[Phase 2]** | Next major release cycle |
| **[Future]** | Long-term roadmap, not currently scoped |

> **Important:** This remains SuperPOS **ERP Lite** — not a full accounting ERP. The goal is a complete business cycle (sales → purchases → inventory → treasury → reports) without the complexity of a general ledger system.

---

## 🎯 1. Executive Summary

SuperPOS ERP Lite is a **cloud-native SaaS retail operating system** designed for cafés and retail shops in MENA and emerging markets. It manages the complete business cycle: point of sale, purchasing, inventory, customer and supplier relationships, treasury, and reporting — all in one unified platform.

**Core Promise:** Any café or retail owner can open their store, sell, buy, track stock, and see their profit — from day one, without an accountant.

**What changed from v2:** The original Cloud POS System was POS-first and cashier-screen focused. Version 3 expands the scope to cover the full business operating cycle, adds café-specific features (recipes, modifiers, touch POS, kitchen printing), and introduces ERP-grade financial tracking (Posting Engine, Movement Ledgers, Account Mapping) — while staying lightweight and approachable.

**Prototype Baseline:** The existing `SuperPOS.html` prototype serves as the UI baseline. All new screens extend the existing design system, component library, and layout patterns from that prototype. Nothing in the prototype is discarded.

---

## 📊 2. Product Definition

### 2.1 What We Are Building

A unified SaaS platform where business owners can:

- **Sell** — fast POS with barcode scanning (compact mode) and touch-screen café mode
- **Buy** — purchase invoices from suppliers, track costs, update stock automatically
- **Track inventory** — across multiple warehouses, with recipes for café ingredient consumption
- **Manage customers and suppliers** — credit sales, statements, payment collection
- **Handle treasury** — cashboxes, bank accounts, wallet accounts, expenses, shift reconciliation
- **See their numbers** — P&L, stock levels, cashier performance, shift reports
- **Work offline** — PWA with IndexedDB queue, auto-sync on reconnect

### 2.2 What We Are NOT Building

The following are explicitly out of scope for this product:

- Full double-entry accounting general ledger (Phase 2)
- Payroll and HR management (Future)
- Multi-currency support (Future)
- eCommerce integration (Future)
- Direct payment terminal integration — card is recorded manually in MVP (Phase 2 for integration)
- Prescription/pharmacy workflow (Future)
- Gym memberships (Future)
- Full restaurant table management with waiters (Phase 2)
- AI-powered forecasting (Future)

### 2.3 Product Name & Positioning

**Product Name:** SuperPOS ERP Lite  
**Positioning:** "The complete operating system for your café or shop"  
**Differentiators:**
- Offline-first (sells even without internet)
- Recipe-based ingredient tracking for cafés
- Shift workflow with cash reconciliation
- Price tiers per customer
- Loyalty points program
- Arabic RTL-first interface

---

## 👥 3. Target Markets

### 3.1 ☕ Cafés & Coffee Shops — Primary MVP Target

**Why primary:** Cafés have the most complex operational needs (recipes, modifiers, ingredient tracking, shifts, takeaway) while being very common in MENA.

**Key Needs:**
- Touch POS with large product tiles and category navigation
- Modifier and size selection per drink (Hot/Iced, Small/Medium/Large, extras)
- Recipe/BOM: selling one drink automatically deducts milk, coffee, cups, straws
- Kitchen and bar printer routing (send hot drinks to bar, food to kitchen)
- Order types: Dine-in, Takeaway (anonymous, no customer required), Delivery
- Shift management with cashbox reconciliation
- Daily expense tracking (supplies, cleaning, etc.)
- Wastage tracking (spoiled milk, unsold pastries)

**Willingness to Pay:** $99–$299/month  
**Typical Setup:** 1–3 terminals, 2–8 staff

---

### 3.2 🛍️ Retail Shops — Second MVP Target

**Key Needs:**
- Barcode-first POS (compact mode, keyboard-optimized)
- Credit sales with customer accounts and payment collection
- Purchase invoices from suppliers
- Stock tracking per item
- Sales returns with stock re-entry
- Customer price tiers (retail vs wholesale vs VIP)

**Willingness to Pay:** $99–$199/month  
**Typical Setup:** 1–2 terminals, 2–5 staff

---

### 3.3 🛒 Supermarkets & Grocery Stores — Phase 2+

**Key Needs:**
- Barcode scanning at high speed (3 items/second)
- Electronic scale integration (weight-based pricing, PLU codes, EAN-13)
- Price label printing
- Large inventory management (10,000+ SKUs)
- Multi-cashier synchronization

**Willingness to Pay:** $299–$499/month

---

### 3.4 💊 Pharmacies — Future / Phase 3

Expiry tracking, batch/serial numbers, prescription workflow, complex tax rules.

### 3.5 🏋️ Gyms — Future / Phase 3

Membership subscriptions, QR check-in, attendance, freeze/pause, auto-renewal.

### 3.6 🍔 Restaurants — Phase 2+

Full table management, KDS screen, bill splitting, waiter roles, delivery integration.

---

## 💰 4. SaaS Business Model

### 4.1 Pricing Strategy

| Plan | Price/Month | Branches | Cashiers | Key Features |
|------|-------------|----------|----------|--------------|
| **Starter** | $99 | 1 | 2 | Core POS, Products, Sales, Basic Reports |
| **Growth** | $299 | Unlimited | 10 | Full ERP Lite, Loyalty, Advanced Reports |
| **Enterprise** | Custom | Unlimited | Unlimited | APIs, Custom Integrations, Priority Support |

### 4.2 Trial & Onboarding

- **14-day free trial** — no credit card required, full feature access
- Onboarding wizard guides tenant through: branch setup → products → cashbox → first sale
- After trial expires:
  - Day 7, Day 11, Day 13: warning banners per role
  - Day 14+: cashier blocked from new sales; owner retains dashboard/settings/billing access
  - Grace period: 3 days (configurable per plan)
- Conversion target: 15–20% trial-to-paid

### 4.3 Revenue Model

- **Recurring SaaS subscriptions:** 85%
- **Premium feature add-ons:** 10% (Loyalty, Advanced Reports, API access)
- **Hardware integration support:** 5%

### 4.4 Unit Economics (Targets)

| Metric | Target |
|--------|--------|
| CAC (Customer Acquisition Cost) | $150 |
| LTV (Lifetime Value, 3-year avg) | $3,600 |
| LTV:CAC Ratio | 24:1 |
| Monthly Churn Rate | < 3% |
| Gross Margin | 78% |

---

## 🏢 5. SaaS Platform Admin (Super Admin Scope)

> This is a **separate interface** from the tenant application. Not visible in the cashier or admin sidebar.

### 5.1 Tenant Management

- Create, view, update, activate, suspend, delete tenants
- Tenant profile: name, plan, billing contact, country, currency
- View usage: branches, users, terminals, transactions per month

### 5.2 Subscription Plans & Limits

- Assign plan per tenant (Starter/Growth/Enterprise)
- Define per-plan limits: max branches, max cashiers, max terminals
- Enforce limits at creation time (block if over limit, show upgrade prompt)
- Existing data never retroactively deleted when downgrading

### 5.3 Trial Period Management

- Set trial start and end dates
- Extend trial for specific tenants
- View trial-to-paid conversion funnel

### 5.4 Account Activation / Suspension / Reactivation

- Activate: full access immediately
- Suspend: full application block (except billing for owner)
- Reactivate: immediate on payment confirmation, all data preserved

### 5.5 Tenant Onboarding Wizard

- Step-by-step setup: branch → terminal → products → cashbox → first sale
- Progress indicator per tenant
- Admin can trigger re-onboarding for stuck tenants

### 5.6 Billing Integration — [MVP Extended]

- Connect to payment gateway for recurring billing
- Invoice generation per tenant
- Payment history and receipts

### 5.7 Usage Limits Enforcement

- Real-time check on every creation action
- Branch creation: check max_branches for plan
- User creation: check max_cashiers for plan
- Show specific limit message per type: "Branch limit reached (1/1 on Starter). Upgrade to Growth."

### 5.8 Tenant Data Export & Portability

- Full data export per tenant on request (CSV/Excel per entity)
- 30-day export window after subscription cancellation
- After 30 days: data archived per retention policy (7 years minimum)

---

## 🔒 6. Subscription Enforcement in POS (Tenant-Side)

### 6.1 Trial Warning Timeline

| Day | Who Sees It | Message |
|-----|-------------|---------|
| Day 7 | Owner + Admin | Amber banner: "Trial ends in 7 days" |
| Day 11 | Owner + Admin | Amber banner: "Trial ends in 3 days" + [Upgrade Now] |
| Day 13 | Owner + Admin | Red banner: "Trial ends tomorrow!" + [Upgrade Now] |
| Day 14+ | Cashier | Lock overlay (see §6.2) |

### 6.2 Lock Behavior After Trial Expiry

- **Cashier:** POS lock overlay — "Your trial has ended. Contact the account owner."
- **Owner/Admin:** Dashboard, settings, reports, and billing settings remain accessible
- **New sales:** Blocked for all cashiers
- **Historical data:** Fully accessible for viewing

### 6.3 Plan Limit Enforcement

When a limit is reached, creation is blocked with a specific message and an [Upgrade Plan] button shown to Owner/Admin only.

### 6.4 Grace Period

- Default: 3 days after trial/subscription expiry
- During grace: warnings shown, sales allowed
- Configurable per plan in Super Admin

### 6.5 Suspension State

- Full application block except owner billing access
- Message: "Account suspended. Contact support."
- Data: fully preserved, not deleted

### 6.6 Re-activation

- Payment confirmed → immediate re-activation
- All data preserved, no gap in history

### 6.7 Offline Subscription Behavior

The POS caches subscription status locally for offline operation:

```
On every successful online session:
  Cache: subscription_status, plan, trial_ends_at
  Cache TTL: configurable (default 24 hours)

When offline:
  If cached status = valid AND within TTL:
    → Allow sales normally
    → Show subtle notice: "Last verified: X hours ago"
  If cached status = expired (even if offline):
    → Block new sales
    → Show: "Cannot verify subscription. Connect to internet."
    → Exception: Owner/Admin billing access still shown

On reconnect:
  → Re-validate against server immediately
  → If expired during offline period: block + notify owner
  → Sync all offline queue as normal
```

---

## 🏗️ 7. High-Level Architecture

### 7.1 System Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Frontend Applications               │
├─────────────────────────────────────────────────────┤
│  POS PWA (Cashier)    Admin Dashboard               │
│  Touch POS / Café     Super Admin (separate)        │
│  Customer Display [Phase 2]   Mobile [Future]       │
└───────────────────────┬─────────────────────────────┘
                        │ REST API + WebSockets
                        ▼
┌─────────────────────────────────────────────────────┐
│              Django REST Framework API              │
│         (Multi-tenant, permission-enforced)         │
└──────────┬──────────────┬────────────┬──────────────┘
           │              │            │
           ▼              ▼            ▼
      PostgreSQL        Redis        Celery
    (multi-tenant)    (cache +     (background
     shared DB)        pubsub)      workers)
                                       │
                                       ▼
                                  S3 Storage
                              (attachments, exports,
                               product images)
           │
           ▼
┌─────────────────────────────────────────────────────┐
│              Hardware Integration Layer             │
├─────────────────────────────────────────────────────┤
│  Barcode Scanner (HID / keyboard emulation)        │
│  Receipt Printer (ESC/POS — USB or Network)        │
│  Kitchen / Bar Printer (ESC/POS ticket routing)    │
│  Cash Drawer (RJ11 signal via printer)             │
│  Electronic Scale (PLU/EAN-13 barcode output)      │
│  Card Terminal (external, manual recording in MVP) │
└─────────────────────────────────────────────────────┘
```

### 7.2 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2 + Django REST Framework |
| Frontend | React 18 + Vite + TailwindCSS |
| State Management | Zustand |
| Offline | PWA + Service Worker + IndexedDB |
| Database | PostgreSQL 15 (shared, multi-tenant) |
| Cache | Redis 7 |
| Queue | Celery + Redis broker |
| Storage | AWS S3 (or compatible) |
| i18n | react-i18next + Backend Model + API translations |

### 7.3 Multi-Tenancy Model

- **Shared database:** All tenants on one PostgreSQL instance
- **Isolation:** `tenant_id` on every table
- **Enforcement:** Middleware adds `tenant_id` filter to every query automatically
- **JWT payload:** Carries `tenant_id`, `user_id`, `branch_id`, `role`, `permissions[]`
- **Row-level security:** `tenant_id` indexed on all tables with frequent queries

### 7.4 Offline-First Strategy

```
PWA Registration (Service Worker)
  ↓
Cache: product catalog, customer list, settings,
       permissions, subscription status
  ↓
Offline Operation:
  Sales → queued in IndexedDB
  Expenses → queued in IndexedDB
  Shift continuation → local state
  ↓
Every queued action carries:
  idempotency_key (UUID generated on device)
  ↓
On reconnect:
  Upload queue to server
  Server checks idempotency_key before processing
  Duplicate key → return existing record (200 OK, not 409)
  Conflict resolution per type
  ↓
Sync complete → confirm all actions, update local cache
```

**Note on idempotency:** The `idempotency_key` is applied to **all state-changing POSTs**, not only offline operations. This prevents double-submit when a cashier accidentally presses the payment button twice on a slow connection.

### 7.5 Database Design Principles

- **Decimal fields (not float)** for all money and quantity values — no floating-point precision errors
- **SELECT FOR UPDATE** on product rows during stock deduction — prevents race conditions
- **F() expressions** for atomic increment/decrement operations
- **Atomic transactions** for all document posting (all effects commit together or all roll back)
- **5 separate status fields** per document (not one combined status string)
- **FK indexes** on all foreign key columns — required for query performance
- **username unique per tenant** (not globally) — `unique_together = (tenant, username)`
- **Outbox pattern** for post-commit side effects (loyalty points, async notifications)

---

## 🧩 8. Module Map

### 8.1 Navigation Modules (Sidebar)

```
SuperPOS ERP Lite — Navigation

─── OPERATIONS ─────────────────────────
  ⊞  Point of Sale           [MVP Core]
  ⊡  Dashboard               [MVP Core]

─── TRADING CYCLE ──────────────────────
  🧾 Sales                   [MVP Core]
  📦 Purchases               [MVP Core]
  👤 Customers               [MVP Core]
  🚚 Suppliers               [MVP Core]

─── PRODUCTS & INVENTORY ───────────────
  ⬡  Products                [MVP Core]
  🏭 Inventory               [MVP Core]

─── FINANCE ────────────────────────────
  ◈  Treasury / Finance      [MVP Core]
     (includes Expenses)

─── INSIGHTS ───────────────────────────
  ▤  Reports                 [MVP Core]

─── ADMIN ──────────────────────────────
  👥 Users                   [MVP Core]
  ⚙  Settings                [MVP Core]
```

**Shift Workflow** is accessed exclusively via the **header profile dropdown** — it is NOT a sidebar navigation item.

### 8.2 Operational Workflows (Non-Sidebar)

These are triggered contextually, not from sidebar navigation:

- **Shift Workflow / Cashier Session** — triggered on POS load and profile dropdown
- **Document Status Lifecycle** — runs on every document state change
- **Posting Engine** — invoked on every document POST action
- **Manager Approval Flow** — triggered when approval thresholds are exceeded

### 8.3 Cross-Cutting Services

These services run across all modules and are not user-facing directly:

| Service | Description |
|---------|-------------|
| Global Audit Log | Records every state-changing action (INSERT only, immutable) |
| Access Log | Records sensitive data reads (P&L views, exports) |
| Operations Log | Records system events (printer failures, sync errors, hardware) |
| Document Numbering Engine | Assigns sequential, immutable document numbers |
| Permission Enforcement | Checks permissions at API level before every state-changing action |
| Posting Engine | Atomic transaction wrapper for all document effects |
| Tax Calculation Engine | Calculates tax, routes to Tax Payable (not revenue) |
| Costing Engine | Calculates COGS via weighted average cost or recipe cost |
| Loyalty Engine | Manages point earning, redemption, and expiry |
| Price Tier Engine | Resolves correct unit price per customer tier |
| Movement Ledger Engine | Creates all movement records on document posting |
| Account Mapping Layer | Routes financial effects to configured accounts |
| Rounding Engine | Handles tax and invoice rounding per tenant settings |
| Offline Queue + Subscription Cache | Manages IndexedDB queue and cached subscription |

---

## 📒 9. Movement Ledger Architecture

> **Core principle:** Every posted document creates movement records in the appropriate ledgers. Reports read from movement ledgers — not from document state fields. This ensures reports are accurate, consistent, and independent of document UI state.

All movement records are created atomically with their parent document's posting transaction. If any ledger write fails, the entire transaction rolls back.

### 9.1 StockMovement Ledger

Tracks every inventory change across all warehouses.

**Movement Types:**

| Type | Triggered By |
|------|-------------|
| `OPENING_BALANCE` | Opening stock entry |
| `PURCHASE_IN` | Purchase invoice posted |
| `SALE_OUT` | Sales invoice posted |
| `SALES_RETURN_IN` | Sales return posted |
| `PURCHASE_RETURN_OUT` | Purchase return posted |
| `TRANSFER_IN` | Warehouse transfer (receiving side) |
| `TRANSFER_OUT` | Warehouse transfer (sending side) |
| `ADJUSTMENT_IN` | Stock adjustment (increase) |
| `ADJUSTMENT_OUT` | Stock adjustment (decrease) |
| `DAMAGE_OUT` | Damage / wastage entry |
| `RECIPE_CONSUME` | Café item sold (ingredient deduction) |
| `PRODUCTION_IN` | Production batch entry [MVP Extended] |

**Fields per movement:**
`id`, `tenant_id`, `product_id`, `product_unit_id`, `warehouse_id`, `branch_id`, `qty` (±), `unit_cost`, `movement_type`, `source_document_type`, `source_document_id`, `shift_id`, `user_id`, `created_at`

### 9.2 FinancialAccountMovement Ledger

Tracks every money movement per financial account.

**Account Types:**
`cashbox` / `bank_account` / `card_settlement` / `wallet_account` / `tax_payable` / `fixed_asset` / `inventory_value` / `accounts_receivable` / `accounts_payable` / `revenue` / `cogs` / `expense` / `inventory_loss` / `depreciation_expense` / `loyalty_discount`

**Fields per movement:**
`id`, `tenant_id`, `account_type`, `account_id`, `amount` (±), `movement_type`, `source_document_type`, `source_document_id`, `shift_id`, `created_at`

**Critical routing rules:**
- Card payment → `card_settlement` account (NOT `cashbox`)
- Wallet payment → `wallet_account` (NOT `cashbox`)
- Tax collected → `tax_payable` (NOT `revenue`)
- Fixed asset purchase → `fixed_asset` account (NOT `expense`)
- Damage/wastage → `inventory_loss` account

### 9.3 CustomerARMovement Ledger

Tracks all changes to customer account receivable balances.

**Movement Types:**

| Type | Event |
|------|-------|
| `OPENING_BALANCE` | Opening balance entry |
| `CREDIT_SALE` | Invoice posted as credit |
| `PARTIAL_PAYMENT_BALANCE` | Remaining on partial payment |
| `RECEIPT_PAYMENT` | Customer pays |
| `SALES_RETURN_CREDIT` | Return refunded to account |
| `ADVANCE_RECEIPT` | Customer advance/deposit |
| `OVERPAYMENT_CREDIT` | Overpayment becomes credit |
| `ALLOCATION` | Advance allocated to invoice |

**Fields:** `id`, `tenant_id`, `customer_id`, `invoice_id`, `amount` (±), `movement_type`, `balance_after`, `created_at`

### 9.4 SupplierAPMovement Ledger

Mirrors CustomerARMovement for supplier accounts payable.

**Movement Types:** `OPENING_BALANCE`, `CREDIT_PURCHASE`, `PAYMENT_MADE`, `PURCHASE_RETURN_CREDIT`, `ADVANCE_PAYMENT`, `OVERPAYMENT_CREDIT`, `ALLOCATION`

### 9.4A AR/AP Double-Counting Rule

CustomerARMovement is the detailed source of truth for customer balances. SupplierAPMovement is the detailed source of truth for supplier balances.

If Account Mapping includes Accounts Receivable or Accounts Payable accounts, they are control/summary accounts only — not a second detailed ledger to be counted again.

**Rules:**
- Credit sale creates CustomerARMovement.
- Customer receipt reduces/allocates CustomerARMovement.
- Credit purchase creates SupplierAPMovement.
- Supplier payment reduces/allocates SupplierAPMovement.
- Reports must not count the same AR/AP amount twice.

### 9.5 ShiftMovementSummary Ledger

Maintains running totals for each shift, updated atomically on every document posting.

**Fields tracked per shift:**

```
cash_sales_total          card_sales_total
wallet_sales_total        credit_sales_total
loyalty_discount_total    cash_returns_total
card_returns_total        discount_total
expense_total             wastage_total
cash_in_total
cash_out_total            cash_drop_total
invoice_count             return_count
cancel_count              opening_cash_expected
opening_cash_actual       opening_variance
expected_closing_cash     actual_closing_cash
closing_variance          card_expected
card_terminal_batch       card_variance
```

### 9.6 LoyaltyTransaction Ledger

**Types:** `EARN`, `REDEEM`, `REVERSE_EARN`, `REVERSE_REDEEM`, `MANUAL_ADJUST`, `EXPIRE`

**Fields:** `id`, `tenant_id`, `customer_id`, `invoice_id`, `points` (±), `type`, `note`, `expires_at`, `created_by`, `created_at`

### 9.7 FixedAssetLedger (AssetLifecycleEvent)

**Types:** `ASSET_PURCHASE`, `DEPRECIATION`, `TRANSFER`, `MAINTENANCE`, `DISPOSAL`, `WRITE_OFF`, `ASSET_SALE`

**Fields:** `id`, `tenant_id`, `asset_id`, `event_type`, `amount`, `book_value_before`, `book_value_after`, `source_document_id`, `approved_by`, `created_at`

### 9.8 Audit Log

Records every **state-changing** business data event. Not triggered by reads, views, or list queries.

**Covers:** Document create/post/cancel/edit, settings changes, permission changes, shift open/close, stock adjustments, manager approvals, manual loyalty adjustments, price changes.

**Fields:** `id`, `tenant_id`, `actor_user_id`, `role`, `branch_id`, `terminal_id`, `timestamp`, `action`, `entity_type`, `entity_id`, `old_value` (JSON), `new_value` (JSON), `reason`, `approval_user_id`, `affected_doc_number`, `source_module`

**Storage:** INSERT only — records are never updated or deleted. Retained minimum 7 years.

### 9.9 Access Log

Records **sensitive data reads** — not every report view, only sensitive ones.

**Covers:** P&L report views, customer statement views, data exports, admin-level data access.

### 9.10 Operations Log

Records **system and hardware events**.

**Covers:** Printer failures, sync errors, offline queue events, Celery job execution, hardware disconnect events.

---

## 💳 10. Account Mapping / Lightweight Chart of Accounts

This is ERP Lite — not a full double-entry accounting system. But financial effects must route to named, configurable accounts to ensure correct reporting.

### 10.1 Account Categories

**Assets:**
- Cashbox accounts (one per physical drawer)
- Bank accounts
- Card Settlement accounts (per payment method)
- Wallet accounts (Vodafone Cash, Fawry, InstaPay, etc.)
- Inventory (stock value)
- Accounts Receivable (customer AR)
- Fixed Assets
- Accumulated Depreciation (contra-asset)

**Liabilities:**
- Accounts Payable (supplier AP)
- Tax Payable / VAT Liability
- Loyalty Points Liability [MVP Extended]

**Income:**
- Sales Revenue (net, excluding tax)
- Service Charge Revenue
- Delivery Fee Revenue (when configured as revenue)
- Other Income

**Cost / Expense:**
- COGS (standard items)
- Recipe COGS (café items)
- Operating Expenses
- Depreciation Expense [MVP Extended]
- Inventory Loss / Wastage
- Loss on Asset Disposal [MVP Extended]
- Card Fees / Commission [Phase 2]

**Contra / Adjustment:**
- Sales Discounts
- Sales Returns
- Loyalty Discount / Rewards Redemption
- Rounding Adjustment

### 10.2 Account Mapping Settings (per Tenant)

Administrators configure which named account receives each type of financial effect:

| Setting Key | Default Label |
|-------------|---------------|
| `default_sales_revenue_account` | Sales Revenue |
| `default_cogs_account` | Cost of Goods Sold |
| `default_inventory_account` | Inventory |
| `default_tax_payable_account` | Tax Payable / VAT |
| `default_cashbox_account` | Main Cashbox |
| `default_card_settlement_account` | Card Settlement |
| `default_wallet_account` | Wallet Account |
| `default_ar_account` | Accounts Receivable |
| `default_ap_account` | Accounts Payable |
| `default_fixed_asset_account` | Fixed Assets |
| `default_accumulated_depreciation_account` | Accumulated Depreciation |
| `default_depreciation_expense_account` | Depreciation Expense |
| `default_inventory_loss_account` | Inventory Loss |
| `default_loyalty_discount_account` | Loyalty Discount |
| `default_rounding_adjustment_account` | Rounding Adjustment |

### 10.3 Critical Routing Rules

These rules are enforced by the Posting Engine and are not configurable — only the account that receives the effect can be configured, not the routing logic itself:

- **Sales Revenue** = net amount (after discounts, excluding tax)
- **Tax collected** → Tax Payable account (liability, NOT revenue)
- **Card payment received** → Card Settlement account (NOT cashbox)
- **Wallet payment received** → Wallet account (NOT cashbox)
- **Fixed asset purchased** → Fixed Asset account (NOT an expense)
- **Depreciation** → Depreciation Expense account (over time, NOT at purchase)
- **Damage/Wastage** → Inventory Loss account (reduces profit)
- **Loyalty redemption** → Loyalty Discount account (reduces revenue, NOT cashbox)
- **Invoice rounding gain/loss** → Rounding Adjustment account (does not silently alter revenue)

### 10.4 Phase Classification

- **Basic account mapping (named accounts + routing)** = MVP Core
- **Full general ledger / double-entry accounting** = Phase 2
- **Full balance sheet** = Phase 2

---

## ⚙️ 11. Financial Posting Matrix

> This section defines exactly what happens when each document type is **Posted**. All effects listed below occur in a **single atomic database transaction** — if any step fails, all steps roll back. No partial postings are possible.

### 11.0 Revenue & Tax Treatment Rules

**Revenue definition:**
```
Net Revenue = Σ (unit_price × qty) − item_discounts − invoice_discount
```
Tax collected is **not** revenue. It is a Tax Payable liability.

**Example:**
```
Invoice total: 115 EGP (includes 15% VAT)
Net Revenue:   100 EGP  → credited to Sales Revenue account
Tax Payable:    15 EGP  → credited to Tax Payable account
Cash received: 115 EGP  → debited to Cashbox account
```

**Service charges:** Treated as Revenue in MVP (taxable if `charge_is_taxable = true`). Pass-through treatment (Phase 2).

**Discount treatment:** Discounts reduce Net Revenue. A 10% discount on a 100 EGP item means 90 EGP revenue, not 100 EGP revenue with a 10 EGP deduction shown separately.

### 11.0B Negative Stock Control Rules — [MVP Core]

> **Business meaning:** This is not customer credit sale. It means the system allows selling or consuming stock even when the system stock balance is not enough, causing the item or ingredient balance to go below zero temporarily.

Examples:
- Café sells Iced Latte while milk invoice has not been entered yet.
- Cashier sells an item that physically exists in the store but was not entered into the system stock.
- Offline sales continue while stock updates are delayed.

**Default behavior:** Negative stock is blocked unless explicitly enabled in Settings.

```
Check stock availability at posting time
  ↓
Check setting: allow_negative_stock_sale

If allow_negative_stock_sale = false (default):
  → Block posting
  → Show specific message:
     "Insufficient stock. Available: X, Required: Y"
  → Applies to Stock Items and Recipe Ingredients

If allow_negative_stock_sale = true:
  Check negative_stock_scope:
    - all_products
    - selected_products_only
    - ingredients_only
    - products_and_ingredients

  If item is outside allowed scope:
    → Block posting

  If item is inside allowed scope:
    Check require_manager_approval_for_negative_stock
      If true:
        → Trigger Manager Approval Flow
        → Manager must approve before posting
      If false:
        → Show cashier warning if enabled
        → Allow posting
```

**Movement behavior when allowed:**

```
Stock Item sale:
  StockMovement: SALE_OUT
  qty decreases even if balance becomes negative
  negative_stock_flag = true if resulting balance < 0

Recipe Product sale:
  StockMovement: RECIPE_CONSUME per ingredient
  ingredient balance may become negative if allowed
  If one ingredient is blocked → entire invoice is blocked

Damage/Wastage:
  Can also be controlled by negative stock settings
  Default: block wastage if no stock unless manager approval is enabled
```

**Batch / Expiry / Serial items:**

```
If block_negative_stock_for_batch_expiry_serial_items = true:
  → Always block negative stock for batch, expiry, and serial-tracked items

Reason:
  These items require a specific physical batch/serial/expiry record.
  Selling below zero without a real batch would break traceability.

Phase classification:
  Batch / Expiry / Serial tracking itself = Phase 2
  The setting placeholder may exist in MVP Core but remains disabled until Phase 2
```

### 11.0C Negative Stock Costing Rules — [MVP Core + MVP Extended]

When a sale is posted while stock is negative, the system may not know the true final cost yet. The system must still store a cost snapshot so that the invoice can be posted and reports remain consistent.

**Setting:** `negative_stock_costing_method`

| Method | Meaning | Phase |
|--------|---------|-------|
| `last_known_average_cost` | Use the last known average cost before stock went negative | MVP Core default |
| `default_purchase_price` | Use ProductUnit.default_purchase_price if avg_cost is unavailable | MVP Core |
| `zero_cost_require_later_adjustment` | Use zero temporarily and force later cost adjustment | MVP Extended only |

**Cost status stored on each affected sale line:**

```
sale_item.cost_status:
  actual      → cost is based on available stock avg_cost
  estimated   → cost was estimated due to negative stock
  adjusted    → later COGS adjustment was created
```

**Rules:**
- The sale can be posted only if negative stock is allowed by settings.
- The cost used at posting time is stored immutably on the sale line.
- If the cost is estimated, the sale appears in **Estimated Cost Sales Report**.
- Historical invoice totals are not changed later.

### 11.0D Negative Stock Settlement on Purchase — [MVP Core + MVP Extended]

When a later Purchase Invoice is posted for an item that currently has negative stock, the purchase quantity naturally offsets the negative balance.

**Simple stock balance behavior — [MVP Core]:**

```
Current milk balance = -5 liters
Purchase Invoice posted = +20 liters
New balance = +15 liters
```

This happens automatically because reports read from StockMovement ledger:

```
Previous movements total: -5
New PURCHASE_IN:        +20
Current balance:        +15
```

**Formal settlement tracking — [MVP Extended]:**

If `auto_settle_negative_stock_on_purchase = true`, the system creates a `NegativeStockSettlement` record linking the new purchase to the old negative stock movements.

```
On PURCHASE_IN posting:
  Check current stock balance before purchase
  If balance < 0:
    negative_qty_to_cover = min(abs(balance), received_qty)
    Link oldest negative StockMovements first (FIFO by movement date)
    Create NegativeStockSettlement record:
      - product_id
      - product_unit_id
      - warehouse_id
      - purchase_invoice_id
      - covered_negative_qty
      - affected_stock_movement_ids
      - estimated_cost_used
      - actual_purchase_cost
      - cost_difference
      - settlement_status
```

**COGS Adjustment after settlement — [MVP Extended]:**

If a sale used estimated cost and the later purchase reveals a different actual cost, the system may create a COGS Adjustment.

```
Example:
  Negative sale consumed: 5 liters milk
  Estimated cost at sale time: 10 EGP/liter
  Actual purchase cost later: 12 EGP/liter
  Difference: 2 EGP × 5 liters = 10 EGP

COGS Adjustment:
  COGS account ↑ by 10 EGP
  Inventory value / adjustment account adjusted according to Account Mapping
```

**Period lock rule:**
- The old sales invoice is never edited.
- If the original sale period is open, the adjustment may reference that period.
- If the original sale period is locked, the COGS Adjustment is posted in the current open period.
- All adjustments require AuditLog and source references.

### 11.0E Negative Stock Settings Summary

These settings live under:

`Settings → Inventory & Warehouse Settings → Negative Stock Control`

| Setting Key | UI Control | Default | Phase | Purpose |
|-------------|------------|---------|-------|---------|
| `allow_negative_stock_sale` | Toggle | false | MVP Core | Allow/block sales that create negative stock |
| `require_manager_approval_for_negative_stock` | Toggle | true | MVP Core | Require manager approval before posting negative stock |
| `negative_stock_scope` | Dropdown | selected_products_only | MVP Core | Defines which items may go negative |
| `show_negative_stock_warning_to_cashier` | Toggle | true | MVP Core | Show warning before posting |
| `create_negative_stock_alert` | Toggle | true | MVP Core | Create dashboard/report alert |
| `negative_stock_costing_method` | Dropdown | last_known_average_cost | MVP Core | Defines estimated costing method |
| `auto_settle_negative_stock_on_purchase` | Toggle | true | MVP Extended | Link later purchases to old negative movements |
| `create_cogs_adjustment_after_negative_stock_settlement` | Toggle | false | MVP Extended | Create cost difference adjustment after settlement |
| `block_negative_stock_for_batch_expiry_serial_items` | Toggle | true | Phase 2 | Prevent traceability issues |
| `show_negative_stock_in_manager_dashboard` | Toggle | true | MVP Core | Surface alerts to managers |

**Product-level override:**

Each Product/ProductUnit can optionally define:

```
allow_negative_stock_override:
  inherit_from_settings
  always_allow
  always_block
  require_manager_approval
```

This allows businesses to permit negative stock for fast-moving café ingredients but block it for controlled products.

### 11.1 Sales Invoice — Posted Effects

```
STOCK:
  Per item (item_type = Stock Item or Ingredient):
    StockMovement: SALE_OUT
    qty: sold quantity
    warehouse: selected sale warehouse
    unit_cost: avg_cost_at_posting (stored immutably on SaleItem)
    Apply negative stock rules (§11.0B)

  Per recipe product (item_type = Recipe Product):
    StockMovement: RECIPE_CONSUME per ingredient
    warehouse: configured recipe_ingredient_warehouse
               (branch_default OR item_specific OR pos_selected)
    qty: recipe_qty × (1 + wastage_factor) × unit_conversion_factor
    unit_cost: ingredient.avg_cost_at_posting

  item_type = Service/Non-Stock:
    No StockMovement created

REVENUE & TAX:
  Net Revenue = Σ (tier_unit_price × qty) − discounts
  FinancialAccountMovement:
    Sales Revenue account ↑ (net amount)
    Tax Payable account ↑ (tax amount)

COGS:
  Per Stock/Ingredient item:
    COGS = avg_cost_at_posting × qty
    Stored: sale_item.avg_cost_at_posting (immutable)
  Per Recipe product:
    COGS = Σ (ingredient_avg_cost × recipe_qty
              × (1 + wastage) × unit_conversion)
    Stored: sale_item.recipe_cost_snapshot (JSON, immutable)
  Service items: no COGS (unless manually configured)
  FinancialAccountMovement: COGS account ↑

PAYMENT ROUTING (per PaymentLine):
  Cash:
    FinancialAccountMovement: Cashbox ↑ (full incl. tax)
    ShiftMovementSummary: cash_sales_total ↑
  Card (manual recording):
    FinancialAccountMovement: Card Settlement account ↑
    ShiftMovementSummary: card_sales_total ↑
    NOTE: cashbox NOT affected
  Wallet:
    FinancialAccountMovement: Wallet account ↑
    ShiftMovementSummary: wallet_sales_total ↑
    NOTE: cashbox NOT affected
  Credit:
    CustomerARMovement: CREDIT_SALE ↑
    ShiftMovementSummary: credit_sales_total ↑
    invoice.payment_status → Unpaid
  Partial:
    Cash/Card/Wallet portion: as above
    Remaining: CustomerARMovement: PARTIAL_PAYMENT_BALANCE ↑
    invoice.payment_status → Partially Paid
  Loyalty Discount:
    LoyaltyRedemption record created
    FinancialAccountMovement: Loyalty Discount account ↑
    NOTE: does NOT go to cashbox, bank, or any cash account
    Reduces invoice total only
    ShiftMovementSummary: loyalty_discount_total ↑ (informational)

SHIFT:
  ShiftMovementSummary: invoice_count ↑
  All relevant totals updated per payment method

LOYALTY (post-commit outbox):
  LoyaltyOutbox record created inside transaction (status: pending)
  After commit, Celery task:
    Calculates points earned on net paid amount
    Creates LoyaltyTransaction: EARN
    Updates CustomerPoints.balance ↑
    Marks LoyaltyOutbox: processed
  NOTE: Points earned AFTER payment commits, not before
  NOTE: Points NOT earned on loyalty discount portion

AUDIT & SNAPSHOT:
  AuditLog: entry written
  posting_snapshot stored on invoice (JSON):
    tax rates per line, tax_mode, discount_before_tax,
    tier_prices per unit, invoice_template_version,
    branch_id, terminal_id, user_id, shift_id,
    avg_cost per item, rounding_settings
```

### 11.2 Sales Invoice — Cancellation Effects

```
All effects of §11.1 reversed atomically:
  StockMovements reversed (SALE_OUT → restore qty)
  RECIPE_CONSUME reversed (ingredients restored)
  Revenue reversed (net amount)
  Tax Payable reversed
  COGS reversed (using cost_snapshot, not current avg_cost)

Per PaymentLine method:
  Cash: Cashbox ↓
  Card: Card Settlement ↓
  Wallet: Wallet account ↓
  Credit: CustomerARMovement reversed
  Loyalty: LoyaltyRedemption reversed

ShiftMovementSummary: all relevant totals reversed
LoyaltyOutbox: cancellation record created (reverses any awarded points)

posting_status → Cancelled
Document number: RETAINED (never reused, ever)
Manager approval: required if setting = true
AuditLog: entry written (reason + approver stored)
```

### 11.3 Sales Return — Posted Effects

```
STOCK:
  StockMovement: SALES_RETURN_IN per returned item
  Stock restored to return warehouse

REVENUE:
  Net Revenue ↓ (return amount, excl. tax)
  Tax Payable ↓ (tax reversed from original snapshot)

COGS:
  Reversed using sale_item.avg_cost_at_posting from original invoice
  NOT recalculated at current avg_cost (prevents manipulation)

REFUND ROUTING (per original PaymentLine method):
  Cash paid:
    Cashbox ↓ (cash physically returned to customer)
  Card paid:
    Card Settlement account ↓
    CardRefundReference record created:
      {card_amount, refund_reference (manual entry),
       terminal_reversal_reference (manual entry),
       refund_status = 'pending'}
    NOTE: Cashbox NOT affected — card refund is on terminal
    NOTE: Cashier must enter terminal reference manually (MVP)
  Wallet paid:
    Wallet account ↓
  Credit/Partial:
    CustomerARMovement: SALES_RETURN_CREDIT ↓ (balance decreases)
  Loyalty discount:
    LoyaltyTransaction: REVERSE_REDEEM (points restored via outbox)
  Mixed payment:
    Each original PaymentLine reversed proportionally
    OR setting: always_refund_cash = true (all refunds go to cashbox)

ShiftMovementSummary:
  return_count ↑
  cash_returns_total ↑ (if cash)
  card_returns_total ↑ (if card)

AuditLog: entry written (reason required, approver if manager required)
```

### 11.4 Purchase Invoice — Posted Effects

Per purchase line `line_type`:

```
Stock Item line:
  StockMovement: PURCHASE_IN
  qty ↑ in selected warehouse
  avg_cost recalculated:
    new_avg = (prev_stock × prev_avg + received_qty × purchase_cost)
              ÷ (prev_stock + received_qty)
  FinancialAccountMovement: Inventory account ↑

Fixed Asset line:
  FixedAsset record created (status: Active)
  FixedAssetLedger: ASSET_PURCHASE
  FinancialAccountMovement: Fixed Asset account ↑
  NO StockMovement, NO expense, NO COGS

Expense line:
  FinancialAccountMovement: Expense account ↑
  NO stock movement

Service line:
  FinancialAccountMovement: Service Expense account ↑
  NO stock movement

PAYMENT ROUTING:
  Cash: Cashbox ↓
  Bank: Bank account ↓
  Credit: SupplierAPMovement: CREDIT_PURCHASE ↑

AuditLog: entry written
posting_snapshot stored
```

### 11.5 Purchase Return — Posted Effects

```
STOCK:
  StockMovement: PURCHASE_RETURN_OUT
  qty ↓ from warehouse

COST BASIS (critical):
  If linked to original Purchase Invoice:
    Use original_purchase_cost_snapshot from that invoice line
    avg_cost recalculated using original cost as the removal basis
  If NOT linked (standalone return):
    Check setting: allow_unlinked_purchase_return
    If false: block — require original invoice link
    If true: use current avg_cost as removal basis
             Manager approval required
             AuditLog: entry with unlinked_return flag

PAYMENT ROUTING:
  Cash refund: Cashbox ↑
  Bank refund: Bank account ↑
  Credit: SupplierAPMovement: PURCHASE_RETURN_CREDIT ↓

AuditLog: entry written
```

### 11.6 Customer Receipt (Payment Collection) — Effects

```
CustomerARMovement: RECEIPT_PAYMENT ↓

Invoice allocation:
  Default: oldest unpaid invoice first (FIFO)
  Manual: cashier selects specific invoice(s)
  Partial allocation: allowed
  Overpayment: CustomerARMovement: OVERPAYMENT_CREDIT ↑
               (remaining becomes unallocated credit)

ReceiptAllocation records created:
  {receipt_id, invoice_id, allocated_amount}

PAYMENT ROUTING:
  Cash: Cashbox ↑, ShiftMovementSummary cash total ↑
  Card: Card Settlement ↑
  Wallet: Wallet account ↑

invoice.payment_status → Paid or Partially Paid

AuditLog: entry written
```

### 11.7 Supplier Payment Voucher — Effects

```
SupplierAPMovement: PAYMENT_MADE ↓

Invoice allocation:
  Default: oldest unpaid first (FIFO)
  Manual: user selects specific purchase invoice(s)
  Overpayment: SupplierAPMovement: OVERPAYMENT_CREDIT ↑

PaymentAllocation records created

PAYMENT ROUTING:
  Cash: Cashbox ↓
  Bank: Bank account ↓

AuditLog: entry written
```

### 11.8 Expense Entry — Effects

```
FinancialAccountMovement: Expense account ↑
PAYMENT ROUTING:
  Cash: Cashbox ↓, ShiftMovementSummary expense_total ↑
  Bank: Bank account ↓

AuditLog: entry written
```

### 11.9 Damage / Wastage — Effects

> This is **not** "no COGS and no impact." Damage has a real financial cost.

```
STOCK:
  StockMovement: DAMAGE_OUT (qty ↓)

FINANCIAL:
  inventory_loss_value = avg_cost_at_posting × damaged_qty
  FinancialAccountMovement:
    Inventory Loss account ↑ (expense — reduces profit)
    Inventory value account ↓

DamageWastage record created:
  {product_id, warehouse_id, qty, unit, avg_cost_at_posting,
   inventory_loss_value, reason, shift_id, created_by}

ShiftMovementSummary: wastage_total ↑ (if linked to active shift)
NOTE: Do NOT increase expense_total unless there is an actual cash expense.

AuditLog: entry written (reason required)
```

### 11.10 Fixed Asset Purchase — Effects

```
FixedAsset record created (status: Active)
FixedAssetLedger: ASSET_PURCHASE

FinancialAccountMovement:
  Fixed Asset account ↑ (the asset is on the balance sheet)
  Cash/Bank/Supplier AP ↓ per payment method

NO StockMovement
NO COGS
NO immediate expense
NO effect on P&L at purchase time

AuditLog: entry written
```

### 11.11 Depreciation Posting — Effects [MVP Extended]

```
Method: Straight-Line (MVP)
  monthly_depreciation =
    (acquisition_cost − salvage_value) ÷ useful_life_months

FixedAssetLedger: DEPRECIATION
FinancialAccountMovement:
  Depreciation Expense account ↑ (reduces profit)
  Accumulated Depreciation account ↑ (contra-asset)

asset.current_book_value ↓ by monthly_depreciation
asset.accumulated_depreciation ↑

No Cashbox, Bank, or Stock movement

AuditLog: entry written
```

### 11.12 Asset Disposal / Write-off — Effects [MVP Extended]

```
Write-off (broken/unusable/lost):
  Loss = current_book_value
  FinancialAccountMovement: Loss on Disposal account ↑
  FixedAssetLedger: WRITE_OFF
  asset.status → Written-off
  Manager approval required

Sold:
  Sale proceeds: Cashbox/Bank ↑
  Gain = proceeds − book_value (if positive → Other Income ↑)
  Loss = book_value − proceeds (if negative → Loss account ↑)
  FixedAssetLedger: ASSET_SALE
  asset.status → Sold

AuditLog: entry written (reason + approver)
```

### 11.13 Cash In / Cash Out — Effects

```
FinancialAccountMovement: Cashbox ↑ (in) or ↓ (out)
ShiftMovementSummary: cash_in_total or cash_out_total ↑
Reason: required
AuditLog: entry written
```

### 11.14 Cash Drop (Drawer → Main Safe) — Effects [MVP Extended]

```
FinancialAccountMovement:
  Cash Drawer account ↓
  Main Safe account ↑
ShiftMovementSummary: cash_drop_total ↑
Manager approval: if setting requires
AuditLog: entry written
NOTE: Cash Drop is NOT an expense — it is an internal transfer
      No P&L impact
```

### 11.15 Stock Adjustment — Effects

```
ADJUSTMENT_IN: StockMovement, qty ↑
  avg_cost recalculated (if cost entered)
ADJUSTMENT_OUT: StockMovement, qty ↓
  inventory_loss_value = avg_cost × adj_qty (informational)
Reason: required
Manager approval: if setting requires
AuditLog: entry written
```

### 11.16 Stocktaking Session Post — Effects [MVP Extended]

```
Per approved variance item:
  Positive variance: ADJUSTMENT_IN movement
  Negative variance: ADJUSTMENT_OUT movement
  Same effects as stock adjustment
Session: posting_status → Posted (immutable)
AuditLog: entry written (who counted, who approved)
```

### 11.17 Opening Balance — Effects

```
Cashbox/Bank/Wallet:
  FinancialAccountMovement: OPENING_BALANCE ↑

Customer AR:
  CustomerARMovement: OPENING_BALANCE (sets initial balance)

Supplier AP:
  SupplierAPMovement: OPENING_BALANCE (sets initial balance)

Stock per item per warehouse:
  StockMovement: OPENING_BALANCE
  Sets initial avg_cost for item

Rule: Immutable after first period close
      Override requires Manager Approval + reason
AuditLog: entry written
```

### 11.18 Shift Open — Effects

```
ShiftMovementSummary record created:
  branch_id, terminal_id, cashbox_id, user_id
  status → Active

Expected opening cash:
  = last_shift.actual_closing_cash (for same cashbox)
  = 0 if first shift ever

Cashier enters actual_counted_cash
opening_variance = expected_opening_cash − actual_counted_cash

If |opening_variance| > setting threshold:
  → Manager Approval Flow (blocking)

AuditLog: entry written (including opening_variance)
```

### 11.19 Shift Close — Effects

```
Expected cash formula:
  opening_cash_actual
  + cash_sales_total
  + customer_cash_receipts (from ShiftMovementSummary)
  + cash_in_total
  − cash_returns_total (cash refunds)
  − cash_out_total
  − expense_total (cash expenses)
  − cash_drop_total (if any)
  = expected_closing_cash

Cashier enters: actual_closing_cash
closing_variance = expected_closing_cash − actual_closing_cash
  Positive variance = shortage (cashier short)
  Negative variance = surplus (cashier has extra)

Card reconciliation:
  card_expected = card_sales_total (from shift)
  card_terminal_batch = cashier enters terminal batch total
  card_variance = card_terminal_batch − card_expected

Wallet reconciliation:
  wallet_expected = wallet_sales_total
  wallet_settlement = cashier enters or confirms

If |closing_variance| > threshold OR significant card_variance:
  → Manager Approval Flow

ShiftMovementSummary: status → Closed
Shift report: auto-generated
AuditLog: entry written (all variance amounts)
```

---

## 📐 12. Costing & COGS Rules

### 12.1 Costing Method: Weighted Average Cost (MVP)

All inventory items use weighted average cost in MVP. FIFO is Phase 2.

### 12.2 Average Cost Formula

```
new_avg_cost =
  (current_stock × current_avg_cost
   + received_qty × purchase_cost_per_unit)
  ÷ (current_stock + received_qty)
```

This is recalculated on every `PURCHASE_IN` and `OPENING_BALANCE` event. The product row is locked with `SELECT FOR UPDATE` during this calculation to prevent race conditions.

### 12.3 Cost Stored Immutably on Sale Line

```python
# On invoice posting:
sale_item.avg_cost_at_posting = product.avg_cost  # snapshot at this moment
sale_item.recipe_cost_snapshot = {...}             # JSON for café items
```

Changes to purchase price **do not affect historical COGS**. Each sale line's cost is the avg_cost at the moment that specific invoice was posted.

### 12.4 Recipe-Based COGS (Café)

For each recipe ingredient at posting time:

```
ingredient_cost =
  ingredient.avg_cost_at_posting (per storage unit)
  × recipe_qty (in recipe unit)
  × (1 + wastage_factor)
  × unit_conversion_factor (recipe unit → storage unit)

Total Recipe COGS = Σ ingredient costs
```

Stored as `sale_item.recipe_cost_snapshot` (JSON with per-ingredient breakdown).

**Example — Ice Mocha:**
```
Milk 250ml × (avg_cost per ml) × 1.02 wastage = X
Coffee 18g × (avg_cost per g) × 1.05 wastage  = Y
Chocolate 20g × (avg_cost per g)               = Z
Cup (1pc) × unit_cost                          = W
Straw (1pc) × unit_cost                        = V
Total COGS per Ice Mocha = X + Y + Z + W + V
```

### 12.5 Unit Conversion in Costing

```
Purchase unit:  1 kg coffee bag @ 200 EGP/kg
Storage unit:   kg
Recipe unit:    g (18g per cup)
Conversion:     1 kg = 1000 g
Cost per g:     200 EGP ÷ 1000 = 0.20 EGP/g
COGS per cup:   0.20 × 18 = 3.60 EGP
```

### 12.6 Sales Return COGS Reversal

Uses `sale_item.avg_cost_at_posting` from the original invoice — not the current avg_cost. This prevents manipulation where a cheap purchase after a return would artificially lower the COGS on the reversal.

### 12.7 Purchase Return Cost Adjustment

- **Linked to original PI:** Use `original_purchase_cost_snapshot` from that PI line. avg_cost is recalculated removing those units at their original cost.
- **Unlinked standalone return:** Use current `avg_cost`. Requires `allow_unlinked_purchase_return = true` (setting) and Manager Approval.

### 12.8 Damage / Wastage Costing

```
inventory_loss = avg_cost_at_damage_time × damaged_qty
```

This is a **real financial loss**, not zero. It is recorded as Inventory Loss expense and reduces Gross Profit. It is separate from operating expenses but appears on the P&L.

### 12.9 Gross Profit Calculation

```
Net Revenue (excl. tax)
− COGS (avg_cost or recipe_cost)
− Inventory Loss (damage/wastage)
= Gross Profit
```

### 12.10 FIFO Costing — [Phase 2]

---

## 🧮 13. Tax Calculation Rules

### 13.1 Tax Mode

Setting: `tax_mode` per tenant

- **`tax_exclusive`** — prices shown without tax; tax added on top
- **`tax_inclusive`** — prices shown with tax included; tax is unwrapped

### 13.2 Tax Exclusive Calculation (per line)

```
net_amount   = (unit_price × qty) − line_discount
tax_amount   = net_amount × tax_rate
line_total   = net_amount + tax_amount
```

### 13.3 Tax Inclusive Unwrap (per line)

```
gross_amount = unit_price × qty  (price already includes tax)
net_amount   = gross_amount ÷ (1 + tax_rate)
tax_amount   = gross_amount − net_amount
line_total   = gross_amount  (no change)
```

### 13.4 Discount Interaction with Tax

Setting: `discount_before_tax` (default: `true`)

```
If discount_before_tax = true:
  taxable_base = price − discount
  tax = taxable_base × rate
  (discount reduces the taxable amount — correct for most jurisdictions)

If discount_before_tax = false:
  tax = price × rate
  total = price + tax − discount
  (tax on full price, discount is a post-tax reduction)
```

### 13.5 Service Charge Tax Interaction

Setting per charge type: `charge_is_taxable`

```
If charge_is_taxable = true:
  Charge amount is added to taxable base before tax calculation
  tax += charge_amount × tax_rate
```

### 13.6 Invoice-Level Tax Aggregation

```
1. Calculate tax per line (as above)
2. Group lines by tax_rate
3. Sum per rate: {rate, taxable_base, tax_amount}
4. Round at invoice level (not per line)
   Rounding method: half-up (default), configurable
5. Store as: invoice.tax_breakdown (JSON array)
```

### 13.7 Tax Payable Treatment

> Tax collected from customers is a **liability**, not revenue.

```
Invoice total: 115 EGP
Net Revenue:    100 EGP → credited to Sales Revenue account
Tax Payable:     15 EGP → credited to Tax Payable account (liability)

P&L shows: Net Revenue (100 EGP) — excludes tax
Balance sheet shows: Tax Payable (15 EGP) — to be remitted to tax authority
```

### 13.8 Tax Summary Report

Dedicated Tax Summary Report showing:
- Total Tax Payable by period
- Breakdown by tax rate
- Taxable amount vs tax amount per rate

This report is used for filing with the tax authority. It is **separate from the P&L**. [MVP Extended]

### 13.9 Tax on Returns

Tax reversed using the same rates from the original invoice's `posting_snapshot`. Not recalculated at return time.

### 13.10 Multiple Tax Rates on One Invoice

A single invoice can have items with different tax rates (e.g., 0% for some items, 14% for others). The tax breakdown shows each rate separately. All rates handled correctly through the aggregation step.

---

## 📄 14. Document Status Model

Rather than a single combined status string, each document carries **five independent status fields**:

### 14.1 The Five Status Fields

| Field | Values |
|-------|--------|
| `posting_status` | `Draft` / `Posted` / `Cancelled` / `Void` |
| `payment_status` | `Unpaid` / `Partially Paid` / `Paid` / `N/A` |
| `return_status` | `Not Returned` / `Partially Returned` / `Returned` |
| `approval_status` | `Not Required` / `Pending` / `Approved` / `Rejected` |
| `sync_status` | `Synced` / `Pending Sync` / `Sync Failed` |

### 14.2 Why Five Fields

A single document can simultaneously be:
- `posting_status = Posted` (document is confirmed)
- `payment_status = Partially Paid` (some money collected)
- `return_status = Partially Returned` (some items returned)
- `approval_status = Not Required` (no approval needed)
- `sync_status = Synced` (confirmed on server)

One combined field like "Partially Paid, Partially Returned" cannot represent this without combinatorial explosion. Five fields handle it cleanly.

### 14.3 Status Transitions

| Transition | Condition |
|-----------|-----------|
| Draft → Posted | Valid document, permissions OK, Posting Engine runs |
| Posted → Cancelled | Manager approval (if required), reversal runs atomically |
| Draft → Void | Mark draft as invalid — no effects to reverse |
| Unpaid → Partially Paid | Customer Receipt collected for partial amount |
| Partially Paid → Paid | Customer Receipt covers remaining balance |
| Not Returned → Partially Returned | Sales Return for subset of items |
| Partially Returned → Returned | Sales Return for all remaining items |

### 14.4 Immutability Rules

- **Posted documents** are read-only — to correct, cancel and create a new document
- **Cancelled documents** are archived — never deleted, original number retained
- **Document numbers** are **never reused**, even after cancellation
  - The rule is "no reuse" — not "no gaps"
  - Gaps are acceptable (from cancellations, voids, offline numbering)
  - What is unacceptable is assigning an old number to a new document
- **Draft numbers** may be temporary — permanent number assigned at posting

---

## 📸 15. Settings Snapshot Rules

When a document is Posted, a snapshot of all relevant settings is stored on the document. This ensures that historical documents remain reproducible regardless of subsequent settings changes.

### 15.1 What Is Captured

```json
{
  "posting_snapshot": {
    "tax_mode": "tax_exclusive",
    "tax_rates_per_line": [{"line_id": 1, "rate": 0.14}],
    "discount_before_tax": true,
    "charge_taxable_map": {"delivery_fee": true},
    "rounding_enabled": true,
    "rounding_amount": 0.05,
    "invoice_template_version": 3,
    "branch_id": 12,
    "terminal_id": 5,
    "user_id": 88,
    "shift_id": 441,
    "tenant_plan_at_posting": "Growth",
    "tier_prices_per_line": [
      {"line_id": 1, "tier_id": 2, "tier_name": "VIP", "price": 4.50}
    ],
    "avg_cost_per_item": {"prod_1": 2.30, "prod_2": 0.18}
  }
}
```

### 15.2 How It Is Used

- **Historical invoice display** always reads from snapshot — not current settings
- **Reprint** uses `invoice_template_version` to render the same template
- **Tax reversal on return** uses `tax_rates_per_line` from snapshot
- **COGS reversal** uses `avg_cost_per_item` from snapshot
- Current settings changes **never alter historical snapshots**

---

## 🔄 16. Offline Idempotency & Duplicate Prevention

### 16.1 Idempotency Key on All State-Changing POSTs

Every API request that creates or modifies data must carry an `idempotency_key` (UUID generated on the client side before sending the request).

This applies to **all state-changing operations** — not only offline ones:
- Online double-submit (cashier presses button twice on slow connection) → prevented
- Offline sync retry → prevented from creating duplicates
- Network timeout where client is unsure if request succeeded → safe to retry

### 16.2 Server-Side Handling

```
Receive POST with idempotency_key

Check: does a record exist with this idempotency_key?
  YES → return existing record (200 OK)
       Do NOT process again
       Do NOT return 409 Conflict
  NO  → process normally, store idempotency_key on the created record
```

### 16.3 Shift Close Offline

If a shift is closed while offline:
- Shift status = `Pending Sync` locally
- On reconnect: server validates shift data and confirms
- If server finds conflict (another shift was opened for same cashbox): flag for manager review

### 16.4 Subscription Cache Offline Behavior

See §6.7 for full subscription offline behavior.

---

## 🖨️ 17. Printer Failure Handling Rules

In a real POS environment, printers fail. These rules prevent a printer failure from disrupting the sale:

1. **Invoice is posted to the database first** (transaction commits)
2. **Print is attempted after the database commit**
3. **If print fails:** show non-blocking dialog:
   - [Retry Print] — try the printer again
   - [Email Receipt] — send to customer email
   - [SMS Receipt] — send to customer phone
   - [Skip] — continue without physical receipt
4. **The dialog does NOT offer [Cancel Invoice]** — the sale is already posted
5. **Invoice remains Posted** regardless of print outcome
6. **Printer failure logged** to Operations Log (not Audit Log)
7. **Kitchen ticket failure:** same rule — Retry/Skip, invoice not affected

---

## 🔓 18. Logout / Session Expiry with Open Shift

A shift must not be automatically closed when a user logs out or a session expires:

- **Logout with open shift:** shift remains Active; on next login, system detects open shift and prompts resume
- **Session expiry (inactivity):** shift remains Active; user re-authenticates and resumes
- **Device lock/sleep:** shift remains Active; resume on unlock
- **Manager force-close orphaned shift:** Manager permission required + reason + Manager Approval Flow + AuditLog entry
- **Orphaned shift alert:** Auto-flag after X hours (configurable setting) — shown to manager

---

## 🏷️ 19. Product / Item Types & Purchase Line Types

### 19.1 Product / Item Types

| Type | Description | Stock | COGS | POS |
|------|-------------|-------|------|-----|
| **Stock Item** | Normal sellable product with inventory | Yes | Avg cost | Yes |
| **Recipe Product** | Café item that consumes ingredients | No own stock | Recipe cost | Yes |
| **Ingredient Item** | Raw material, consumed in recipes | Yes | Avg cost | Optional |
| **Service / Non-Stock** | Service sold (e.g., delivery, labor) | No | None | Yes |
| **Bundle / Combo** [MVP Extended] | Group of items sold together | Per component | Per component | Yes |
| **Fixed Asset** (purchase only) | Equipment, furniture, etc. | No | None | No |

### 19.2 Purchase Invoice Line Types

Each line in a Purchase Invoice has a `line_type` that determines its posting behavior:

| Line Type | Stock Effect | Financial Effect |
|-----------|-------------|-----------------|
| **Stock Item** | PURCHASE_IN movement, avg_cost update | Inventory account ↑ |
| **Expense** | None | Expense account ↑ (immediate P&L) |
| **Fixed Asset** | None | Fixed Asset account ↑ (balance sheet) |
| **Service** | None | Service Expense account ↑ |
| **Non-Stock Purchase** | None | Expense or Service account ↑ |

The `line_type` is selected per line in the purchase invoice form — not set at product level for the entire invoice.

### 19.3 Rules

- `line_type` determines which movement ledger receives the entry
- `line_type` determines which account mapping is used
- Wrong `line_type` (e.g., treating a fixed asset as expense) will misstate P&L and balance sheet — validation warns but does not block
- Default `line_type` per product is derived from `product.item_type`

---

## 🚀 20. Core MVP Modules — Shift Workflow / Cashier Session

> **The Shift Workflow is an operational workflow — it is NOT a sidebar navigation item.** It is accessed exclusively via the header profile dropdown.

### 20.1 Shift Access (Header Profile Dropdown)

**When no shift is open:**
```
○ No active shift
─────────────────
▷ Open Shift
─────────────────
🚪 Sign Out
```

**When shift is open:**
```
● Shift open · Cairo #03 · Cashbox-01 · since 08:12
  87 invoices · €4,287
─────────────────────────
📊 Current Shift Summary
⏹ Close Shift
📈 Today's Performance
─────────────────────────
🚪 Sign Out
```

### 20.2 Open Shift Modal

Fields shown to cashier:
- **Branch** (auto from user assignment)
- **Terminal / Device** (auto-detected or selectable)
- **Cashbox** (select from assigned cashboxes)
- **Expected opening cash:** system-calculated from last shift close
- **Actual counted cash:** cashier enters manually
- **Opening variance:** auto-calculated (shown if non-zero)
- **Notes** (optional)

If `|opening_variance| > threshold` → Manager Approval Flow triggered before shift opens.

### 20.3 Shift State Machine

```
No Shift
  ↓ [Open Shift Modal]
Active Shift
  ↓ [Close Shift Modal from profile dropdown]
Closing (cashier entering counts)
  ↓ [Confirm + optional manager approval]
Closed (shift report generated)
```

### 20.4 Real-Time Shift Tracking

The ShiftMovementSummary is updated automatically on every document posting — no manual action required. The cashier's profile dropdown shows live totals.

### 20.5 Shift Closing (Expected Cash Formula)

```
Expected Closing Cash =
  opening_cash_actual
  + cash_sales_total
  + customer_cash_receipts
  + cash_in_total
  − cash_returns_total (cash refunds paid out)
  − cash_out_total
  − expense_total (cash expenses)
  − cash_drop_total (if cash drops made to safe)

Shortage  = expected − actual counted   (cashier is short)
Surplus   = actual counted − expected   (cashier has extra)
```

Card reconciliation (at shift close):
- System shows: card_expected = Σ card PaymentLines in shift
- Cashier enters: terminal batch total (from physical terminal report)
- Variance = terminal_batch − card_expected (should be zero)
- Significant variance → flagged for manager review

---

## 💻 21. Point of Sale

### 21.1 POS Compact Mode (Barcode-First)

The existing SuperPOS.html POS screen is the baseline. Preserved and extended.

**Critical design rules:**
- Barcode input always has focus — autofocus after every action
- Keyboard-first workflow — experienced cashiers don't use the mouse
- Sale completable in under 3 clicks
- No unnecessary animations or distractions

**Key flows:**
1. Scan barcode → product added (or scale barcode parsed for weighted items)
2. Edit quantity if needed
3. Customer selector (optional unless credit sale or loyalty)
4. Discount panel (if permitted)
5. Payment → Post → Print receipt → Cash drawer signal

### 21.2 POS Touch / Café Mode

Large-tile interface designed for touchscreen tablets in cafés.

**Layout:**
- Category tiles (top or left panel) → tap to filter
- Product tiles (main grid): large image (or colored initials fallback), name, price
- Modifier popup: appears after product tap if modifiers exist
- Cart on right side (same as compact mode)
- Order type selector (Dine-in / Takeaway / Delivery) in cart header

**Order types:**
- **Dine-in:** Customer optional (setting). Kitchen ticket: normal.
- **Takeaway:** Customer NOT required. Anonymous sale is fully valid. Packaging charge optional (setting). Kitchen ticket: labeled **"تيك أواي"** prominently.
- **Delivery:** Customer required (setting). Delivery address captured. Delivery fee added as invoice charge. Kitchen ticket: labeled **"ديليفري"** with address.

### 21.3 Modifier / Size Selection

After a product with modifiers is added (touch mode) or scanned (compact mode with modifiers):

- Modifier popup appears
- Groups shown: Size, Temperature, Extras, etc.
- Required groups: must select before adding to cart
- Optional groups: can skip
- Price delta shown per option
- Selected modifiers shown on cart line, receipt, and kitchen ticket

### 21.4 Price Tier Resolution

```
When item added to cart:
  1. Check if customer is selected
  2. If yes: get customer.price_tier_id
  3. Query ProductUnitTierPrice WHERE
       product_unit_id = X AND price_tier_id = Y
  4. Use that price as unit_price
  5. If no match for tier: fallback to default tier
  6. If no default: fallback to product_unit.default_sale_price

When customer changes mid-transaction:
  Re-resolve all cart line prices
  Show confirmation: "Prices updated for [tier name]"
  Cashier can override per line (if permission)
```

### 21.5 Payment Flow

All payment options:

| Method | Routes To | Notes |
|--------|-----------|-------|
| Cash | Cashbox | Change calculated and shown |
| Visa/Card | Card Settlement account | Manual recording. Reference number optional/required by setting. Cashbox not affected. |
| Wallet (Vodafone Cash, Fawry, InstaPay) | Wallet account | Manual recording. Reference optional. Cashbox not affected. |
| Credit | Customer AR | Customer must be selected. Credit limit checked. |
| Partial | Split: paid now + AR | Any combination. Invoice stays Partially Paid. |
| Mixed | Multiple PaymentLines | Any combination, each routed to correct account. |
| Loyalty Discount | Loyalty Discount account | Reduces total due. NOT cashbox/bank. Remaining paid by other methods. |

### 21.6 Kitchen / Bar Printer Routing — [MVP Core for Cafés]

After invoice posts:
- Each item checked against `item_group.printer_assignment`
- Hot drinks → bar printer
- Food → kitchen printer
- Ticket format: order number, order type label, items, qty, modifiers, order notes, timestamp
- Printer failure: Retry / Skip dialog — invoice not affected
- Full KDS screen (tablet display) → Phase 2

---

## 🧾 22. Sales Cycle

### 22.1 Sales Invoice

Created automatically when cashier completes a POS sale. Can also be created manually from the Sales module (basic in MVP, full advanced mode in Phase 2).

**Document number series:** `SI-YYYY-XXXXX` (configurable)

**Status lifecycle:**
- `posting_status`: Draft → Posted (after payment confirms and Posting Engine runs)
- `payment_status`: Paid (cash) / Unpaid (credit) / Partially Paid (partial)
- `return_status`: Not Returned → Partially/Fully Returned

### 22.2 Sales Return

**Two flows:**

Flow A — Return with original invoice (preferred):
1. Search invoice by number
2. Select items and quantities to return
3. Select refund method (defaults to original PaymentLine method)
4. Post — stock re-enters, revenue reverses, COGS reverses

Flow B — Return without original invoice (if `allow_return_without_invoice = true`):
1. Manually enter items to return
2. Reason required
3. Manager approval required (setting)
4. Refund method: configured default (cashbox or credit)

**Card refund:** Cashier must enter terminal refund reference number. Card refund status = `pending` until manager confirms terminal batch.

**Document number series:** `SR-YYYY-XXXXX`

### 22.3 Customer Receipt (Payment Collection)

When a credit or partially-paid invoice needs payment collected:

1. Open customer profile or find unpaid invoice
2. Create Customer Receipt
3. Enter amount and payment method
4. Allocate to specific invoice(s) (default: oldest first)
5. Invoice payment_status → Paid or Partially Paid

**Document number series:** `RC-YYYY-XXXXX`

---

## 📦 23. Purchase Cycle

### 23.1 Purchase Invoice

Supplier delivers goods/services. Cashier or manager creates purchase invoice.

**Per line:** Select `line_type` (Stock Item / Fixed Asset / Expense / Service)

**Stock Item lines:**
- Select product, unit, quantity, purchase cost
- Select warehouse (which warehouse receives the stock)
- Tax and discount per line
- Stock increases on Post, avg_cost recalculated

**Fixed Asset lines:**
- Select asset category and name
- Enter acquisition cost
- Fixed Asset record created automatically on Post

**Expense lines:**
- Direct to expense account
- No stock movement

**Payment:**
- Cash: cashbox decreases
- Bank: bank account decreases
- Credit: supplier AP increases (invoice stays Unpaid)
- Mixed: any combination

**Document number series:** `PI-YYYY-XXXXX`

### 23.2 Purchase Return

Return items to supplier. Preferably linked to original Purchase Invoice.

- **Linked return:** Uses original cost snapshot for avg_cost recalculation
- **Unlinked return:** Uses current avg_cost (requires setting + manager approval)

**Document number series:** `PR-YYYY-XXXXX`

### 23.3 Supplier Payment Voucher

Pay against outstanding supplier balances.

1. Select supplier
2. Enter amount and payment method
3. Allocate to specific purchase invoices (default: oldest first)
4. Supplier AP decreases, cashbox/bank decreases

**Document number series:** `PV-YYYY-XXXXX`

---

## 👤 24. Customers Module

### 24.1 Customer Master Fields

`id`, `tenant_id`, `customer_code` (auto-generated), `name`, `phone`, `email`, `tax_number`, `address`, `credit_limit`, `price_tier_id`, `customer_group_id` [MVP Extended], `notes`, `is_active`, `created_at`

### 24.2 Credit Limit Enforcement

```
At invoice posting (credit sale):
  If customer.ar_balance + new_invoice_total > customer.credit_limit:
    Check: allow_credit_limit_override (setting)
    If true:  → Manager Approval Flow
              Approved: proceed, note added
              Rejected: block
    If false: block with error "Credit limit exceeded"
```

### 24.3 Opening Balance

- Entry creates CustomerARMovement: OPENING_BALANCE
- Sets initial AR balance (represents pre-system outstanding debt)
- Immutable after first period close
- Included in all balance reports and statements from day one

### 24.4 Customer Statement

Shows chronological list of all CustomerARMovement entries:
- Opening balance
- Each invoice (credit sales)
- Each receipt (payments collected)
- Each return (credits)
- Running balance after each entry

### 24.5 Payment Allocation

When customer pays (Customer Receipt):
- Default: oldest unpaid invoice allocated first (FIFO)
- Manual: cashier/manager selects specific invoices
- Overpayment: excess becomes unallocated credit (shown in statement)
- ReceiptAllocation records created per invoice

---

## 🚚 25. Suppliers Module

### 25.1 Supplier Master Fields

`id`, `tenant_id`, `supplier_code`, `name`, `phone`, `email`, `tax_number`, `address`, `payment_terms` (Net 7/15/30), `supplier_group_id` [MVP Extended], `notes`, `is_active`, `created_at`

### 25.2 Opening Balance

- Creates SupplierAPMovement: OPENING_BALANCE
- Sets initial AP balance (pre-system outstanding payables)

### 25.3 Supplier Statement

Chronological list of all SupplierAPMovement entries with running balance.

### 25.4 Payment Allocation

When paying supplier (Supplier Payment Voucher):
- Default: oldest unpaid purchase invoice allocated first (FIFO)
- Manual: user selects specific invoices
- Overpayment: excess becomes supplier advance/credit

---

## ⬡ 26. Products & Items Module

### 26.1 Product Master Fields

`id`, `tenant_id`, `item_code`, `name`, `item_type` (stock/recipe/ingredient/service/asset), `item_group_id`, `description`, `image_url` [MVP Extended], `tax_rate`, `is_active`, `visible_in_pos`, `is_discountable`, `notes`, `created_at`

### 26.2 Product Units (ProductUnit)

Each product has one or more units. Each unit has its own barcode and prices.

`id`, `product_id`, `unit_id`, `barcode` (EAN-13 or custom), `sku`, `conversion_factor` (relative to base unit), `default_purchase_price`, `last_purchase_price`, `default_sale_price`, `is_default_sale`, `is_default_purchase`, `is_active`

### 26.3 Product Unit Tier Prices (ProductUnitTierPrice)

Sale prices are per unit per price tier — not per product. This is because a product sold as a bottle has a different price than the same product sold as a carton, and both prices may differ by customer tier. Purchase prices are not tier-based; they live on ProductUnit as default/last purchase price, or later in SupplierProductPrice.

`id`, `tenant_id`, `product_unit_id`, `price_tier_id`, `sale_price`, `is_active`, `created_at`

### 26.4 Item Groups (Hierarchical — 2 Levels in MVP)

```
مشروبات (Beverages)
├── ساخنة (Hot)
│   ├── Espresso
│   ├── Cappuccino
│   └── Latte
└── باردة (Cold)
    ├── Iced Coffee
    └── Milkshakes

Food
├── Pastries
├── Sandwiches
└── Salads
```

Used in: touch POS navigation, reports filter, discount rules, price update batches, kitchen printer routing.

### 26.5 Units & Unit Conversions

`Unit` master: name, abbreviation, type (weight/volume/count)

`UnitConversion`: from_unit_id, to_unit_id, factor
Example: 1 kg = 1000 g (factor: 1000)

### 26.6 Recipes / BOM

Each Recipe Product has a recipe (Bill of Materials):

```
Recipe: Iced Latte
├── Espresso 30ml      (ingredient: Coffee, unit: ml, qty: 30, wastage: 2%)
├── Milk 200ml         (ingredient: Milk, unit: ml, qty: 200, wastage: 3%)
├── Ice cubes 5pcs     (ingredient: Ice, unit: piece, qty: 5)
└── Plastic cup 1pc    (ingredient: Cup 500ml, unit: piece, qty: 1)
```

`RecipeIngredient` table: recipe_id, product_id (ingredient), product_unit_id, qty, wastage_factor

**Ingredient warehouse:** Configured per branch via `recipe_ingredient_warehouse_source`:
- `branch_default` — all ingredients from one branch warehouse
- `item_specific` — each ingredient has its own default warehouse
- `pos_selected` — use the sale warehouse (less common for cafés)

### 26.7 Modifiers & Sizes

`ModifierGroup`: name, is_required, min_select, max_select
`ModifierOption`: group_id, name, price_delta, is_default

Example:
```
Size (required, select 1):
  Small    (−2.00 EGP)
  Medium   (0.00 EGP) ← default
  Large    (+3.00 EGP)

Extras (optional, select 0+):
  Extra shot  (+5.00 EGP)
  Soy milk    (+8.00 EGP)
  Oat milk    (+10.00 EGP)
```

### 26.8 Quick Item Edit — [MVP Extended]

Spreadsheet-like bulk editing interface. Authorized users can:
- Filter by item group, warehouse, branch
- Edit price, cost, min stock, max stock, active status inline
- See a diff preview before saving (which fields changed)
- Save triggers: field-level audit log per changed field + POS cache refresh

---

## 🏭 27. Inventory & Warehouses Module

### 27.1 Warehouse Setup

- Multiple warehouses per branch
- Each warehouse: name, branch, type (retail/bar/kitchen/storage), default flag, is_active
- Items can have different stock levels per warehouse
- Warehouse selector shown in purchase invoices and sales (if multi_warehouse_enabled = true)

### 27.2 Opening Stock Entry

- Creates StockMovement: OPENING_BALANCE per item per warehouse
- Sets initial avg_cost for each item
- Immutable after first period close (override requires manager)

### 27.3 Stock Levels

Shown per item × warehouse. Real-time from StockMovement ledger.

Alerts:
- Low stock: `qty ≤ reorder_point`
- Out of stock: `qty = 0`
- Negative stock: `qty < 0` (if allowed by setting)
- Expiry alert [Phase 2]

### 27.4 Scale / PLU Codes

For supermarkets with electronic scales. Existing prototype feature, preserved.

Scale barcode format: `21[5-digit PLU][5-digit weight/price]`

PLU management screen: PLU code, product name, price/kg, last sync status.

### 27.5 Stock Adjustment

Reason required. Manager approval optional (setting). Creates ADJUSTMENT_IN or ADJUSTMENT_OUT movement. AuditLog entry.

### 27.6 Damage / Wastage Entry

Creates DAMAGE_OUT movement + DamageWastage financial record. `inventory_loss_value = avg_cost × qty`. Reduces profit. Reason required.

### 27.7 Warehouse Transfer

TRANSFER_OUT from source warehouse + TRANSFER_IN to destination warehouse. Both in one atomic transaction. Manager approval for large transfers (setting).

### 27.8 Item Movement Log

View of StockMovement records per item, per warehouse, per date range. Exportable.

### 27.9 Stocktaking / Physical Count — [MVP Extended]

1. Create count session (branch, warehouse, item group selection)
2. System freezes expected_qty snapshot
3. User enters actual_qty per item
4. System shows variance per item (and total loss value = variance × avg_cost)
5. Manager reviews and approves/rejects per item
6. Approved variances → ADJUSTMENT_IN or OUT movements
7. Session locked after posting
8. AuditLog entry

---

## 🏢 28. Fixed Assets / الأصول الثابتة — [MVP Core: Register; MVP Extended: Depreciation]

### 28.1 What Fixed Assets Are

Fixed assets are long-life business equipment that are NOT:
- Inventory items (they are not sold to customers)
- Immediate expenses (their cost is spread over useful life via depreciation)

**Examples for cafés and retail:**
Coffee machine, POS device, receipt printer, barcode scanner, scale, refrigerator, air conditioner, chairs, tables, kitchen equipment, furniture, laptop, display screen.

### 28.2 Fixed Asset Categories

- IT Equipment & Electronics
- Kitchen & Café Equipment
- Furniture & Fixtures
- Store Equipment
- Vehicles [Future]
- Other

### 28.3 Fixed Asset Register — [MVP Core]

Each asset record contains:

| Field | Description |
|-------|-------------|
| `asset_category_id` | Category |
| `name` | Asset name |
| `serial_number` | Serial/model number |
| `acquisition_date` | Purchase date |
| `acquisition_cost` | Original cost (EGP) |
| `salvage_value` | Expected residual value at end of life |
| `useful_life_months` | How many months until fully depreciated |
| `depreciation_method` | Straight-line (MVP) |
| `current_book_value` | Acquisition − accumulated depreciation |
| `accumulated_depreciation` | Total depreciation posted so far |
| `status` | Active / Inactive / Written-off / Sold |
| `location` (branch) | Where the asset is |
| `purchase_invoice_id` | Links back to purchase invoice |
| `warranty_expiry` | Optional |

### 28.4 Asset Purchase Flow — [MVP Core]

- Via Purchase Invoice with `line_type = Fixed Asset`
- FixedAsset record created automatically on posting
- `Fixed Asset account ↑` (balance sheet)
- NO stock movement, NO immediate expense, NO COGS

### 28.5 Depreciation — [MVP Extended]

**Method:** Straight-Line

```
monthly_depreciation =
  (acquisition_cost − salvage_value) ÷ useful_life_months
```

**Posting (manual trigger, monthly):**
- `Depreciation Expense account ↑` (reduces net profit)
- `Accumulated Depreciation account ↑`
- `asset.current_book_value ↓`
- FixedAssetLedger: DEPRECIATION
- No cashbox or bank movement

**Automatic monthly depreciation posting:** Phase 2

### 28.6 Asset Write-off — [MVP Extended]

When an asset is broken, lost, or unusable:
- Manager Approval required
- `Loss on Disposal = current book_value`
- `Loss account ↑` (reduces profit)
- `asset.status → Written-off`
- AuditLog entry with reason

### 28.7 Asset Sale — [MVP Extended]

When an asset is sold:
- Cash/bank receives sale proceeds
- Gain = proceeds − book_value (if positive → Other Income)
- Loss = book_value − proceeds (if negative → Loss account)
- `asset.status → Sold`

### 28.8 Asset Reports

- Fixed Asset Register [MVP Core]: list of all assets with status and book value
- Depreciation Report [MVP Extended]: depreciation schedule per asset
- Asset Disposal Report [MVP Extended]: write-offs and sales

---

## 🏷️ 29. Price Tiers / شرائح الأسعار — [MVP Core]

### 29.1 What Price Tiers Are

A Price Tier is a **named set of prices** for the same product/unit. It is NOT a discount applied on top of the default price — it is a separate price structure.

**Example tiers:** Default (counter price), VIP, Wholesale, Staff

### 29.2 Tier Management

- Tenant creates tiers dynamically: any name, any number
- System creates "Default" tier on tenant creation (cannot be deleted)
- Each tenant configures which tiers they use

### 29.3 Prices Per Unit Per Tier (ProductUnitTierPrice)

Each price entry is per `product_unit` × `price_tier`:

```
Product: Pepsi
  Unit: Bottle (330ml) — Barcode: 5410188006353
    Default tier:    5.00 EGP (sale)
    VIP tier:        4.50 EGP (sale)
    Wholesale tier:  3.50 EGP (sale)
  Unit: Carton (24 bottles) — Barcode: 5410188006001
    Default tier:   96.00 EGP (sale)
    VIP tier:       86.00 EGP (sale)
    Wholesale tier: 72.00 EGP (sale)
```

### 29.4 Customer Tier Assignment

Each customer has a `price_tier_id` field. Set when creating or editing the customer. Default: system default tier.

### 29.5 Price Resolution at POS

```
1. Customer selected → get customer.price_tier_id
2. Item scanned → get product_unit_id (from barcode)
3. Query ProductUnitTierPrice WHERE
     product_unit_id = X AND price_tier_id = Y
4. Use that sale_price
5. If not found: fallback to default tier price
6. If still not found: fallback to product_unit.default_sale_price

Tier price stored in posting_snapshot per invoice line
Historical invoices show original tier price
```

### 29.6 Tier Price + Discounts

Tier price = BASE price. Discounts are applied ON TOP of the tier price. A 10% discount on a VIP customer using VIP tier pricing reduces the VIP price by 10%.

---

## 🏆 30. Loyalty & Rewards Program — [MVP Extended]

### 30.1 Program Configuration (Dynamic Per Tenant)

- `points_per_amount`: e.g., 1 point per 10 EGP spent
- `amount_per_point_value`: e.g., 100 points = 1 EGP discount
- `points_expiry_days`: 0 = never expire
- `min_redemption_points`: minimum balance to redeem
- `max_redemption_percent`: maximum % of invoice total that can be paid by loyalty
- `is_active`: toggle

### 30.2 Earning Rules (Dynamic)

Tenant configures earning rules:

| Rule Type | Example |
|-----------|---------|
| `invoice_amount` | 1 point per 10 EGP on any invoice |
| `per_item` | 5 points per unit of product X |
| `per_group` | 3 points per unit from group "Hot Drinks" |

Multiple rules can coexist. Points calculated on **net paid amount** (after discounts, after tier pricing, **excluding the loyalty discount itself**).

### 30.3 Loyalty Redemption

> **Loyalty redemption is a discount type — NOT a payment method.**

It reduces the invoice total due from the customer. The remaining amount is paid by cash, card, wallet, or credit. Loyalty does NOT go to the cashbox, bank, or any financial account. It is tracked only in LoyaltyTransaction ledger.

```
At payment step:
  If customer selected + has redeemable points:
    Show: "استخدام النقاط (رصيدك: 500 نقطة = 5.00 جنيه خصم)"
    Cashier enters points to redeem (up to max_redemption)
    System shows: "خصم نقاط الولاء: −5.00 جنيه"
    Remaining: invoice_total − loyalty_discount
    Remaining paid by cash/card/wallet/credit (PaymentLines)

Inside posting transaction:
  LoyaltyRedemption record created
  CustomerPoints.balance ↓ immediately (not via outbox)
  ShiftMovementSummary: loyalty_discount_total ↑ (informational)
```

### 30.4 Points Lifecycle

| Event | When | Method |
|-------|------|--------|
| Earned | After invoice commits | Outbox pattern (guaranteed) |
| Redeemed | Inside posting transaction | Direct (immediate) |
| Reversed on return | After return commits | Outbox pattern |
| Manually adjusted | Manager permission + reason | Direct + AuditLog |
| Expired | Nightly batch job (Celery) | Batch + LoyaltyTransaction |

### 30.5 Points Guarantee (Outbox Pattern)

Points are **created as a pending LoyaltyOutbox record inside the posting transaction** — they are NOT created after the commit in a separate step that could be lost.

```
INSIDE transaction:
  Create LoyaltyOutbox {invoice_id, customer_id, points_to_award, status: pending}

AFTER commit (Celery task — safe to retry):
  Check LoyaltyOutbox: status = pending AND invoice still Posted
  Check: not already processed (idempotent check)
  Create LoyaltyTransaction: EARN
  Update CustomerPoints.balance ↑
  Mark LoyaltyOutbox: processed
```

If the Celery task fails, it retries safely. Points can never be lost because the outbox record persists until processed.

### 30.6 Customer Points Visibility

- Customer selector in POS: shows `🏆 X نقطة` below customer name
- POS cart (customer selected): "رصيدك: X نقطة" + [استخدام النقاط] button
- Receipt: "نقاط مكتسبة: +X نقطة | رصيدك بعد المعاملة: Y نقطة"
- Customer profile screen: balance, lifetime earned, transaction history

---

## 💰 31. Treasury / Finance Module

### 31.1 Financial Accounts

**Cashboxes:**
- Each physical cash drawer is one Cashbox
- Linked to: branch, terminal (optional), default for terminal
- Has: opening balance, current balance (from FinancialAccountMovement)

**Bank Accounts:**
- External bank accounts
- Used for: purchase payments, cash drops to bank, card settlement settlement (Phase 2)
- Balance tracked (not real-time — reconciled manually in MVP)

**Card Settlement Accounts:**
- Used for Visa/Card payments recorded manually in MVP
- Not the same as cashbox and not direct bank settlement
- Reconciled against terminal batch at shift close

**Wallet Accounts:**
- Vodafone Cash, Fawry, InstaPay, etc.
- Each is a separate financial account
- Balance tracked per wallet type

### 31.2 Payment Method Configuration

Each payment method is configured per tenant:

| Setting | Description |
|---------|-------------|
| `method_type` | cash / card / wallet / credit |
| `linked_account_id` | Which cashbox/bank/wallet/card settlement account this routes to |
| `linked_account_type` | cashbox / bank_account / wallet_account / card_settlement_account |
| `requires_reference` | Whether reference number input is required |
| `include_in_shift` | Whether tracked in shift totals |
| `report_category` | cashbox_report / bank_report / wallet_report / card_settlement_report |
| `is_visible_in_pos` | Show as payment option in POS |

### 31.3 Cash In / Cash Out

- Reason required
- Linked to shift (updates ShiftMovementSummary)
- Cashbox balance updated via FinancialAccountMovement
- AuditLog entry

### 31.4 Cashbox Transfer

Move money between two cashboxes (e.g., from terminal drawer to main cashbox):
- Source cashbox ↓
- Destination cashbox ↑
- Both via FinancialAccountMovement
- Manager approval if amount exceeds threshold (setting)

### 31.5 Cash Drop — [MVP Extended]

Move excess cash from terminal drawer to main safe during or after shift:
- Cash Drawer ↓
- Main Safe ↑
- ShiftMovementSummary: cash_drop_total ↑
- **Not an expense** — internal transfer, no P&L impact
- Manager approval if required

### 31.6 Main Safe / Secondary Cashbox

- Separate financial account from terminal drawers
- Not used by cashiers for sales
- Used by owner/manager to store excess cash
- Transfers from drawers via Cash Drop

---

## 💸 32. Expenses Module

Expenses are accessed from the **Treasury / Finance** sidebar section — not a standalone sidebar module.

### 32.1 Expense Categories

Configurable per tenant. Examples:
- Rent
- Electricity / Utilities
- Staff salaries
- Cleaning supplies
- Maintenance / Repairs
- Marketing
- Daily café supplies (milk, cups, packaging)

### 32.2 Expense Entry

| Field | Description |
|-------|-------------|
| Category | Required |
| Amount | Required |
| Description | Optional |
| Payment Method | Cash (from cashbox) / Bank |
| Shift | Auto-linked to current open shift |
| Date | Defaults to today |
| Attachment | Receipt photo [MVP Extended] |

**Effects:**
- `FinancialAccountMovement`: Expense account ↑
- Cashbox ↓ (if cash) / Bank account ↓ (if bank)
- `ShiftMovementSummary`: expense_total ↑

### 32.3 Expense Approval — [MVP Extended]

Expenses above a configured threshold require manager approval before posting.

---

## 🏷️ 33. Discounts, Offers & Charges

### 33.1 Discount Types

**Item-Level Discount (per cart line):**
- % discount or fixed amount
- Applied before invoice discount
- Permission-controlled per role
- Maximum % per role (setting): `max_item_discount_cashier`, `max_item_discount_manager`
- Exceeds limit → Manager Approval Flow

**Invoice-Level Discount (on subtotal):**
- Applied after all line discounts
- Same permission and limit rules

**Discount Before/After Tax:** Controlled by `discount_before_tax` setting (§13.4)

### 33.2 Service Charges & Fees

Added as invoice charge lines (positive additions):
- Delivery fee
- Packaging fee
- Service charge
- Each charge can be taxable or not (`charge_is_taxable` per charge type)
- Shown as separate line on receipt

### 33.3 Coupon / Promo Codes — [MVP Extended]

`DiscountCode` table:
- `code`: unique string
- `discount_type`: percent / fixed
- `discount_value`: amount
- `valid_from`, `valid_until`
- `max_uses`, `uses_count`
- `applicable_to`: all / item_group / specific_items
- `minimum_invoice_amount`

Validation at POS: code entered → system checks all rules → applies if valid.

### 33.4 Time-Based Offers — [MVP Extended]

Happy hour and similar: price overrides active during configured time windows per item group.

### 33.5 Manager Approval for Discounts

If cashier applies a discount exceeding their role limit:
→ Manager Approval Modal appears
→ Manager enters PIN/password
→ Approved/rejected + AuditLog entry
→ Approval record stored on invoice

---

## 🔢 34. Document Numbering

All documents have configurable, sequential, unique numbers that are **never reused**.

### 34.1 Document Series

| Document | Default Prefix | Example |
|----------|---------------|---------|
| Sales Invoice | SI | SI-2026-00001 |
| Sales Return | SR | SR-2026-00001 |
| Customer Receipt | RC | RC-2026-00001 |
| Purchase Invoice | PI | PI-2026-00001 |
| Purchase Return | PR | PR-2026-00001 |
| Supplier Payment | PV | PV-2026-00001 |
| Expense Voucher | EXP | EXP-2026-00001 |
| Shift | SHF | SHF-2026-00001 |
| Stock Adjustment | ADJ | ADJ-2026-00001 |
| Warehouse Transfer | TR | TR-2026-00001 |
| Quotation [Phase 2] | QT | QT-2026-00001 |

### 34.2 Series Configuration Per Tenant

- Prefix (configurable)
- Year/month format in number
- Starting number
- Minimum digits (zero-padded)
- Reset policy: yearly / monthly / never
- Branch-specific numbering: optional

### 34.3 Rules

- Number assigned on POST (not on Draft creation)
- Draft documents may show a temporary "pending" reference
- Once assigned, number is permanent and immutable
- Cancelled documents keep their original number (shown as Cancelled)
- Numbers are never reused — gaps are acceptable, reuse is not
- Manual numbering: requires permission `numbering.manual_override`

---

## 📊 35. Reports Center

Reports read from Movement Ledgers — not from document state. This ensures accuracy even when documents are partially paid or partially returned.

### 35.1 MVP Core Reports

**Sales Reports:**
- Daily sales summary (revenue, invoices, avg basket, by payment method)
- Sales by period (date range, with comparison)
- Sales by cashier (performance, discount usage, return rate)
- Sales by branch
- Sales by payment method
- Sales by item (top sellers, revenue, qty, COGS, margin)
- Sales returns report (by period, by reason)
- Discounts report (total discounts given, by cashier, by type)
- Cancelled invoices report

**Purchase Reports:**
- Purchase invoices (by period, by supplier)
- Purchases by item
- Purchase returns report

**Inventory Reports:**
- Item movement report (per item: all stock changes in date range)
- Item balance report (current stock per item per warehouse)
- Stock adjustment report
- Damage / wastage report (qty + inventory loss value)
- Minimum stock alerts (items at or below reorder point)
- Negative stock alerts report (items currently below zero, by warehouse, product, and user)

**Customer Reports:**
- Customer statement (all AR movements per customer)
- Customer balances (outstanding AR, grouped by aging)
- Customer payments received

**Supplier Reports:**
- Supplier statement (all AP movements per supplier)
- Supplier balances (outstanding AP)
- Supplier payments made

**Treasury / Cashbox Reports:**
- Cashbox movement report (all cash-in, cash-out, sales, returns per cashbox)
- Shift report (full shift summary including reconciliation)
- Expenses report (by period, by category, by branch)
- Cash shortage / surplus history

**User / Shift Reports:**
- User performance (sales, returns, discounts, cancellations per user)
- Cashier movement report (daily activity per cashier)
- User sales report

**P&L Report (Basic):**
```
Net Revenue (excl. tax)
− COGS (avg_cost or recipe_cost)
− Inventory Loss (damage/wastage)
= Gross Profit
− Operating Expenses
= Net Profit (Operating)
```
Tax Payable shown separately — NOT in P&L.

### 35.2 MVP Extended Reports

- Tax Summary Report (Tax Payable by period, by rate)
- Warehouse balance report (stock value per warehouse)
- Profit by item / by item group / by branch
- User shift history report
- User activity log report
- Loyalty reports: points earned, redeemed, liability, top customers
- Rounding Adjustment Report: rounding gain/loss by period and branch
- Negative Stock Settlement Report: purchases that covered previous negative balances
- Estimated Cost Sales Report: sales posted using estimated cost due to negative stock
- COGS Adjustment Report: cost adjustments created after negative stock settlement

### 35.3 Phase 2 Reports

- Bank movement report (deposits, withdrawals, card settlement)
- Advanced tax reports (VAT return format)
- Custom report builder (drag-and-drop)
- Scheduled reports (email delivery)

---

## 👥 36. Users & RBAC

### 36.1 Roles

| Role | Description |
|------|-------------|
| **Owner** | Full access, subscription management, all settings |
| **Admin** | Full access except subscription/billing |
| **Manager** | Sales, purchases, inventory, reports, user management within branch |
| **Cashier** | POS sales, basic reports (own performance) |
| **Inventory Clerk** | Inventory adjustments, purchases, warehouse management |
| **Accountant / Finance** | Reports, treasury, expense management, P&L |
| **Waiter** [Phase 2] | Table orders, order modification |
| **Gym Receptionist** [Future] | Check-ins, membership management |

### 36.2 Key Granular Permissions (Selected)

| Permission Code | Description |
|----------------|-------------|
| `sales.create` | Create sales invoices in POS |
| `sales.edit_price` | Edit item price in invoice |
| `sales.discount` | Apply discounts |
| `sales.cancel` | Cancel a posted invoice |
| `sales.return` | Create sales returns |
| `sales.credit_sale` | Allow credit sales |
| `sales.partial_payment` | Allow partial payments |
| `purchase.create` | Create purchase invoices |
| `purchase.return` | Create purchase returns |
| `purchase.unlinked_return` | Return without original PI link |
| `inventory.adjust` | Create stock adjustments |
| `inventory.transfer` | Create warehouse transfers |
| `inventory.damage` | Create damage/wastage entries |
| `inventory.stocktake` | Create and approve stocktaking sessions |
| `cashbox.open_shift` | Open a cashier shift |
| `cashbox.close_shift` | Close a shift |
| `cashbox.approve_variance` | Approve shift shortage/surplus |
| `cashbox.cash_drop` | Create cash drops |
| `fixed_assets.create` | Create fixed asset records |
| `fixed_assets.depreciate` | Post depreciation |
| `fixed_assets.dispose` | Write-off or sell assets |
| `reports.view_pl` | View P&L report |
| `reports.view_all_branches` | View reports across all branches |
| `reports.export` | Export reports |
| `settings.edit` | Edit system settings |
| `settings.account_mapping` | Edit account mapping |
| `discount.override_limit` | Apply discount above role limit |
| `price_tier.assign_customer` | Assign price tier to customer |
| `loyalty.configure` | Setup loyalty program |
| `loyalty.manual_adjust` | Manually adjust customer points |
| `loyalty.redeem` | Redeem customer points at POS |
| `period.lock` | Lock a business period |
| `numbering.manual_override` | Manually set document number |
| `attachments.upload` | Upload document attachments |

### 36.3 Manager Approval Triggers

The following actions trigger the Manager Approval Flow when configured:

- Discount exceeds role's maximum percentage
- Selling below cost price
- Credit sale above customer credit limit
- Return without original invoice
- Shift opening variance exceeds threshold
- Shift closing variance exceeds threshold
- Stock adjustment (if setting requires approval)
- Unlinked purchase return
- Invoice cancellation (if setting requires approval)
- Negative stock override
- Manual loyalty points adjustment
- Period lock override
- Asset write-off
- Cash drop above threshold
- Price edit on posted document

### 36.4 User Activity Monitoring

Each user has a tracked activity record:
- Login/logout history with timestamp, IP, device
- User session tracking (active sessions)
- Current open shift indicator
- Shift history (per shift: open time, close time, cashbox, terminal, totals)
- Performance metrics: total sales, total returns, total discounts, total cancellations, avg transaction value, invoice count

---

## ⚙️ 37. Settings Center

The Settings Center is a dedicated section with category-based left-panel navigation. All 14 categories shown in MVP Core navigation; content depth varies.

### 37.1 Settings Categories

| # | Category | Label |
|---|----------|-------|
| 1 | System Settings | إعدادات النظام |
| 2 | Branch & Terminal Management | إعدادات الفروع والأجهزة |
| 3 | Invoice Settings | إعدادات الفواتير |
| 4 | Inventory & Warehouse Settings | إعدادات المخزون والمخازن |
| 5 | Customer & Supplier Settings | إعدادات العملاء والموردين |
| 6 | Tax Settings | إعدادات الضرائب |
| 7 | User Permission Settings | إعدادات الصلاحيات |
| 8 | Hardware & Printer Settings | إعدادات الأجهزة والطابعات |
| 9 | Display Settings | إعدادات طريقة العرض |
| 10 | Invoice & Receipt Designer | تصميم الفواتير والإيصالات |
| 11 | Document Numbering | أرقام التعاملات |
| 12 | Payment Methods | طرق الدفع |
| 13 | Shift & Cashbox Settings | إعدادات الشفتات والخزائن |
| 14 | Discounts & Charges Settings | إعدادات الخصومات والإضافات |

**Additional categories:**
- Opening Balances setup (in each entity module)
- Account Mapping (in System Settings)
- Data Import / Export [MVP Extended]
- Loyalty Program [MVP Extended]
- Report Preferences [Phase 2]

### 37.2 Key Settings That Control Business Behavior

| Setting | Effect |
|---------|--------|
| `require_shift_before_selling` | Blocks POS if no open shift |
| `allow_credit_sale` | Enables credit PaymentLine |
| `require_customer_for_credit` | Forces customer selection for credit |
| `allow_return_without_invoice` | Enables sales return flow B |
| `max_cashier_discount_percent` | Triggers approval if exceeded |
| `max_manager_discount_percent` | Hard limit for manager discounts |
| `discount_before_tax` | Changes tax base calculation |
| `charge_is_taxable` (per charge type) | Adds charge to tax base |
| `tax_mode` | tax_exclusive / tax_inclusive |
| `allow_negative_stock_sale` | Allows or blocks posting sales that create negative stock |
| `require_manager_approval_for_negative_stock` | Requires manager approval before posting negative stock |
| `negative_stock_scope` | all_products / selected_products_only / ingredients_only / products_and_ingredients |
| `show_negative_stock_warning_to_cashier` | Shows warning before posting sale with insufficient stock |
| `create_negative_stock_alert` | Creates alert when stock balance becomes negative |
| `negative_stock_costing_method` | last_known_average_cost / default_purchase_price / zero_cost_require_later_adjustment |
| `auto_settle_negative_stock_on_purchase` | Links later purchases to old negative stock movements |
| `create_cogs_adjustment_after_negative_stock_settlement` | Creates COGS adjustment when actual purchase cost differs from estimated sale cost |
| `block_negative_stock_for_batch_expiry_serial_items` | Blocks negative sale for batch/expiry/serial items |
| `show_negative_stock_in_manager_dashboard` | Shows negative stock alerts in manager dashboard |
| `recipe_ingredient_warehouse_source` | branch_default / item_specific / pos_selected |
| `allow_unlinked_purchase_return` | Allow PR without original PI |
| `require_cashbox_for_shift` | Forces cashbox selection on open |
| `require_denomination_count` | Require denomination breakdown at close |
| `cash_drop_enabled` | Enable cash drop workflow |
| `loyalty_program_active` | Enable loyalty features in POS |
| `earn_on_credit` | Earn points on credit sales |
| `price_tiers_enabled` | Enable tier pricing in POS |
| `require_customer_for_takeaway` | (false by default for cafés) |
| `takeaway_packaging_charge` | Auto-add packaging fee for takeaway |
| `subscription_offline_grace_hours` | How long offline subscription is valid |

### 37.2A Negative Stock Control Settings

Location:

`Settings → Inventory & Warehouse Settings → Negative Stock Control`

**Business purpose:** Allow each tenant to decide whether the POS should block sales when stock is not available, or allow temporary negative stock with proper warnings, approval, alerts, and later settlement.

**UI layout:**

```
[Toggle] Allow Negative Stock Sale
  السماح بالبيع عند عدم توفر مخزون كافي

  If enabled:
    [Toggle] Require Manager Approval for Negative Stock
    [Dropdown] Negative Stock Scope
      - All products
      - Selected products only
      - Ingredients only
      - Products and ingredients
    [Toggle] Show cashier warning before posting
    [Toggle] Create Negative Stock Alert
    [Dropdown] Costing behavior when stock is negative
      - Use last known average cost
      - Use default purchase price
      - Use zero cost and require later adjustment
    [Toggle] Auto-settle negative stock on purchase
    [Toggle] Create COGS adjustment after settlement
    [Toggle] Block negative stock for batch/expiry/serial items
    [Toggle] Show negative stock in manager dashboard
```

**Cashier warning example:**

```
This sale will create negative stock.
Item: Milk
Available: 0 liters
Required: 5 liters
Resulting balance: -5 liters

Manager approval required: Yes/No depending on settings.
```

**Phase classification:**
- Basic block/allow toggle = MVP Core
- Cashier warning = MVP Core
- Manager approval = MVP Core
- Negative stock alert = MVP Core
- Product-level override = MVP Core
- Automatic quantity offset by future purchases = MVP Core through StockMovement balance
- Formal NegativeStockSettlement records = MVP Extended
- COGS Adjustment after actual purchase cost is known = MVP Extended
- Batch/expiry/serial-specific blocking enforcement = Phase 2

### 37.3 Invoice & Receipt Designer

Settings for how receipts and invoices are rendered:

- Template type: thermal 80mm / A4
- Show/hide: logo, QR code, cashier name, branch name, customer name, payment method, item barcode, item discount, invoice discount, tax breakdown, service charges, return policy, footer message, loyalty points earned
- Number of printed copies
- Language: Arabic / English
- RTL/LTR layout
- Currency display format
- Date/time format
- Printer assignment per document type
- Kitchen/bar printer ticket configuration

Changes affect print format only — historical data is unaffected (snapshot rules §15).

### 37.4 Branch & Terminal Management

**Branches:**
- Name, address, active/inactive
- Default warehouse
- Default cashbox
- Branch-specific tax number (optional)

**Terminals / Devices:**
- Name, serial, branch
- Default cashbox
- Default receipt printer
- Default kitchen printer
- Default bar printer
- Default barcode scanner
- Default scale
- Active/inactive

**User Assignments:**
- User → branch (restrict to specific branch)
- User → terminal (restrict to specific terminal)
- User → cashbox (restrict to specific cashbox)

---

## 📋 38. Customer & Supplier Advances / Deposits — [MVP Extended]

### 38.1 Customer Advance

Customer pays money before a specific invoice exists:

1. Create Customer Advance (or record via Customer Receipt with "advance" flag)
2. Cash/Card/Wallet/Bank increases per payment method
3. `CustomerARMovement: ADVANCE_RECEIPT` — customer credit balance increases
4. Later: allocate advance to specific invoices manually or via FIFO
5. Allocation creates: `CustomerARMovement: ALLOCATION`
6. Invoice payment_status → Paid / Partially Paid

### 38.2 Supplier Advance

Business pays supplier before a purchase invoice exists. This is not normal Accounts Payable owed to the supplier; it represents a prepaid supplier balance / supplier credit that the business can later allocate against future purchase invoices.

1. Record Supplier Advance
2. Cashbox/Bank decreases now
3. Supplier ledger records `ADVANCE_PAYMENT` as supplier credit / prepaid balance
4. Later: allocate the advance to purchase invoice(s)
5. Allocation reduces the unallocated supplier advance balance
6. Reports must show supplier advances separately from normal unpaid AP

---

## 🪙 39. Cash Denomination Counting — [MVP Extended]

### 39.1 Purpose

At shift open/close, cashier counts physical cash by denomination rather than entering a single total. This is more accurate and provides an audit trail.

### 39.2 Configuration

Denomination values configurable per tenant:

| Denomination | Example |
|-------------|---------|
| 200 EGP note | × count = subtotal |
| 100 EGP note | × count = subtotal |
| 50 EGP note | × count = subtotal |
| 20 EGP note | × count = subtotal |
| 10 EGP note | × count = subtotal |
| 5 EGP note/coin | × count = subtotal |
| 1 EGP coin | × count = subtotal |
| 50 piastres coin | × count = subtotal |
| Total: auto-calculated | |

### 39.3 Settings

- `require_denomination_count_on_close`: force denomination breakdown
- `require_denomination_count_on_open`: force at opening too
- `allow_manual_total_only`: allow single total entry (no breakdown)

**MVP Core:** Manual total entry (current behavior)  
**MVP Extended:** Denomination breakdown with auto-total

---

## 📎 40. Document Attachments — [MVP Extended]

### 40.1 Supported Documents

- Purchase Invoice (supplier invoice photo)
- Expense Entry (expense receipt photo)
- Fixed Asset (warranty, purchase proof)
- Asset Maintenance record (repair invoice)
- Supplier Payment Voucher (bank transfer slip)
- Sales Return (return proof)
- Shift Close (terminal batch screenshot)

### 40.2 Rules

- Stored in S3 with tenant-scoped path
- Linked to: `entity_type`, `entity_id`, `tenant_id`
- Access: permission-controlled (`attachments.upload`, `attachments.view`, `attachments.delete`)
- AuditLog entry on upload and on delete
- Allowed types: JPG, PNG, PDF (configurable)
- Max file size: configurable per tenant
- Cancelled documents are read-only for business fields, but attachments may still be uploaded with permission
- Use case: attach cancellation proof, refund proof, manager approval evidence, or receipt evidence after cancellation
- Upload/delete on cancelled documents must write AuditLog
- Attachment history remains visible

### 40.3 Database

```
DocumentAttachment:
  id, tenant_id, entity_type, entity_id,
  file_name, file_url, file_type, file_size,
  uploaded_by, created_at
```

---

## 🔢 41. Rounding & Precision Rules

### 41.1 Money Precision

- All monetary values stored as `Decimal` (not `float`)
- Default precision: 2 decimal places
- Configurable: `currency_decimal_places`
- No floating-point precision errors — `Decimal('0.10') + Decimal('0.20') = Decimal('0.30')`

### 41.2 Quantity Precision

- Stock quantities: 3 decimal places (kg, liters)
- Recipe quantities: 4 decimal places (grams, ml)
- Configurable: `quantity_decimal_places`

### 41.3 Tax Rounding

- Calculated at invoice level (not per line) — see §13.6
- Method: half-up (round 0.5 up)
- Configurable: `tax_rounding_method` (`half_up` / `half_even`)

### 41.4 Invoice Rounding Adjustment

Optional small rounding adjustment to make totals round numbers:

- Setting: `invoice_rounding_enabled`
- `rounding_amount` stored as a separate field on invoice
- Included in `posting_snapshot`
- Shows on receipt as a separate line
- Rounding affects total due, but must not silently change revenue
- Any rounding gain/loss routes to the Rounding Adjustment account via `default_rounding_adjustment_account`

### 41.5 Cash Change Rounding

Cash change calculation handles denomination gaps (e.g., if smallest denomination is 50 piastres):
- Setting: `cash_rounding_enabled`
- Card and wallet: exact amount, no rounding

---

## 🔐 42. Security, Privacy & Data Protection

### 42.1 Tenant Isolation

- `tenant_id` on every table row
- `tenant_id` carried in JWT payload
- Middleware adds `tenant_id` filter to every database query automatically
- No cross-tenant data access possible via any API endpoint

### 42.2 RBAC at API Level

- Permission check runs on every state-changing API endpoint
- Enforcement is server-side — client UI hiding alone is not sufficient
- Failed permission check: HTTP 403, logged in AccessLog
- Repeated failures: alert logged, admin notified (configurable threshold)

### 42.3 Password & Session Security

- Passwords: hashed with bcrypt
- Access tokens: JWT, 15-minute expiry
- Refresh tokens: 30-day expiry, stored as httpOnly cookie
- Session invalidated immediately on logout
- Auto-logout after configurable inactivity period
- Device sessions tracked: device_id, IP, user_agent

### 42.4 Financial Data Protection

- Sensitive financial actions (cancel invoice, large discounts, price edits) require re-authentication or Manager PIN
- All financial changes written to Audit Log (immutable)
- No card data stored — card terminal is external, only reference numbers stored

### 42.5 API Rate Limiting

Applied per tenant and per endpoint. Configurable thresholds. Rate limit hits logged to Operations Log.

### 42.6 Audit Log Immutability

Audit log records are INSERT-only. No UPDATE or DELETE operations are permitted on AuditLog table. Enforced at DB level (trigger or application constraint).

### 42.7 Data Retention Policy

| Data Type | Minimum Retention |
|-----------|-------------------|
| Transaction records | 7 years |
| Audit logs | 7 years |
| Operations logs | 1 year |
| Access logs | 3 years |
| Deleted user data | Anonymized, not deleted |
| Expired tenant data | Archived after 30-day export window |

### 42.8 Backup & Restore

- Daily automated database backups
- Point-in-time recovery capability
- Backup tested monthly
- RTO (Recovery Time Objective): 4 hours
- RPO (Recovery Point Objective): 24 hours
- S3 storage (attachments, exports): versioned + cross-region replication

### 42.9 Tenant Data Export

- Full data export per tenant (CSV/Excel per entity type)
- 30-day export window after subscription cancellation
- After 30 days: data archived per retention policy

---

## ⚡ 43. Non-Functional Requirements

### 43.1 Performance Targets

| Metric | Target |
|--------|--------|
| POS page load | < 1 second |
| Barcode scan → product display | < 300ms |
| Invoice posting (full atomic) | < 2 seconds |
| Report generation (most reports) | < 5 seconds |
| Offline sync on reconnect | < 30 seconds |
| Dashboard load | < 2 seconds |
| Product catalog cache refresh | < 5 seconds |

### 43.2 Reliability & Correctness Requirements

| Requirement | Implementation |
|-------------|---------------|
| Invoice posting must be atomic | Single DB transaction, all-or-nothing |
| No duplicate invoice numbers | Sequence + unique constraint |
| No stock race conditions | SELECT FOR UPDATE on product rows |
| Offline queue must not duplicate | idempotency_key on all POSTs |
| Printer failure must not cancel invoice | Post to DB first, print after commit |
| avg_cost must update on every purchase | Triggered in Posting Engine |
| Tax must route to Tax Payable (not revenue) | Account Mapping Layer enforced |
| Loyalty points must not be lost | Outbox pattern with Celery retry |
| Fixed asset purchase must not be an expense | line_type validation in Posting Engine |

### 43.3 Scalability

- 10,000+ tenants on shared PostgreSQL database
- 100,000+ transactions per tenant per year
- FK indexes on all foreign key columns
- Composite indexes on (tenant_id, created_at) for all high-frequency tables
- DB partitioning planned after 100GB per table
- Redis caching for product catalog, permissions, subscription status

### 43.4 Availability

- Target uptime: 99.9% (planned maintenance during off-peak hours)
- Offline-first design means local downtime does not affect cashier operations

### 43.5 Security

- OWASP Top 10 compliance
- SQL injection prevention via ORM parameterized queries
- XSS prevention via output encoding
- CSRF protection on all state-changing endpoints
- File upload validation (type, size, content scanning)

### 43.6 Accessibility

- WCAG 2.1 AA minimum standard
- Full keyboard navigation
- Screen reader support (semantic HTML, ARIA labels)
- Full Arabic RTL support (CSS logical properties throughout)

---

## 🗄️ 44. Database / Schema Requirements

### 44.1 Existing Tables (Preserve & Extend)

The following tables exist in the current codebase and are preserved:

`Tenant`, `Branch`, `User`, `Terminal`, `Category` (to be extended with hierarchy), `Product`, `Sale`, `SaleItem`, `InventoryBatch`, `StockMovement`

**Required fixes to existing tables:**
- Add FK indexes on all foreign key columns (performance fix)
- Add `SELECT FOR UPDATE` usage for stock deduction (race condition fix)
- Change `username` to unique per tenant (not globally)
- Add `warehouse_id` and `branch_id` to `StockMovement`
- Make `Sale.branch` non-nullable (required field)

### 44.2 New Tables — MVP Core

**Document Status Fields (add to all document tables):**
```
posting_status   VARCHAR(20)
payment_status   VARCHAR(20)
return_status    VARCHAR(20)
approval_status  VARCHAR(20)
sync_status      VARCHAR(20)
idempotency_key  UUID (unique)
posting_snapshot JSONB
```

**Movement Ledgers:**
- `StockMovement` (extended from existing)
- `FinancialAccountMovement`
- `CustomerARMovement`
- `SupplierAPMovement`
- `ShiftMovementSummary`

**Account Mapping:**
- `AccountMapping` (tenant_id, account_type, account_name, account_id)

**Financial Accounts:**
- `Cashbox` (tenant_id, branch_id, terminal_id, name, opening_balance)
- `BankAccount` (tenant_id, name, account_number, bank_name)
- `WalletAccount` (tenant_id, name, wallet_type, account_reference)
- `PaymentMethod` (tenant_id, name, type, linked_account_type, linked_account_id, config JSON)

**Customers & Suppliers:**
- `Customer` (extended — add price_tier_id, credit_limit)
- `Supplier` (new — name, phone, payment_terms, balance)
- `ReceiptAllocation` (receipt_id, invoice_id, allocated_amount)
- `PaymentAllocation` (payment_id, purchase_invoice_id, allocated_amount)

**Price Tiers:**
- `PriceTier` (tenant_id, name, description, is_system_default)
- `ProductUnitTierPrice` (tenant_id, product_unit_id, price_tier_id, sale_price, is_active)
- Purchase prices are stored on `ProductUnit` (`default_purchase_price`, `last_purchase_price`)
- `SupplierProductPrice` for supplier-specific purchasing prices is MVP Extended / Phase 2

**Purchase Cycle:**
- `PurchaseInvoice`, `PurchaseInvoiceItem` (with line_type field)
- `PurchaseReturn`, `PurchaseReturnItem`
- `SupplierPayment`
- `CardRefundReference`

**Sales Extended:**
- `SalesReturn`, `SalesReturnItem`
- `CustomerReceipt`

**Inventory:**
- `Warehouse` (tenant_id, branch_id, name, type, is_default)
- `StockLevel` (product_id, product_unit_id, warehouse_id, qty, avg_cost)
- `DamageWastage`
- `NegativeStockAlert` (product_id, product_unit_id, warehouse_id, qty_shortage, source_document_id, user_id, status)

**Shift:**
- `Shift` (user_id, cashbox_id, terminal_id, branch_id, opening_expected, opening_actual, opening_variance, status)

**Fixed Assets:**
- `FixedAssetCategory`
- `FixedAsset`
- `FixedAssetLedger` (asset lifecycle events)

**Logging:**
- `AuditLog`
- `AccessLog`
- `OperationsLog`

**Document Numbering:**
- `DocumentNumberingSeries` (tenant_id, document_type, prefix, next_number, reset_policy)

### 44.3 New Tables — MVP Extended

- `LoyaltyProgram`, `LoyaltyRule`, `CustomerPoints`
- `LoyaltyOutbox` (guarantee pattern)
- `LoyaltyRedemption` (separate from PaymentLine)
- `LoyaltyTransaction` (ledger)
- `DiscountCode`, `DiscountRule`
- `AssetDepreciationEntry`, `AssetDisposal`, `AssetMaintenance`, `AssetTransfer`
- `InventoryCountSession`, `InventoryCountLine`
- `CustomerAdvance`, `SupplierAdvance`
- `CashDenominationConfig`, `CashCountLine`
- `CashDrop`
- `DocumentAttachment`
- `PeriodLock`
- `DataImportLog`
- `InvoiceCharge` (service charges, delivery fees)
- `NegativeStockSettlement` (purchase_invoice_id, product_unit_id, warehouse_id, covered_negative_qty, affected_stock_movement_ids, estimated_cost, actual_cost, cost_difference)
- `COGSAdjustment` (source_settlement_id, adjustment_amount, period_id, account_mapping_id, reason)

### 44.4 New Tables — Phase 2

- `PurchaseOrder`, `PurchaseRequest`, `GoodsReceipt`
- `Quotation`, `SalesOrder`, `DeliveryOrder`
- `InventoryBatchExpiry` (batch/serial tracking)
- `BankReconciliation`, `BankStatement`
- `PriceList` (date-range pricing)
- `TableManagement` (restaurant)

---

## 🔌 45. Hardware Integration

### 45.1 Barcode Scanner

- Protocol: HID (keyboard emulation)
- Input: appears as keystrokes in barcode input field
- POS screen: barcode input always autofocused
- Scale barcode detection: prefix `21XXXXXYYYYY` pattern
- No driver required — plug and play via USB or Bluetooth

### 45.2 Receipt Printer (ESC/POS)

- Protocol: ESC/POS commands over USB or network
- Formats: thermal 80mm (primary), thermal 58mm (supported)
- Connection: USB, TCP/IP (network printer), or Bluetooth
- Test print: available from Settings → Hardware
- Failure handling: post invoice first, print after, retry dialog (§17)

### 45.3 Kitchen / Bar Printer — [MVP Core for Cafés]

- Same ESC/POS protocol as receipt printer
- Separate printer instance per terminal
- Routes by `item_group.printer_assignment` (bar/kitchen/none)
- Ticket format: large text, order type label, items, modifiers, notes, timestamp
- Full KDS display screen → Phase 2

### 45.4 Cash Drawer

- Protocol: RJ11 signal sent via receipt printer
- Opens automatically after payment confirmation (cash sales)
- Opens via manual button in POS (manager permission)
- Failure: operations log entry, invoice not affected

### 45.5 Electronic Scale

- Protocol: Scale prints EAN-13 barcode with embedded weight/price
- POS detects: prefix `21` = weighted item
- Parses: PLU code (5 digits) + weight in grams (5 digits)
- Calculates: price = weight × price_per_kg from PLU database
- PLU export/import: CSV format for scale programming
- Direct scale sync: Phase 2

### 45.6 Card Terminal (External)

- **MVP:** No direct integration. Terminal is a physical device managed by the bank.
- Cashier: processes card on terminal → records "Visa/Card" in POS manually
- Reference number: optional or required per setting
- At shift close: cashier enters terminal batch total for reconciliation
- **Phase 2:** Direct terminal integration (PAX, Ingenico, Verifone)

### 45.7 Customer Display — [Phase 2]

Second screen showing customer what they're buying as items are scanned.

---

## ✅ 46. MVP Acceptance Criteria

A release is ready for production when ALL of the following are verifiable:

**POS & Shift:**
- [ ] Cashier can open a shift with expected vs actual cash shown
- [ ] Opening variance triggers manager approval when above threshold
- [ ] Cash sale posts atomically (stock, cashbox, shift, COGS, audit all updated)
- [ ] Card sale posts to card settlement account (NOT cashbox)
- [ ] Wallet sale posts to wallet account (NOT cashbox)
- [ ] Credit sale creates customer AR balance (NOT cashbox)
- [ ] Mixed payment routes each PaymentLine to correct account
- [ ] Loyalty discount reduces total due, does NOT affect cashbox
- [ ] Printer failure does not cancel invoice
- [ ] Kitchen ticket routes correctly to bar or kitchen printer
- [ ] Cashier can close shift with expected vs actual cash reconciliation
- [ ] Card reconciliation shown at shift close
- [ ] Logout does not close open shift

**Finance & Tax:**
- [ ] Tax collected shows in Tax Payable account (not in revenue)
- [ ] P&L shows Net Revenue (excluding tax)
- [ ] Tax breakdown visible on invoice and receipt
- [ ] Discount before/after tax setting changes calculation correctly
- [ ] Service charge tax applied correctly when charge_is_taxable = true

**COGS & Inventory:**
- [ ] Stock deducted atomically on each sale
- [ ] Recipe ingredients deducted from configured ingredient warehouse
- [ ] COGS calculated from weighted average cost
- [ ] Recipe COGS calculated from ingredient avg costs with wastage and unit conversion
- [ ] Damage/wastage creates inventory loss record (financial impact, not just stock)
- [ ] avg_cost recalculated on every purchase
- [ ] Sales return reverses COGS using original cost snapshot
- [ ] Purchase return uses original PI cost snapshot (if linked)
- [ ] If negative stock is disabled, sale is blocked when stock/ingredient stock is insufficient
- [ ] If negative stock is enabled, sale can post below zero only within configured scope
- [ ] Negative stock sale creates NegativeStockAlert when alert setting is enabled
- [ ] Product-level negative stock override can allow/block/require approval independently from global setting
- [ ] Later Purchase Invoice naturally offsets negative balance through StockMovement ledger
- [ ] Estimated-cost negative sales appear in Estimated Cost Sales Report
- [ ] COGS Adjustment is created after settlement when enabled and actual cost differs from estimated cost

**Purchase & Fixed Assets:**
- [ ] Purchase invoice stock line increases stock and recalculates avg_cost
- [ ] Purchase invoice fixed asset line creates FixedAsset record (no stock, no expense)
- [ ] Purchase invoice expense line debits expense account directly

**Documents & Status:**
- [ ] All 5 status fields set correctly on each document
- [ ] Cancelled invoices retain their document number
- [ ] Document numbers never reused
- [ ] idempotency_key prevents duplicate on double-submit
- [ ] Historical invoices display from posting_snapshot (not current settings)

**Reports:**
- [ ] Daily sales report matches sum of posted sales invoices
- [ ] P&L = Net Revenue − COGS − Inventory Loss − Expenses (Tax excluded)
- [ ] Customer statement shows all AR movements with correct running balance
- [ ] Shift report shows correct expected and actual cash

**Other:**
- [ ] Loyalty points created via outbox (cannot be lost)
- [ ] Subscription offline cache allows sales for configured grace period
- [ ] Data import and all 4 documentation files (PRD, FLOW, DESIGN, DOMAIN) consistent

---

## 📈 47. Success Metrics (MVP Launch)

| Metric | Target |
|--------|--------|
| POS checkout time (5 items) | < 30 seconds |
| Barcode scan → product display | < 300ms |
| Invoice posting (complete) | < 2 seconds |
| System uptime | 99.9% |
| Offline sync on reconnect | < 30 seconds |
| Trial to paid conversion | 15–20% |
| Customer support satisfaction | > 4.5/5 stars |
| Monthly churn rate | < 3% |

---

## ⚠️ 48. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Financial calculation bugs (COGS, tax, P&L) | Atomic transactions + comprehensive test suite + acceptance criteria checklist |
| Offline sync duplicates | idempotency_key on all POSTs — online and offline |
| Multi-tenant data leakage | Middleware enforces tenant_id on every query; penetration testing |
| MVP scope too large | Clear MVP Core / MVP Extended split; phased milestone rollout |
| Printer failures disrupting sales | Invoice always posts before print; retry dialog; no cancel option |
| Stock race conditions | SELECT FOR UPDATE + F() expressions on all stock updates |
| Negative stock causing misleading profit | Settings-controlled negative sale + estimated cost flag + alerts + optional COGS adjustment after purchase settlement |
| Loyalty points lost | Outbox pattern — LoyaltyOutbox inside transaction, processed by Celery |
| Fixed asset expensed accidentally | line_type validation in Posting Engine; UI warning on mismatch |
| Tax appearing as revenue | Account Mapping Layer enforces routing; Tax Payable account required setup |
| Recipe ingredient deducted from wrong warehouse | setting per branch; configurable per ingredient |
| Card payment increasing cashbox | Routing enforced in Posting Engine; card_settlement ≠ cashbox |

---

## 🚀 49. Implementation Roadmap — Six Milestones

### Milestone 1 — Foundation [Weeks 1–4]

**Deliverables:**
- Authentication + multi-tenant JWT + tenant isolation middleware
- Branch and Terminal management
- User management + granular RBAC
- Global Audit Log (state-changing events)
- Document Numbering Engine (configurable series)
- Account Mapping (basic configuration)
- Product master + Item Groups (2 levels) + Units + Conversions
- ProductUnitTierPrice per tier (basic: default tier only at this stage)
- POS Compact Mode — cash payment only
- Receipt printing (ESC/POS)
- Basic Settings Center (hardware, receipt, system)

**Quality gate:** Cashier can log in, scan items, pay cash, print receipt, and see audit log.

---

### Milestone 2 — Core POS Complete [Weeks 5–8]

**Deliverables:**
- POS Touch / Café Mode (large tiles, category nav)
- Modifiers & Sizes
- Recipes / BOM + RECIPE_CONSUME ingredient deduction
- Shift Workflow (open/close, reconciliation, opening variance)
- Cashbox + all payment methods (card manual, wallet manual, credit, partial, mixed)
- Price Tiers (full tier resolution per unit per customer)
- Loyalty hooks/placeholders only (no full earning/redemption flow in MVP Core)
- Sales Returns (both flows)
- Customer Receipts (payment collection)
- Tax Calculation Engine (inclusive/exclusive, Tax Payable separation)
- Costing Engine (avg cost, recipe COGS)
- Kitchen / Bar printer ticket routing
- Subscription enforcement (trial lock, plan limits)
- Offline PWA + idempotency_key on all POSTs

**Quality gate:** Full café POS flow works end-to-end. Shift opens and closes with correct reconciliation. Tax routes to Tax Payable.

---

### Milestone 3 — Business Cycle [Weeks 9–12]

**Deliverables:**
- Customer master + credit limit + price tier assignment
- Customer AR (CustomerARMovement ledger)
- Supplier master + AP (SupplierAPMovement ledger)
- Purchase Invoices (stock, fixed asset, expense, service line types)
- Purchase Returns (linked + unlinked)
- Supplier Payment Vouchers (with allocation)
- Fixed Asset Register (basic — create record via purchase invoice)
- Opening Balances (cashbox, bank, wallet, customers, suppliers, stock)
- Customer Advances [MVP Extended if time allows]

**Quality gate:** Full buy/sell cycle. Purchase increases stock and updates avg_cost. Fixed asset purchase routes to asset account. P&L shows correct numbers.

---

### Milestone 4 — Inventory & Treasury [Weeks 13–16]

**Deliverables:**
- Warehouse management (multiple warehouses per branch)
- Stock Levels per warehouse
- Stock Adjustments (ADJUSTMENT_IN/OUT)
- Damage / Wastage (with Inventory Loss financial impact)
- Warehouse Transfers
- Item Movement Log
- Cashbox management + opening balance
- Bank account setup
- Wallet account setup
- Cash In / Cash Out
- Cashbox Transfer
- FinancialAccountMovement ledger complete
- Expenses module
- Movement Ledger reports (item movement, cashbox movement)

**Quality gate:** Inventory is accurate across warehouses. Damage reduces profit. Cashbox balance matches manual cash count.

---

### Milestone 5 — Reports & Settings [Weeks 17–20]

**Deliverables:**
- Reports Center (all MVP Core reports)
- P&L Report (Net Revenue − COGS − Inventory Loss − Expenses)
- Customer Statement
- Supplier Statement
- Shift Report
- User Performance Report
- Settings Center complete (all 14 categories)
- Invoice & Receipt Designer (basic toggles)
- Document Numbering configuration
- Payment Method configuration
- Period Lock (basic — manager approval for old edits) [MVP Extended]
- Subscription offline cache behavior

**Quality gate:** Owner can see their daily P&L. Shift report is accurate. Settings control all key business behaviors.

---

### Milestone 6 — MVP Extended [Weeks 21–26]

**Deliverables:**
- Quick Item Edit (bulk spreadsheet)
- Product Images (S3 upload)
- Customer / Supplier Groups
- Full Loyalty & Rewards Program (earning, redemption, points history, expiry, reports, coupon codes, time-based offers)
- Tax Summary Report
- Profit by item / group / branch reports
- Fixed Asset Depreciation posting + disposal
- Stocktaking / Physical Count sessions
- Cash Denomination counting
- Cash Drop workflow
- Document Attachments (S3 upload)
- Data Import (products, customers, suppliers, opening stock)
- Data Export (all reports → Excel/PDF)
- Full Invoice Designer (template editor)
- SaaS Billing Integration
- Recipe Production Entry

**Quality gate:** Product is feature-complete for MVP Extended scope. Ready for public release.

---

## 🍽️ 50. Table Service & Open Orders — [MVP Core for Cafés]

### 50.1 Business Purpose

Table Service enables a café or restaurant to manage dine-in orders across multiple tables. A customer sits, orders over time, and pays once at the end. The order stays open on the table between kitchen sends and is only financially posted when the customer pays.

**Critical distinctions:**

| Concept | Meaning |
|---|---|
| Open Order | Operational order in progress — NOT financially posted yet |
| Sales Invoice | Financial document posted only when customer pays |
| Credit Sale | Posted invoice where customer pays later (AR increases) |
| Negative Stock Sale | Stock goes below zero due to insufficient inventory |

Open Order is none of the above until converted to a Sales Invoice at payment.

### 50.2 New Entities

**DiningSection**
A named area in the venue.
Examples: Main Hall, Terrace, VIP Room, Bar.

Fields: `id`, `tenant_id`, `branch_id`, `name`, `is_active`

**DiningTable**
A physical table within a section.

Fields: `id`, `tenant_id`, `branch_id`, `section_id`, `table_number`, `capacity`, `status`, `is_active`

Table statuses:
- `available`
- `occupied`
- `needs_bill`
- `reserved` (Phase 2)

**OpenOrder**
The live operational order on a table. One active OpenOrder per table at a time.

Fields: `id`, `tenant_id`, `branch_id`, `table_id`, `opened_by_user_id`, `cashier_user_id`, `shift_id`, `status`, `notes`, `opened_at`, `closed_at`, `idempotency_key`

OpenOrder statuses:
- `open` — order in progress, items being added
- `sent_to_kitchen` — at least one send has happened
- `needs_bill` — customer requested bill
- `paid` — converted to Sales Invoice and paid
- `cancelled` — cancelled before any payment (manager approval if items were sent)
- `voided` — draft with no sent items, cancelled without effects

**OpenOrderLine**
Each item on the open order.

Fields: `id`, `open_order_id`, `product_id`, `product_unit_id`, `modifier_selections` (JSON), `qty`, `unit_price`, `status`, `sent_at`, `kitchen_ticket_id`, `notes`

OpenOrderLine statuses:
- `draft` — added but not sent to kitchen yet
- `sent` — included in a kitchen ticket
- `preparing` — kitchen acknowledged (Phase 2 with KDS)
- `served` — delivered to table (Phase 2 with KDS)
- `cancelled` — cancelled before preparation (manager approval if was sent)
- `voided` — removed before being sent

**KitchenTicket**
A printed ticket sent to kitchen or bar printer. One ticket per Send to Kitchen action.

Fields: `id`, `tenant_id`, `open_order_id`, `table_id`, `table_number`, `ticket_number`, `printer_target` (kitchen/bar), `lines` (JSON snapshot), `printed_at`, `status`, `notes`

KitchenTicket statuses:
- `printed`
- `reprint_requested`
- `cancelled_item_appended` (when a cancel notice is added)

### 50.3 Roles and Permissions

| Role | What they can do |
|---|---|
| Cashier | Open table, add items, send to kitchen, collect payment |
| Waiter | Open table, add items, send to kitchen (cannot process payment) |
| Manager | Everything above + cancel sent items + remove prepared items from bill |

Waiter sees all tables across the branch.
Cashier sees all tables across the branch.
Manager sees all tables.

### 50.4 Stock Commit Timing

Setting: `stock_commit_timing`

| Value | Meaning |
|---|---|
| `on_kitchen_send` | Stock committed / ingredients consumed when Send to Kitchen is pressed |
| `on_payment` | Stock committed only when Sales Invoice is posted |

Default for Table Service: `on_kitchen_send`

This means:
- At Send to Kitchen: `StockMovement` or `RECIPE_CONSUME` is created
- At Payment: financial posting only — stock movements already exist, do not duplicate

### 50.5 Item Cancellation Rules

| Item Status | Who Can Cancel | Effect |
|---|---|---|
| Draft / Unsent | Cashier or Waiter | Delete freely, no approval, no audit required |
| Sent, Not Prepared | Manager only | Manager Approval + reason + Stock reversal (if `on_kitchen_send`) + Cancel notice appended to kitchen ticket + NOT added to invoice |
| Prepared or Served | Manager only | Default: bill the customer. If manager removes: Wastage or Complimentary record created. Never silently deleted. AuditLog always. |

### 50.6 Complimentary Record

When a manager removes a Prepared/Served item from the bill, the system creates a `Complimentary` record:

Fields: `id`, `tenant_id`, `open_order_id`, `open_order_line_id`, `product_id`, `qty`, `unit_price`, `reason`, `approved_by`, `created_at`

This feeds into a Complimentary Report so the owner can see what was given for free and why.

Complimentary is separate from Wastage:
- **Wastage**: product was made but spoiled, dropped, or unusable
- **Complimentary**: product was served to customer but not billed (guest relations, complaint resolution, owner gesture)

### 50.7 Payment (Convert to Sales Invoice)

When customer pays:
1. OpenOrder status → `needs_bill` (optional step, can go straight to pay)
2. Cashier presses Pay
3. System shows all billed lines (excludes cancelled/voided lines)
4. Payment panel appears (same as normal POS payment)
5. On payment confirmation → Posting Engine runs:
   - Sales Invoice created and posted
   - Financial movements: revenue, tax, payment routing
   - If `stock_commit_timing = on_kitchen_send`: no duplicate stock movements
   - If `stock_commit_timing = on_payment`: stock movements created now
   - ShiftMovementSummary updated
   - OpenOrder.status → `paid`
   - DiningTable.status → `available`
6. Receipt printed

### 50.8 Subsequent Kitchen Sends

When customer adds more items after first kitchen send:
- New items are added as `draft` lines to the existing OpenOrder
- Only `draft` lines are included in the next Send to Kitchen action
- New KitchenTicket is created for the new lines only
- Already-sent lines are not re-sent

### 50.9 MVP Core Scope

**Included in MVP Core:**
- DiningSection and DiningTable setup
- Table Grid screen in POS Touch mode
- OpenOrder lifecycle (open → send → bill → pay)
- Multiple sequential kitchen sends per order
- KitchenTicket printing (ESC/POS)
- Item cancellation rules (draft/sent/prepared/served)
- Complimentary record
- Waiter role (add items, send to kitchen)
- Manager cancellation with approval
- Single order per table
- Full order billed to table (no split)

**Phase 2:**
- Split bill
- Table transfer
- Order transfer between waiters
- Kitchen Display System (KDS)
- Reservation management
- Floor plan drag-and-drop
- Table merging
- Advanced coursing / firing

### 50.10 New Database Tables

**MVP Core:**
- `DiningSection`
- `DiningTable`
- `OpenOrder`
- `OpenOrderLine`
- `KitchenTicket`
- `Complimentary`

**New Settings:**
- `table_service_enabled` (toggle)
- `stock_commit_timing` (on_kitchen_send / on_payment)
- `require_manager_approval_for_sent_item_cancel` (toggle, default true)
- `default_dining_section_id`

**New Permissions:**
- `table.open`
- `table.view_all`
- `order.add_items`
- `order.send_to_kitchen`
- `order.cancel_draft_item`
- `order.cancel_sent_item` (manager only)
- `order.remove_prepared_from_bill` (manager only)
- `order.collect_payment`

### 50.11 Acceptance Criteria

- [ ] Cashier/Waiter can open a table and add items freely
- [ ] Send to Kitchen creates KitchenTicket and prints to correct printer
- [ ] Only draft/unsent items are sent in each kitchen ticket
- [ ] Already-sent items are not re-sent on subsequent Send to Kitchen actions
- [ ] Draft items can be deleted freely with no approval
- [ ] Sent but not prepared items require manager approval to cancel
- [ ] Cancelled sent items are not added to the final invoice
- [ ] Stock committed at kitchen send is reversed on item cancellation (if `on_kitchen_send`)
- [ ] Prepared/served items appear on bill by default
- [ ] Manager removing prepared item from bill creates Complimentary record
- [ ] Payment converts OpenOrder to Sales Invoice with full financial posting
- [ ] No duplicate stock movements when `stock_commit_timing = on_kitchen_send`
- [ ] Table status updates correctly at each stage
- [ ] All cancellations write AuditLog with reason and approver
- [ ] Waiter cannot process payment (permission-controlled)
- [ ] Manager can see all tables and their full order details

---

## 📁 51. Supporting Documentation

| File | Purpose | Status |
|------|---------|--------|
| **PRD.md** | This document — product requirements | ✅ v3.6 — Draft Pending Final Review |
| **FLOW.md** | Business logic workflows and state machines | Pending Generation |
| **DESIGN.md** | UI/UX design system and screen specifications | Pending Generation |
| **DOMAIN.md** | Business domain rules per vertical | Pending Generation |
| **SuperPOS.html** | Existing UI prototype (baseline, preserved) | ✅ Baseline |

All four documentation files must remain synchronized. Any change to business rules in PRD.md must be reflected in FLOW.md (workflows), DESIGN.md (UI behavior), and DOMAIN.md (domain rules).

---

*SuperPOS ERP Lite — PRD v3.6*  
*Last Updated: June 2026*  
*Status: Draft — Pending Final Review*  
*Next: FLOW.md generation after PRD final approval*