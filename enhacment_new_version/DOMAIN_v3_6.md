# 🎯 SuperPOS ERP Lite — Domain Knowledge (DOMAIN.md)

**Version:** 3.6  
**Last Updated:** June 2026  
**Status:** Draft — Pending Final Review  
**Scope:** Core domain rules, vertical-specific business rules, invariants, and terminology  
**Based on:** `PRD.md v3.6 with Negative Stock` + `FLOW.md v3.6 with Negative Stock`  
**Prototype Baseline:** `SuperPOS.html`

---

## 📖 How to Read This Document

This document defines the **business domain knowledge** behind SuperPOS ERP Lite.

It does **not** replace:

- `PRD.md` — what the product must include.
- `FLOW.md` — how each workflow moves step by step.
- `DESIGN.md` — how the user interface looks and behaves.

Instead, `DOMAIN.md` explains the rules that must stay true across all modules, workflows, reports, and future verticals.

### Phase Labels

| Label | Meaning |
|---|---|
| **[MVP Core]** | Must ship in the first live-usable release. |
| **[MVP Extended]** | Ships shortly after MVP Core; planned but not blocking first launch. |
| **[Phase 2]** | Next major release cycle. |
| **[Future]** | Long-term roadmap, not currently scoped. |

### Core Domain Principle

SuperPOS ERP Lite is **not a full accounting ERP**, but it must behave like a reliable business operating system:

```text
Sales → Payments → Stock Movements → Costing → Treasury → Reports
Purchases → Stock / Expenses / Assets → Supplier Balances → Reports
Shifts → Cash/Card/Wallet Reconciliation → Audit Trail
```

The system must remain simple enough for a café/shop owner, but accurate enough that financial, stock, and operational reports are trustworthy.

---

# 1. Domain Architecture Overview

## 1.1 Domain Layers

SuperPOS ERP Lite has four main domain layers:

```text
1. SaaS Platform Domain
   Tenants, subscriptions, plans, limits, billing, suspension.

2. Core ERP/POS Domain
   Sales, purchases, products, inventory, treasury, customers, suppliers,
   shifts, reports, settings, posting engine, movement ledgers.

3. Vertical Domains
   Café, Retail, Supermarket, Restaurant, Pharmacy, Gym.

4. Cross-Cutting Domain Services
   Audit, access log, operations log, permissions, document numbering,
   idempotency, offline sync, settings snapshot, account mapping.
```

## 1.2 Domain Extension Rule

Vertical domains **extend** the core domain. They must not break core posting rules.

Example:

```text
Café sale = normal sales invoice
+ order type
+ modifiers
+ kitchen/bar ticket
+ recipe ingredient consumption
```

The sale is still posted through the same Posting Engine and movement ledger architecture.

## 1.3 Source of Truth Rule

The system must not rely on UI state for reporting.

Reports read from:

```text
StockMovement
FinancialAccountMovement
CustomerARMovement
SupplierAPMovement
ShiftMovementSummary
LoyaltyTransaction
FixedAssetLedger
AuditLog / AccessLog / OperationsLog
```

Documents are business records. Movement ledgers are the historical evidence of business impact.

---

# 2. SaaS Platform Domain

## 2.1 Tenant Rule

Every business using SuperPOS is a **Tenant**.

A tenant owns:

- branches
- terminals
- users
- products
- customers
- suppliers
- cashboxes
- warehouses
- financial accounts
- documents
- settings
- reports

Every tenant-scoped table must include `tenant_id`.

## 2.2 Tenant Isolation Rule

A user from Tenant A must never see, modify, export, or infer data from Tenant B.

Enforcement must happen at:

```text
API layer
Query layer
Permissions layer
File storage path
Exports
Background jobs
```

## 2.3 Subscription Status Rule

Tenant usage is controlled by subscription status.

| Status | Behavior |
|---|---|
| Trial Active | Full allowed access within plan limits. |
| Grace Period | Sales allowed, warnings shown. |
| Expired | Cashiers blocked from new sales; owner/admin can access billing/settings/history. |
| Suspended | Full app block except owner billing/reactivation access. |
| Active Paid | Normal usage. |

## 2.4 Offline Subscription Rule

When offline, POS uses the last cached subscription status.

```text
Offline + valid cache within TTL → allow sales.
Offline + expired/suspended cache → block new sales.
On reconnect → revalidate immediately.
```

Offline sales created during a valid grace/cache window are synced normally.

## 2.5 Plan Limit Rule

Plan limits apply when creating new resources.

Examples:

```text
Starter allows 1 branch.
If tenant already has 1 branch → block creating branch #2 and show upgrade message.
Existing data must never be deleted automatically after downgrade.
```

## 2.6 Super Admin Separation Rule

SaaS Platform Admin is separate from tenant application.

A tenant cashier/manager must never see Super Admin features.

---

# 3. Users, Roles, Permissions, and Approvals

## 3.1 Role Rule

Roles describe common business responsibilities.

Default roles:

| Role | Domain Meaning |
|---|---|
| Owner | Full business control, subscription/billing, final authority. |
| Admin | Operational admin with most permissions except platform billing ownership. |
| Manager | Handles approvals, shifts, returns, adjustments, reports. |
| Cashier | Sells, takes payments, opens/closes own shift. |
| Inventory Clerk | Handles stock, purchases, transfers, stocktaking. |
| Accountant / Finance User | Treasury, suppliers, customers, reports, tax, assets. |
| Waiter [Phase 2] | Restaurant/table order capture. |

## 3.2 Permission Rule

Permissions are the true enforcement mechanism. Role is only a shortcut/group.

Every sensitive or state-changing action must check permission at API level.

UI hiding is not enough.

## 3.3 Manager Approval Rule

Manager approval is required when an action exceeds normal user authority.

Common triggers:

- discount above allowed limit
- negative stock override
- selling below cost
- credit limit override
- shift variance over threshold
- unlinked purchase return
- return without original invoice
- posted document cancellation
- stock adjustment if setting requires
- stocktaking variance approval
- asset write-off
- cash drop above threshold
- period lock override
- manual loyalty points adjustment

## 3.4 Approval Audit Rule

Every approval must store:

```text
approval_user_id
approval_time
reason
affected action
old values / new values where relevant
```

Approval must be recorded in AuditLog.

---

# 4. Branch, Terminal, Cashbox, and Warehouse Domain

## 4.1 Branch Rule

A branch is a physical or operational location.

A branch can have:

- terminals
- cashboxes
- warehouses
- users assigned to it
- default ingredient warehouse
- local settings overrides [Phase 2]

## 4.2 Terminal Rule

A terminal represents a POS device.

A terminal may be linked to:

- branch
- cashbox
- receipt printer
- kitchen/bar printer routes
- hardware profile

## 4.3 Cashbox Rule

A cashbox is a financial account representing a cash drawer or safe.

Types:

| Cashbox Type | Meaning |
|---|---|
| Cash Drawer | Used by cashier during active shift. |
| Main Safe | Used by owner/manager/accountant for stored cash. |
| Petty Cash [MVP Extended] | Small operational cash account. |

## 4.4 Warehouse Rule

A warehouse represents a stock location.

Types:

- selling floor
- bar
- kitchen
- storage
- branch default warehouse
- ingredient warehouse

Sales and recipes must know which warehouse is affected.

## 4.5 Cash Drawer vs Main Safe Rule

A cash drawer is linked to shift operations.

A main safe is not directly used for cashier sales.

Cash Drop moves money from drawer to safe. It is **not an expense** and has no P&L impact.

---

# 5. Document Domain Rules

## 5.1 Document Definition

A document is a business record such as:

- Sales Invoice
- Sales Return
- Customer Receipt
- Purchase Invoice
- Purchase Return
- Supplier Payment Voucher
- Expense Entry
- Cash In / Cash Out
- Warehouse Transfer
- Stock Adjustment
- Damage/Wastage
- Shift Open/Close
- Fixed Asset event
- Stocktaking session

## 5.2 Five-Status Model

Each business document uses five independent status fields:

| Field | Values |
|---|---|
| `posting_status` | Draft / Posted / Cancelled / Void |
| `payment_status` | Unpaid / Partially Paid / Paid / N/A |
| `return_status` | Not Returned / Partially Returned / Returned |
| `approval_status` | Not Required / Pending / Approved / Rejected |
| `sync_status` | Synced / Pending Sync / Sync Failed |

A document can be `Posted`, `Partially Paid`, `Partially Returned`, and `Synced` at the same time.

## 5.3 Document Immutability Rule

Posted documents are read-only for business fields.

Corrections are done by:

```text
Cancel + recreate
or
Return / reversal / adjustment document
```

## 5.4 Document Numbering Rule

Document numbers are assigned when posting, not necessarily at draft creation.

Rules:

- posted number is immutable
- cancelled document keeps its number
- numbers are never reused
- gaps are acceptable
- reuse is forbidden

## 5.5 Cancellation Rule

Cancellation reverses all effects atomically.

A cancelled document is not deleted. It stays visible for audit and historical reports.

## 5.6 Void Rule

Void is for draft/invalid documents with no posted business effect.

Void does not create financial or stock reversals.

---

# 6. Posting Engine Domain Contract

## 6.1 Posting Meaning

Posting means confirming a document and creating all its business effects.

A posted sales invoice must create:

```text
invoice record
stock movements
financial movements
customer AR if credit
shift totals
COGS
Tax Payable
posting snapshot
audit log
```

## 6.2 Atomicity Rule

All effects of a posted document must happen in one transaction.

If any effect fails, everything rolls back.

No partial posting is allowed.

## 6.3 Idempotency Rule

Every state-changing POST must include `idempotency_key`.

Duplicate key returns existing result without reprocessing.

This applies to both:

```text
online submit
offline sync retry
```

## 6.4 Settings Snapshot Rule

At posting time, the document stores the relevant settings and values used.

This includes:

- tax mode/rates
- discount rules
- price tier used
- product unit price
- avg cost snapshots
- rounding settings
- invoice template version
- branch / terminal / user / shift
- tenant plan at posting

Historical documents must never be recalculated using current settings.

## 6.5 Outbox Rule

Post-commit side effects such as loyalty points must use outbox pattern.

The pending outbox record is created inside the posting transaction, then processed after commit.

This prevents lost side effects.

---

# 7. Movement Ledger Domain Rules

## 7.1 Ledger Principle

Every posted document creates movement records.

Reports read from ledgers, not UI-only fields.

## 7.2 StockMovement Rule

StockMovement tracks all stock quantity changes.

Movement types:

```text
OPENING_BALANCE
PURCHASE_IN
SALE_OUT
SALES_RETURN_IN
PURCHASE_RETURN_OUT
TRANSFER_IN
TRANSFER_OUT
ADJUSTMENT_IN
ADJUSTMENT_OUT
DAMAGE_OUT
RECIPE_CONSUME
PRODUCTION_IN [MVP Extended]
```

## 7.3 FinancialAccountMovement Rule

FinancialAccountMovement tracks money/account movements.

Used for:

- cashbox
- bank account
- card settlement
- wallet account
- revenue
- tax payable
- inventory value
- COGS
- expenses
- inventory loss
- fixed asset
- depreciation expense
- rounding adjustment

## 7.4 CustomerARMovement Rule

CustomerARMovement is the detailed source of truth for customer balances.

Used for:

- opening balance
- credit sales
- partial remaining balances
- receipts
- sales returns on credit
- customer advances
- overpayments
- allocations

## 7.5 SupplierAPMovement Rule

SupplierAPMovement is the detailed source of truth for supplier balances.

Used for:

- opening balance
- credit purchases
- supplier payments
- purchase returns
- supplier advances / prepaid balances
- overpayments
- allocations

## 7.6 ShiftMovementSummary Rule

ShiftMovementSummary tracks shift totals.

It must separate:

```text
cash_sales_total
customer_cash_receipts_total
card_sales_total
wallet_sales_total
credit_sales_total
cash_returns_total
card_returns_total
expense_total
wastage_total
cash_in_total
cash_out_total
cash_drop_total
loyalty_discount_total
```

Customer receipts are **not** sales. They are cash collected against existing AR.

Damage/wastage is **not** a cash expense. It goes to `wastage_total`.

## 7.7 LoyaltyTransaction Rule

Loyalty transactions are MVP Extended.

Types:

```text
EARN
REDEEM
REVERSE_EARN
REVERSE_REDEEM
MANUAL_ADJUST
EXPIRE
```

## 7.8 FixedAssetLedger Rule

FixedAssetLedger tracks asset lifecycle events:

```text
ASSET_PURCHASE
DEPRECIATION
TRANSFER
MAINTENANCE
DISPOSAL
WRITE_OFF
ASSET_SALE
```

## 7.9 AR/AP Double Counting Rule

CustomerARMovement and SupplierAPMovement are detailed ledgers.

If Account Mapping includes AR/AP accounts, those are control/summary accounts only.

Reports must not count the same AR/AP amount twice.

---

# 8. Account Mapping Domain Rules

## 8.1 ERP Lite Accounting Rule

SuperPOS ERP Lite does not implement a full double-entry general ledger in MVP.

However, every financial effect must route to a named account for correct reporting.

## 8.2 Account Categories

### Assets

- Cashbox
- Bank Account
- Card Settlement Account
- Wallet Account
- Inventory
- Accounts Receivable
- Fixed Assets
- Accumulated Depreciation

### Liabilities

- Accounts Payable
- Tax Payable / VAT Liability
- Loyalty Points Liability [MVP Extended]

### Income

- Sales Revenue
- Service Charge Revenue
- Delivery Fee Revenue
- Other Income

### Cost / Expense

- COGS
- Recipe COGS
- Operating Expenses
- Depreciation Expense
- Inventory Loss / Wastage
- Loss on Asset Disposal
- Card Fees / Commission [Phase 2]

### Contra / Adjustment

- Sales Discounts
- Sales Returns
- Loyalty Discount / Reward Redemption
- Rounding Adjustment

## 8.3 Routing Rules

| Business Effect | Routes To |
|---|---|
| Net sales revenue | Sales Revenue account |
| Tax collected | Tax Payable / VAT Liability |
| Cash received | Cashbox |
| Card/Visa payment | Card Settlement Account |
| Wallet payment | Wallet Account |
| Credit sale | CustomerARMovement |
| Credit purchase | SupplierAPMovement |
| Fixed asset purchase | Fixed Asset account |
| Depreciation | Depreciation Expense + Accumulated Depreciation |
| Damage/Wastage | Inventory Loss + Inventory Value decrease |
| Loyalty redemption | Loyalty Discount / Reward Redemption |
| Rounding difference | Rounding Adjustment account |

## 8.4 Non-Configurable Business Logic Rule

Admins can configure which account receives each effect.

They cannot change fundamental routing logic.

Example:

```text
Card payment must never route to Cashbox.
Tax must never route to Revenue.
Fixed asset purchase must never route to Expense at purchase time.
```

---

# 9. Product, Item, Unit, and Pricing Domain

## 9.1 Product / Item Types

| Type | Meaning | Stock | COGS | POS |
|---|---|---|---|---|
| Stock Item | Normal sellable inventory item | Yes | Avg cost | Yes |
| Recipe Product | Café item that consumes ingredients | No own stock | Recipe cost | Yes |
| Ingredient Item | Raw material consumed in recipes | Yes | Avg cost | Optional |
| Service / Non-Stock | Service or non-stock charge | No | No COGS unless configured | Yes |
| Bundle / Combo [MVP Extended] | Group of items sold together | Per component | Per component | Yes |
| Fixed Asset (purchase only) | Equipment/furniture/assets | No | No | No |

## 9.2 ProductUnit Rule

A product can have multiple units and barcodes.

Example:

```text
Water Bottle
- single bottle barcode
- carton barcode
```

`ProductUnit` stores:

```text
product_id
unit_id
barcode
sku
conversion_factor
default_purchase_price
last_purchase_price
default_sale_price
is_default_sale
is_default_purchase
is_active
```

## 9.3 ProductUnitTierPrice Rule

Price tiers are per product unit, not per product.

`ProductUnitTierPrice` stores sale price only:

```text
tenant_id
product_unit_id
price_tier_id
sale_price
is_active
```

Purchase prices must not be stored in ProductUnitTierPrice.

Supplier-specific purchase prices can be introduced later as `SupplierProductPrice` [MVP Extended / Phase 2].

## 9.4 Price Tier Rule

Price Tier is a base sale price list, not a discount.

Examples:

- Default
- VIP
- Wholesale
- Staff

When customer is selected, POS resolves sale price by customer price tier.

## 9.5 Price Resolution Rule

Resolution chain:

```text
Customer price tier + ProductUnitTierPrice
→ default tier price
→ ProductUnit.default_sale_price
```

If customer changes during cart, prices are recalculated and cashier is notified.

## 9.6 Service / Non-Stock Item Rule

Service/non-stock items:

- can be sold in POS
- create revenue
- can have tax and discount
- do not create StockMovement
- do not create COGS unless explicitly configured

Examples:

- delivery service
- packaging fee as item
- consulting/service labor

---

# 10. Sales Domain Rules

## 10.1 Sales Invoice Rule

A Sales Invoice represents confirmed sale of products/services.

Sales Invoice can originate from:

- POS compact mode
- POS touch/café mode
- manual sales screen [Phase 2 advanced]

## 10.2 Customer Requirement Rule

Customer is optional by default.

Customer becomes required when:

- credit sale
- loyalty earn/redeem
- delivery order if setting requires
- customer-specific tax/invoice data required
- customer-specific price tier is needed

## 10.3 Walk-in / Anonymous Rule

Walk-in/anonymous sales are valid.

For anonymous sales:

- no customer AR
- no loyalty points
- default price tier applies
- reports show customer as Walk-in / Anonymous

## 10.4 Sales Return Rule

Sales return should preferably link to original invoice.

Linked return uses original snapshots:

- price snapshot
- tax snapshot
- cost snapshot
- payment lines

Unlinked return requires setting and manager approval.

## 10.5 Card Refund Rule

Card refunds in MVP are manual.

The cashier must process refund on external terminal and record:

- refund reference
- terminal reversal reference
- refund status
- batch reference if available

Card refund affects Card Settlement, not Cashbox.

## 10.6 Mixed Payment Rule

Each payment method creates its own effect.

Example:

```text
Invoice total = 300
Cash = 100 → Cashbox
Card = 150 → Card Settlement
Credit = 50 → CustomerARMovement
```

---

# 11. Purchase Domain Rules

## 11.1 Purchase Invoice Rule

A Purchase Invoice can contain different line types in the same document.

Line types:

| Line Type | Domain Effect |
|---|---|
| Stock Item | PURCHASE_IN + avg cost update |
| Expense | Expense immediately |
| Fixed Asset | FixedAsset created; no immediate expense |
| Service | Service expense; no stock |
| Non-stock purchase | Expense/service treatment |

## 11.2 Purchase Return Rule

Purchase return should link to original Purchase Invoice.

If linked:

```text
Use original purchase cost snapshot.
```

If unlinked:

```text
Use current average cost only if setting allows.
Manager approval required.
```

## 11.3 Supplier Credit Rule

Credit purchase increases supplier payable.

SupplierAPMovement is the detailed source of truth.

## 11.4 Supplier Advance Rule

Supplier advance means business paid supplier before invoice exists.

It creates a prepaid supplier balance / supplier credit.

It reduces cashbox or bank now, then is allocated against future purchase invoices.

It must not be confused with normal AP owed to supplier.

---

# 12. Customer and Supplier Balance Domain

## 12.1 Customer AR Rule

Customer balance is calculated from CustomerARMovement.

Positive customer balance means customer owes the business.

## 12.2 Supplier AP Rule

Supplier balance is calculated from SupplierAPMovement.

Positive supplier payable means the business owes the supplier.

## 12.3 Receipt Allocation Rule

Customer receipt allocation can be:

- FIFO oldest unpaid invoice first
- manual invoice selection
- partial allocation
- unallocated credit if overpaid

## 12.4 Supplier Payment Allocation Rule

Supplier payment allocation can be:

- FIFO oldest unpaid purchase invoice first
- manual purchase invoice selection
- partial allocation
- supplier advance/prepaid balance if overpaid

## 12.5 Overpayment Rule

Customer overpayment becomes customer credit.

Supplier overpayment becomes supplier advance/prepaid balance.

Reversal cannot exceed available unallocated balance.

---

# 13. Treasury and Payment Domain

## 13.1 Payment Method Types

| Method | Domain Account |
|---|---|
| Cash | Cashbox |
| Card / Visa | Card Settlement Account |
| Wallet | Wallet Account |
| Bank | Bank Account |
| Credit | CustomerARMovement / SupplierAPMovement |
| Loyalty Discount | Loyalty Discount account; not payment money |

## 13.2 Card Settlement Rule

Card/Visa payments do not go to cashbox and do not directly go to bank in MVP.

They go to Card Settlement Account until reconciled with terminal/bank settlement.

Direct terminal integration is Phase 2.

## 13.3 Wallet Rule

Wallet payments go to Wallet Account, not Cashbox.

Wallet settlement to bank is a separate action [Phase 2].

## 13.4 Cash In / Cash Out Rule

Cash In and Cash Out affect Cashbox and ShiftMovementSummary.

They require reason and AuditLog.

## 13.5 Cash Drop Rule

Cash Drop is internal transfer from drawer to main safe.

It affects:

```text
Cash Drawer ↓
Main Safe ↑
ShiftMovementSummary.cash_drop_total ↑
```

It does not affect P&L.

## 13.6 Shift Close Cash Formula

```text
Expected Drawer Cash =
opening_cash_actual
+ cash_sales_total
+ customer_cash_receipts_total
+ cash_in_total
- cash_returns_total
- cash_out_total
- expense_total
- cash_drop_total
```

Damage/wastage is not subtracted from cash because it is not cash leaving drawer.

## 13.7 Denomination Counting Rule [MVP Extended]

Cash can be counted by denominations at open/close.

The system calculates total from counts.

Variance compares expected cash against counted cash.

---

# 14. Shift Domain Rules

## 14.1 Shift Is a Workflow Rule

Shift is not a cashier sidebar module.

It is accessed from POS/header profile dropdown.

## 14.2 Active Shift Requirement Rule

If `require_shift_before_selling = true`, POS is blocked until a shift is open.

## 14.3 Opening Cash Rule

Expected opening cash comes from last shift's actual closing cash for the same cashbox.

Cashier enters actual cash.

Variance beyond threshold requires manager approval.

## 14.4 Shift Remains Open on Logout Rule

Logout or session expiry does not close shift automatically.

Manager can force-close orphaned shift with reason and AuditLog.

## 14.5 Shift Report Rule

Shift report must show:

- opening expected/actual/variance
- sales by payment method
- customer cash receipts separately from sales
- returns
- expenses
- wastage
- cash in/out
- cash drops
- expected/actual closing cash
- card expected vs terminal batch
- wallet expected vs settlement
- approvals and notes

---

# 15. Inventory and Warehouse Domain

## 15.1 Inventory Source Rule

Stock quantity is derived from StockMovement ledger.

Product cached quantities can exist for performance but must reconcile with movements.

## 15.2 Negative Stock Control Rule [MVP Core]

Negative stock means the business is allowed to sell or consume an item even when the system stock balance is not enough.

This is **not** the same as credit sale.

```text
Credit Sale = customer pays later; AR increases.
Negative Stock Sale = stock balance goes below zero; inventory is owed internally.
```

Default behavior: **block negative stock**.

The behavior is fully settings-controlled under:

```text
Settings → Inventory & Warehouse Settings → Negative Stock Control
```

Core settings:

| Setting | Type | Domain Meaning | Phase |
|---|---|---|---|
| `allow_negative_stock_sale` | Toggle | Allows posting sales/recipe consumption when stock is insufficient. | MVP Core |
| `require_manager_approval_for_negative_stock` | Toggle | Requires manager approval before posting a sale that will create negative stock. | MVP Core |
| `negative_stock_scope` | Dropdown | Controls whether negative stock is allowed for all items, selected items only, ingredients only, or products + ingredients. | MVP Core |
| `show_negative_stock_warning_to_cashier` | Toggle | Shows warning before posting. | MVP Core |
| `create_negative_stock_alert` | Toggle | Creates manager alert when negative stock occurs. | MVP Core |
| `negative_stock_costing_method` | Dropdown | Defines costing method when cost is estimated. | MVP Core |
| `auto_settle_negative_stock_on_purchase` | Toggle | Later purchases automatically cover negative balances by quantity. | MVP Core for quantity balance; settlement record is MVP Extended |
| `create_cogs_adjustment_after_negative_stock_settlement` | Toggle | Creates a COGS adjustment when actual purchase cost differs from estimated sale cost. | MVP Extended |
| `block_negative_stock_for_batch_expiry_serial_items` | Toggle | Blocks negative stock for batch/expiry/serial controlled items. | Phase 2 |
| `show_negative_stock_in_manager_dashboard` | Toggle | Shows negative stock alerts to managers. | MVP Core |

Scope values:

```text
all_products
selected_products_only
ingredients_only
products_and_ingredients
```

Costing method values:

```text
last_known_average_cost          ← recommended default
default_purchase_price
zero_cost_require_later_adjustment
```

## 15.2A Negative Stock Product Override Rule [MVP Core]

Tenant-level settings define default behavior, but individual products/product units may override the behavior.

Examples:

```text
Milk ingredient → allow negative with manager approval.
Coffee beans → allow negative with warning.
Ready bottled drinks → block negative stock.
Serial-controlled devices → always block.
```

Product-level fields:

```text
allow_negative_stock_override
negative_stock_allowed
negative_stock_requires_approval
negative_stock_max_qty
negative_stock_costing_method_override
```

Product override must never bypass batch/expiry/serial blocking rules in Phase 2.

## 15.2B Negative Stock Posting Rule [MVP Core]

When a posted document will reduce stock below zero:

```text
If allow_negative_stock_sale = false:
  Block posting.
  Show insufficient stock message.

If allow_negative_stock_sale = true:
  Check scope and product override.
  If not allowed for this item → block.
  If approval required → Manager Approval Flow.
  If approved or no approval required → post normally.
```

For normal stock items:

```text
StockMovement: SALE_OUT
Stock balance may become negative.
NegativeStockAlert may be created.
```

For recipe products:

```text
StockMovement: RECIPE_CONSUME per ingredient.
Ingredient balance may become negative.
NegativeStockAlert may be created per insufficient ingredient.
```

If one ingredient is blocked, the entire sale must be blocked. Partial recipe posting is not allowed.

## 15.2C Negative Stock Alert Rule [MVP Core]

When negative stock is created and alerts are enabled, the system creates a NegativeStockAlert.

Minimum fields:

```text
tenant_id
branch_id
warehouse_id
product_id
product_unit_id
source_document_type
source_document_id
source_movement_id
negative_qty_created
balance_after
cost_status
created_by
created_at
status: open / settled / ignored
```

Alerts appear in:

- Manager Dashboard
- Inventory Alerts
- Item Movement Report
- Negative Stock Alert Report

## 15.2D Negative Stock Settlement on Purchase Rule [MVP Core + MVP Extended]

A later purchase naturally increases stock and therefore offsets the negative balance by quantity.

Example:

```text
Milk balance before purchase = -5 liters
Purchase Invoice received = +20 liters
Final stock balance = +15 liters
```

This quantity offset is a core inventory behavior because StockMovement balance is cumulative.

If `auto_settle_negative_stock_on_purchase = true`, the system should also identify which old negative movements were covered by the new purchase.

Formal `NegativeStockSettlement` records are MVP Extended.

Minimum settlement fields:

```text
tenant_id
product_id
product_unit_id
warehouse_id
purchase_invoice_id
purchase_movement_id
covered_negative_movement_id
covered_qty
estimated_cost_at_sale
actual_purchase_cost
cost_difference
cogs_adjustment_id
created_at
```

Settlement order:

```text
Oldest negative stock movement first (FIFO by movement date).
Only settle movements for the same product_unit and warehouse.
Do not settle across tenants.
Cross-warehouse settlement requires explicit transfer or setting [Phase 2].
```

## 15.2E Negative Stock Costing Rule [MVP Core + MVP Extended]

When stock is negative, the true cost may be unknown or incomplete at the moment of sale.

The system uses `negative_stock_costing_method`:

| Method | Meaning |
|---|---|
| `last_known_average_cost` | Use last known avg cost and mark cost as estimated if stock was insufficient. |
| `default_purchase_price` | Use ProductUnit.default_purchase_price. |
| `zero_cost_require_later_adjustment` | Store zero temporary cost and require later COGS adjustment. |

Sale line or recipe ingredient consumption should store:

```text
cost_status = actual / estimated / pending_adjustment
estimated_cost_source
estimated_unit_cost
```

Recommended MVP default:

```text
negative_stock_costing_method = last_known_average_cost
```

## 15.2F COGS Adjustment After Settlement Rule [MVP Extended]

If a negative stock sale used estimated cost, and a later purchase provides actual cost, the system may create a COGS Adjustment.

Example:

```text
Sold using estimated milk cost = 10 EGP/liter
Later purchase actual cost = 12 EGP/liter
Covered negative qty = 5 liters
COGS Adjustment = (12 - 10) × 5 = +10 EGP
```

Rules:

```text
Do not edit the original posted sale.
Do not change the original invoice snapshot.
Create a separate COGS Adjustment movement.
If the original period is locked, post the adjustment in the current open period.
AuditLog must record adjustment reason and source settlement.
```

The adjustment affects profit reporting, not customer balance and not cashbox.

## 15.3 Warehouse Transfer Rule

Transfer creates two movements:

```text
TRANSFER_OUT from source
TRANSFER_IN to destination
```

No P&L impact.

## 15.4 Stock Adjustment Rule

Stock adjustment must have reason.

Manager approval depends on settings/thresholds.

## 15.5 Opening Stock Rule

Opening stock creates OPENING_BALANCE movement and sets initial average cost.

After period lock, changing opening stock requires approval.

## 15.6 Stocktaking Rule [MVP Extended]

Stocktaking freezes expected quantity at session creation time.

Only approved variances create stock adjustments.

Posted count sessions are immutable.

---

# 16. Recipe / BOM Domain

## 16.1 Recipe Product Rule

Recipe Product is sold in POS but usually does not hold own stock.

It consumes ingredients when sold.

## 16.2 Ingredient Consumption Rule

Selling a recipe product creates `RECIPE_CONSUME` per ingredient.

Each ingredient consumption uses:

```text
recipe quantity
wastage factor
unit conversion
ingredient avg cost
ingredient warehouse source
```

## 16.3 Ingredient Warehouse Source Rule

Controlled by setting:

```text
branch_default
item_specific
pos_selected
recipe_specific [Phase 2]
```

## 16.4 Recipe COGS Rule

Recipe COGS is sum of ingredient costs at posting time.

It is stored as immutable snapshot on sale line.

## 16.5 Modifier Rule

Modifiers can change price and kitchen ticket text.

If modifier consumes stock (e.g., extra shot), it must either:

- be part of recipe adjustment, or
- create its own ingredient consumption [MVP Extended]

---

# 17. Costing and COGS Domain

## 17.1 Costing Method Rule

MVP uses Weighted Average Cost.

FIFO is Phase 2.

## 17.2 Cost Snapshot Rule

Sale line stores average cost at posting time.

Historical COGS must not change after later purchases.

Exception: when a sale was posted under negative stock with estimated cost, the original sale remains immutable, but a separate COGS Adjustment may be posted later after negative stock settlement.

## 17.2A Estimated Cost Under Negative Stock Rule [MVP Core]

When negative stock is allowed, the system may need to calculate cost before actual stock is available.

The system must mark the cost clearly:

```text
cost_status = estimated
```

Estimated cost is allowed only to keep operations running. It must not be hidden from reports.

Reports should be able to show:

- sales with estimated cost
- items that need cost review
- negative stock settlements waiting for adjustment

## 17.3 Sales Return Cost Rule

Sales return reverses COGS using original sale cost snapshot.

## 17.4 Purchase Return Cost Rule

Linked purchase return uses original purchase cost snapshot.

Unlinked purchase return uses current average cost only if setting allows and approval is granted.

## 17.5 Damage/Wastage Cost Rule

Damage/wastage value:

```text
avg_cost_at_posting × damaged_qty
```

It is Inventory Loss, not cash expense.

## 17.6 Gross Profit Rule

```text
Gross Profit = Net Revenue - COGS - Inventory Loss
```

Tax is excluded from revenue.

---

# 18. Tax Domain Rules

## 18.1 Tax Payable Rule

Tax collected from customer is liability, not revenue.

## 18.2 Revenue Rule

Revenue is net sales excluding tax and after discounts.

## 18.3 Tax Inclusive/Exclusive Rule

Tenant can choose tax mode:

- tax exclusive
- tax inclusive

Historical invoices use snapshot.

## 18.4 Discount and Tax Rule

Discount interaction with tax is setting-controlled.

Default: discount before tax.

## 18.5 Tax Return Rule

Tax on return uses original invoice tax snapshot.

## 18.6 Tax Report Rule

Tax Summary Report is separate from P&L.

---

# 19. Rounding and Precision Domain

## 19.1 Decimal Rule

All money and quantities must use Decimal, never float.

## 19.2 Money Precision Rule

Default money precision: 2 decimals.

Configurable per tenant/currency.

## 19.3 Quantity Precision Rule

Stock quantities may need 3 decimals.

Recipe quantities may need 4 decimals.

## 19.4 Rounding Adjustment Rule

Invoice rounding is stored separately as `rounding_amount`.

Rounding affects total due but must not silently change revenue.

Rounding differences route to Rounding Adjustment account.

## 19.5 Cash Rounding Rule

Cash rounding can apply to cash payments.

Card/wallet payments should use exact amount by default.

---

# 20. Damage / Wastage Domain

## 20.1 Definition

Damage/Wastage is loss of inventory.

Examples:

- spoiled milk
- expired pastry
- broken sellable stock item
- wasted coffee beans
- dropped cup stock

## 20.2 Not an Expense Rule

Damage/wastage is not cash expense.

It affects:

```text
StockMovement: DAMAGE_OUT
Inventory Loss account ↑
Inventory Value account ↓
ShiftMovementSummary.wastage_total ↑ if linked to shift
```

It does not increase `expense_total`.

## 20.3 Reason Rule

Reason is always required.

Manager approval can be required by setting or threshold.

## 20.4 Report Rule

Wastage appears in:

- Inventory Loss report
- Wastage report
- Gross Profit calculation
- Shift report as wastage, not expense

---

# 21. Fixed Assets Domain

## 21.1 Definition

Fixed Asset is a long-term item used by business over time.

Examples:

- laptop
- POS device
- receipt printer
- barcode scanner
- electronic scale
- coffee machine
- fridge
- air conditioner
- chairs
- tables
- kitchen equipment
- furniture

## 21.2 Not Inventory Rule

Fixed Asset is not inventory.

It is not sold in POS and does not create StockMovement.

## 21.3 Not Immediate Expense Rule

Fixed Asset purchase does not hit P&L immediately.

It creates FixedAsset record and routes to Fixed Asset account.

## 21.4 Depreciation Rule [MVP Extended]

Straight-line depreciation:

```text
monthly_depreciation = (acquisition_cost - salvage_value) / useful_life_months
```

Depreciation affects P&L over time.

## 21.5 Write-off Rule [MVP Extended]

When asset is broken/lost/unusable:

```text
Loss = current book value
status = Written-off
Manager approval required
```

## 21.6 Asset Sale Rule [MVP Extended]

Asset sale records cash/bank proceeds and gain/loss vs book value.

## 21.7 Maintenance Rule [MVP Extended]

Maintenance event can be linked to asset.

Normal repair cost is expense.

Capital improvement that extends useful life is Phase 2.

## 21.8 Transfer Rule [MVP Extended]

Asset transfer changes branch/location/custodian.

No P&L impact.

---

# 22. Expenses Domain

## 22.1 Expense Definition

Expense is a cost consumed immediately or in short period.

Examples:

- rent
- electricity
- cleaning
- internet
- staff meal
- small repairs
- delivery fees paid by business

## 22.2 Expense vs Asset Rule

If it benefits the business for long period, classify as Fixed Asset.

If consumed quickly, classify as Expense.

## 22.3 Expense Payment Rule

Cash expense reduces cashbox and shift expense_total.

Bank expense reduces bank account but may not affect cashier shift.

## 22.4 Expense Approval Rule

Expense above threshold can require manager approval.

---

# 23. Discounts, Offers, and Charges Domain

## 23.1 Discount Rule

Discount reduces revenue.

Discount can be item-level or invoice-level.

Permission and threshold settings control who can discount.

## 23.2 Selling Below Cost Rule

Selling below cost can trigger manager approval.

## 23.3 Charges Rule

Charges include:

- service charge
- delivery fee
- packaging fee
- other invoice fees

Each charge has:

```text
is_taxable
is_revenue
applies_to_order_type
```

## 23.4 Takeaway Packaging Rule

Takeaway can automatically add packaging charge by setting.

## 23.5 Coupon Rule [MVP Extended]

Coupons validate:

- date range
- max uses
- minimum invoice amount
- applicable products/groups
- customer eligibility

---

# 24. Loyalty Domain [MVP Extended]

## 24.1 Phase Rule

Full loyalty business flow is MVP Extended.

MVP Core may include hooks/placeholders/settings readiness only.

## 24.2 Customer Requirement Rule

No customer = no loyalty.

Walk-in sales do not earn points.

## 24.3 Earn Rule

Points are earned after successful posted and paid invoice.

Recommended MVP Extended rule:

```text
Earn on net paid amount excluding tax and after discounts.
No points on loyalty redemption amount.
```

## 24.4 Redemption Rule

Loyalty redemption is a discount/reward redemption.

It is not cash/card/wallet/bank movement.

It reduces total due and creates LoyaltyTransaction.

## 24.5 Reversal Rule

Returns/cancellations reverse earned/redeemed points using outbox/idempotency.

## 24.6 Manual Adjustment Rule

Manual points adjustment requires permission, reason, and AuditLog.

---

# 25. Attachments Domain

## 25.1 Attachment Definition

Attachments are proof files linked to business documents.

Examples:

- supplier invoice photo
- expense receipt
- warranty document
- bank deposit slip
- terminal batch screenshot
- cancellation proof
- refund proof

## 25.2 Storage Rule

Attachments are stored in tenant-scoped path in S3-compatible storage.

## 25.3 Permission Rule

Upload, view, and delete require permissions.

## 25.4 Cancelled Document Rule

Cancelled documents are read-only for business fields.

Attachments may still be uploaded with permission.

Reason: business may need to attach cancellation proof, refund proof, or manager approval proof.

Upload/delete writes AuditLog.

## 25.5 Audit Rule

Attachment upload/delete must write AuditLog.

Attachment viewing can write AccessLog if sensitive.

---

# 26. Offline and Sync Domain

## 26.1 Offline Capability Rule

POS must allow core selling while offline if cached data and subscription status allow it.

## 26.2 Offline Queue Rule

Offline operations are queued with:

```text
idempotency_key
device_id
local_sequence
created_at
user_id
tenant_id
```

## 26.3 Sync Rule

On reconnect, queued operations are sent in order.

Server idempotency prevents duplicate creation.

## 26.4 Conflict Rule

Conflict examples:

- stock became insufficient
- shift closed elsewhere
- subscription expired
- document already exists

Conflict must be flagged for manager review, not silently ignored.

## 26.5 Local Cache Rule

Local cache includes:

- product catalog
- price tiers
- customers subset
- settings snapshot
- permissions
- subscription status

Sensitive data should be minimized.

---

# 27. Logs Domain

## 27.1 AuditLog Rule

AuditLog is for state-changing business actions.

Examples:

- post invoice
- cancel invoice
- change price
- change settings
- approve override
- adjust stock
- open/close shift
- upload/delete attachment

## 27.2 AccessLog Rule

AccessLog is for sensitive reads/exports.

Examples:

- P&L viewed
- customer statement viewed
- supplier statement viewed
- audit log viewed
- data export generated

## 27.3 OperationsLog Rule

OperationsLog is for system/hardware events.

Examples:

- printer failure
- kitchen ticket failure
- sync error
- Celery job failure
- hardware disconnected
- scale barcode parse error

---

# 28. Reports Domain

## 28.1 Reports Source Rule

Reports must read from movement ledgers.

Do not calculate financial truth from UI state only.

## 28.2 Sales Reports

Sales reports use:

- Sales Invoice records
- FinancialAccountMovement
- StockMovement
- ShiftMovementSummary

Revenue excludes tax.

## 28.3 Inventory Reports

Inventory reports use StockMovement.

Item balance = sum of stock movements.

## 28.3A Negative Stock Reports [MVP Core + MVP Extended]

Negative stock must be visible and traceable, not hidden inside normal stock balances.

Required reports:

| Report | Purpose | Phase |
|---|---|---|
| Negative Stock Alert Report | Shows products/ingredients currently below zero or recently allowed below zero. | MVP Core |
| Estimated Cost Sales Report | Shows sales posted with estimated cost because stock was insufficient. | MVP Core |
| Negative Stock Settlement Report | Shows which later purchases covered earlier negative balances. | MVP Extended |
| COGS Adjustment Report | Shows cost differences posted after settlement. | MVP Extended |

Negative stock reports must show:

```text
product / ingredient
warehouse
source sale or recipe consume movement
negative qty
estimated cost
later purchase document
settled qty
remaining negative qty
cogs adjustment amount
status
```

## 28.4 Customer/Supplier Statements

Customer statement reads CustomerARMovement.

Supplier statement reads SupplierAPMovement.

## 28.5 P&L Rule

P&L uses:

```text
Net Revenue
- COGS
- Inventory Loss
- Operating Expenses
- Depreciation Expense [MVP Extended]
= Profit
```

Tax is not revenue.

## 28.6 Shift Report Rule

Shift report separates:

- sales
- receipts
- expenses
- wastage
- cash drops
- card settlement
- wallet settlement

---

# 29. Security, Privacy, and Data Protection Domain

## 29.1 Tenant Data Rule

Tenant data is private and isolated.

## 29.2 Permission Enforcement Rule

API must enforce permissions on every sensitive action.

## 29.3 Financial Data Rule

Financial reports and exports require permissions and may write AccessLog.

## 29.4 Token Rule

Sessions and tokens must invalidate on logout, password change, or security-sensitive changes.

## 29.5 Export Rule

Exports must be scoped by tenant and permission.

---

# 30. Period Lock and Opening Balances

## 30.1 Opening Balance Rule

Opening balances establish pre-system state.

They can exist for:

- stock
- cashbox
- bank
- wallet
- customer AR
- supplier AP
- fixed assets [MVP Extended]

## 30.2 Period Lock Rule [MVP Extended]

After day/period lock, posted documents cannot be edited.

Corrections use reversal documents.

Unlock requires manager/admin permission and AuditLog.

## 30.3 Same-Shift Lock Rule

After shift close, editing/cancelling documents from that shift requires permission/approval.

---

# 31. Hardware Domain

## 31.1 Barcode Scanner Rule

Barcode scanner acts as keyboard input.

Barcode input should stay focused in POS.

## 31.2 Receipt Printer Rule

Invoice posting happens before printing.

Printer failure does not cancel invoice.

Failures go to OperationsLog.

## 31.3 Kitchen/Bar Printer Rule

Kitchen/bar tickets are routed by item group/printer assignment.

Failure does not cancel invoice.

## 31.4 Cash Drawer Rule

Cash drawer opens after posted cash sale, not before.

## 31.5 Scale Rule [Phase 2 / Partial MVP depending hardware]

Scale barcode can encode PLU and weight.

POS parses scale barcode and calculates quantity/price.

Direct scale integration is Phase 2.

## 31.6 Card Terminal Rule

MVP uses manual card recording.

Direct integration is Phase 2.

---

# 32. Café Domain [Primary MVP]

## 32.1 Café Identity

Café domain focuses on:

- fast touch POS
- recipes/BOM
- ingredient consumption
- modifiers/sizes
- kitchen/bar tickets
- takeaway/delivery labels
- shifts and cash reconciliation
- daily expenses
- wastage

## 32.2 Café Product Structure

Common café item types:

| Item | Type |
|---|---|
| Iced Latte | Recipe Product |
| Milk | Ingredient Item |
| Coffee beans | Ingredient Item |
| Cup | Ingredient Item / packaging stock |
| Delivery Fee | Service/Non-stock |
| Coffee Machine | Fixed Asset |

## 32.3 Café Order Types

| Order Type | Customer Required? | Domain Notes |
|---|---|---|
| Dine-in | Optional by setting | Table number Phase 2. |
| Takeaway | No | Anonymous sale valid; packaging charge optional. |
| Delivery | Usually yes | Address and delivery fee. |

## 32.4 Takeaway Anonymous Rule

Takeaway does not require customer name/phone.

Kitchen ticket must show order type clearly.

## 32.5 Modifiers and Sizes Rule

Modifiers may affect:

- price
- kitchen/bar ticket text
- recipe ingredient consumption [MVP Extended]

## 32.6 Recipe Deduction Rule

Selling a café recipe product consumes ingredients automatically.

Ingredients come from configured ingredient warehouse.

## 32.7 Café Wastage Rule

Café wastage includes:

- spilled milk
- expired pastry
- wasted coffee shots
- broken disposable stock

It is Inventory Loss, not cash expense.

## 32.8 Café Fixed Assets

Examples:

- coffee machine
- grinder
- fridge
- POS tablet
- receipt printer
- chairs/tables

Purchased as Fixed Asset line in Purchase Invoice.

## 32.9 Café Reports

Required café reports:

- sales by order type
- sales by category
- shift report
- ingredient consumption
- recipe margin
- wastage report
- cashier performance
- top products
- payment method breakdown

---

# 33. Retail Domain [Second MVP]

## 33.1 Retail Identity

Retail domain focuses on:

- barcode-first POS
- stock tracking
- customer accounts
- price tiers
- supplier purchases
- returns
- inventory reports

## 33.2 Barcode Rule

Retail POS must be keyboard/barcode optimized.

Barcode scan should add item quickly with minimal clicks.

## 33.3 Price Tier Rule

Retail often uses:

- Retail price
- Wholesale price
- VIP/customer-specific tier

Price tiers apply per ProductUnit.

## 33.4 Retail Credit Rule

Credit sales require customer and credit limit checks.

Customer statement is essential.

## 33.5 Retail Returns Rule

Return with original invoice is preferred.

Unlinked return requires setting and approval.

## 33.6 Retail Inventory Rule

Stock items are the main product type.

Recipe features are usually off unless enabled.

## 33.7 Retail Fixed Assets

Examples:

- shelves
- barcode scanner
- POS device
- scale
- display equipment

---

# 34. Supermarket Domain [Phase 2+]

## 34.1 Supermarket Identity

Supermarket domain focuses on high transaction volume and many SKUs.

## 34.2 Scale Barcode Rule

Supermarkets use PLU/weight barcode for items sold by weight.

## 34.3 Batch/Expiry Rule [Phase 2]

Expiry tracking is required for many grocery items.

Expired/near-expiry stock must appear in reports and alerts.

## 34.4 High-Speed Checkout Rule

POS must support fast scanning and minimal clicks.

## 34.5 Large Inventory Rule

Supermarket inventory can include 10,000+ SKUs.

Performance and indexing are critical.

---

# 35. Restaurant Domain [Phase 2+]

## 35.1 Restaurant Identity

Restaurant domain extends café with:

- table management
- open orders/tabs
- waiter roles
- KDS screen
- split bills
- table transfer
- service charge

## 35.2 Table Rule [Phase 2]

A table can have open order.

Orders can be held before final payment.

## 35.3 KDS Rule [Phase 2]

Kitchen Display System replaces or complements printed kitchen tickets.

## 35.4 Split Bill Rule [Phase 2]

Order total can be split by items, equal shares, or custom amount.

---

# 36. Pharmacy Domain [Future]

## 36.1 Pharmacy Identity

Pharmacy requires stricter compliance than MVP.

## 36.2 Batch/Expiry Rule

Batch and expiry tracking is mandatory.

## 36.3 Prescription Rule

Prescription workflow is future scope.

## 36.4 Restricted Items Rule

Some items may require permission, prescription, or pharmacist approval.

---

# 37. Gym Domain [Future]

## 37.1 Gym Identity

Gym domain focuses on membership/subscription workflows.

## 37.2 Membership Rule

Members have active/inactive/frozen membership states.

## 37.3 Check-in Rule

QR/member ID check-in is required.

## 37.4 POS Rule

Gym can still use POS for supplements, drinks, and merchandise.

---

# 38. Domain Conflict and Precedence Rules

## 38.1 Core Precedence Rule

Core posting and accounting rules always override vertical preferences.

Example:

```text
Even in Café mode, card payments must still go to Card Settlement account.
```

## 38.2 Settings Precedence Rule

When business behavior differs between tenants, use settings.

Do not hardcode tenant-specific behavior.

## 38.3 Snapshot Precedence Rule

Historical document snapshot overrides current settings.

## 38.4 Permission Precedence Rule

If UI allows an action but permission denies it, API must block it.

---

# 39. Domain Acceptance Criteria

## 39.1 Sales Domain Acceptance

- Posted sale creates correct stock, financial, customer, shift, audit, and snapshot records.
- Card payment does not touch cashbox.
- Tax is separated as Tax Payable.
- Customer credit sale updates CustomerARMovement.
- Walk-in sale works without customer.
- Takeaway sale works without customer.
- If negative stock is disabled, sale is blocked when stock or recipe ingredients are insufficient.
- If negative stock is enabled, sale can post with warning/approval according to settings.
- Negative stock sale creates SALE_OUT or RECIPE_CONSUME movement and NegativeStockAlert when enabled.
- Negative stock costing is marked as estimated when actual cost is not reliable.

## 39.2 Purchase Domain Acceptance

- Stock purchase updates stock and average cost.
- Expense line creates expense, no stock.
- Fixed asset line creates asset, no stock, no immediate P&L expense.
- Credit purchase updates SupplierAPMovement.
- Purchase stock automatically offsets existing negative stock balance by quantity.
- If formal settlement is enabled, purchase creates NegativeStockSettlement records for covered negative movements.
- If COGS adjustment is enabled, purchase settlement creates separate COGS Adjustment when estimated sale cost differs from actual purchase cost.

## 39.3 Inventory Domain Acceptance

- Every stock change has StockMovement.
- Recipe sale consumes ingredients.
- Damage creates Inventory Loss and wastage_total, not expense_total.
- Stocktaking variances create adjustments only after approval.
- Negative stock behavior is controlled by settings and product-level overrides.
- Negative stock must be visible in inventory alerts and manager dashboard when enabled.
- Batch/expiry/serial items must not be allowed to go negative when strict blocking is enabled.

## 39.4 Treasury Domain Acceptance

- Cash affects cashbox.
- Card affects Card Settlement.
- Wallet affects Wallet Account.
- Cash Drop is internal transfer and reduces expected drawer cash.
- Shift close formula separates sales, receipts, expenses, wastage, and drops.

## 39.5 Fixed Asset Domain Acceptance

- Asset purchase creates FixedAsset.
- Depreciation reduces book value over time.
- Write-off records loss and requires approval.
- Asset transfer has no P&L impact.

## 39.6 Logs Domain Acceptance

- AuditLog only for state changes.
- AccessLog for sensitive reads/exports.
- OperationsLog for hardware/sync/system events.

---

# 40. Glossary

| Term | Meaning |
|---|---|
| Tenant | Business account using SuperPOS. |
| Branch | Physical operating location. |
| Terminal | POS device. |
| Cashbox | Cash financial account/drawer/safe. |
| Warehouse | Stock location. |
| Shift | Cashier session tied to cashbox/terminal. |
| Posting | Confirming a document and creating business effects. |
| Movement Ledger | Historical record of stock/money/customer/supplier/asset effect. |
| AR | Accounts Receivable — customers owe the business. |
| AP | Accounts Payable — business owes suppliers. |
| COGS | Cost of Goods Sold. |
| Wastage | Inventory loss due to damage/spoilage. |
| Negative Stock | Stock balance below zero because sale/recipe consumption was allowed while system stock was insufficient. |
| Negative Stock Alert | Manager-facing alert created when stock goes below zero. |
| Negative Stock Settlement | Linking later purchase quantity to earlier negative stock movements. |
| Estimated Cost | Temporary cost used when actual cost is unknown due to negative stock. |
| COGS Adjustment | Separate cost correction after estimated cost is compared with actual purchase cost. |
| Fixed Asset | Long-term business asset, not inventory or immediate expense. |
| Depreciation | Spreading asset cost over useful life. |
| Card Settlement | Temporary account for card payments before bank settlement. |
| Price Tier | Base sale price list per customer tier. |
| ProductUnit | Unit/barcode row for a product. |
| ProductUnitTierPrice | Sale price per product unit per price tier. |
| Snapshot | Immutable copy of settings/values at posting time. |
| Idempotency Key | Client-generated key preventing duplicate POST processing. |
| Outbox | Reliable post-commit side-effect queue. |

---

# 41. Final Domain Notes

This document must evolve with `PRD.md`, `FLOW.md`, and `DESIGN.md`.

Any future change to a business rule must be checked against:

```text
1. Does it affect movement ledgers?
2. Does it affect account mapping?
3. Does it affect shift reconciliation?
4. Does it affect reports?
5. Does it require settings?
6. Does it require permissions or manager approval?
7. Does it need snapshotting for history?
8. Does it work offline/idempotently?
```

If the answer is yes, update PRD, FLOW, DESIGN, and DOMAIN together.

---

---

# 41. Table Service & Open Orders Domain — [MVP Core for Cafés]

## 41.1 Core Domain Rule

An Open Order is an **operational document**, not a financial document.

It lives between the moment a customer sits down and the moment they pay. Nothing in the Open Order lifecycle creates revenue, tax, AR, or shift payment totals. These only happen when the customer pays and the Open Order is converted to a posted Sales Invoice.

## 41.2 One Order Per Table Rule

A table can have only one active OpenOrder at a time.

If a table shows status `occupied`, `sent_to_kitchen`, or `needs_bill`, no new order can be opened on it until the current one is paid or cancelled.

## 41.3 Open Order ≠ Sales Invoice

| Open Order | Sales Invoice |
|---|---|
| Operational — in progress | Financial — permanent record |
| No revenue posted | Revenue posted |
| No tax payable posted | Tax Payable posted |
| No stock movement (if `on_payment`) or provisional movement (if `on_kitchen_send`) | Final stock movement posted |
| Editable (with rules) | Immutable after posting |
| No document number | Gets document number at posting |

## 41.4 Open Order ≠ Credit Sale

Credit Sale = posted Sales Invoice where customer pays later. AR increases. It is a financial event.

Open Order = operational holding state. The customer has not yet been billed. There is no AR, no revenue, no tax payable.

## 41.5 Open Order ≠ Negative Stock Sale

Negative Stock Sale = sale posted while stock is insufficient, controlled by settings.

Open Order = operational state before posting. Negative stock rules apply at the moment of posting (at kitchen send if `on_kitchen_send`, at payment if `on_payment`), not at item entry.

## 41.6 Item Status Lifecycle Rule

```
Draft
  ↓ Send to Kitchen
Sent
  ↓ (Phase 2 with KDS)
Preparing → Served
  ↓ (at payment)
Billed
```

Items can also be:
- `cancelled` — removed with or without manager approval depending on status
- `voided` — removed before being sent (no approval, no effects)

## 41.7 Sent Item Cancellation Rule

Once an item is Sent, the kitchen has received the instruction. The system must:
- Never silently delete a sent item
- Always require manager approval to cancel a sent item
- Record the cancellation in AuditLog with reason and approver

If the item was already prepared or served, it cannot be cancelled without business consequence:
- Default: bill the customer (item appears on invoice)
- Manager removes it: must create either a Wastage or Complimentary record

## 41.8 Complimentary vs Wastage Rule

| Complimentary | Wastage |
|---|---|
| Item was served to customer, manager chose not to bill | Item was made but not served (spoiled, dropped, unusable) |
| Guest relations, complaint resolution, owner gesture | Operational loss |
| Creates Complimentary record | Creates Wastage record → Inventory Loss |
| No inventory loss (item was consumed by customer) | Inventory value decreases |
| Appears in Complimentary Report | Appears in Wastage Report + P&L |

## 41.9 Stock Commit Timing Rule

Controlled by setting `stock_commit_timing`.

**`on_kitchen_send`** (default for table service):
- StockMovement / RECIPE_CONSUME created when Send to Kitchen is pressed
- At payment: financial posting only, no new stock movements for already-sent lines
- If sent item is cancelled: stock movement reversed

**`on_payment`**:
- No stock movements during order lifecycle
- All stock movements created when Sales Invoice is posted at payment
- Cancelled items: no stock effect (never moved)

The system must not create duplicate stock movements regardless of which setting is active.

## 41.10 Kitchen Ticket Immutability Rule

A KitchenTicket is a physical document that has already been sent to the kitchen printer. It cannot be modified after printing.

If an item is cancelled after the ticket was printed:
- The original ticket remains unchanged
- A cancel notice is appended (printed as a separate cancellation ticket or note)
- The cancellation is visible in the KitchenTicket history on the OpenOrder

## 41.11 Table Ownership Rule

A table belongs to a branch. Any Cashier or Waiter in the branch can view all tables and interact with any open order.

There is no exclusive ownership of a table by one waiter in MVP. Any user with `order.add_items` permission can add to any open order.

## 41.12 Shift Linking Rule

An OpenOrder is linked to the shift that was active when it was opened. The resulting Sales Invoice posts into the shift that is active at payment time.

If the shift changes between order open and payment (rare but possible), the invoice is posted to the shift at payment time, not the shift at order open time.

## 41.13 Glossary Additions

| Term | Meaning |
|---|---|
| OpenOrder | Operational live order on a table, not yet financially posted |
| OpenOrderLine | Single item on an open order with its status |
| KitchenTicket | Printed ticket sent to kitchen/bar for preparation |
| DiningTable | Physical table in the venue |
| DiningSection | Named area grouping tables (Main Hall, Terrace, etc.) |
| Complimentary | Item served to customer but not billed by manager decision |
| stock_commit_timing | Setting controlling when stock movements are created in table service |

---

**Supporting Documentation Status**

- `PRD.md` — v3.6 + Table Service
- `FLOW.md` — v3.6 + Table Service
- `DESIGN.md` — v3.6 + Table Service
- `DOMAIN.md` — v3.6 + Table Service

