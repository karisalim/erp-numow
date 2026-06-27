# 🎨 SuperPOS ERP Lite — User Interface & Experience Design (DESIGN.md)

**Version:** 3.6  
**Last Updated:** June 2026  
**Status:** Draft — Consistency-Audited with PRD/FLOW/DOMAIN  
**Scope:** UI/UX design rules, screen behavior, interaction patterns, layout system, and implementation guidance  
**Based on:** `PRD_v3.6.md` + `FLOW_v3.6.md` + `DOMAIN_v3.6.md`  
**Visual Prototype Baseline:** `SuperPOS.html`  

---

## 📖 How to Read This Document

This file defines **how SuperPOS ERP Lite should look and behave in the user interface**.

It does not replace:

- `PRD.md` — defines what the product must include.
- `FLOW.md` — defines the business workflows and posting sequence.
- `DOMAIN.md` — defines the core business rules and terminology.

This file translates those requirements into a consistent UI/UX language for designers, frontend developers, and AI coding tools.

### Source of Truth Priority

| Priority | Source | Purpose |
|---:|---|---|
| 1 | `PRD_v3.6_with_negative_stock.md` | Product scope and business requirements |
| 2 | `FLOW_v3.6_with_negative_stock.md` | Workflow behavior and state transitions |
| 3 | `DOMAIN_v3.6_with_negative_stock.md` | Domain rules and business invariants |
| 4 | `SuperPOS.html` | Visual reference only |
| 5 | Older `DESIGN.md` / outline | Historical structure reference only |

### Important Prototype Rule

`SuperPOS.html` is an old prototype. It must be used as a **visual/UI reference only**, not as a business logic source.

Use it for:

- Sidebar shape and compact navigation rhythm.
- Header height, account area, online/offline badge style.
- Card borders, rounded corners, shadows, and spacing.
- Modal feel, table density, badge style, and POS cart layout.
- The general calm, clean, fast POS personality.

Do **not** use it for:

- Business rules.
- Payment routing.
- Shift logic.
- Inventory rules.
- Negative stock behavior.
- Customer/supplier balances.
- Card settlement rules.
- Tax or COGS behavior.

If `SuperPOS.html` conflicts with PRD/FLOW/DOMAIN, follow PRD/FLOW/DOMAIN.

---

# 1. Design Principles

## 1.1 Product Design Positioning

SuperPOS ERP Lite is a **business operating system for cafés and retail shops**, not just a cashier screen.

The design must feel:

- Fast enough for a cashier under pressure.
- Simple enough for a café/shop owner without accounting background.
- Accurate enough to show trustworthy stock, cash, and profit data.
- Unified enough that POS, purchasing, inventory, treasury, and reports feel like one system.

## 1.2 Core UX Principles

| Principle | Meaning in UI |
|---|---|
| Speed first | POS screens prioritize scan, tap, pay, print. No unnecessary confirmations. |
| Business clarity | Users must understand where money, stock, and balances go. |
| Settings-controlled behavior | Screens must reflect enabled settings instead of assuming fixed behavior. |
| Safe posting | Destructive or financially sensitive actions require explicit states, permissions, and approvals. |
| Ledger transparency | Important documents should link to their movement effects. |
| RTL/Arabic readiness | Layout must support Arabic from day one. |
| Offline awareness | User must always know if work is local, synced, failed, or blocked. |
| Consistent status language | Same badge names/colors across all modules. |
| Prototype continuity | Extend SuperPOS visually; do not redesign into a new unrelated product. |

## 1.3 ERP Lite Design Rule

The product should expose business effects without forcing the user to understand full accounting.

Use business language such as:

- Cashbox
- Card Settlement
- Customer Balance
- Supplier Balance
- Inventory Value
- Wastage
- Profit
- Tax Payable

Avoid exposing heavy accounting language unless needed in Account Mapping or reports.

## 1.4 Design for Trust

Any posted document should answer:

1. Who created it?
2. When was it posted?
3. What did it affect?
4. Was it paid?
5. Was it synced?
6. Was it approved?
7. Can it still be edited?
8. Where are its stock/cash/customer/supplier movements?

---

# 2. Visual System Based on SuperPOS.html

## 2.1 Visual Direction

The UI should preserve the current prototype personality:

- White cards on a light neutral background.
- Compact sidebar.
- 64px header height.
- Calm blue primary actions.
- Soft borders and small shadows.
- Dense but readable tables.
- Badge-driven operational status.
- POS split layout: product/search area + current sale cart.

## 2.2 Design Tokens

Use the same token families from the prototype.

### Neutral Palette

| Token | Hex | Usage |
|---|---|---|
| neutral-50 | `#FAFBFC` | Light surface / subtle row background |
| neutral-100 | `#F3F4F6` | Page background |
| neutral-200 | `#E5E7EB` | Subtle border |
| neutral-300 | `#D1D5DB` | Input/table border |
| neutral-400 | `#9CA3AF` | Disabled text |
| neutral-500 | `#6B7280` | Secondary text |
| neutral-600 | `#4B5563` | Body text |
| neutral-700 | `#374151` | Strong labels |
| neutral-800 | `#1F2937` | Headings |
| neutral-900 | `#111827` | Primary text |

### Semantic Palette

| Semantic | Base | Usage |
|---|---|---|
| Primary/Brand | `#3B82F6` / `#2563EB` | Primary buttons, active nav, focused actions |
| Success | `#10B981` | Paid, synced, completed, positive variance |
| Warning | `#F59E0B` | Pending, variance, negative stock warning, estimated cost |
| Danger | `#EF4444` | Blocked, failed, cancelled, shortage, destructive |
| Info | `#06B6D4` | Informational notices, settlement hints |

## 2.3 Typography

Use the same font direction as the prototype:

```text
Body font: Segoe UI, system UI, sans-serif
Mono font: SF Mono / Monaco / Menlo / Courier New
```

Guidelines:

- Use 14px base body text.
- Use 12px for metadata, secondary hints, and table helper text.
- Use 15–16px for card titles.
- Use 22–28px for financial totals and POS payment totals.
- Use tabular numerals for money, quantities, totals, and balances.

## 2.4 Spacing and Shape

| Element | Rule |
|---|---|
| App shell | Full-height flex layout |
| Sidebar | 220px desktop width, fixed left in LTR, fixed right in RTL |
| Header | 64px height |
| Page padding | 20–24px desktop |
| Card radius | 8px |
| Button height | 32px small, 40px standard, 48–56px POS primary |
| Input height | 40px standard, 56px POS barcode |
| Table row height | 52–64px depending on density |
| Modal width | 420px small, 640px medium, 900px complex |

## 2.5 Component Style

### Cards

Cards should use:

```text
white background
neutral-200 border
8px radius
small shadow
```

Card anatomy:

- Header: 56px height, title + optional action.
- Body: 16–24px padding.
- Footer: separated by top border when actions exist.

### Buttons

Button types:

| Type | Usage |
|---|---|
| Primary | Post, save, proceed to payment, open shift |
| Secondary | Test printer, export, preview |
| Ghost | Minor actions, filters, header quick actions |
| Danger | Cancel, delete, void, write-off |
| Warning | Manager approval required, review conflict |

### Badges

Badges must be compact, readable, and consistent across all modules.

Use badges for document status, sync state, stock state, payment state, and approval state.

---

# 3. Application Shell & Navigation

## 3.1 Shell Layout

The application shell follows the prototype:

```text
┌─────────────────────────────────────────────┐
│ Sidebar │ Header                            │
│         ├───────────────────────────────────┤
│         │ Page Content                      │
└─────────────────────────────────────────────┘
```

Desktop:

- Sidebar fixed width: 220px.
- Header spans the remaining content area.
- Content area uses light neutral background.
- Main page scrolls independently where needed.

Tablet POS:

- Sidebar can collapse into icon-only mode.
- POS layout remains two-column where possible.
- Touch café POS can take full width.

Mobile/manager view:

- Read-only summaries and approvals only.
- Not intended as full cashier POS MVP unless explicitly scoped later.

## 3.2 Sidebar Navigation

Recommended module order:

1. Point of Sale
2. Dashboard
3. Sales
4. Purchases
5. Customers
6. Suppliers
7. Products
8. Inventory
9. Treasury / Finance
10. Reports
11. Users
12. Settings

### Sidebar Rules

- Keep labels short.
- Use icons consistently.
- Active route uses primary-50 background and primary-700 text.
- Hover uses neutral-100.
- Avoid nesting more than one level in the sidebar.
- Deep sub-sections should use tabs inside pages, not sidebar clutter.

## 3.3 Important Shift Navigation Rule

**Shift Workflow / Cashier Session must not be a sidebar module.**

Shift actions live in:

- POS header context.
- Profile dropdown.
- Current shift status pill.
- Manager reports/history under Reports or Settings.

Do not add “Shifts” as a main sidebar item for cashier use.

## 3.4 Header Design

Header should include:

- Page title.
- Short subtitle/context.
- Optional page action buttons.
- Online/offline sync indicator.
- Active branch/terminal/cashier context.
- Profile dropdown.

Header examples:

```text
Point of Sale
Come Back Main · POS-01 · Shift open 08:12
```

```text
Inventory Movement
Main Branch · Warehouse: Bar Storage
```

## 3.5 Profile Dropdown

Profile dropdown should include:

- User name and role.
- Branch and terminal.
- Current shift status.
- Open Shift / Close Shift action.
- Today summary quick view.
- Sync status.
- Subscription/trial warning if applicable.
- Logout.

### Profile Dropdown States

| State | UI |
|---|---|
| No active shift | Warning row + `Open Shift` primary action |
| Active shift | Green shift pill + `View Summary` + `Close Shift` |
| Offline | Offline badge + pending sync count |
| Trial ending | Amber subscription badge |
| Suspended/expired | Red blocked notice where relevant |

### Logout With Open Shift

If cashier attempts logout with an active shift:

- Show modal: “You still have an open shift.”
- Actions:
  - Close Shift
  - Logout Anyway (permission-controlled)
  - Cancel

---

# 4. UI Architecture Patterns

## 4.1 Page Types

The product uses these page patterns:

| Pattern | Used For |
|---|---|
| Dashboard page | Home dashboard, manager alerts |
| List + filters page | Sales, purchases, products, customers, suppliers |
| Detail page | Document, product, customer, supplier, fixed asset |
| Form page | Purchase invoice, stock adjustment, settings |
| Split POS page | Barcode POS and cart |
| Touch POS page | Café product grid and cart |
| Report page | Ledger-driven reports |
| Settings page | Grouped cards and toggles |

## 4.2 List Pages

List pages should include:

- Header with title and primary action.
- Summary cards where useful.
- Search input.
- Filter chips/selectors.
- Table with status badges.
- Empty state.
- Export if permission allows.

Example structure:

```text
Header
Summary Cards
Filter Bar
Data Table
Pagination / Load More
```

## 4.3 Detail Pages

Every detail page should include:

- Header with document/entity title.
- Five document status badges when applicable.
- Main details card.
- Lines/items card.
- Movement effects card.
- Attachments card.
- Audit timeline.
- Actions area controlled by status and permissions.

## 4.4 Forms

Forms should be grouped by business meaning, not database structure.

Use:

- Section cards.
- Inline validation.
- Required field indicator.
- Save draft / Post actions where applicable.
- Clear warnings before irreversible posting.

## 4.5 Modals and Drawers

Use modals for:

- Open shift.
- Close shift.
- Payment.
- Manager approval.
- Quick customer create.
- Return confirmation.
- Negative stock warning.
- Printer failure.

Use drawers for:

- Quick product detail.
- Customer side profile in POS.
- Movement detail preview.
- Settings side explanation if needed.

## 4.6 Toasts and Alerts

Use toasts for short-lived feedback:

- Saved successfully.
- Posted successfully.
- Sync queued.
- Printer failed; invoice posted.

Use persistent alert banners for:

- Offline mode.
- Subscription expired/grace period.
- Missing account mapping.
- No active shift.
- Sync conflict requiring review.

---

# 5. POS Design

## 5.1 POS Modes

SuperPOS must support two POS modes:

| Mode | Target | Primary Input |
|---|---|---|
| Compact Barcode POS | Retail / supermarket-like checkout | Barcode scanner + keyboard |
| Touch Café POS | Café / quick-service | Touch product tiles + modifiers |

The user can configure default POS mode in Settings.

## 5.2 Compact Barcode POS Layout

Follow the prototype split layout:

```text
┌───────────────────────────────────────────────┐
│ Header: Point of Sale · Branch · Shift · Sync │
├────────────────────────────┬──────────────────┤
│ Barcode/Search + Products  │ Current Sale Cart│
│ Quick Select / Search      │ Totals + Payment │
└────────────────────────────┴──────────────────┘
```

Recommended desktop grid:

- Left side: 7 columns.
- Right cart: 5 columns.
- Gap: 20px.
- Page padding: 20px.

### Barcode Input

The barcode input should:

- Remain focused by default.
- Show “Listening” indicator.
- Support scanner input.
- Support manual barcode entry.
- Show product not found warning.
- Support scale barcode parsing in Phase 2 / supermarket mode.

Error state:

```text
No product found for "8480000000000"
```

## 5.3 Current Sale Cart

Cart line should show:

- Product name.
- Unit/barcode/variant if relevant.
- Quantity controls.
- Unit price.
- Line discount if applied.
- Tax indicator.
- Line total.
- Warning badges where relevant:
  - Negative Stock
  - Estimated Cost
  - Price Tier
  - Modifier Required

Cart footer should show:

- Subtotal.
- Discount.
- Charges.
- Tax.
- Rounding.
- Total.
- Payment button.

Tax must be shown separately from revenue.

## 5.4 Customer Selector in POS

Default state:

```text
Customer: Walk-in
```

When customer is selected:

- Show customer name.
- Show price tier.
- Show AR balance if credit enabled.
- Show credit limit warning if relevant.
- Update prices if customer has tier pricing.
- Show confirmation if cart prices change.

Price change confirmation:

```text
Customer price tier changed from Default to Municipality.
3 cart lines were updated.
Review prices before payment.
```

## 5.5 Order Type Selector

POS should include an order type selector:

- Dine-in
- Takeaway
- Delivery

Default depends on business settings.

### Dine-in

MVP café can support simple dine-in label without full table management.

Future restaurant mode can add:

- Table selection.
- Waiter assignment.
- Split bill.
- Table transfer.

### Takeaway

Takeaway must not require customer by default.

Show:

- Takeaway badge on order.
- Kitchen/bar ticket label.
- Optional packaging charge if configured.

### Delivery

Delivery may require customer/address depending on settings.

Show:

- Customer required warning if enabled.
- Address drawer.
- Delivery charge.
- Driver/status placeholder for future.

## 5.6 Payment Panel

Payment methods:

- Cash
- Card/Visa
- Wallet
- Credit
- Loyalty redemption placeholder / MVP Extended

### Payment Routing Clarity

The payment panel must visually explain money destination:

| Method | UI Destination Label |
|---|---|
| Cash | Cashbox / Drawer |
| Card/Visa | Card Settlement |
| Wallet | Wallet Account |
| Credit | Customer Balance |
| Loyalty Redemption | Reward Discount |

Important warnings:

- Card/Visa must never look like it enters the cashbox.
- Wallet must never look like it enters the cashbox.
- Credit is not money received now.
- Loyalty redemption is not a payment line; it is a discount/reward effect.

## 5.7 Mixed Payments

Mixed payment UI should allow multiple payment lines:

```text
Total: 250.00 EGP
Cash: 100.00 → Cashbox
Card: 100.00 → Card Settlement
Credit: 50.00 → Customer Balance
```

Rules:

- Credit requires a selected customer.
- Card requires manual reference if configured.
- Wallet may require wallet provider/reference.
- Cash overpayment shows change due.

## 5.8 Credit Sale UX

Credit sale means the **customer pays later**.

UI must show:

```text
This will increase customer balance by 250.00 EGP.
```

If credit limit exceeded:

- Block by default.
- Allow manager override only if setting/permission allows.

Credit sale is different from negative stock.

## 5.9 POS Posting Feedback

After successful posting:

- Show receipt screen or print dialog.
- Show document number.
- Show sync state.
- Show payment summary.
- Show stock update message if online.
- If offline, show queued badge.

Printer failure after posting:

```text
Invoice posted successfully, but receipt printing failed.
You can retry printing from the receipt screen.
```

Do not cancel posted invoice because printing failed.

---

# 6. Café Touch POS Design

## 6.1 Touch Layout

Touch café POS should use larger product tiles:

```text
┌───────────────────────────────────────────────┐
│ Categories / Search / Order Type             │
├────────────────────────────┬──────────────────┤
│ Product Tiles + Modifiers  │ Order Cart       │
└────────────────────────────┴──────────────────┘
```

Tile rules:

- Large enough for finger tap.
- Show product name.
- Show price.
- Show image or initials fallback.
- Show availability/negative stock badge if relevant.
- Show “Recipe”/“Modifier” cues when needed.

## 6.2 Category Tiles

Categories can include:

- Coffee
- Iced Drinks
- Desserts
- Bakery
- Snacks
- Add-ons
- Offers

Use horizontal filter chips or left-side category rail depending on screen width.

## 6.3 Modifier Popup

When a recipe product requires choices, open a modifier modal.

Examples:

- Size: Small / Medium / Large.
- Temperature: Hot / Iced.
- Milk type: Regular / Skimmed / Oat.
- Extras: Caramel / Chocolate / Extra shot.

Modifier modal should show:

- Required groups with validation.
- Optional groups.
- Price delta.
- Ingredient impact if useful.
- Add to cart button disabled until required choices selected.

## 6.4 Recipe Ingredient Warnings

When adding a recipe product, the UI may show warning if ingredients are insufficient.

Possible states:

| State | UI |
|---|---|
| Enough ingredients | No warning |
| Low stock | Amber “Low ingredient stock” |
| Insufficient and blocked | Red modal blocks sale |
| Insufficient but allowed | Amber negative stock warning |
| Requires approval | Manager approval modal |

## 6.5 Kitchen / Bar Ticket Feedback

After sale or order posting:

- Show kitchen/bar ticket status.
- Show printer routing.
- If printer fails, show retry action.
- OperationsLog should record printer failure.

Ticket label must include:

- Order number.
- Order type.
- Items/modifiers.
- Notes.
- Time.
- Cashier/user.

---

# 7. Shift Workflow Design

## 7.1 Shift Is a Workflow, Not a Module

Cashier shift is part of POS session lifecycle.

Entry points:

- POS page load.
- Header shift pill.
- Profile dropdown.

Manager/admin can view shift history from Reports/Settings, but cashier should not see “Shift” as a sidebar module.

## 7.2 No Active Shift State

If settings require shift before sale and no active shift exists, POS should show a blocking state:

```text
No active shift
Open a shift before starting sales on this terminal.
```

Actions:

- Open Shift.
- Switch user.
- View settings if permission allows.

## 7.3 Open Shift Modal

Open Shift modal fields:

- Branch.
- Terminal.
- Cashbox.
- Cashier.
- Expected opening cash.
- Actual counted cash.
- Opening variance.
- Notes.
- Cash denomination counting if enabled.

If variance exceeds setting threshold:

- Require manager approval.
- Require reason.
- Record audit trail.

## 7.4 Cash Denomination Counting

If enabled, show denomination table:

| Denomination | Count | Total |
|---:|---:|---:|
| 200 EGP | 2 | 400 |
| 100 EGP | 3 | 300 |
| 50 EGP | 1 | 50 |

Total counted cash is calculated automatically.

If manual total is allowed, show:

```text
Use manual total instead of denomination breakdown
```

## 7.5 Active Shift Indicator

Header shift pill:

```text
Shift open · 08:12 · Drawer-01
```

Dropdown quick summary:

- Cash sales.
- Customer cash receipts.
- Card sales.
- Wallet sales.
- Credit sales.
- Cash returns.
- Expenses.
- Cash drops.
- Wastage total.
- Pending sync count.

## 7.6 Close Shift Modal

Close Shift modal should include:

1. System expected drawer cash.
2. Actual counted cash.
3. Variance.
4. Cash denomination counting.
5. Card terminal batch total.
6. Wallet settlement confirmation.
7. Cash drop summary.
8. Expenses summary.
9. Wastage summary.
10. Manager approval if variance exceeds threshold.

## 7.7 Expected Drawer Cash Formula

Display the formula in a collapsible explanation panel:

```text
Expected Drawer Cash =
Opening Cash
+ Cash Sales
+ Customer Cash Receipts
+ Cash In
- Cash Returns
- Cash Out
- Cash Expenses
- Cash Drop
```

Use system field labels:

```text
opening_cash_actual
+ cash_sales_total
+ customer_cash_receipts_total
+ cash_in_total
- cash_returns_total
- cash_out_total
- expense_total
- cash_drop_total
```

Important:

- `wastage_total` must not be included in drawer cash formula.
- Damage/wastage is inventory loss, not cash leaving drawer.
- Card sales are not drawer cash.
- Wallet sales are not drawer cash.
- Credit sales are not drawer cash.

## 7.8 Shift Report Layout

Shift report should show:

- Opening cash.
- Cash sales.
- Customer cash receipts.
- Cash returns.
- Cash in/out.
- Cash expenses.
- Cash drop.
- Expected drawer cash.
- Actual counted cash.
- Variance.
- Card sales vs terminal batch.
- Wallet sales.
- Credit sales.
- Wastage total.
- Negative stock events during shift.
- Approval events.
- Sync issues.

---

# 8. Negative Stock Design

## 8.1 Business Meaning

Negative Stock Sale means:

```text
The product or recipe ingredient is insufficient in inventory,
but the system allows the sale based on settings.
```

Credit Sale means:

```text
The customer received the order and will pay later.
```

They are different and must not be confused in the UI.

## 8.2 Negative Stock Settings Location

Add a settings card under:

```text
Settings → Inventory Settings → Negative Stock Control
```

Card title:

```text
Negative Stock Control
```

Card description:

```text
Control whether cashiers can sell products or recipe items when the current stock is not enough.
```

## 8.3 Negative Stock Settings UI

Fields:

| UI Control | Field | Type |
|---|---|---|
| Allow negative stock sale | `allow_negative_stock_sale` | Toggle |
| Require manager approval | `require_manager_approval_for_negative_stock` | Toggle |
| Scope | `negative_stock_scope` | Dropdown |
| Show cashier warning | `show_negative_stock_warning_to_cashier` | Toggle |
| Create manager alert | `create_negative_stock_alert` | Toggle |
| Costing method | `negative_stock_costing_method` | Dropdown |
| Auto-settle on purchase | `auto_settle_negative_stock_on_purchase` | Toggle |
| Create COGS adjustment | `create_cogs_adjustment_after_negative_stock_settlement` | Toggle |
| Block batch/expiry/serial items | `block_negative_stock_for_batch_expiry_serial_items` | Toggle |
| Show in manager dashboard | `show_negative_stock_in_manager_dashboard` | Toggle |

### Scope Dropdown Values

- All products
- Selected products only
- Ingredients only
- Products and ingredients

### Costing Method Values

- Last known average cost
- Default purchase price
- Zero cost and require later adjustment

## 8.4 Settings Dependency Behavior

If `allow_negative_stock_sale` is OFF:

- Disable dependent fields.
- Show helper text:

```text
Negative stock sale is disabled. Sales will be blocked when stock is insufficient.
```

If ON:

- Enable scope, warning, approval, alert, and costing controls.
- Show warning:

```text
Allowing negative stock can keep sales moving but may require later cost review.
```

If `negative_stock_costing_method = zero_cost_require_later_adjustment`:

- Strongly recommend enabling COGS adjustment report.
- Show “Estimated Cost” badges on related sale lines.

## 8.5 Product-Level Override

Product detail should include a “Negative Stock Behavior” section:

Options:

- Inherit tenant setting.
- Always block.
- Allow with warning.
- Allow with manager approval.
- Allow without approval if tenant allows.

Display current product stock state:

```text
Current stock: -3.000 units
Status: Negative Stock
```

For recipe products, show ingredient-level behavior and warnings.

## 8.6 POS Negative Stock Warning

If sale will create negative stock and warning is enabled, show a modal or inline panel before posting.

Content:

```text
This sale will create negative stock.

Item: Milk
Available: 0.000 L
Required: 2.500 L
Resulting balance: -2.500 L
Cost status: Estimated using last known average cost
```

Actions:

- Cancel.
- Continue.
- Request Manager Approval if required.

## 8.7 Manager Approval for Negative Stock

Approval modal includes:

- Item/product list causing negative stock.
- Available qty.
- Required qty.
- Resulting balance.
- Costing method.
- Reason field.
- Manager PIN/password.

After approval:

- Show approval badge on document.
- Add audit timeline event.
- Continue posting.

## 8.8 Negative Stock Alerts

If enabled, create alert visible in:

- Manager dashboard.
- Inventory alerts page.
- Product detail.
- Negative Stock Alert Report.

Alert card fields:

- Product/ingredient.
- Warehouse.
- Current balance.
- First negative date.
- Last affected document.
- Estimated cost exposure.
- Responsible branch/terminal.
- Status: Open / Partially Settled / Settled / Dismissed.

## 8.9 Negative Stock Settlement on Purchase

When a purchase invoice covers negative stock, purchase UI should show:

```text
This purchase will cover existing negative stock.
```

Settlement preview:

| Product | Current Balance | Purchase Qty | Negative Covered | Final Balance |
|---|---:|---:|---:|---:|
| Milk | -5.000 L | 20.000 L | 5.000 L | 15.000 L |

If formal settlement records are enabled:

- Show `NegativeStockSettlement` link in purchase detail.
- Show affected old sale/recipe consumption movements.
- Show estimated vs actual cost difference if available.

## 8.10 Estimated Cost Badge

When a sale uses estimated cost because stock was negative, show a badge:

```text
Estimated Cost
```

Where shown:

- Sale invoice detail line.
- Product movement report.
- Estimated Cost Sales Report.
- Negative stock settlement report.

## 8.11 COGS Adjustment UI

If actual purchase cost differs from estimated cost and setting allows adjustment:

Show in settlement report:

```text
Estimated cost: 10.00 EGP/L
Actual cost: 12.00 EGP/L
Difference: +2.00 EGP/L
Adjusted qty: 5.000 L
COGS Adjustment: +10.00 EGP
```

If old period is locked:

```text
Original sale period is locked. Adjustment will be posted in the current open period.
```

Do not edit the old invoice.

## 8.12 Negative Stock Reports

Reports:

1. Negative Stock Alerts.
2. Negative Stock Settlement.
3. Estimated Cost Sales.
4. COGS Adjustment.

Each report should support filters:

- Date range.
- Branch.
- Warehouse.
- Product.
- Status.
- Cost status.
- Settled/unsettled.

---

# 9. Inventory Design

## 9.1 Inventory Overview

Inventory pages must show stock as movement-ledger driven, not manually trusted UI state.

Key pages:

- Warehouses.
- Stock balances.
- Stock movement report.
- Stock adjustment.
- Damage/wastage.
- Warehouse transfer.
- Opening stock.
- Stocktaking sessions.
- Negative stock alerts.

## 9.2 Warehouses List

Show:

- Warehouse name.
- Branch.
- Type: Main / Sales / Ingredients / Kitchen / Damaged / Virtual.
- Active status.
- Current stock value.
- Negative item count.
- Low stock item count.

## 9.3 Stock Movement Report

Table columns:

- Date/time.
- Product.
- Warehouse.
- Movement type.
- Document reference.
- Quantity in.
- Quantity out.
- Balance after movement.
- Cost snapshot.
- User.
- Sync status.

Movement types include:

- PURCHASE_IN
- SALE_OUT
- RECIPE_CONSUME
- SALES_RETURN_IN
- PURCHASE_RETURN_OUT
- ADJUSTMENT_IN
- ADJUSTMENT_OUT
- DAMAGE_OUT
- TRANSFER_IN
- TRANSFER_OUT
- OPENING_STOCK

## 9.4 Stock Adjustment Screen

Form fields:

- Warehouse.
- Product.
- Current qty.
- Adjustment type.
- New qty or difference.
- Reason.
- Attachment optional.
- Manager approval if required.

UI must warn:

```text
This adjustment will affect inventory reports and stock valuation.
```

## 9.5 Damage / Wastage Screen

Damage/wastage is not a cash expense.

Screen fields:

- Product/ingredient.
- Warehouse.
- Quantity.
- Unit.
- Reason.
- Cost preview.
- Shift link if created during active shift.
- Attachment optional.
- Manager approval if threshold exceeded.

Posting preview:

```text
Stock will decrease.
Inventory loss will increase.
Shift wastage_total will increase if linked to active shift.
Cash drawer will not change.
```

## 9.6 Warehouse Transfer Screen

Form fields:

- From warehouse.
- To warehouse.
- Product lines.
- Quantity.
- Notes.
- Attachment optional.

Show:

```text
Internal transfer only — no P&L effect.
```

## 9.7 Stocktaking Session

Basic stock adjustment is MVP Core.
Full stocktaking sessions are MVP Extended.

Stocktaking session UI:

- Create session.
- Select warehouse.
- Freeze expected quantities.
- Count actual quantities.
- Show variance.
- Require approval for significant variance.
- Post adjustments.
- Lock session after posting.

---



## 9.8 Recipe Ingredient Warehouse Selection

Recipe ingredient stock must be visually traceable before and after POS posting.

Design requirements:

- Recipe Product detail shows the default ingredient source policy.
- POS ingredient validation must show which warehouse will be consumed from.
- Settings page must expose the configured ingredient source rule.
- Stock movement drill-down must show the warehouse used for each `RECIPE_CONSUME` movement.
- If the source warehouse is missing or inactive, POS must show a blocking setup error before posting.

Supported source rules to reflect from business logic:

| Source Rule | UX Meaning |
|---|---|
| Branch default ingredient warehouse | POS consumes ingredients from the branch configured ingredient warehouse. |
| Product-specific ingredient warehouse | The recipe/product overrides the branch default. |
| POS selected warehouse | Cashier/terminal selected warehouse controls source. |
| Recipe-specific source warehouse | Each recipe/component may define its own source. |

Ingredient warning must include:

- Ingredient name.
- Required quantity.
- Available quantity.
- Source warehouse.
- Resulting balance after sale.
- Whether the sale is blocked, allowed with warning, or requires manager approval.

If negative stock is allowed for ingredients, the same negative stock badges, approval modal, alerts, estimated cost status, and settlement reports must apply to `RECIPE_CONSUME` movements.

# 10. Products Design

## 10.1 Product List

Table columns:

- Product name.
- Type.
- Category/group.
- Default sale price.
- Current stock.
- Stock status.
- Price tier coverage.
- Active/POS visible.
- Last updated.

Badges:

- Stock Item.
- Recipe.
- Ingredient.
- Service.
- Non-stock.
- Negative Stock.
- Low Stock.
- Estimated Cost.

## 10.2 Product Detail Layout

Recommended tabs:

1. Overview.
2. Units & Barcodes.
3. Prices.
4. Inventory.
5. Recipe / BOM.
6. Modifiers.
7. Suppliers.
8. Movement.
9. Settings.
10. Audit.

## 10.3 Product Type Selector

Product types:

- Stock Item.
- Recipe Product.
- Ingredient Item.
- Service / Non-stock.
- Modifier / Add-on.
- Bundle / Combo.
- Fixed Asset purchase-only behavior.

UI must explain impact:

| Type | Stock Impact | POS Behavior |
|---|---|---|
| Stock Item | Stock in/out | Can sell directly |
| Ingredient Item | Used in recipes | Usually not sold directly unless allowed |
| Recipe Product | Consumes ingredients | Sold as menu item |
| Service/Non-stock | No stock movement | Can be sold/charged |
| Fixed Asset | No stock movement | Purchase-side only |

## 10.4 ProductUnit Design

Each product can have multiple units/barcodes.

Fields:

- Unit.
- Barcode.
- SKU.
- Conversion factor.
- Default purchase price.
- Last purchase price.
- Default sale price.
- Is default sale unit.
- Is default purchase unit.
- Active.

Example:

```text
Product: Water
Unit 1: Bottle, barcode 123, conversion 1
Unit 2: Carton, barcode 456, conversion 24
```

## 10.5 ProductUnitTierPrice Grid

Price tiers are sale prices only.

Grid should be per ProductUnit row:

| Unit/Barcode | Default Price | VIP | Wholesale | Municipality | Staff |
|---|---:|---:|---:|---:|---:|
| Bottle / 123 | 10.00 | 9.00 | 8.50 | 8.00 | 7.50 |
| Carton / 456 | 220.00 | 210.00 | 200.00 | 195.00 | 190.00 |

Important:

- Do not put purchase price inside `ProductUnitTierPrice`.
- Purchase prices belong to ProductUnit or supplier-specific purchase pricing later.

## 10.6 Recipe / BOM Editor

Recipe Product tab should show:

- Ingredient lines.
- Quantity per unit.
- Unit conversion.
- Source warehouse rule.
- Optional wastage percentage.
- Estimated recipe cost.
- Margin preview.

Fields per ingredient:

- Ingredient item.
- Quantity.
- Unit.
- Source warehouse.
- Required/optional.

## 10.7 Modifier Editor

Modifier groups:

- Required / optional.
- Single-select / multi-select.
- Min/max selection.
- Price delta.
- Ingredient impact optional.

Examples:

- Size.
- Milk type.
- Extra shot.
- Toppings.

## 10.8 Product-Level Negative Stock Override

Add setting panel in product detail:

```text
Negative Stock Behavior
```

Options:

- Inherit tenant setting.
- Always block.
- Allow with warning.
- Allow with manager approval.
- Allow without approval if tenant allows.

For batch/expiry/serial products, show:

```text
Negative stock is blocked for this item due to batch/expiry/serial tracking.
```

---

# 11. Price Tiers and Customer Segments Design

## 11.1 Price Tier List

Price tiers examples:

- Default.
- VIP.
- Wholesale.
- Municipality.
- Staff.
- Special Guests.

Table columns:

- Name.
- Description.
- Active customers.
- Products priced.
- Default fallback behavior.
- Active status.

## 11.2 Price Tier Detail

Fields:

- Name.
- Code.
- Description.
- Active.
- Priority/fallback if needed.

Sections:

- Assigned customers.
- Product unit price grid.
- Audit history.

## 11.3 Assign Price Tier to Customer

Customer detail should include:

```text
Price Tier: Municipality
```

Changing customer tier should warn:

```text
Future POS sales for this customer will use Municipality prices where configured.
```

## 11.4 POS Price Tier Behavior

When customer selected:

- Display tier badge near customer.
- Update line prices based on ProductUnitTierPrice.
- If tier price missing, fallback to default sale price.
- Show “Default price used” hint for missing tier price if needed.

---

# 12. Customers Design

## 12.1 Customer List

Columns:

- Name.
- Phone.
- Price tier.
- AR balance.
- Credit limit.
- Status.
- Last sale.

Badges:

- VIP.
- Municipality.
- Over credit limit.
- Has credit.
- Inactive.

## 12.2 Customer Detail

Cards:

- Profile.
- AR balance.
- Credit limit.
- Price tier.
- Recent sales.
- Receipts.
- Statement.
- Advances / prepaid balance.
- Attachments.
- Audit.

## 12.3 Customer Statement

Statement must read from `CustomerARMovement`.

Columns:

- Date.
- Document.
- Type.
- Debit.
- Credit.
- Balance.
- Notes.

## 12.4 Customer Receipt UI

Fields:

- Customer.
- Payment method.
- Amount.
- Reference.
- Allocation method:
  - Manual invoice allocation.
  - Oldest unpaid first.
  - Unallocated customer credit.

Important:

- Customer receipt is not a new sale.
- If cash, it affects `customer_cash_receipts_total`, not `cash_sales_total`.

## 12.5 Customer Advance

Customer advance/prepaid balance UI:

- Receive payment before invoice.
- Show as customer credit.
- Later allocate to invoices.

Label:

```text
Customer credit available
```

Do not show as sales revenue until allocated through proper sale document behavior.

## 12.6 Walk-in / Anonymous

Walk-in sale behavior:

- Default POS customer is Walk-in.
- No customer required for normal cash/card takeaway.
- Walk-in earns no loyalty points.
- Walk-in cannot do credit sale.
- Walk-in cannot have price tier unless special quick customer selected.

---

# 13. Suppliers Design

## 13.1 Supplier List

Columns:

- Name.
- Phone.
- AP balance.
- Advance balance.
- Last purchase.
- Status.

## 13.2 Supplier Detail

Cards:

- Profile.
- AP balance.
- Supplier advance/prepaid balance.
- Purchase history.
- Payment history.
- Statement.
- Attachments.
- Audit.

## 13.3 Supplier Statement

Statement reads from `SupplierAPMovement`.

Columns:

- Date.
- Document.
- Type.
- Debit.
- Credit.
- Balance.

## 13.4 Supplier Payment UI

Fields:

- Supplier.
- Payment account.
- Amount.
- Reference.
- Allocation method:
  - Manual purchase invoice allocation.
  - Oldest unpaid first.
  - Supplier advance if overpaid.

Important:

- Supplier payment settles AP or creates supplier advance.
- Supplier payment is not automatically an expense unless the source document is an expense purchase line/document.

## 13.5 Supplier Advance

Supplier advance means:

```text
Money paid to supplier before invoice.
```

UI label:

```text
Supplier advance / prepaid balance
```

Do not show as normal AP payable.

---

# 14. Sales Design

## 14.1 Sales Invoice List

Columns:

- Invoice number.
- Date/time.
- Customer.
- Order type.
- Total.
- Payment status.
- Return status.
- Posting status.
- Sync status.
- Cashier.

Filters:

- Date range.
- Customer.
- Payment method.
- Payment status.
- Return status.
- Sync status.
- Cashier.
- Order type.

## 14.2 Sales Invoice Detail

Sections:

1. Header and status badges.
2. Customer/order information.
3. Line items.
4. Discounts/charges/tax/rounding.
5. Payment lines.
6. Movement effects.
7. Attachments.
8. Audit timeline.
9. Related returns/receipts.

## 14.3 Five Status Badges

Every sales document detail should show:

- `posting_status`: Draft / Posted / Cancelled / Void.
- `payment_status`: Unpaid / Partially Paid / Paid / Overpaid / N/A.
- `return_status`: Not Returned / Partially Returned / Returned.
- `approval_status`: Not Required / Pending / Approved / Rejected.
- `sync_status`: Synced / Pending Sync / Failed.

## 14.4 Sales Return Flow Design

Return with original invoice:

- Search/select invoice.
- Select lines/quantities.
- Show original price/tax/cost snapshot.
- Select refund method.
- Post return.

Return without invoice:

- Requires manager approval if setting demands.
- Uses configured costing behavior.
- Must show risk warning.

## 14.5 Manual Card Refund UI

Card refund fields:

- Original card payment reference.
- Refund terminal reference.
- Batch number.
- Refund status: pending/confirmed.
- Notes.

UI reminder:

```text
Card refund is recorded manually. Confirm refund on external terminal.
```

Card refund affects card settlement, not cashbox.

## 14.6 Cancelled Document Read-only Design

Cancelled/voided documents:

- Business fields read-only.
- Clear cancelled badge.
- Cancellation reason.
- Cancelled by/date.
- Reversal/related document links.
- Attachments allowed only with permission.
- Audit timeline always visible.

---

# 15. Purchases Design

## 15.1 Purchase Invoice List

Columns:

- Purchase number.
- Supplier.
- Date.
- Total.
- Payment status.
- Posting status.
- Receiving status if needed.
- Negative stock settlement indicator.
- User.

## 15.2 Purchase Invoice Form

Header fields:

- Supplier.
- Date.
- Branch.
- Warehouse.
- Reference number.
- Notes.

Line fields:

- Line type.
- Product/service/asset/expense.
- Quantity.
- Unit.
- Unit cost.
- Tax.
- Discount.
- Total.

Line types:

- Stock Item.
- Expense.
- Fixed Asset.
- Service.
- Non-stock Purchase.

## 15.3 Line Type UX

When line type changes, show effect preview:

| Line Type | UI Preview |
|---|---|
| Stock Item | Increases stock and inventory value |
| Expense | Records business expense, no stock |
| Fixed Asset | Creates fixed asset record, no stock |
| Service | Expense/service cost, no stock |
| Non-stock Purchase | Purchase record only, no stock unless configured |

## 15.4 Negative Stock Settlement Preview

If purchase line covers existing negative stock:

Show inline badge:

```text
Covers negative stock
```

Preview panel:

```text
Milk current balance: -5 L
Purchase quantity: 20 L
Negative quantity covered: 5 L
Final expected balance: 15 L
```

If estimated cost sales exist, show:

```text
This purchase may generate COGS adjustments after posting.
```

## 15.5 Purchase Detail

Sections:

- Supplier.
- Status badges.
- Lines grouped by type.
- Stock effects.
- Expense effects.
- Fixed asset effects.
- Supplier AP effects.
- Negative stock settlement effects.
- Attachments.
- Audit timeline.

## 15.6 Purchase Return

Purchase return UI:

- Prefer link to original purchase invoice.
- Show original cost snapshot.
- Allow unlinked return only if setting allows / manager approval.
- Show stock impact.
- Show supplier AP or refund effect.

---

# 16. Treasury / Finance Design

## 16.1 Treasury Overview

Treasury pages show money locations and movement, not full accounting ledger complexity.

Accounts:

- Cashbox.
- Main Safe.
- Bank Account.
- Card Settlement Account.
- Wallet Account.

## 16.2 Cashbox Accounts

Cashbox detail shows:

- Current balance.
- Active shift if linked.
- Cash sales.
- Customer cash receipts.
- Cash returns.
- Cash in/out.
- Expenses.
- Cash drops.
- Movement list.

## 16.3 Main Safe

Main Safe is manager/owner controlled.

UI actions:

- Receive cash drop.
- Transfer to bank.
- Transfer to cashbox.
- View movements.

Cash Drop is internal transfer, not expense.

## 16.4 Card Settlement Account

Card/Visa payment UI must route here.

Card settlement page shows:

- Pending card payments.
- Terminal batch reference.
- Settlement status.
- Expected amount.
- Settled amount.
- Variance.
- Bank deposit reference.

## 16.5 Wallet Account

Wallet settlement page shows:

- Provider.
- Pending wallet payments.
- Reference.
- Settlement status.
- Transfer to bank.

## 16.6 Expenses

Expense entry UI:

- Expense category.
- Amount.
- Payment account.
- Tax if applicable.
- Attachment.
- Notes.

Important:

- Damage/wastage is not entered here.
- Supplier payment is not automatically an expense.

## 16.7 Rounding Adjustment Visibility

Invoice detail and reports must show rounding amount separately.

Example:

```text
Subtotal: 100.03
Rounding: -0.03
Total Due: 100.00
```

Rounding must not silently modify revenue.

---

# 17. Fixed Assets Design

## 17.1 Fixed Asset Register

Columns:

- Asset code.
- Name.
- Category.
- Acquisition date.
- Acquisition cost.
- Book value.
- Status.
- Location.
- Assigned branch.

Examples:

- Coffee machine.
- Receipt printer.
- POS device.
- Tables.
- Chairs.
- Laptop.
- Fridge.

## 17.2 Asset Detail

Tabs:

1. Overview.
2. Purchase information.
3. Depreciation.
4. Maintenance.
5. Transfers.
6. Sale/write-off.
7. Attachments.
8. Audit.

## 17.3 Asset Purchase From Purchase Invoice

When purchase line type is Fixed Asset:

- Show asset creation panel.
- Require asset name/category.
- No stock movement.
- No immediate expense.
- Payment still affects cash/bank/AP.

## 17.4 Depreciation UI

MVP Extended.

Show:

- Acquisition cost.
- Salvage value.
- Useful life months.
- Monthly depreciation.
- Accumulated depreciation.
- Book value.
- Next depreciation date.

## 17.5 Maintenance / Transfer / Write-off

Maintenance:

- Maintenance cost.
- Vendor.
- Date.
- Attachment.

Transfer:

- From branch/location.
- To branch/location.
- Date.
- Reason.

Write-off:

- Reason.
- Current book value.
- Loss preview.
- Manager approval required.

---

# 18. Loyalty Design

## 18.1 Phase Rule

Loyalty full functionality is MVP Extended.

MVP Core can show:

- Placeholder hooks.
- Customer points badge if configured later.
- Disabled loyalty panel with “Coming in MVP Extended” label.

## 18.2 Loyalty POS Panel

MVP Extended panel shows:

- Customer points.
- Earn estimate.
- Redeem amount.
- Redemption rules.
- Expiry warning.

Important:

- No customer = no points.
- Walk-in does not earn points.
- Redemption is discount/reward, not payment.

## 18.3 Loyalty Settings

Fields:

- Enable loyalty.
- Points earning rule.
- Redemption rule.
- Expiry.
- Minimum spend.
- Exclude tax from earning.
- Exclude redeemed/free amount from earning.

## 18.4 Loyalty Transactions

Show:

- Earned.
- Redeemed.
- Reversed.
- Expired.
- Manual adjustment.
- Related document.

---

# 19. Reports Center Design

## 19.1 Reports Principle

Reports must clearly communicate that they are ledger-driven.

Do not design reports as simple UI aggregates from current screen state.

## 19.2 Reports Center Layout

Use report cards grouped by area:

- Sales.
- Shift & Cashier.
- Treasury.
- Inventory.
- Customers.
- Suppliers.
- Fixed Assets.
- Tax.
- Logs.
- Negative Stock.

Each report card shows:

- Name.
- Short description.
- Key source ledger.
- Last generated / export action.

## 19.3 Required Reports

Required report cards:

- Sales Summary.
- P&L.
- Shift Report.
- Cashbox Movement.
- Card Settlement.
- Wallet Settlement.
- Customer Statement.
- Supplier Statement.
- Inventory Movement.
- Stock Valuation.
- Damage/Wastage.
- Negative Stock Alerts.
- Negative Stock Settlement.
- Estimated Cost Sales.
- COGS Adjustment.
- Tax Summary.
- Fixed Asset Register.
- Depreciation.
- Audit Log.
- Access Log.
- Operations Log.

## 19.4 P&L Report Design

P&L layout:

```text
Net Sales Revenue
- Discounts / Returns / Loyalty Redemption
= Net Revenue excluding Tax
- COGS
- Recipe COGS
- Inventory Loss / Wastage
= Gross Profit
- Operating Expenses
- Depreciation Expense
- Rounding Adjustments
= Net Profit
```

Important:

- Tax is not revenue.
- Customer receipts are not sales.
- Supplier payments are not expenses by themselves.
- Damage/wastage appears as inventory loss.

## 19.5 Negative Stock Reports

### Negative Stock Alerts Report

Columns:

- Product.
- Warehouse.
- Current negative qty.
- First negative date.
- Last sale/document.
- Estimated cost exposure.
- Status.

### Negative Stock Settlement Report

Columns:

- Settlement date.
- Purchase invoice.
- Product.
- Negative qty covered.
- Final balance.
- Affected movements.
- Cost difference.

### Estimated Cost Sales Report

Columns:

- Sale invoice.
- Product/ingredient.
- Qty.
- Estimated cost method.
- Estimated cost.
- Settlement status.

### COGS Adjustment Report

Columns:

- Adjustment document.
- Product.
- Original sale.
- Purchase invoice.
- Estimated cost.
- Actual cost.
- Difference.
- Posted period.

---

# 20. Settings Design

## 20.1 Settings Layout

Settings should use grouped cards similar to the prototype.

Recommended groups:

- Company / Tenant.
- Branches.
- Warehouses.
- POS Settings.
- Inventory Settings.
- Negative Stock Control.
- Shift Settings.
- Payment Methods.
- Tax Settings.
- Rounding Settings.
- Document Numbering.
- Account Mapping.
- Price Tiers.
- Loyalty Settings.
- Permissions.
- Hardware / Printers.
- Offline / Sync.
- Subscription / Billing.

## 20.2 Settings UI Rules

- Use toggles for enable/disable.
- Use dropdowns for behavior options.
- Use helper text to explain business impact.
- Show warnings for settings that affect reporting or financial behavior.
- Changing critical settings requires permission and audit.
- Some settings may be locked after first posting or period lock.

## 20.3 Inventory Settings

Include:

- Default warehouse.
- Ingredient source warehouse rule.
- Low stock threshold behavior.
- Negative Stock Control.
- Stock adjustment approval thresholds.
- Damage/wastage approval thresholds.
- Batch/expiry/serial settings in Phase 2.

## 20.4 POS Settings

Include:

- Default POS mode.
- Require active shift before sale.
- Default order type.
- Customer required for delivery.
- Customer required for credit.
- Enable mixed payments.
- Enable manual card reference.
- Enable wallet reference.
- Print receipt automatically.
- Kitchen/bar print routing.

## 20.5 Payment Methods Settings

Each payment method should configure:

- Enabled.
- Display name.
- Linked account type.
- Linked account.
- Requires reference.
- Allowed in POS.
- Allowed in refunds.

Linked account types:

- Cashbox.
- Bank Account.
- Card Settlement.
- Wallet Account.

---

# 21. Account Mapping Design

## 21.1 Account Mapping Purpose

SuperPOS ERP Lite is not a full accounting ERP, but it needs mapping so business effects are not hardcoded.

Settings → Account Mapping should show business-friendly account categories.

## 21.2 Account Mapping Fields

Include UI for:

- Sales Revenue account.
- COGS account.
- Inventory account.
- Tax Payable account.
- Cashbox account.
- Bank account.
- Card Settlement account.
- Wallet account.
- AR control account.
- AP control account.
- Fixed Asset account.
- Accumulated Depreciation.
- Depreciation Expense.
- Inventory Loss.
- Loyalty Discount.
- Rounding Adjustment.

## 21.3 AR/AP Double Counting Warning

Show explanation:

```text
CustomerARMovement and SupplierAPMovement are the detailed sources of truth.
Mapped AR/AP accounts are summary/control accounts only and must not create duplicate report totals.
```

## 21.4 Missing Mapping State

If a required mapping is missing:

- Block posting if necessary.
- Show clear error.
- Link to Account Mapping settings.

Example:

```text
Cannot post invoice. Tax Payable account is not configured.
```

---

# 22. Document Detail Design

## 22.1 Universal Document Detail Layout

Every document detail screen should show:

- Document number.
- Five status badges.
- Customer/supplier/party.
- Branch.
- Date/time.
- User.
- Lines.
- Tax breakdown.
- Payment lines.
- Posting snapshot summary.
- Movement ledger links.
- Attachments.
- Audit timeline.
- Approval history.
- Related documents.
- Sync status.
- Permission-based actions.

## 22.2 Movement Links

Movement effect card should show:

- Stock movements.
- Financial account movements.
- Customer AR movements.
- Supplier AP movements.
- Shift summary effects.
- Fixed asset ledger effects.
- Loyalty transactions if applicable.

Each movement row can open detail drawer.



Movement links must be visible because reports are ledger-driven, not UI-state-driven.

Document detail should provide drill-down links to the movements created by posting:

| Document Type | Movement Links to Show |
|---|---|
| Sales Invoice | StockMovement, FinancialAccountMovement, CustomerARMovement when credit, ShiftMovementSummary, tax breakdown. |
| Sales Return | Reverse stock/tax/revenue/COGS movements and refund/payment movements. |
| Purchase Invoice | StockMovement for stock lines, SupplierAPMovement for credit, FixedAssetLedger for fixed asset lines, expense/financial movements. |
| Purchase Return | SupplierAPMovement, StockMovement, financial refund/payment movement when applicable. |
| Customer Receipt | CustomerARMovement plus Cashbox/Bank/Card/Wallet movement depending on method. |
| Supplier Payment | SupplierAPMovement plus Cashbox/Bank movement. |
| Damage/Wastage | StockMovement DAMAGE_OUT and Inventory Loss movement; no cash drawer expense movement. |
| Cash Drop | Cashbox decrease and Main Safe increase; no P&L movement. |
| Fixed Asset Event | FixedAssetLedger and related financial movement. |
| Negative Stock Settlement | Settlement link between purchase movement and older negative stock movements, plus COGS adjustment if applicable. |

The design must not imply that reports are calculated directly from editable invoice UI fields.

## 22.3 Posted / Cancelled Safety

Posted documents:

- Business fields read-only.
- Allow actions only through business flows: return, cancel, reversal, receipt/payment allocation.

Cancelled documents:

- Read-only business fields.
- Attachments can be added with permission.
- Audit timeline visible.

---

# 23. Attachments Design

## 23.1 Attachment Panel

Attachment panel appears on supported entities:

- Purchase invoice.
- Expense.
- Fixed asset.
- Maintenance.
- Supplier payment.
- Customer receipt.
- Sales return.
- Shift close.
- Card settlement.
- Cancelled documents with permission.

## 23.2 Attachment List

Show:

- File icon.
- Filename.
- Type.
- Uploaded by.
- Upload date.
- Notes.
- Preview/download action.
- Delete action if permission allows.

## 23.3 Attachment Rules

- Upload creates AuditLog.
- Delete creates AuditLog.
- Tenant-scoped storage path.
- Cancelled documents allow attachments with permission.
- Business fields remain locked.

---



## 23.4 Attachments on Cancelled Documents

Cancelled documents are read-only for business fields, but attachments can still be useful as supporting evidence.

Design rules:

- A cancelled document must keep all financial, inventory, tax, party, and line fields locked.
- The attachment panel remains visible if the user has permission.
- Upload action appears only for users with the relevant attachment permission.
- The upload dialog should require an attachment category or note when the document is cancelled.
- Allowed examples:
  - cancellation proof
  - supplier refund proof
  - card refund reference
  - customer signed return proof
  - management approval evidence
- Upload/delete actions must create AuditLog entries.
- Attachment changes must not change posting status, payment status, return status, approval status, stock movements, or financial movements.

This section is intentionally separate to prevent AI coding tools from treating cancelled documents as fully editable.

# 24. Offline / Sync Design

## 24.1 Offline Banner

Use prototype-style banner:

```text
Offline mode active. Transactions are saved locally and will sync when connection returns.
3 pending
```

## 24.2 Sync Badges

Badges:

- Synced.
- Pending Sync.
- Sync Failed.
- Conflict.

## 24.3 Pending Sync Queue

Queue view:

- Local document number.
- Action type.
- Created time.
- User.
- Status.
- Retry count.
- Error message.
- Retry action.


## 24.4 Idempotency and Safe Retry UX

The UI must make retries feel safe and must never encourage duplicate posting.

Design requirements:

- Every locally created critical document should show a local pending reference while offline.
- Pending sync rows should show status, created time, user, terminal, and retry state.
- If the user clicks retry, show messaging such as: "Retry is safe. The system will not create duplicate invoices." 
- Do not expose raw technical keys to normal cashiers, but admin/debug detail panels may show:
  - `idempotency_key`
  - `client_transaction_id`
  - `device_id`
  - local sequence
  - last sync attempt
  - server response summary
- If the server already accepted the same idempotency key, the UI must mark the local item as Synced and link it to the existing server document instead of showing an error.
- If sync fails after posting partially, the UI must use "Needs Review" and route to conflict review instead of allowing blind repost.

Idempotency wording must be consistent across POS, purchases, stock adjustments, shift close, payments, returns, cash movements, and offline queue screens.

## 24.5 Conflict Review Screen

Conflict screen shows:

- Local action.
- Server state.
- Conflict reason.
- Suggested resolution.
- Manager action.

## 24.6 Subscription Offline State

If cached subscription is valid:

- Allow within grace.
- Show small notice.

If cached expired/suspended:

- Block new sales.
- Allow limited settings/billing view.

---

# 25. Manager Approval UX

## 25.1 Approval Modal

Approval modal fields:

- Reason for approval.
- Manager username/PIN/password.
- Summary of risky action.
- Impact preview.
- Approve / Reject buttons.

## 25.2 Approval Triggers

Triggers:

- High discount.
- Negative stock.
- Stock adjustment.
- Shift variance.
- Credit limit override.
- Return without invoice.
- Cash drop threshold.
- Asset write-off.
- Period lock override.
- Unlinked purchase return.
- Opening cash variance.

## 25.3 Approval History

Show approval history badge on related document.

Audit timeline event:

```text
Approved by Manager Name · reason · timestamp
```

Rejected action should not post.

---

# 26. Status, Badge, and Color System

## 26.1 Document Status Badges

| Status | Color |
|---|---|
| Draft | Gray |
| Posted | Success |
| Cancelled | Danger |
| Void | Danger |
| Paid | Success |
| Partially Paid | Warning |
| Unpaid | Gray/Warning |
| Overpaid | Info |
| Returned | Danger/Gray |
| Partially Returned | Warning |
| Pending Approval | Warning |
| Approved | Success |
| Rejected | Danger |
| Synced | Success |
| Pending Sync | Warning |
| Sync Failed | Danger |

## 26.2 Operational Badges

| Badge | Meaning |
|---|---|
| Negative Stock | Stock balance below zero |
| Estimated Cost | Cost is temporary/estimated |
| Settled | Negative stock or card batch settled |
| Needs Review | Manager review required |
| Wastage | Inventory loss document/line |
| Inventory Loss | Loss impact shown in reports |
| Card Settlement Pending | Card money not yet settled to bank |
| Subscription Warning | Trial/grace/expired notice |
| Offline | Device not connected |

---

# 27. Empty / Error / Warning States

## 27.1 Empty States

Examples:

- Empty cart.
- No products.
- No customers.
- No stock movements.
- No reports yet.
- No attachments.

Empty state should include:

- Icon.
- Clear title.
- Short explanation.
- Primary action if relevant.

## 27.2 Error States

Examples:

- Product not found.
- Missing account mapping.
- Permission denied.
- Sync failed.
- Printer failed.
- Period locked.
- Subscription expired.

## 27.3 Warning States

Warnings:

- Insufficient stock blocked.
- Negative stock allowed.
- Estimated cost used.
- Credit limit exceeded.
- Shift variance exceeded.
- Missing price tier price.
- Missing recipe ingredient.

Warnings should explain business impact, not only technical error.

---

# 28. Responsive Design

## 28.1 Desktop Admin

- Full sidebar.
- Two-column settings pages.
- Wide tables.
- Detail pages with side panels.

## 28.2 Tablet POS

- Sidebar collapsible.
- Touch targets larger.
- Product grid optimized.
- Cart remains visible.

## 28.3 Small Laptop

- Reduce summary cards per row.
- Keep barcode input visible.
- Allow table horizontal scroll.

## 28.4 Mobile Manager View

Limited mobile support:

- Dashboard summary.
- Approvals.
- Reports summary.
- Alerts.
- No full POS cashier workflow unless scoped later.

---

# 29. RTL / Arabic Design

## 29.1 RTL Rule

The UI must support RTL layout from the beginning.

RTL behavior:

- Sidebar on right.
- Text aligned right.
- Icons mirror only where directionally meaningful.
- Tables keep numeric columns readable.
- Money remains tabular.
- Mixed English identifiers remain LTR where needed.

## 29.2 Arabic Labels

Common Arabic labels:

| English | Arabic |
|---|---|
| Point of Sale | نقطة البيع |
| Sales | المبيعات |
| Purchases | المشتريات |
| Customers | العملاء |
| Suppliers | الموردون |
| Inventory | المخزون |
| Treasury | الخزينة / المالية |
| Reports | التقارير |
| Settings | الإعدادات |
| Open Shift | فتح وردية |
| Close Shift | قفل وردية |
| Negative Stock | مخزون سالب |
| Card Settlement | تسوية كروت |
| Wastage | هالك |

## 29.3 Currency and Numbers

- Support EGP display.
- Use locale-aware separators.
- Keep internal identifiers in English when necessary.
- Receipt must support Arabic business name and item names.

---

# 30. Hardware UX Design

## 30.1 Barcode Scanner

- Barcode input stays focused.
- Scanner feedback beep/flash.
- Product not found warning.
- Scale barcode support in relevant mode.

## 30.2 Receipt Printer

Printer states:

- Ready.
- Printing.
- Failed.
- Offline.

Printer failure must not cancel posted document.

## 30.3 Kitchen / Bar Printers

Show routing status:

- Sent to kitchen.
- Sent to bar.
- Failed.
- Retry.

## 30.4 Cash Drawer

Drawer opens after cash sale posting.

If drawer fails:

- Show warning.
- Record OperationsLog.
- Do not cancel sale.

## 30.5 Card Terminal

MVP is manual recording.

UI should say:

```text
Take payment on external terminal, then record reference here.
```

Direct terminal integration is Phase 2.

---

# 31. Security and Permission UX

## 31.1 Permission-Based UI

Actions hidden or disabled based on permissions.

If disabled, show reason:

```text
You do not have permission to cancel posted invoices.
```

## 31.2 Sensitive Reports

Accessing sensitive reports may write AccessLog:

- P&L.
- Customer statements.
- Supplier statements.
- Exported data.
- Audit logs.

UI should show export permission clearly.

## 31.3 Safe Destructive Actions

Destructive actions require:

- Clear confirmation.
- Reason.
- Permission.
- Audit.
- Manager approval if configured.

---

# 32. Design Acceptance Criteria

## 32.1 POS Usability

- Cashier can start sale from barcode input without mouse.
- Touch café mode supports product/modifier selection quickly.
- Cart totals are always visible.
- Payment routing is clear.
- Credit sale requires customer.
- Negative stock warning is clear and not confused with customer credit.

## 32.2 Shift Workflow

- If shift required and no shift active, POS is blocked.
- Open shift captures expected and actual opening cash.
- Close shift separates cash sales, customer cash receipts, card, wallet, credit, expenses, cash drops, and wastage.
- Wastage is not included in drawer cash formula.

## 32.3 Payment Routing

- Cash appears in cashbox/drawer.
- Card/Visa appears in Card Settlement.
- Wallet appears in Wallet Account.
- Credit appears in Customer AR.
- Loyalty redemption appears as discount/reward, not payment.

## 32.4 Negative Stock

- Negative stock setting exists and is discoverable.
- POS shows warning before allowing negative stock if enabled.
- Manager approval is requested when configured.
- Product-level override exists.
- Purchase invoice shows settlement preview when covering negative stock.
- Estimated cost and COGS adjustment reports are represented.

## 32.5 Inventory Movement Visibility

- Every stock-affecting document links to stock movements.
- Damage/wastage shows inventory loss effect.
- Warehouse transfers show no P&L impact.
- Reports read from movement ledgers.

## 32.6 Settings Discoverability

- Settings are grouped by business area.
- Critical settings have helper text.
- Missing mapping/settings errors link to the right settings page.

## 32.7 Manager Approval

- Approval modal explains the risky action.
- Reason and manager credential are required.
- Approval history appears on the document.
- Rejected actions do not post.

## 32.8 Reports Readability

- P&L excludes tax from revenue.
- Customer receipts are not sales.
- Supplier payments are not expenses by themselves.
- Card settlement is separate from cashbox.
- Negative stock and estimated cost are reportable.

## 32.9 RTL Readiness

- App can render in Arabic RTL.
- Sidebar/header/table alignment works.
- Currency and numbers remain readable.
- Receipts support Arabic.

## 32.10 Offline / Sync Clarity

- Offline banner appears when disconnected.
- Pending documents show Pending Sync.
- Failed sync shows retry and error details.
- Subscription cache state is visible.
- Idempotent retry messaging prevents duplicate fear.

## 32.11 Posted/Cancelled Safety

- Posted documents are read-only.
- Cancelled documents are read-only.
- Attachments may be added to cancelled documents only with permission.
- Corrections happen through returns/reversals/adjustments, not direct edits.

---


# 33. Business Consistency Matrix

This matrix exists to keep DESIGN.md aligned with PRD.md, FLOW.md, and DOMAIN.md.

| Business Rule | Required Design Reflection |
|---|---|
| PRD defines ERP Lite scope | UI avoids full accounting complexity and keeps accounting impact explainable. |
| FLOW defines posting transaction boundary | UI shows posting result, movement links, and prevents partial-user edits after posting. |
| DOMAIN defines business terms | UI labels must not confuse Credit Sale, Negative Stock Sale, Cashbox, Card Settlement, Main Safe, Wallet, Wastage, and Expense. |
| Card/Visa MVP is manual | POS captures external terminal reference and routes to Card Settlement, not Cashbox. |
| Shift is a workflow | Shift is accessed from POS/header/profile dropdown, not as sidebar module. |
| Customer receipts are not sales | Shift and reports display customer_cash_receipts_total separately from cash_sales_total. |
| Damage/Wastage is inventory loss | UI shows wastage_total and Inventory Loss; it is not a cash drawer expense. |
| Negative stock is settings-controlled | UI exposes toggles, product override, warning, approval, alerts, settlement, estimated cost, and COGS adjustment reports. |
| ProductUnitTierPrice is sale-price-only | Product price tier grid never places purchase price inside ProductUnitTierPrice. |
| Fixed Asset is not inventory/expense at purchase | Purchase line UI routes Fixed Asset lines to FixedAsset and asset register screens. |
| Tax is not revenue | Invoice and reports show net revenue separate from Tax Payable. |
| Rounding is explicit | Invoice total shows rounding_amount and reports expose Rounding Adjustment. |
| Loyalty full flow is MVP Extended | Core UI can show placeholders/hooks; full earning/redemption is not forced into MVP Core. |
| Attachments on cancelled documents are allowed with permission | Cancelled documents stay read-only while attachment panel remains permission-controlled. |
| Offline sync uses idempotency | Pending sync/retry UI communicates duplicate-safe retry and exposes technical details only to admin/debug views. |
| Reports are ledger-driven | Reports and document details link to movement ledgers rather than implying UI-field calculations. |
| Period lock protects history | Locked-period documents show read-only state and reversal-only correction guidance. |
| Manager approvals are auditable | Approval modal requires reason and records approval history. |

# 34. Out-of-Scope / Not Yet Added Design Notes

The following ideas were discussed but are not part of the current PRD/FLOW/DOMAIN baseline unless added later:

- Complimentary / Hospitality Orders as a formal separate order type.
- Full restaurant table management and split billing.
- Full pharmacy compliance workflow.
- Full gym membership lifecycle.
- Direct card terminal integration.

If any of these become required, update PRD.md first, then FLOW.md, DOMAIN.md, and finally DESIGN.md.

# 35. Final Implementation Notes for AI Coding Tools

---

# 36. Table Service & Open Orders Design — [MVP Core for Cafés]

## 36.1 Entry Point

When `table_service_enabled = true`, POS Touch mode starts with the **Table Grid** instead of the Product Grid.

The cashier/waiter first selects a table, then manages the order on that table.

The normal Product Grid is still reachable from within an Open Order (to add items).

## 36.2 Table Grid Screen

The Table Grid is the home screen for table service mode.

```
┌─────────────────────────────────────────────────────────────────┐
│ Point of Sale · Main Hall · POS-01             ● Online        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  MAIN HALL                                                      │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐      │
│  │   TABLE 01    │  │   TABLE 02    │  │   TABLE 03    │      │
│  │  ● Occupied   │  │  ○ Available  │  │  🧾 Needs    │      │
│  │  4 items      │  │               │  │    Bill       │      │
│  │  180.00 EGP   │  │               │  │  210.90 EGP  │      │
│  │  35 min       │  │               │  │  52 min       │      │
│  └───────────────┘  └───────────────┘  └───────────────┘      │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐                         │
│  │   TABLE 04    │  │   TABLE 05    │                         │
│  │  🍳 Kitchen   │  │  ○ Available  │                         │
│  │  Sent         │  │               │                         │
│  │  45.00 EGP    │  │               │                         │
│  │  18 min       │  │               │                         │
│  └───────────────┘  └───────────────┘                         │
│                                                                 │
│  TERRACE                                                        │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐                         │
│  │   TABLE 06    │  │   TABLE 07    │                         │
│  │  ○ Available  │  │  ○ Available  │                         │
│  │               │  │               │                         │
│  └───────────────┘  └───────────────┘                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Table Card States

| Status | Color | Icon | Shows |
|---|---|---|---|
| available | Neutral/white | ○ | Table number only |
| occupied | Success-tinted | ● green dot | Items count, total, elapsed time |
| sent_to_kitchen | Warning-tinted | 🍳 | "Kitchen Sent", total, elapsed time |
| needs_bill | Brand-tinted | 🧾 | "Needs Bill", total, elapsed time (prominent) |

### Table Card Rules

- Minimum size: 140px × 120px (large enough to tap)
- Elapsed time turns amber after 30 min (configurable warning threshold)
- Elapsed time turns red after 60 min (configurable alert threshold)
- Clicking an available table → opens a new order immediately
- Clicking an occupied/sent/needs_bill table → opens the existing order

### Section Navigation

If the venue has multiple DiningSections:
- Show section headers as separators within the grid
- Or use tabs at the top for section switching

## 36.3 OpenOrder Detail Screen

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Tables  │  Table 01 · Main Hall · 35 min  │  Ahmed H.       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ITEM                       QTY   STATUS      TOTAL            │
│  ──────────────────────────────────────────────────────────    │
│  Iced Mocha                 ×2    ✓ Sent      90.00            │
│  Cappuccino                 ×1    🍳 Sent     35.00            │
│  Chocolate Cake             ×2    ✓ Sent      60.00            │
│  ──────────────────────────────────────────────────────────    │
│  [Draft] Lemon Tart         ×1    ✏ Draft     22.00  [✕]      │
│          Edit qty: [−] 1 [+]                                   │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  Kitchen Tickets                                               │
│  🎫 #1 · 14:33 · Bar    ✓  2x Iced Mocha                      │
│  🎫 #2 · 14:45 · Bar    🍳  1x Cappuccino                     │
│  🎫 #3 · 14:50 · Kitchen ✓  2x Chocolate Cake                 │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│  Subtotal:                                      207.00         │
│  Tax 14%:                                        28.98         │
│  Total:                                         235.98         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [+ Add Items]    [Send to Kitchen ▶]    [🧾 Needs Bill]       │
│                                                                 │
│                              [Pay →]                           │
└─────────────────────────────────────────────────────────────────┘
```

### Line Item Badges

| Badge | Color | Meaning |
|---|---|---|
| ✏ Draft | Gray | Not sent yet — editable |
| ✓ Sent | Success green | In kitchen queue |
| 🍳 Sent | Warning amber | Sent — preparing |
| ✗ Cancelled | Danger red strikethrough | Removed from order |

### Action Button Rules

| Button | Visible When | Enabled When |
|---|---|---|
| Send to Kitchen | Always | At least one Draft line exists |
| Needs Bill | Occupied / Sent | No draft lines (or warn if drafts exist) |
| Pay | Always | Order has at least one billed line |
| + Add Items | Always | Order is not paid/cancelled |

## 36.4 Line Item Actions

### Draft Lines
- Show [−] [+] quantity controls inline
- Show [✕] delete button (no confirmation needed, no AuditLog)
- Tapping the line name → opens edit panel (qty, notes)

### Sent Lines (Normal Cashier/Waiter)
- Read-only — no edit or delete controls shown
- Status badge only
- Tapping the line → shows detail modal (read only)

### Sent Lines (Manager)
- Read-only by default
- Long press or [⋮] menu → shows "Cancel Item" option
- Triggers Cancel Sent Item flow (§28.8 in FLOW.md)

## 36.5 Add Items Panel

When cashier presses [+ Add Items]:
- Opens the normal POS Touch Product Grid as a slide-over or bottom sheet
- Category navigation + product tiles
- Modifier popup if needed
- Selected items return to the OpenOrder as Draft lines
- User does not leave the OpenOrder Detail context

## 36.6 Send to Kitchen Button Behavior

```
[Send to Kitchen ▶] pressed:
  ↓
If no draft lines:
  Button disabled (grayed out, tooltip: "No new items to send")

If draft lines exist:
  Show quick confirmation:
  "إرسال للمطبخ: [N] عنصر جديد"
  [Confirm] [Cancel]
  ↓
On confirm → backend flow runs (§28.5 in FLOW.md)
  ↓
Success:
  Draft lines change to Sent badge (animated)
  New KitchenTicket appears in history
  Toast: "تم الإرسال للمطبخ ✓"

Printer failure:
  Toast: "⚠️ فشل الطباعة — تم تسجيل الطلب"
  [Retry Print] option in kitchen ticket history
```

## 36.7 Cancel Sent Item Modal (Manager)

```
┌────────────────────────────────────────────────┐
│ إلغاء صنف مُرسل — موافقة المدير               │
├────────────────────────────────────────────────┤
│                                                │
│ الصنف:    Cappuccino × 1                       │
│ الحالة:   تم الإرسال للمطبخ                    │
│                                                │
│ السبب:                                         │
│ [________________________________]             │
│                                                │
│ كلمة مرور المدير:                              │
│ [________________________________]             │
│                                                │
│           [إلغاء]        [موافقة وإلغاء الصنف]│
└────────────────────────────────────────────────┘
```

## 36.8 Remove Prepared Item from Bill Modal (Manager)

```
┌────────────────────────────────────────────────┐
│ إزالة من الفاتورة — موافقة المدير              │
├────────────────────────────────────────────────┤
│                                                │
│ الصنف:    Chocolate Cake × 2                   │
│ الحالة:   تم التحضير / تم التقديم             │
│                                                │
│ ⚠️ تم تحضير هذا الصنف. اختر الإجراء:          │
│                                                │
│  ● مجانية (Complimentary)                      │
│    تم تقديمه للعميل — لن يُدرج في الفاتورة    │
│                                                │
│  ○ هالك (Wastage)                              │
│    لم يُقدَّم — خسارة مخزون                   │
│                                                │
│ السبب:                                         │
│ [________________________________]             │
│                                                │
│ كلمة مرور المدير:                              │
│ [________________________________]             │
│                                                │
│     [إلغاء]          [موافقة وإزالة]           │
└────────────────────────────────────────────────┘
```

## 36.9 Pay Screen from Open Order

When cashier presses [Pay →]:
- Opens the same Payment Panel as normal POS (§5.6 in DESIGN.md)
- Shows only the billed lines (sent/prepared/served — not cancelled)
- Customer selector available (for loyalty, credit, tier pricing)
- All payment methods available
- On completion → receipt prints, table becomes Available

## 36.10 Manager Table View

Manager sees all tables in all sections from any device.

Additional columns/info visible to manager (not waiter):
- Who opened the order
- Time since last activity
- Total cancellations on this order
- Any manager approvals given

Manager Dashboard card:
```
Open Orders          5 tables
Needs Bill           2 tables
Avg. table time      28 min
Complimentary today  3 items · 85 EGP
```

## 36.11 Kitchen Ticket Format

```
┌──────────────────────────────────────┐
│ TABLE 01 · Main Hall                │
│ Ticket #2 · 14:45                   │
│ Waiter: Ahmed H.                    │
├──────────────────────────────────────┤
│ 1× Cappuccino                       │
│   Oat milk                          │
│   Extra shot                        │
│   No sugar                          │
│                                     │
│ 2× Iced Mocha                       │
│   Extra caramel                     │
└──────────────────────────────────────┘
```

### Cancellation Appendix Ticket

```
┌──────────────────────────────────────┐
│ *** CANCEL — TABLE 01 ***           │
│ Ticket #2 · Cancelled 14:52         │
├──────────────────────────────────────┤
│ CANCEL: 1× Cappuccino               │
│ Reason: Customer changed mind       │
│ Approved by: Manager                │
└──────────────────────────────────────┘
```

## 36.12 Design Rules for Table Service

- Table cards use the existing Card component — just with status-colored top border or background tint
- Status badges follow the global badge system (§26 in DESIGN.md)
- All cancellation modals require both reason text AND manager credential — two separate fields, no shortcuts
- Draft items have a visual distinction (lighter, dashed border, or edit icons) vs sent items (solid, locked)
- Sent items must look clearly locked — no edit affordances visible to non-managers
- The [Send to Kitchen] button is primary-colored only when draft items exist; otherwise ghost/disabled
- The [Pay →] button is always primary-colored as long as the order has billed lines
- Elapsed time warning colors: neutral → amber at threshold → red at alert threshold
- Kitchen ticket history is collapsed by default, expandable

## 36.13 Business Consistency Rules for UI

- Never show a sent item as editable to a non-manager
- Never show a Pay button on an order with only draft lines (force Send to Kitchen first or allow direct pay with implicit send)
- Never allow payment to include cancelled or voided lines in the total
- Complimentary and Wastage are always visible in the manager view of the order — not hidden
- The Table Grid must refresh in real time (WebSocket or polling) so all users see current table state

---

When generating screens from this DESIGN.md:

1. Preserve the SuperPOS visual direction.
2. Do not invent new business rules from the old prototype.
3. Follow PRD/FLOW/DOMAIN for all business behavior.
4. Treat settings as business controls.
5. Keep shift workflow outside sidebar navigation.
6. Keep Card/Visa separate as Card Settlement.
7. Keep Damage/Wastage separate from cash expenses.
8. Keep Negative Stock Sale separate from Credit Sale.
9. Show movement effects on posted documents.
10. Make every risky action permission and audit aware.
11. Keep Open Order separate from Sales Invoice — no financial effects until payment.
12. Never show edit controls on sent lines to non-managers.
13. Always require both reason and manager credential for cancellation of sent/prepared items.

---

*SuperPOS ERP Lite — DESIGN.md v3.6*  
*Last Updated: June 2026*  
*Based on: PRD/FLOW/DOMAIN v3.6 with Negative Stock Control & Settlement & Table Service*  
*Prototype: SuperPOS.html visual reference only*  
*Status: Draft — Consistency-Audited with PRD/FLOW/DOMAIN*
