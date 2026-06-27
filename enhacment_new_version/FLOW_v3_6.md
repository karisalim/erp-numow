# 🔄 SuperPOS ERP Lite — Business Logic & Workflows (FLOW.md)

**Version:** 3.6  
**Last Updated:** June 2026  
**Scope:** All business workflows, state machines, and posting rules  
**Based on:** PRD v3.6 with Negative Stock Control & Settlement

---

## 📌 Overview & Principles

This document defines **how the system works** — not what it looks like (DESIGN.md), but how data flows, what rules govern every action, and what happens in the database when a user does something.

**Principle 1: Every process is a state machine.**  
Every document moves through well-defined states. Every transition has prerequisites, effects, and audit records.

**Principle 2: Every state change writes to movement ledgers.**  
Reports read from ledgers (StockMovement, FinancialAccountMovement, CustomerARMovement, etc.) — not from document state fields. This keeps reports accurate regardless of what UI state a document is in.

**Principle 3: Every document posting is one atomic transaction.**  
All effects — stock, financial, customer balance, shift totals, audit log, snapshot — commit together or all roll back. No partial postings.

**Principle 4: Every state-changing POST carries an idempotency key.**  
`idempotency_key` (UUID) is generated on the client before sending. The server checks it before processing. Duplicate = return existing record (200 OK). This applies online AND offline — prevents double-submit and offline sync duplicates.

**Principle 5: Settings control behavior, not hardcoded logic.**  
Every place where behavior could vary by business type is controlled by a setting. The flows below indicate which setting is checked at each decision point.

**Principle 6: Audit Log covers state-changing events only.**  
Reads, list views, and report loads do NOT write to AuditLog. Sensitive reads write to AccessLog. System/hardware events write to OperationsLog.

**Principle 7: Outbox pattern for post-commit side effects.**  
Loyalty points and async notifications are created as pending outbox records INSIDE the transaction, then processed after commit by Celery. This guarantees they cannot be lost.

---

## 🔐 1. Authentication & Session Flows

### 1.1 User Login Flow

```
User submits email + password
  ↓
API validates credentials
  ├─ Invalid → HTTP 401 (wrong email or password)
  │             AuditLog: failed_login (too many → alert)
  └─ Valid →
       Load: user_id, tenant_id, branch_id, role, permissions[]
       Generate: JWT access token (15 min, payload includes above)
       Generate: Refresh token (30 days, stored httpOnly cookie)
       Create UserSession:
         {device_id, user_id, tenant_id, login_timestamp,
          ip_address, user_agent, status: active}
       AuditLog: user_login
       ↓
       Return: JWT + user profile + permissions + tenant config
```

### 1.2 JWT Token Management

```
Access Token (15 min expiry):
  Payload: user_id, tenant_id, branch_id, role, permissions[]
  Sent in: Authorization: Bearer <token> header

Refresh Token (30 days expiry):
  Stored in: httpOnly cookie (not accessible via JS)
  Used to: get new access token when expired

Token refresh flow:
  Access token expires → client sends refresh request
  Server validates refresh token → issues new access token
  If refresh token also expired → force re-login
```

### 1.3 Session Management

```
Active session tracks:
  last_activity (updated on every API call)
  ip_address, user_agent

Auto-logout triggers:
  Configurable inactivity timeout (setting: auto_logout_minutes)
  On timeout: session marked inactive, client force-logged out

Logout:
  Session.status → inactive
  Refresh token invalidated
  AuditLog: user_logout

Open shift behavior on logout:
  Shift STAYS OPEN — not auto-closed
  On next login: system detects open shift → prompt resume
  Manager can force-close orphaned shift (see §3.7)
```

### 1.4 Subscription Check on Login

```
After authentication:
  Load tenant.subscription_status, trial_ends_at, plan
  Cache these values locally (TTL: configurable, default 24h)

If subscription expired AND system is online:
  Block cashier access
  Show lock overlay: "Trial ended. Contact account owner."
  Owner/Admin: dashboard + settings + billing remain accessible

If subscription expired AND system is offline:
  Check cached subscription_status
  If cached within TTL and was valid: allow sales (grace window)
  If cached expired: block with "Cannot verify subscription"
  
On reconnect: always re-validate against server immediately
```

---

## 🔢 2. Cross-Cutting Flows

### 2.1 Permission Check Flow

Runs before EVERY state-changing API endpoint.

```
Receive API request with JWT
  ↓
Extract permissions[] from token
  ↓
Check required permission code for this endpoint
  ├─ Permission present → proceed to handler
  └─ Permission missing →
       HTTP 403 Forbidden
       AccessLog: unauthorized_attempt (entity, user, timestamp)
       If repeated failures → alert admin (configurable threshold)

UI note:
  Elements requiring permissions the user lacks → HIDDEN (not disabled)
  Elements requiring manager approval → visible, triggers approval modal on click
```

### 2.2 Idempotency Check Flow

Runs at the start of EVERY state-changing POST handler.

```
Receive request with idempotency_key (UUID)
  ↓
Query: SELECT * FROM document WHERE idempotency_key = X
  ├─ Record found → return existing record (200 OK)
  │   Do NOT process again
  │   Do NOT return 409
  └─ Not found → proceed with normal processing
       Store idempotency_key on the created/updated record

Applies to:
  Sales invoices, purchase invoices, returns, receipts,
  expenses, cash-in/out, adjustments, shifts,
  all other state-changing document operations
```

### 2.3 Document Numbering Assignment Flow

```
On document POST (inside atomic transaction):
  SELECT number_series FOR UPDATE
  WHERE tenant_id = X AND document_type = Y
  ↓
  Assign: prefix + year_format + zero_padded(next_number)
  Increment: next_number + 1
  Release lock
  ↓
  number is permanent and immutable from this point
  AuditLog: number_assigned (doc_type, number, user)

Rules:
  Draft documents show temporary reference or null
  Posted documents have immutable permanent number
  Cancelled documents RETAIN their number (marked Cancelled)
  Numbers are never reused — gaps are acceptable
```

### 2.3A Document Status State Machine Flow

```
Every business document carries five independent status fields:

posting_status:  Draft / Posted / Cancelled / Void
payment_status:  Unpaid / Partially Paid / Paid / N/A
return_status:   Not Returned / Partially Returned / Returned
approval_status: Not Required / Pending / Approved / Rejected
sync_status:     Synced / Pending Sync / Sync Failed

Rule:
  Do not collapse these into one combined status.
  A single invoice can be Posted + Partially Paid + Partially Returned + Synced.
```

### 2.4 Audit Log Write Flow

Triggered at the END of every state-changing operation (inside the same transaction).

```
AuditLog record created:
  tenant_id, actor_user_id, role, branch_id, terminal_id,
  timestamp, action, entity_type, entity_id,
  old_value (JSON — state before change),
  new_value (JSON — state after change),
  reason (if provided), approval_user_id (if applicable),
  affected_doc_number, source_module

Storage rules:
  INSERT ONLY — no UPDATE, no DELETE ever
  Retention: minimum 7 years
  Separate table partition per month (for query performance)

Does NOT trigger on:
  Report views, list reads, search queries, dashboard loads
  (those may trigger AccessLog for sensitive views)
```

### 2.5 Access Log Write Flow

```
Triggers (sensitive data reads):
  P&L report viewed
  Customer statement viewed
  Full data export initiated
  Admin-level user list accessed
  Audit log itself viewed

Record:
  user_id, tenant_id, resource_type, resource_id,
  action (view/export), timestamp, ip_address
```

### 2.6 Operations Log Write Flow

```
Triggers (system/hardware events):
  Printer failure (receipt or kitchen)
  Cash drawer failed to open
  Scale barcode parse error
  Offline sync error
  Celery job failure
  Hardware disconnect detected
  idempotency duplicate detected

Record:
  event_type, device_type, device_id, terminal_id,
  error_message, timestamp, resolved_at
```

### 2.7 Account Mapping Resolution Flow

Called before every FinancialAccountMovement creation.

```
Input: account_type (e.g., "cashbox", "tax_payable", "revenue")

Query AccountMapping:
  WHERE tenant_id = X AND account_type = Y
  ↓
  Found → use configured account_id and account_name
  Not found → use system default account for this type

Pass resolved account_id to FinancialAccountMovement
```

### 2.8 Manager Approval Flow

Triggered by any action that exceeds a configured threshold or requires explicit authorization.

**Triggers include:**
- Discount exceeds role's max percentage
- Selling below cost price
- Credit sale above customer credit limit
- Return without original invoice
- Shift opening variance above threshold
- Shift closing variance/shortage above threshold
- Stock adjustment (if setting requires)
- Unlinked purchase return
- Invoice cancellation (if setting requires)
- Negative stock override
- Manual loyalty points adjustment
- Period lock override
- Asset write-off
- Cash drop above threshold
- Price edit on posted document

```
Action requires approval
  ↓
Show Manager Approval Modal:
  Title: "Manager Approval Required"
  Description: what action + amount/detail requiring approval
  Reason field: required text input (always)
  Manager PIN or password: required
  [Approve] [Cancel]
  ↓
  Cashier submits → API verifies:
    Manager credentials valid?
    Manager has required permission?
    ├─ Yes → Approved:
    │     action.approval_status → Approved
    │     Store: approval_user_id, approval_time, reason
    │     AuditLog: manager_approval_granted
    │     Proceed with original action
    └─ No → Rejected:
          AuditLog: manager_approval_rejected
          Block action
          Show: "Manager rejected this action"
```

---

## ⚙️ 3. Posting Engine / Transaction Boundary

The Posting Engine is the central mechanism for all document state transitions. It wraps every POST in a single atomic database transaction.

### 3.1 What "Post" Means

Moving a document from `posting_status = Draft` to `posting_status = Posted` triggers all business effects. These effects all happen together or none of them happen.

### 3.2 Generic Posting Sequence

```
┌────────────────────────────────────────────────────────┐
│ BEGIN TRANSACTION                                      │
│                                                        │
│  STEP 0: Check idempotency_key (§2.2)                 │
│           Duplicate found → return 200, abort          │
│                                                        │
│  STEP 1: Validate document                             │
│           Required fields, item existence,             │
│           quantities > 0, prices valid                 │
│                                                        │
│  STEP 2: Check permissions (§2.1)                      │
│           403 if missing required permission           │
│                                                        │
│  STEP 3: Check settings                               │
│           Is credit allowed? require shift open?       │
│           Is warehouse required? discount allowed?     │
│                                                        │
│  STEP 4: Check credit limit (if credit PaymentLine)   │
│           AR balance + invoice > credit_limit?         │
│           → trigger Manager Approval or block          │
│                                                        │
│  STEP 5: Check Negative Stock Control (§13.9)          │
│           Per product/unit, ingredient, warehouse      │
│           Read tenant + product-level settings         │
│           → block, warn, allow, or Manager Approval    │
│           If allowed: mark movement as negative-stock  │
│           If estimated cost used: cost_status=estimated│
│                                                        │
│  STEP 6: Resolve prices per Price Tier + Unit          │
│           Query ProductUnitTierPrice                   │
│           sale_price only; purchase prices stay on     │
│           ProductUnit (not in tier price table)        │
│           Fallback chain: tier → default tier → base  │
│                                                        │
│  STEP 7: Calculate Net Revenue (excl. tax)            │
│           Σ(tier_price × qty) − all discounts          │
│                                                        │
│  STEP 8: Tax Calculation Engine (§5)                  │
│           Tax → Tax Payable account (NOT revenue)      │
│                                                        │
│  STEP 9: Rounding Calculation (§6)                    │
│           Apply if invoice_rounding_enabled            │
│                                                        │
│  STEP 10: COGS Calculation Engine (§7)                │
│            avg_cost or recipe_cost per item            │
│                                                        │
│  STEP 11: Calculate loyalty discount (if applied)     │
│            MVP Extended full flow; MVP Core hooks only │
│            Discount-type, NOT a PaymentLine to cashbox │
│                                                        │
│  STEP 12: Assign document number (§2.3)               │
│            SELECT ... FOR UPDATE on series             │
│            Permanent, immutable                        │
│                                                        │
│  STEP 13: Set posting_status = Posted                 │
│            Set payment_status based on PaymentLines    │
│                                                        │
│  STEP 14: Create StockMovements                       │
│            Per item type and line_type                 │
│            SELECT FOR UPDATE on product rows           │
│            F() expressions for atomic qty changes      │
│                                                        │
│  STEP 15: Create RECIPE_CONSUME movements             │
│            Per ingredient, from configured warehouse   │
│                                                        │
│  STEP 16: Create FinancialAccountMovements            │
│            Revenue → Revenue account                   │
│            Tax → Tax Payable account                   │
│            Per PaymentLine → correct account           │
│            Via Account Mapping Layer (§2.7)            │
│                                                        │
│  STEP 17: Create CustomerARMovement (if credit)       │
│            Or SupplierAPMovement (if purchase credit)  │
│                                                        │
│  STEP 18: Create LoyaltyRedemption record (if used)   │
│            MVP Extended full flow; MVP Core hooks only │
│            Points deducted from CustomerPoints         │
│            Loyalty Discount account ↑                  │
│                                                        │
│  STEP 19: Update ShiftMovementSummary                 │
│            All relevant totals per payment method      │
│                                                        │
│  STEP 20: Create LoyaltyOutbox record (pending)       │
│            MVP Extended full flow; MVP Core hooks only │
│            Inside transaction — guaranteed to exist    │
│                                                        │
│  STEP 21: Store posting_snapshot (JSON on document)   │
│            tax_rates, discount_settings, tier_prices,  │
│            avg_costs, template_version, context IDs    │
│                                                        │
│  STEP 22: Write AuditLog entry (§2.4)                 │
│                                                        │
│ COMMIT                                                 │
│                                                        │
│ ── AFTER COMMIT (async, Celery) ────────────────────  │
│                                                        │
│  STEP 23: Process LoyaltyOutbox                       │
│            MVP Extended full flow; MVP Core hooks only │
│            Check outbox: status = pending              │
│            Check: invoice still Posted                 │
│            Check: not already processed (idempotent)   │
│            Create LoyaltyTransaction: EARN             │
│            Update CustomerPoints.balance ↑             │
│            Mark LoyaltyOutbox: processed               │
│            Retry if failure (safe — idempotent)        │
└────────────────────────────────────────────────────────┘
```

### 3.3 Stock Effect per Item Type

```
item_type = Stock Item:
  STEP 14 creates: StockMovement SALE_OUT
  qty: sold quantity × unit.conversion_factor (to storage unit)
  warehouse: selected sale warehouse
  unit_cost: product.avg_cost (at this moment, stored on SaleItem)
  SELECT FOR UPDATE on product.stock + product.avg_cost

item_type = Recipe Product:
  STEP 14: NO SALE_OUT for the product itself
  STEP 15: RECIPE_CONSUME per ingredient
    For each RecipeIngredient:
      qty = recipe_qty × (1 + wastage_factor) × unit_conversion
      warehouse = resolved per recipe_ingredient_warehouse_source setting
      unit_cost = ingredient.avg_cost (at this moment)
      SELECT FOR UPDATE on ingredient product row

item_type = Service / Non-Stock:
  No StockMovement created at all

item_type = Ingredient Item (if sold directly):
  Same as Stock Item (SALE_OUT)

item_type = Fixed Asset (purchase line only):
  No StockMovement
  Creates FixedAsset record instead (STEP 14 variant for purchase)
```

### 3.4 Financial Effect per Account Mapping

```
For each financial effect, resolve account via §2.7 then create:
FinancialAccountMovement {
  account_type, account_id,  ← resolved from Account Mapping
  amount (+/-),
  movement_type,
  source_document_type, source_document_id,
  shift_id, created_at
}

Revenue effect:
  account_type: revenue
  amount: net_amount (excl. tax, after discounts)

Tax effect:
  account_type: tax_payable
  amount: tax_amount (NEVER added to revenue)

Cash PaymentLine:
  account_type: cashbox
  account_id: shift.cashbox_id (the active cashbox)
  amount: +payment_amount

Card PaymentLine:
  account_type: card_settlement  ← NOT cashbox
  account_id: configured card settlement account
  amount: +payment_amount

Wallet PaymentLine:
  account_type: wallet_account  ← NOT cashbox
  account_id: configured wallet account
  amount: +payment_amount

Credit PaymentLine:
  No FinancialAccountMovement
  Creates CustomerARMovement instead (STEP 17)

AR/AP double-counting rule:
  CustomerARMovement is the detailed source of truth for customer balances
  SupplierAPMovement is the detailed source of truth for supplier balances
  AR/AP accounts in Account Mapping are summary/control accounts only
  Reports must not count AR/AP twice

Loyalty Discount:
  account_type: loyalty_discount  ← NOT cashbox, NOT revenue
  amount: discount_value
  Does NOT increase any cashbox or bank account

COGS effect:
  account_type: cogs
  amount: +cogs_value

Inventory effect (on purchase):
  account_type: inventory_value
  amount: +received_qty × purchase_cost

Fixed Asset effect (on purchase):
  account_type: fixed_asset
  amount: +acquisition_cost

Expense effect:
  account_type: expense
  amount: +expense_amount
```

### 3.5 Failure Scenarios

```
DB constraint violation:
  → ROLLBACK entire transaction
  → Return 400 with specific error message
  → No partial effects exist

Concurrent stock deduction race condition:
  → SELECT FOR UPDATE prevents this
  → One transaction waits, then proceeds after first commits
  → If stock becomes insufficient after wait: apply §11.0B rules

Network drop mid-POST (client disconnects):
  → Transaction either commits or rolls back (DB handles atomicity)
  → Client retries with same idempotency_key (§2.2)
  → Server returns existing result if already committed

Celery task failure (post-commit loyalty):
  → LoyaltyOutbox record persists (was created in transaction)
  → Celery retries automatically (idempotent check prevents double-award)
  → Points cannot be permanently lost
```

---

## ❌ 4. Cancellation / Void / Reversal Flow

### 4.1 Eligibility Rules

```
posting_status = Draft:
  → DELETE allowed (no effects to reverse)
  → Or VOID (mark as invalid, status → Void)
  
posting_status = Posted:
  → CANCEL only (never DELETE)
  → All posting effects must be reversed atomically

posting_status = Cancelled:
  → No further action allowed

payment_status = Paid or Partially Paid:
  → Cancel triggers payment reversal (money flows back)

return_status = Returned:
  → Cannot cancel (returns already processed)
  → Must use Sales Return to correct
```

### 4.2 Cancellation Effects (Atomic)

```
┌──────────────────────────────────────────────────┐
│ BEGIN TRANSACTION (CANCELLATION)                 │
│                                                  │
│  1. Check cancellation eligibility (§4.1)        │
│  2. Check permission: sales.cancel               │
│  3. Require reason (always)                      │
│  4. Trigger Manager Approval Flow (if setting)   │
│                                                  │
│  5. Reverse StockMovements                       │
│     SALE_OUT → restore qty                       │
│     RECIPE_CONSUME → restore ingredients         │
│     (inverse movement types, same amounts)       │
│                                                  │
│  6. Reverse FinancialAccountMovements            │
│     Revenue reversed (net amount)                │
│     Tax Payable reversed                         │
│     Per PaymentLine: each account reversed       │
│                                                  │
│  7. Reverse CustomerARMovement (if credit)       │
│  8. Reverse LoyaltyRedemption (if loyalty used)  │
│  9. Reverse ShiftMovementSummary totals          │
│ 10. Create LoyaltyOutbox: REVERSE_EARN           │
│     (reverses any already-awarded points)        │
│ 11. Set posting_status → Cancelled               │
│ 12. RETAIN document number (never reused)        │
│ 13. Write AuditLog (reason + approver required)  │
│                                                  │
│ COMMIT                                           │
└──────────────────────────────────────────────────┘
```

### 4.3 Void (Draft Only)

```
Draft document marked as Void:
  posting_status → Void
  No financial/stock effects to reverse (Draft never posted)
  AuditLog: document_voided (reason optional)
  Document retained for audit trail
```

### 4.4 Partial Cancellation

Not supported in MVP. To correct a posted invoice:
1. Cancel the original invoice (full reversal)
2. Create a new correct invoice

For returning some items (not cancelling): use Sales Return (§11).

---

## 🧮 5. Tax Calculation Engine Flow

### 5.1 When It Runs

Triggered by: add item to cart, edit qty, edit price, apply discount, add charge, change tax setting, submit invoice.

### 5.2 Per-Line Tax Calculation

```
Get per line: unit_price, qty, tax_rate, line_discount

If tax_mode = tax_exclusive:
  If discount_before_tax = true (default):
    net_amount = (unit_price × qty) − line_discount
  Else:
    net_amount = unit_price × qty
  tax_amount = net_amount × tax_rate
  line_total  = net_amount + tax_amount

If tax_mode = tax_inclusive:
  gross_amount = unit_price × qty
  net_amount   = gross_amount ÷ (1 + tax_rate)
  tax_amount   = gross_amount − net_amount
  line_total   = gross_amount (price already contains tax)
  
  Note: if discount_before_tax for inclusive:
    gross_with_discount = gross_amount − line_discount
    net_amount = gross_with_discount ÷ (1 + tax_rate)
    tax_amount = gross_with_discount − net_amount
```

### 5.3 Service Charge Tax

```
If charge.charge_is_taxable = true:
  charge_tax = charge_amount × active_tax_rate
  Total tax += charge_tax
```

### 5.4 Invoice-Level Aggregation

```
1. Collect all line tax results
2. Group by tax_rate:
   [{rate: 0.14, taxable_base: 500, tax_amount: 70},
    {rate: 0.00, taxable_base: 100, tax_amount: 0}]
3. Apply invoice rounding (see §6)
4. Store as invoice.tax_breakdown (JSON)
5. Total tax = Σ tax_amount across all groups
```

### 5.5 Tax Payable Treatment

```
tax_amount goes to: Tax Payable account (LIABILITY)
tax_amount is NOT added to Net Revenue

Revenue → Sales Revenue account
Tax     → Tax Payable account
Cash received (Cashbox) = Revenue + Tax (full invoice amount)

At shift close and in reports:
  Net Revenue = Σ net_amounts (excl. tax)
  P&L shows Net Revenue (not gross)
  Tax Payable shown separately (not in P&L)
```

### 5.6 Tax on Returns

```
Use tax_snapshot from original invoice's posting_snapshot
Do NOT recalculate at current settings
tax_reversed = original tax_amount (from snapshot)
Tax Payable ↓ by tax_reversed
```

---

## 💰 6. Rounding Calculation Flow

### 6.1 When It Runs

After Tax Calculation, before total display and before payment step. Only if `invoice_rounding_enabled = true`.

### 6.2 Rounding Calculation

```
raw_total = net_amount + tax_amount + charges
rounded_total = round_to_nearest(raw_total, rounding_unit)
rounding_amount = rounded_total − raw_total

Store on invoice:
  invoice.rounding_amount = rounding_amount
  (can be positive or negative — gain or loss)
```

### 6.3 Cash Rounding

```
If cash_rounding_enabled = true:
  Applied to cash payments only
  Card and wallet: exact amount always
  Change calculation uses rounded total for cash
```

### 6.4 Rounding in Snapshot and Posting

```
posting_snapshot includes: rounding_amount, rounding_enabled
FinancialAccountMovement:
  account_type: rounding_adjustment
  account mapping setting: default_rounding_adjustment_account
  amount: rounding_amount (can be ± small amount)
Rules:
  Rounding affects total due
  Rounding must not silently change revenue
  Rounding gain/loss goes to the Rounding Adjustment account
Shown on invoice as separate line: "تقريب الفاتورة"
```

---

## 📦 7. Costing & COGS Engine Flow

### 7.1 Average Cost Update (on PURCHASE_IN)

```
BEGIN TRANSACTION (or within posting transaction)
  SELECT product, product_unit FOR UPDATE  ← prevents race condition
  
  current_stock = product_unit.qty_in_stock
  current_avg   = product_unit.avg_cost
  received_qty  = purchase_invoice_item.qty
  purchase_cost = purchase_invoice_item.unit_cost
  
  new_avg_cost =
    (current_stock × current_avg + received_qty × purchase_cost)
    ÷ (current_stock + received_qty)
  
  UPDATE product_unit SET avg_cost = new_avg_cost

Also triggered on: OPENING_BALANCE, ADJUSTMENT_IN (if cost provided)
```

### 7.2 COGS Calculation on SALE_OUT

```
For each sale_item (item_type = Stock Item or Ingredient):
  cogs = product_unit.avg_cost × qty_sold
  sale_item.avg_cost_at_posting = product_unit.avg_cost  ← immutable snapshot
  
FinancialAccountMovement: COGS account ↑ by cogs_amount
```

### 7.3 Recipe COGS (Café Items)

```
For each RecipeIngredient at posting time:
  ingredient_avg_cost = ingredient_product_unit.avg_cost
  
  ingredient_cost =
    ingredient_avg_cost         ← per storage unit
    × recipe_qty                ← amount specified in recipe
    × (1 + wastage_factor)      ← e.g., 1.05 for 5% waste
    × unit_conversion_factor    ← recipe unit → storage unit

Total Recipe COGS = Σ ingredient_costs

Stored on sale_item:
  sale_item.recipe_cost_snapshot = {
    ingredients: [
      {product_id, qty, unit, avg_cost, wastage, conversion, cost},
      ...
    ],
    total_recipe_cogs: X
  }
  (JSON — immutable, never updated)
```

### 7.4 Sales Return COGS Reversal

```
On Sales Return posting:
  Fetch: original sale_item.avg_cost_at_posting
  
  COGS_reversed = original.avg_cost_at_posting × return_qty
  
  FinancialAccountMovement: COGS account ↓ by COGS_reversed
  
  NOTE: Use original snapshot cost — NOT current avg_cost
  This prevents: cheap purchase after return artificially
  lowering COGS on the reversal
```

### 7.5 Purchase Return Cost Adjustment

```
On Purchase Return posting:
  
  If linked to original Purchase Invoice:
    removal_cost = original_PI_line.unit_cost  ← from PI snapshot
    new_avg_cost recalculated:
      remaining_stock = current_stock − return_qty
      value_removed   = removal_cost × return_qty
      remaining_value = (current_stock × current_avg) − value_removed
      new_avg = remaining_value ÷ remaining_stock (if > 0)
      
  If NOT linked (standalone, setting allows):
    removal_cost = current avg_cost
    Same recalculation with current avg_cost
    AuditLog: unlinked_purchase_return flag
```

### 7.6 Damage / Wastage Costing

```
inventory_loss = product_unit.avg_cost × damaged_qty

This is a REAL financial loss, not zero.

FinancialAccountMovement:
  Inventory Loss account ↑ (expense — reduces gross profit)
  Inventory value account ↓ (asset decreases)

DamageWastage record:
  {product_id, warehouse_id, qty, avg_cost_at_posting,
   inventory_loss_value, reason, shift_id, created_by}

ShiftMovementSummary:
  wastage_total ↑  ← NOT expense_total
  (Damage is not a cash expense — it's an inventory loss)
```

### 7.7 Estimated Cost & COGS Adjustment for Negative Stock

This flow is used only when the system allows selling stock or recipe ingredients while the available balance is insufficient.

```
During Sale Posting:
  If stock balance will go below zero:
    Check negative_stock_costing_method:
      last_known_average_cost:
        estimated_cost = product_unit.avg_cost or last_known_avg_cost
      default_purchase_price:
        estimated_cost = product_unit.default_purchase_price
      zero_cost_require_later_adjustment:
        estimated_cost = 0

    Store on sale line / recipe consume line:
      cost_status = estimated
      estimated_unit_cost = estimated_cost
      negative_stock_qty = shortage_qty

    Create FinancialAccountMovement:
      COGS account ↑ using estimated_cost

    Create NegativeStockAlert if setting enabled
```

When later purchase stock arrives, the system can compare the real purchase cost against the estimated cost and post an adjustment. The original sales invoice is never edited.

```
On Negative Stock Settlement:
  actual_unit_cost = purchase_invoice_line.unit_cost
  estimated_unit_cost = stored estimated cost on negative sale/consume movement
  settled_qty = qty from purchase used to cover old negative balance

  cogs_adjustment = (actual_unit_cost − estimated_unit_cost) × settled_qty

  If create_cogs_adjustment_after_negative_stock_settlement = true:
    FinancialAccountMovement:
      COGS account ↑ if adjustment positive
      COGS account ↓ if adjustment negative

    COGSAdjustment record created:
      {negative_stock_settlement_id, original_sale_id, purchase_invoice_id,
       estimated_unit_cost, actual_unit_cost, settled_qty, adjustment_amount}

  If original sale period is locked:
    Post adjustment in current open period
    Do NOT edit the old invoice, cost snapshot, or old financial movement

  AuditLog: negative_stock_cogs_adjustment_posted
```

---

## ⏰ 8. Shift Workflow / Cashier Session

> **The Shift Workflow is an operational workflow — NOT a sidebar navigation item.**  
> Accessed exclusively via the **header profile dropdown**.

### 8.1 POS Load → Shift Check

```
User logs in → POS screen loads
  ↓
Check: setting require_shift_before_selling
  ├─ false → POS available immediately (no shift required)
  └─ true → Check: is there an Active shift for this user/cashbox?
               ├─ YES → Load shift context, POS available
               └─ NO  → Show Open Shift Modal (BLOCKING)
                         POS cannot be used until shift opened
```

### 8.2 Open Shift Modal Flow

```
Open Shift Modal displays:
  Branch: auto-loaded from user.branch_id
  Terminal: auto-detected (or select if multiple)
  Cashbox: select from assigned cashboxes
    (required if require_cashbox_for_shift = true)
  
  System shows:
    Expected opening cash: last_shift.actual_closing_cash
                           (for this cashbox, or 0 if first ever)
  
  Cashier enters:
    Actual counted cash: [manual entry]
    Optional denomination breakdown if setting enabled:
      200 EGP × count
      100 EGP × count
      50 EGP × count
      coins / custom denominations
      System auto-calculates actual counted cash
  
  System calculates:
    opening_variance = expected_opening_cash − actual_counted_cash

  If |opening_variance| > setting threshold:
    → Manager Approval Flow (BLOCKING before shift opens)
    Manager must approve → shift opens
    Manager rejects → try again or re-count
  
  Cashier clicks [Open Shift]
  ↓
  BEGIN TRANSACTION
    ShiftMovementSummary record created:
      {tenant_id, branch_id, terminal_id, cashbox_id, user_id,
       opening_cash_expected, opening_cash_actual, opening_variance,
       status: Active, opened_at: now}
    Assign document number: SHF-YYYY-NNNNN
    AuditLog: shift_opened (with opening_variance)
  COMMIT
  ↓
  POS becomes available
  Profile dropdown shows: "● Shift open · [branch] · [cashbox] · since HH:MM"
```

### 8.3 Shift State Machine

```
No Shift
  ↓ [Open Shift Modal submitted + approved]
Active (الوردية مفتوحة)
  ↓ [Close Shift from profile dropdown]
Closing (الكاشير بيدخل الأرقام)
  ↓ [Submit close modal]
Closed (الوردية مقفولة)
```

### 8.4 Real-Time Shift Tracking

ShiftMovementSummary is updated atomically on EVERY document posting within the shift. No manual action required from the cashier.

```
On every Sales Invoice POST:
  ShiftMovementSummary.invoice_count ↑
  ShiftMovementSummary.cash_sales_total ↑ (if cash PaymentLine)
  ShiftMovementSummary.card_sales_total ↑ (if card PaymentLine)
  ShiftMovementSummary.wallet_sales_total ↑ (if wallet PaymentLine)
  ShiftMovementSummary.credit_sales_total ↑ (if credit PaymentLine)
  ShiftMovementSummary.loyalty_discount_total ↑ (if loyalty applied)
  ShiftMovementSummary.discount_total ↑ (item/invoice discounts)

On every Sales Return POST:
  ShiftMovementSummary.return_count ↑
  ShiftMovementSummary.cash_returns_total ↑ (if cash refund)
  ShiftMovementSummary.card_returns_total ↑ (if card refund)

On every Expense POST:
  ShiftMovementSummary.expense_total ↑

On every Damage/Wastage POST:
  ShiftMovementSummary.wastage_total ↑  ← separate from expense_total

On every Cash In:
  ShiftMovementSummary.cash_in_total ↑

On every Cash Out:
  ShiftMovementSummary.cash_out_total ↑

On every Cash Drop:
  ShiftMovementSummary.cash_drop_total ↑

On every Customer Receipt (cash):
  ShiftMovementSummary.customer_cash_receipts_total ↑
  NOTE: Customer receipts are cash collected from AR, not new sales
```

### 8.5 Close Shift Modal Flow

```
Cashier clicks "Close Shift" from profile dropdown
  ↓
System shows Close Shift Modal:

  ┌─ Cashbox Reconciliation ──────────────────────────────────┐
  │ Expected Cash:                                            │
  │   = opening_cash_actual                                   │
  │   + cash_sales_total                                      │
  │   + customer_cash_receipts_total (from shift)             │
  │   + cash_in_total                                         │
  │   − cash_returns_total (cash refunds paid out)            │
  │   − cash_out_total                                        │
  │   − expense_total (cash expenses paid)                    │
  │   − cash_drop_total (if drops made to safe)               │
  │   = [system calculated: X EGP]                           │
  │                                                           │
  │ Actual Counted Cash: [________] (cashier enters)          │
  │ Optional Denomination Count:                              │
  │   200 / 100 / 50 / 20 / coins — configurable             │
  │   System auto-calculates actual counted cash              │
  │ Shortage / Surplus:  [auto-calculated]                    │
  └───────────────────────────────────────────────────────────┘
  
  ┌─ Card / Visa Reconciliation ──────────────────────────────┐
  │ Expected Card Amount (from invoices): [X EGP]             │
  │ Terminal Batch Total (cashier enters): [________]         │
  │ Card Variance: [auto-calculated]                          │
  │ Batch Reference Number: [optional/required by setting]    │
  └───────────────────────────────────────────────────────────┘
  
  ┌─ Wallet / Online Payment Reconciliation ──────────────────┐
  │ Expected Wallet Amount (from invoices): [X EGP]           │
  │ Settlement Confirmation: [optional/required by setting]   │
  └───────────────────────────────────────────────────────────┘
  
  Notes: [textarea — optional]
  
  [Close Shift]
  ↓
  If |closing_variance| > threshold (setting):
    → Manager Approval Flow (blocking)
    
  If |card_variance| significant:
    → Flag for manager review (may require approval by setting)

  BEGIN TRANSACTION
    ShiftMovementSummary:
      actual_closing_cash = cashier_entry
      closing_variance = expected_closing_cash − actual_closing_cash
      card_terminal_batch = cashier_entry
      card_variance = card_terminal_batch − card_expected
      status → Closed
      closed_at = now
    Assign shift close reference
    Generate shift report (auto)
    AuditLog: shift_closed (all variance amounts)
  COMMIT
```

### 8.6 Cash Denomination Counting Flow — [MVP Extended]

```
Used inside Open Shift and Close Shift modals when enabled by setting.

Settings:
  require_denomination_count_on_open
  require_denomination_count_on_close
  allow_manual_total_count
  cash_denominations_config

Flow:
  System loads active denominations for tenant:
    200 / 100 / 50 / 20 / 10 / 5 / 1 / coins
  Cashier enters count per denomination
  System calculates:
    subtotal per denomination = denomination_value × count
    actual_counted_cash = Σ subtotals
  Variance calculated against expected cash
  If variance exceeds threshold:
    → Manager Approval Flow

Records:
  CashCountLine per denomination
  Stored with shift open/close record
  AuditLog stores final amount + variance
```

### 8.7 Logout / Session Expiry with Open Shift

```
Cashier logs out OR session expires OR device locks:
  → Shift REMAINS ACTIVE (status stays Active)
  → UserSession.status → inactive
  → Shift NOT auto-closed

On next login (same or different user):
  System detects: open shift exists for this cashbox/terminal
  Options shown:
    [Resume My Shift] — original cashier
    [Contact Manager] — another user

Manager force-close orphaned shift:
  Permission required: cashbox.approve_variance
  Requires reason
  → Manager Approval Flow
  → Shift.status → Closed
  → closing_variance may be 0 or estimated
  → AuditLog: orphaned_shift_force_closed
  → Generates shift report with "force closed" flag
```

### 8.8 Shift Report

Auto-generated on every shift close. Contains:
- Branch, terminal, cashbox, user, dates
- All ShiftMovementSummary totals
- Expected vs actual cash (opening + closing)
- Shortage/surplus
- Card expected vs terminal batch
- Wallet expected vs settlement
- Invoice count, return count, cancel count
- Loyalty discount total (informational)
- Approval records (if any)

---

## 🏪 9. POS Flows

### 9.1 POS Compact Mode Sale Flow

```
POS loads → barcode input auto-focused
  ↓
Cashier scans barcode (or manual type + Enter)
  ↓
  ┌─ Barcode type detection ───────────────────────────────┐
  │ Scale barcode? (starts with "21", 11 digits)           │
  │   Yes → Parse PLU (5 digits) + weight (5 digits)      │
  │          Look up product by PLU                        │
  │          qty = weight / 1000 (kg)                      │
  │          price = price_per_kg × qty                    │
  │   No  → Standard product barcode                       │
  │          Look up ProductUnit by barcode                │
  └────────────────────────────────────────────────────────┘
  ↓
  Product found:
    → Resolve price per tier + unit (§9.2)
    → Add to cart: {product_unit_id, qty: 1, unit_price: resolved_price}
    → Flash animation on cart line (existing prototype behavior)
    → Beep sound
    → Barcode input cleared and re-focused

  Product not found:
    → Show error: "Product not found: [barcode]"
    → Options: [Search by name] [Manual price] [Cancel]
    → Barcode input stays focused
```

### 9.2 Price Tier Resolution at POS

```
When item added to cart:
  1. Get active customer (if selected) → customer.price_tier_id
  2. Get product_unit_id from scanned barcode
  3. Query ProductUnitTierPrice:
       WHERE product_unit_id = X AND price_tier_id = Y
  4. If found → use sale_price
  5. If not found for this tier → query with default tier
  6. If not found for default tier → use product_unit.default_sale_price

  ProductUnit stores:
    default_purchase_price
    last_purchase_price
    default_sale_price

  ProductUnitTierPrice stores sale prices only:
    product_unit_id + price_tier_id + sale_price
    purchase_price must NOT be stored here

When customer changes mid-transaction:
  Re-query all cart lines with new tier
  Show confirmation toast: "Prices updated for [tier name]"
  Cashier can override per line (if permission: sales.edit_price)
```

### 9.3 Cart Management

```
Edit quantity:
  Click on cart line → quantity controls appear
  For weighted items: ± in 0.001 kg steps
  For standard items: ± in 1 unit steps
  Manual input allowed

Remove item:
  Trash icon on cart line → confirm → item removed

Apply item discount:
  Click on line → discount panel opens
  Enter % or fixed amount
  Check: max_cashier_discount_percent setting
  If exceeds → Manager Approval Flow

Apply invoice discount:
  "Discount" button below cart
  Enter % or fixed amount
  Same approval rules

Add service charge / delivery fee:
  "Charges" button → select charge type → enter amount
  charge_is_taxable? → Tax Engine recalculates

Clear entire cart:
  [Clear Cart] → confirmation → all lines removed
  cart.discount → 0
  cart.charges → []
```

### 9.4 POS Touch / Café Mode Flow

```
POS Touch Mode activates when:
  Setting: touch_pos_mode = true (default for cafés)
  OR: cashier manually switches mode

Layout:
  Left: category navigation panel
  Center: product tile grid (large tiles, images/initials)
  Right: cart (same as compact mode)
  Bottom of cart: order type selector

Category Navigation:
  Level 1: item groups (e.g., Hot Drinks, Cold Drinks, Food)
  Level 2: subgroups (e.g., Espresso, Latte, Cappuccino)
  Tap group → filter products to that group

Product Tile Tap:
  1. Tap tile → add to cart
  2. If product has ModifierGroups:
     → Show Modifier Selection Popup BEFORE adding to cart
  3. Modifiers selected → add to cart with modifiers
  4. If product is weighted → show weight entry popup

Modifier Selection Popup:
  Title: "[Product Name]"
  Groups shown in order (required groups first):
    Each group shows options with price delta
    Required: must select at least min_select
    Optional: can skip
  [Add to Cart] → only enabled when all required groups satisfied
  [Cancel] → return without adding
```

### 9.5 Order Type Selection

```
Order type selector in cart header:
  [Dine-in] [Takeaway] [Delivery]
  Default: Dine-in (configurable per tenant)

Dine-in:
  Customer selection: optional (setting: require_customer_for_dine_in)
  Table number: optional (Phase 2 for full table management)
  Kitchen ticket: normal format

Takeaway:
  Customer: NOT required — anonymous sale is fully valid
  No customer data collected
  Setting: takeaway_packaging_charge → auto-add if true
  Kitchen ticket: "تيك أواي" label prominent
  
Delivery:
  Customer: required (setting: require_customer_for_delivery)
  Delivery address: captured in order notes
  Delivery fee: added as invoice charge (InvoiceCharge)
  Kitchen ticket: "ديليفري" label + address
```

### 9.6 Customer Selection (Inline POS)

```
Customer selector in POS header area:
  Search by: name, phone, customer code
  Shows results inline (dropdown)
  Each result shows: name, phone, balance, points (🏆 X)
  
On customer selection:
  → Price tiers re-resolved for all cart items (§9.2)
  → Customer AR balance shown
  → Loyalty points balance shown: "رصيدك: X نقطة"
  → Credit limit shown (if credit sale mode)
  
Remove customer:
  × button → customer cleared
  → Cart prices revert to default tier
```

### 9.7 Payment Flow

```
Cashier clicks [Proceed to Payment]
  ↓
  Check: require_shift_before_selling (if no shift → block)
  ↓
  Show payment panel

  ┌─ Cart Summary ─────────────────────────────────┐
  │ Subtotal:          X EGP                       │
  │ Discounts:        −Y EGP                       │
  │ Charges:          +Z EGP                       │
  │ Tax (X%):         +T EGP                       │
  │ Rounding:         ±R EGP (if enabled)          │
  │ Total Due:         N EGP                       │
  └────────────────────────────────────────────────┘
  
  ┌─ Loyalty Discount Panel (if customer + active) ─┐
  │ رصيدك: 500 نقطة                                │
  │ أقصى خصم: 50 نقطة = 5.00 جنيه                 │
  │ استخدام: [___] نقطة = [__] جنيه خصم            │
  │ [تطبيق خصم النقاط] [تخطي]                      │
  │                                                 │
  │ After applying:                                 │
  │   Total Due after loyalty: N − discount         │
  └─────────────────────────────────────────────────┘
  
  Payment method selection:
  ┌──────────────────────────────────────────────────┐
  │ Payment Lines (one or more):                    │
  │                                                  │
  │ [+] Add payment line:                            │
  │   Method: [Cash ▼]  Amount: [_____]              │
  │   Method: [Card ▼]  Amount: [_____]  Ref: [___] │
  │   Method: [Credit ▼] (customer must be selected) │
  │                                                  │
  │ Total entered: X EGP                             │
  │ Remaining:     Y EGP                             │
  └──────────────────────────────────────────────────┘
  
  [Complete Payment] → enabled when:
    Σ PaymentLines ≥ total_due (for non-credit)
    OR exactly = total_due (for credit combinations)
```

### 9.8 Cash Payment Detail

```
When method = Cash:
  Cashbox: auto-selected (from shift.cashbox_id)
  Amount paid: entry (or [Exact], [Round up] buttons)
  Change = amount_paid − total_due
  Change shown prominently in green if > 0
  
  Quick amount buttons: [exact] [round to 10] [round to 50]
  Keypad available for touch mode
  
  [Complete] → triggers Posting Engine (§3.2)
  → Cash drawer signal sent (after DB commit)
```

### 9.9 Card Payment (Manual Recording)

```
When method = Card:
  Label: "Visa / Card — Manual Recording"
  Amount: equals remaining (or manual entry for partial)
  Reference number:
    If requires_reference = true: REQUIRED field
    If requires_reference = false: optional field
  
  Note shown: "Process card on terminal, then confirm here"
  
  [Confirm Card Payment] → marks as card in system
  → Card Settlement account ↑ (NOT cashbox)
  → Shift card_sales_total ↑
  → CardRefundReference NOT created here (only on returns)
  
At shift close:
  Cashier will enter terminal batch total for reconciliation
```

### 9.10 Wallet Payment (Manual Recording)

```
When method = Wallet (Vodafone Cash / Fawry / InstaPay):
  Select wallet type from configured methods
  Amount: remaining or manual
  Reference number: optional or required by setting
  
  [Confirm Wallet Payment] → Wallet account ↑ (NOT cashbox)
  → Shift wallet_sales_total ↑
```

### 9.11 Credit Sale Flow

```
When method = Credit (or Partial Credit):
  Check: allow_credit_sale setting
  ├─ false → block, show: "Credit sales not enabled"
  └─ true →
       Check: require_customer_for_credit setting
       ├─ true → customer must be selected
       │          If no customer → show customer selector first
       └─ false → allowed without customer (unusual)
       
  Check: customer.credit_limit
    If AR_balance + invoice_total > credit_limit:
      Check: allow_credit_limit_override setting
      ├─ true → Manager Approval Flow
      │          Approved → proceed
      └─ false → block: "Credit limit exceeded"
  
  Payment line created: {method: credit, amount: credit_portion}
  CustomerARMovement: CREDIT_SALE ↑
  invoice.payment_status → Unpaid (full credit) or Partially Paid
```

### 9.12 Mixed Payment Flow

```
Cashier adds multiple payment lines:
  Line 1: Cash, 100 EGP
  Line 2: Card, 50 EGP
  Line 3: Credit, 30 EGP (if customer selected + credit allowed)
  
Total entered: 180 EGP
Total due: 180 EGP → [Complete Payment]

Each line routed independently (§3.4):
  Cash → Cashbox ↑
  Card → Card Settlement ↑
  Credit → CustomerARMovement ↑

If Σ PaymentLines < total_due:
  Remaining automatically becomes credit (if credit allowed)
  OR error: "Payment amount is insufficient"
```

### 9.13 Overpayment Handling

```
Cash overpayment:
  Change = amount_paid − total_due
  Change displayed prominently
  Cashbox ↑ by amount_paid (full amount received)
  No change movement (cashier physically gives change from drawer)

Wallet/Card overpayment:
  Unusual — normally exact amount
  If recorded: excess becomes customer credit (if customer selected)
  Or: return overpayment through same method
```

### 9.14 Post-Sale Effects

After payment confirmed, Posting Engine (§3.2) runs:

```
Database effects (all atomic):
  1. Sales invoice created + posted
  2. StockMovements + RECIPE_CONSUME (if café)
  3. FinancialAccountMovements (revenue, tax, per payment method)
  4. CustomerARMovement (if credit/partial)
  5. ShiftMovementSummary updated
  6. LoyaltyOutbox created (if customer + loyalty active)
  7. posting_snapshot stored
  8. AuditLog entry

After DB commit:
  Print receipt (ESC/POS) → if fails: show Printer Failure dialog (§9.15)
  Send kitchen ticket (if café items) → route by item group
  Cash drawer signal (if cash payment)
  Loyalty points processed (Celery, async)
  
POS resets:
  Cart cleared
  Customer selector cleared
  Barcode input re-focused
  Show: "Sale complete. Total: X | Change: Y"
```

### 9.15 Printer Failure Flow

```
Invoice posts to DB (commits) successfully
THEN print attempted

If print fails:
  Show non-blocking dialog:
    "⚠️ Receipt not printed — Invoice #SI-XXXX saved"
    [Retry Print]  [Email Receipt]  [Skip]
    
  Does NOT offer: [Cancel Invoice]
  Invoice remains Posted regardless of print outcome
  
OperationsLog: printer_failure_event {
  printer_id, invoice_id, error_message, timestamp
}

Kitchen ticket failure:
  Show: "⚠️ Kitchen ticket failed"
  [Retry Kitchen Print] [Skip]
  Invoice NOT affected
  OperationsLog: kitchen_printer_failure_event
```

### 9.16 Kitchen / Bar Ticket Routing

```
After invoice commits:
  For each sale_item:
    Check item_group.printer_assignment:
      "bar"     → send to bar printer
      "kitchen" → send to kitchen printer
      "none"    → no ticket

  Group items by printer assignment
  Generate ticket per printer:
    ┌──────────────────────────────┐
    │ TAKEAWAY / دايني / ديليفري  │ ← order type (large, prominent)
    │ Order #SI-XXXX               │
    │ 14:32                        │
    ├──────────────────────────────┤
    │ 1× Iced Latte (Large)        │
    │   Extra shot                 │
    │   Oat milk                   │
    │   [note: extra hot]          │
    │                              │
    │ 2× Cappuccino (Medium)       │
    └──────────────────────────────┘
  
  Send to configured printer (ESC/POS)
  If fails → Kitchen Printer Failure dialog (§9.15)
```

---

## 🧾 10. Sales Cycle Flows

### 10.1 Sales Invoice Status Machine

```
Draft (مسودة)
  ↓ [Posting Engine runs]
Posted (مسجلة)
  ├─ payment_status: Unpaid → Partially Paid → Paid
  ├─ return_status: Not Returned → Partially Returned → Returned
  └─ [Cancel if allowed] → Cancelled (رقم محتجز، لا يُحذف)

Void: Draft only → marks Draft as invalid
```

### 10.2 Sales Return Flow

#### Flow A — Return with Original Invoice (Preferred)

```
User selects: Sales → Returns → [New Return]
  ↓
Search original invoice by number / customer / date
  ↓
Invoice found → display invoice lines
  ↓
Select items and quantities to return:
  Return qty ≤ (original qty − already returned qty)
  ↓
Select return reason:
  Defective / Wrong item / Customer changed mind /
  Size/quality issue / Other
  (reason always required)
  ↓
Select refund method:
  Default: original PaymentLine method
  Override: setting allows_cash_override
    (refund method different from original payment)
  ↓
[Post Return]
  ↓
BEGIN TRANSACTION
  1. StockMovement: SALES_RETURN_IN per returned item
  2. Revenue: ↓ by net return amount
  3. Tax Payable: ↓ by original tax (from snapshot)
  4. COGS: reversed using sale_item.avg_cost_at_posting
  5. Refund routing per original PaymentLine:
       Cash → Cashbox ↓ (cash paid out to customer)
       Card → Card Settlement ↓
               CardRefundReference created:
                 {card_amount, refund_reference: pending,
                  terminal_reversal_reference: pending,
                  refund_status: 'pending'}
               NOTE: cashier must enter reference later
       Wallet → Wallet account ↓
       Credit → CustomerARMovement: SALES_RETURN_CREDIT ↓
       Loyalty used → LoyaltyOutbox: REVERSE_REDEEM
  6. ShiftMovementSummary: return totals updated
  7. original_invoice.return_status updated
  8. AuditLog: sales_return_posted
COMMIT
  ↓
Print return receipt
```

#### Flow B — Return without Original Invoice

```
Only allowed if: allow_return_without_invoice = true (setting)

  User selects items to return manually
  Reason REQUIRED (always)
  Manager Approval REQUIRED (blocking)
  
  Refund method: configured default (cashbox or credit)
  
  posting_snapshot.linked_invoice = null
  AuditLog: unlinked_return flag
  
  Effects otherwise identical to Flow A
  (stock re-enters, refund processed)
```

#### Partial Return

```
User selects SUBSET of items from original invoice
  return_qty < original_qty (per line)
  
  original_invoice.return_status → Partially Returned
  
  Subsequent partial returns allowed until:
  total_returned_qty = original_qty (all lines)
  → return_status → Returned
```

### 10.3 Customer Receipt Flow (Collect Payment on Unpaid Invoice)

```
User opens Customer Profile → unpaid invoices listed
OR: Treasury → Customers → select customer → collect payment

  Show: list of unpaid/partially paid invoices
  Customer enters: amount, payment method

Invoice allocation:
  Default: FIFO — oldest unpaid invoice first
  Manual: user can drag/select which invoice(s) to allocate to
  Partial: allowed per invoice

[Post Receipt]
  ↓
BEGIN TRANSACTION
  1. CustomerARMovement: RECEIPT_PAYMENT ↓
  2. ReceiptAllocation records per invoice:
       {receipt_id, invoice_id, allocated_amount}
  3. FinancialAccountMovement per PaymentLine:
       Cash → Cashbox ↑, ShiftMovementSummary ↑
       Card → Card Settlement ↑
       Wallet → Wallet account ↑
  4. invoice.payment_status updated per allocation
  5. AuditLog: customer_receipt_posted
COMMIT
  ↓
Print customer receipt (document RC-YYYY-NNNNN)
```

---

## 📦 11. Purchase Cycle Flows

### 11.1 Purchase Invoice Flow

```
User: Purchases → [New Purchase Invoice]
  ↓
Select supplier
  ↓
Add lines:
  Per line:
    Select product (or free-text for non-stock)
    Select line_type: [Stock Item | Expense | Fixed Asset | Service]
    Select product unit (if stock item)
    Enter: quantity, unit cost, tax, discount
    Select warehouse (if stock item)
    
  line_type determines posting behavior:
    Stock Item → StockMovement PURCHASE_IN + avg_cost update
    Fixed Asset → FixedAsset record created
    Expense → FinancialAccountMovement expense account
    Service → FinancialAccountMovement service expense
  ↓
Select payment method:
  Cash → Cashbox selected
  Bank → Bank account selected
  Credit → invoice stays Unpaid, Supplier AP ↑
  Mixed → any combination
  ↓
[Post Invoice]
  ↓
BEGIN TRANSACTION (Posting Engine §3.2)
  Per line by line_type:
    Stock Item:
      StockMovement: PURCHASE_IN
      avg_cost recalculated (§7.1)
      FinancialAccountMovement: Inventory account ↑
    Fixed Asset:
      FixedAsset record created (status: Active)
      FixedAssetLedger: ASSET_PURCHASE
      FinancialAccountMovement: Fixed Asset account ↑
    Expense:
      FinancialAccountMovement: Expense account ↑
    Service:
      FinancialAccountMovement: Service Expense account ↑
  
  Payment routing:
    Cash → Cashbox ↓
    Bank → Bank account ↓
    Credit → SupplierAPMovement: CREDIT_PURCHASE ↑
  
  AuditLog: purchase_invoice_posted
  posting_snapshot stored
COMMIT
```

### 11.2 Purchase Return Flow

```
User: Purchases → [New Purchase Return]
  ↓
Select original Purchase Invoice (preferred):
  System shows original PI lines
  Select items and return qty
  Validate: return_qty ≤ (received_qty − already_returned)
  
  If no original PI:
    Check: allow_unlinked_purchase_return = true
    If false → block, require PI link
    If true → Manager Approval required
              Manual item entry + reason
  ↓
[Post Return]
  ↓
BEGIN TRANSACTION
  StockMovement: PURCHASE_RETURN_OUT
  Cost basis:
    Linked → use original PI line cost (snapshot)
    Unlinked → use current avg_cost
  avg_cost recalculated after removal
  
  Payment routing:
    Cash refund → Cashbox ↑
    Bank refund → Bank account ↑
    Credit → SupplierAPMovement: PURCHASE_RETURN_CREDIT ↓
  
  AuditLog: purchase_return_posted
COMMIT
```

### 11.3 Supplier Payment Voucher Flow

```
User: Suppliers → select supplier → [New Payment]
OR: Purchases → Supplier Payments → [New]
  ↓
Select supplier
Show: outstanding AP balance, list of unpaid purchase invoices
  ↓
Enter: amount, payment method (cash/bank)
  ↓
Invoice allocation:
  Default: FIFO (oldest unpaid PI first)
  Manual: select specific PIs
  Partial: allowed per PI
  ↓
[Post Payment]
  ↓
BEGIN TRANSACTION
  SupplierAPMovement: PAYMENT_MADE ↓
  PaymentAllocation records per PI
  FinancialAccountMovement:
    Cash → Cashbox ↓
    Bank → Bank account ↓
  AuditLog: supplier_payment_posted
COMMIT
  ↓
Print supplier payment voucher (PV-YYYY-NNNNN)
```

---

## 👤 12. Customer & Supplier Flows

### 12.1 Customer Creation Flow

```
User: Customers → [New Customer]
  ↓
Fill fields:
  name (required), phone, email, tax_number, address,
  credit_limit (default: 0 = unlimited),
  price_tier_id (select from tenant's tiers, default: Default)
  notes
  ↓
[Save]
  ↓
Customer record created
customer_code: auto-generated (configurable prefix)
AuditLog: customer_created
```

### 12.2 Opening Balance Setup (Customer)

```
Customer profile → [Set Opening Balance]
  ↓
Enter: opening balance amount (positive = customer owes us)
Enter: as-of date
Reason: "Pre-system balance" (pre-filled)
  ↓
[Save Opening Balance]
  ↓
BEGIN TRANSACTION
  CustomerARMovement: OPENING_BALANCE
    {customer_id, amount: +opening_balance, type: OPENING_BALANCE,
     balance_after: opening_balance}
  AuditLog: opening_balance_set
COMMIT
  
Rule: immutable after first period close
Override requires: Manager Approval + reason
```

### 12.3 Credit Limit Enforcement

```
At POS (or standalone invoice creation) when credit PaymentLine selected:
  
  ar_balance = Σ CustomerARMovement.amount (for this customer)
  new_total = ar_balance + invoice_total
  
  If new_total > customer.credit_limit AND credit_limit > 0:
    Check: allow_credit_limit_override setting
    ├─ true → Manager Approval Flow (blocking)
    │           Approved: proceed + note on invoice
    │           Rejected: block
    └─ false → Block: "Credit limit exceeded. Limit: X, Balance: Y"
```

### 12.4 Customer Statement Generation

```
Reports → Customer Reports → Customer Statement
  ↓
Select: customer, date range
  ↓
Query CustomerARMovement WHERE customer_id = X ORDER BY created_at
  ↓
Display:
  Date | Document | Type | Debit (+) | Credit (-) | Balance
  ─────────────────────────────────────────────────────
  01/06 | Opening  | OB   |  500      |            | 500
  05/06 | SI-00001 | Sale |  230      |            | 730
  10/06 | RC-00001 | Pay  |           |  300       | 430
  15/06 | SR-00001 | Ret  |           |   50       | 380
  ─────────────────────────────────────────────────────
  Closing Balance: 380 EGP (amount customer owes)
```

### 12.5 Supplier Creation + Opening Balance + Statement

Mirrors Customer flows (§12.1–12.4) for supplier/AP side.

---

### 12.6 Customer Advance Flow — [MVP Extended]

```
Customer pays before an invoice exists.
Example: deposit, reservation, advance payment.

User: Customer Profile → [New Advance]
  ↓
Enter: amount, payment method, notes
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement:
    Cash/Card/Wallet account ↑ per payment method
  CustomerARMovement:
    ADVANCE_RECEIPT ↑ as unallocated customer credit
  CustomerAdvance record created (or ledger entry with allocation_status = unallocated)
  AuditLog: customer_advance_posted
COMMIT

Later allocation:
  User opens unpaid invoice or customer statement
  Select unallocated advance
  Allocate to invoice(s) FIFO or manual
  ReceiptAllocation records created
  CustomerARMovement: ALLOCATION ↓
```

### 12.7 Supplier Advance Flow — [MVP Extended]

```
Business pays supplier before receiving a Purchase Invoice.
This is prepaid supplier balance / supplier credit.
It is NOT normal Accounts Payable owed to the supplier.

User: Supplier Profile → [New Advance Payment]
  ↓
Enter: amount, payment method (cash/bank), notes
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement:
    Cashbox/Bank ↓
  SupplierAPMovement:
    ADVANCE_PAYMENT recorded as supplier credit / prepaid balance
  SupplierAdvance record created (or ledger entry with allocation_status = unallocated)
  AuditLog: supplier_advance_posted
COMMIT

Later allocation:
  When Purchase Invoice is posted:
    Allocate advance to PI manually or FIFO
    PaymentAllocation records created
    SupplierAPMovement: ALLOCATION ↓
```

---

## 🏭 13. Inventory Flows

### 13.1 Warehouse Setup Flow

```
Settings → Warehouses → [New Warehouse]
  Fields: name, branch, type (retail/bar/kitchen/storage),
          is_default, is_active
  
  Branch default warehouse: used for sales if no warehouse selected
  Recipe ingredient warehouse: configured per branch
    setting: recipe_ingredient_warehouse_source
```

### 13.2 Opening Stock Entry Flow

```
Inventory → Opening Stock → [New Entry]
  ↓
Select: warehouse
Add items:
  product_unit_id, qty, avg_cost (unit cost)
  ↓
[Post Opening Stock]
  ↓
BEGIN TRANSACTION
  Per item:
    StockMovement: OPENING_BALANCE
      {product_id, product_unit_id, warehouse_id, qty,
       unit_cost: avg_cost_entered, movement_type: OPENING_BALANCE}
    product_unit.avg_cost = avg_cost_entered (if first entry)
  AuditLog: opening_stock_posted
COMMIT

Rule: immutable after period close
Override requires Manager Approval + reason
```

### 13.3 Stock Adjustment Flow

```
Inventory → Stock Adjustments → [New Adjustment]
  ↓
Select: warehouse, product, unit
Enter: current system qty shown, actual qty
System calculates: variance = actual − system
Enter: reason (REQUIRED)
  ↓
Check: require_approval_for_adjustment setting
  If true → Manager Approval Flow
  ↓
[Post Adjustment]
  ↓
BEGIN TRANSACTION
  variance > 0: StockMovement ADJUSTMENT_IN
    avg_cost recalculated if new cost provided
  variance < 0: StockMovement ADJUSTMENT_OUT
    inventory_loss_value = avg_cost × |variance| (informational)
  AuditLog: stock_adjustment_posted (reason, user, variance, value)
COMMIT
```

### 13.4 Damage / Wastage Flow

```
Inventory → Damage/Wastage → [New Entry]
OR: POS Café sidebar (manager access during shift)
  ↓
Select: product, unit, warehouse, qty
Enter: reason (REQUIRED)
  ↓
System calculates:
  inventory_loss_value = product_unit.avg_cost × qty
  Shows: "This entry will reduce profit by X EGP"
  ↓
[Post]
  ↓
BEGIN TRANSACTION
  StockMovement: DAMAGE_OUT {qty, warehouse_id, unit_cost: avg_cost}
  DamageWastage record: {product_id, warehouse_id, qty, avg_cost_at_posting,
                          inventory_loss_value, reason, shift_id, created_by}
  FinancialAccountMovement:
    Inventory Loss account ↑ (by inventory_loss_value)
    Inventory value account ↓ (by inventory_loss_value)
  ShiftMovementSummary: wastage_total ↑ (NOT expense_total)
  AuditLog: damage_wastage_posted
COMMIT
```

### 13.5 Warehouse Transfer Flow

```
Inventory → Warehouse Transfers → [New Transfer]
  ↓
Select: source warehouse, destination warehouse
  (must be different)
Add items: product, unit, qty
Enter: reason
  ↓
Check: require_approval_for_transfer setting
  If true AND amount > threshold → Manager Approval
  ↓
[Post Transfer]
  ↓
BEGIN TRANSACTION
  StockMovement: TRANSFER_OUT {source_warehouse, qty, unit_cost: avg_cost}
  StockMovement: TRANSFER_IN  {dest_warehouse, qty, unit_cost: avg_cost}
  avg_cost at destination = avg_cost at source (no change)
  AuditLog: warehouse_transfer_posted
COMMIT
```

### 13.6 Item Movement Query Flow

```
Inventory → Item Movement Report
  ↓
Filter: product, warehouse, date range, movement type(s)
  ↓
Query StockMovement WHERE filters
  ↓
Display:
  Date | Movement Type | Document | Qty In | Qty Out | Balance
  12/06 | OPENING_BALANCE |          | 100    |         | 100
  13/06 | PURCHASE_IN     | PI-00001 |  50    |         | 150
  14/06 | SALE_OUT        | SI-00012 |        |  10     | 140
  14/06 | RECIPE_CONSUME  | SI-00013 |        |   1.8   | 138.2
  15/06 | DAMAGE_OUT      | DMG-001  |        |   2     | 136.2
```

### 13.7 Recipe Consume Flow (Auto-Triggered on POS Sale)

```
Inside Posting Engine STEP 15 (per recipe product sold):
  ↓
Fetch recipe: RecipeIngredient list for product
  ↓
Determine ingredient warehouse:
  Check: recipe_ingredient_warehouse_source setting
  ├─ branch_default → use branch.default_ingredient_warehouse
  ├─ item_specific  → use ingredient_product.default_warehouse
  └─ pos_selected   → use sale_invoice.warehouse_id

For each ingredient:
  consumed_qty = recipe_qty × (1 + wastage_factor) × unit_conversion
  
  Check stock in resolved warehouse:
    If insufficient → apply negative stock rules (§3.2 STEP 5)
  
  StockMovement: RECIPE_CONSUME {
    product_id: ingredient.product_id,
    product_unit_id: ingredient.product_unit_id,
    warehouse_id: resolved_warehouse,
    qty: -consumed_qty,
    unit_cost: ingredient.avg_cost,
    source_document_type: sales_invoice,
    source_document_id: invoice.id
  }
```

### 13.8 Stocktaking Session Flow — [MVP Extended]

```
Inventory → Stocktaking → [New Count Session]
  ↓
Select: branch, warehouse, item group(s) or all
  ↓
System creates session:
  count_session.status → In Progress
  Freezes expected_qty snapshot per item:
    expected_qty = current stock in StockMovement ledger
  ↓
User enters actual counts (one item at a time or bulk):
  count_line.actual_qty = [cashier counts physical stock]
  variance = actual_qty − expected_qty (shown in real-time)
  variance_value = |variance| × avg_cost (shown)
  ↓
Submit for approval:
  count_session.status → Pending Approval
  ↓
Manager reviews:
  Per item: approve or reject variance
  Can approve all or select specific
  ↓
Manager clicks [Post Approved Variances]:
  ↓
BEGIN TRANSACTION
  Per approved item with variance ≠ 0:
    If variance > 0: StockMovement ADJUSTMENT_IN
    If variance < 0: StockMovement ADJUSTMENT_OUT
  count_session.status → Posted (immutable)
  AuditLog: stocktaking_posted (who counted, who approved)
COMMIT
```

### 13.9 Negative Stock Control & Sale Flow

Negative stock means the system allows a sale or recipe consumption even when the current stock balance is not enough. This is useful when stock exists physically but the purchase invoice has not been entered yet, or when the business chooses to continue selling and fix the inventory later.

This is controlled from:

```
Settings → Inventory Settings → Negative Stock Control
```

#### 13.9.1 Negative Stock Settings

```
allow_negative_stock_sale: boolean
  false = block sale when stock is insufficient
  true  = allow sale according to the rules below

require_manager_approval_for_negative_stock: boolean
  true = manager PIN/password required before posting negative stock sale

negative_stock_scope: enum
  all_products
  selected_products_only
  ingredients_only
  products_and_ingredients

show_negative_stock_warning_to_cashier: boolean
  true = show clear warning before posting

create_negative_stock_alert: boolean
  true = create alert record for manager dashboard

negative_stock_costing_method: enum
  last_known_average_cost
  default_purchase_price
  zero_cost_require_later_adjustment

auto_settle_negative_stock_on_purchase: boolean
  true = later purchase automatically covers oldest negative balances first

create_cogs_adjustment_after_negative_stock_settlement: boolean
  true = post COGS adjustment if actual purchase cost differs from estimated cost

block_negative_stock_for_batch_expiry_serial_items: boolean
  true = batch/expiry/serial-controlled items cannot go negative

show_negative_stock_in_manager_dashboard: boolean
  true = dashboard shows negative stock alerts and unresolved settlements
```

Product-level override:

```
product.allow_negative_stock_override: null / allow / block

null  = follow tenant setting
allow = allow this item even if global scope is selected products only
block = always block this item from negative stock sale
```

#### 13.9.2 Standard Stock Item Negative Sale

```
Sale attempts to deduct stock item
  ↓
Calculate available_qty in selected warehouse
Calculate required_qty = sale_qty × product_unit.conversion_factor
  ↓
If available_qty >= required_qty:
  Continue normal SALE_OUT flow

If available_qty < required_qty:
  shortage_qty = required_qty − available_qty
  resulting_balance = available_qty − required_qty

  Check block_negative_stock_for_batch_expiry_serial_items:
    If item is batch/expiry/serial controlled AND setting = true:
      Block sale, show: "Cannot sell negative stock for batch/serial item"

  Check allow_negative_stock_sale:
    false → Block sale
            Show: "Insufficient stock. Available: X, Required: Y"

    true → Check negative_stock_scope + product override
            If item not allowed by scope → Block sale
            If allowed → continue

  If show_negative_stock_warning_to_cashier = true:
    Show warning modal:
      Item name
      Available qty
      Required qty
      Resulting negative balance
      Costing method that will be used

  If require_manager_approval_for_negative_stock = true:
    Trigger Manager Approval Flow
      Approved → continue
      Rejected → block sale

  Create StockMovement: SALE_OUT
    qty = -required_qty
    negative_stock_flag = true
    negative_stock_shortage_qty = shortage_qty
    cost_status = estimated if estimated cost used

  Create NegativeStockAlert if setting enabled
  Continue Posting Engine
```

#### 13.9.3 Recipe Ingredient Negative Consume

```
Recipe Product sold at POS
  ↓
For each ingredient:
  Resolve ingredient warehouse
  Calculate consumed_qty from recipe
  Check available ingredient stock

If ingredient stock is insufficient:
  Apply same negative stock settings as stock items

If one ingredient is blocked:
  Entire invoice posting is blocked

If allowed:
  StockMovement: RECIPE_CONSUME
    ingredient qty goes negative
    negative_stock_flag = true
    cost_status = estimated if needed

  NegativeStockAlert created per ingredient if setting enabled
```

#### 13.9.4 Negative Stock Alert Creation

```
If create_negative_stock_alert = true:
  Create NegativeStockAlert record:
    tenant_id
    branch_id
    warehouse_id
    product_id
    product_unit_id
    source_document_type = SalesInvoice / RecipeConsume
    source_document_id
    shortage_qty
    resulting_balance
    estimated_unit_cost
    cost_status = estimated / actual
    status = open
    created_by
    created_at

If show_negative_stock_in_manager_dashboard = true:
  Manager Dashboard card shows:
    "Negative Stock Items"
    Count of open alerts
    Total estimated value impact
```

#### 13.9.5 Negative Stock Settlement on Purchase

When a Purchase Invoice is posted for an item with a negative balance, the purchase increases stock normally. If auto-settlement is enabled, the system also records which purchase quantities covered old negative balances.

```
Purchase Invoice posts PURCHASE_IN for product/unit/warehouse
  ↓
Check current balance before purchase
  If balance_before >= 0:
    Normal purchase flow only

  If balance_before < 0:
    negative_qty_to_cover = abs(balance_before)
    purchase_qty = received quantity
    settled_qty = min(negative_qty_to_cover, purchase_qty)

    New balance = balance_before + purchase_qty

    If auto_settle_negative_stock_on_purchase = false:
      Balance still updates normally through StockMovement
      No formal settlement record created
      Alerts remain open until manually reviewed

    If auto_settle_negative_stock_on_purchase = true:
      Find oldest open negative StockMovements / NegativeStockAlerts first
      Allocate settled_qty FIFO by created_at

      Create NegativeStockSettlement record(s):
        {purchase_invoice_id, purchase_line_id,
         negative_stock_alert_id, negative_stock_movement_id,
         product_id, product_unit_id, warehouse_id,
         settled_qty, actual_unit_cost, estimated_unit_cost,
         cost_difference, status: settled}

      Close or partially close NegativeStockAlert:
        fully covered → status = settled
        partially covered → remaining_qty updated, status = partial

      If create_cogs_adjustment_after_negative_stock_settlement = true:
        Run COGS Adjustment Flow (§7.7)

      AuditLog: negative_stock_settled
```

Example:

```
Milk balance before purchase = -5 liters
Purchase Invoice receives      = +20 liters
Settled negative qty           = 5 liters
Final stock balance            = +15 liters
```

#### 13.9.6 Manual Negative Stock Review

```
Inventory → Negative Stock Alerts
  ↓
Manager sees:
  Product / ingredient
  Warehouse
  Current balance
  Source sale / recipe consume
  Estimated cost
  Age of alert
  Suggested action

Available actions:
  [Create Purchase Invoice] — starts PI filtered to missing item
  [Mark Reviewed] — no stock effect, AuditLog only
  [Create Stock Adjustment] — if physical stock was counted
  [Export Report]

All actions require permission:
  inventory.negative_stock.review
```

#### 13.9.7 Phase Classification

```
MVP Core:
  allow_negative_stock_sale toggle
  block / allow / manager approval behavior
  cashier warning
  NegativeStockAlert
  Dashboard alert
  Product-level override

MVP Core or MVP Extended depending on implementation scope:
  automatic balance offset by later PurchaseMovement

MVP Extended:
  formal NegativeStockSettlement records
  COGS Adjustment after settlement
  Estimated Cost Sales Report

Phase 2:
  strict batch/expiry/serial settlement
  FIFO layer-based costing
```

---

## 🏢 14. Fixed Asset Flows

### 14.1 Asset Purchase Flow (via Purchase Invoice)

```
In Purchase Invoice form:
  Add line → select line_type = Fixed Asset
  Fields:
    asset_name (required)
    asset_category_id
    serial_number (optional)
    acquisition_date (defaults to invoice date)
    salvage_value (optional, default 0)
    useful_life_months (required for depreciation)
    
[Post Invoice] triggers:

BEGIN TRANSACTION
  ...normal PI posting...
  
  For each Fixed Asset line:
    FixedAsset record created:
      {tenant_id, name, category, serial, acquisition_date,
       acquisition_cost: line_unit_cost × qty,
       salvage_value, useful_life_months,
       current_book_value: acquisition_cost,
       status: Active, purchase_invoice_id: PI.id}
    
    FixedAssetLedger: ASSET_PURCHASE
    
    FinancialAccountMovement:
      Fixed Asset account ↑ (by acquisition_cost)
      NO Inventory, NO Expense, NO COGS
    
    AuditLog: fixed_asset_created
COMMIT
```

### 14.2 Depreciation Posting Flow — [MVP Extended]

```
Fixed Assets → [Asset Name] → [Post Depreciation]
OR: Monthly batch trigger (manual in MVP, auto in Phase 2)
  ↓
System calculates:
  monthly_depreciation =
    (acquisition_cost − salvage_value) ÷ useful_life_months
  
  remaining_months = useful_life_months − months_depreciated
  If remaining_months <= 0: cannot depreciate further
  ↓
[Post Depreciation for Month X]
  ↓
BEGIN TRANSACTION
  FixedAssetLedger: DEPRECIATION {amount: monthly_depreciation}
  FinancialAccountMovement:
    Depreciation Expense account ↑ (reduces P&L)
    Accumulated Depreciation account ↑ (contra-asset)
  asset.current_book_value ↓ by monthly_depreciation
  asset.accumulated_depreciation ↑ by monthly_depreciation
  AuditLog: depreciation_posted
COMMIT
```

### 14.3 Asset Write-off Flow — [MVP Extended]

```
Fixed Assets → [Asset Name] → [Write Off]
  ↓
Require reason
→ Manager Approval Flow (blocking — always)
  ↓
If approved:
BEGIN TRANSACTION
  loss_amount = asset.current_book_value
  FinancialAccountMovement:
    Loss on Disposal account ↑ (reduces P&L)
  FixedAssetLedger: WRITE_OFF
  asset.status → Written-off
  AuditLog: asset_written_off (reason, approver, loss_amount)
COMMIT
```

### 14.4 Asset Sale Flow — [MVP Extended]

```
Fixed Assets → [Asset Name] → [Record Sale]
  ↓
Enter: sale proceeds, payment method (cash/bank), date
  ↓
System calculates:
  book_value = asset.current_book_value
  gain = proceeds − book_value (if positive)
  loss = book_value − proceeds (if negative)
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement:
    Cashbox/Bank ↑ by proceeds
    If gain > 0: Other Income account ↑ by gain
    If loss > 0: Loss on Disposal account ↑ by loss
  FixedAssetLedger: ASSET_SALE
  asset.status → Sold
  AuditLog: asset_sold
COMMIT
```

### 14.5 Asset Maintenance Flow — [MVP Extended]

```
Fixed Assets → [Asset Name] → [Record Maintenance]
  ↓
Enter:
  maintenance_date
  description
  cost
  payment method (cash/bank/credit)
  attachment/receipt (optional)
  ↓
BEGIN TRANSACTION
  AssetMaintenance record created
  FixedAssetLedger: MAINTENANCE
  FinancialAccountMovement:
    Maintenance/Expense account ↑
    Cashbox/Bank/Supplier AP per payment method
  Asset status may become: Under Maintenance
  AuditLog: asset_maintenance_recorded
COMMIT

Rule:
  Normal maintenance is expense.
  Capital improvement that extends useful life is Phase 2.
```

### 14.6 Asset Transfer Flow — [MVP Extended]

```
Fixed Assets → [Asset Name] → [Transfer]
  ↓
Select: destination branch / location / custodian
Enter: reason
  ↓
BEGIN TRANSACTION
  FixedAssetLedger: TRANSFER
  asset.branch_id / location / custodian_user_id updated
  No P&L impact
  No cash/bank/stock movement
  AuditLog: asset_transferred
COMMIT
```

---

## 💰 15. Treasury Flows

### 15.1 Payment Method Routing Flow

```
Payment method registered in system:
  method_type: cash / bank / card / wallet / credit
  linked_account_type: cashbox / bank_account / card_settlement / wallet_account
  linked_account_id: specific account
  
On every document posting:
  For each PaymentLine:
    Resolve linked account via payment_method.linked_account_id
    Create FinancialAccountMovement to that account
    
  Cash → goes to shift.cashbox_id (active cashbox)
  Bank → goes to configured bank_account
         Used for supplier payments, bank receipts, transfers
  Card → goes to configured card_settlement_account
         (NOT cashbox, NOT direct bank — never)
  Wallet → goes to configured wallet_account
            (NOT cashbox — never)
  Credit → goes to CustomerARMovement (no financial account)
```

### 15.2 Cash In Flow

```
Treasury → [Cash In]
  ↓
Enter: amount, reason (required), cashbox
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: Cashbox ↑
  ShiftMovementSummary: cash_in_total ↑
  AuditLog: cash_in_posted
COMMIT
```

### 15.3 Cash Out Flow

```
Treasury → [Cash Out]
  ↓
Enter: amount, reason (required), cashbox
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: Cashbox ↓
  ShiftMovementSummary: cash_out_total ↑
  AuditLog: cash_out_posted
COMMIT
```

### 15.4 Cashbox Transfer Flow

```
Treasury → [Transfer Between Cashboxes]
  ↓
Enter: source cashbox, destination cashbox, amount, reason
  ↓
Check: amount > threshold → Manager Approval
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: Source cashbox ↓
  FinancialAccountMovement: Destination cashbox ↑
  AuditLog: cashbox_transfer_posted
COMMIT
```

### 15.5 Cash Drop Flow — [MVP Extended]

```
POS header → [Cash Drop] (manager access during shift)
OR: Treasury → [Cash Drop]
  ↓
Enter: amount, destination safe/cashbox, notes
  ↓
Check: require_approval_for_cash_drop → Manager Approval
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: Cash Drawer ↓
  FinancialAccountMovement: Main Safe ↑
  ShiftMovementSummary: cash_drop_total ↑
  AuditLog: cash_drop_posted
COMMIT

NOTE: Cash Drop is NOT an expense. No P&L impact.
      It is an internal transfer between two cashboxes.
```

---

## 💸 16. Expense Flows

### 16.1 Expense Entry Flow

```
Treasury → Expenses → [New Expense]
OR: During shift via POS sidebar
  ↓
Enter:
  category_id (required)
  amount (required)
  description (optional)
  payment_method: cash (from cashbox) / bank
  date: defaults to today
  attachment: receipt photo [MVP Extended]
  ↓
Check: expense_approval_threshold setting
  If amount > threshold [MVP Extended] → Manager Approval
  ↓
[Post Expense]
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: Expense account ↑
  Payment routing:
    Cash → Cashbox ↓ + ShiftMovementSummary.expense_total ↑
    Bank → Bank account ↓
  AuditLog: expense_posted
COMMIT
  ↓
Print expense voucher (EXP-YYYY-NNNNN) if needed
```

---

## 📎 17. Document Attachment Flows — [MVP Extended]

### 17.1 Attachment Upload Flow

```
Supported entities:
  Purchase Invoice, Expense Entry, Fixed Asset,
  Asset Maintenance, Supplier Payment, Customer Receipt,
  Sales Return, Shift Close, Card Settlement Reference

User opens document detail → Attachment Panel
  ↓
Select or drag file
  ↓
Server validates:
  file type (JPG/PNG/PDF by default)
  max file size per tenant setting
  user permission: attachments.upload
  entity exists and belongs to same tenant
  ↓
Upload to S3 tenant-scoped path
  ↓
BEGIN TRANSACTION
  DocumentAttachment record created:
    {tenant_id, entity_type, entity_id, file_name,
     file_url, file_type, file_size, uploaded_by}
  AuditLog: attachment_uploaded
COMMIT
```

### 17.2 Attachments on Cancelled Documents

```
Cancelled documents:
  Business fields remain read-only and locked.
  Attachments may still be uploaded with permission.

Reason:
  Business may need cancellation proof, refund proof,
  manager approval proof, or receipt evidence after cancellation.

Rules:
  attachments.upload_on_cancelled permission required
  Upload/delete writes AuditLog
  Attachment history remains visible
```

---

## 🏷️ 18. Discount & Charges Flows

### 18.1 Item-Level Discount Flow

```
Cart line → [Discount] button
  ↓
Enter: % or fixed amount
  ↓
Check: allow_item_discount setting
  If false → block
  
Check: max_cashier_discount_percent (for cashier role)
  If % exceeds limit → Manager Approval Flow (§2.8)
  
Tax Engine recalculates:
  If discount_before_tax = true: discount reduces taxable base
  If discount_before_tax = false: tax calculated on pre-discount price
  
Cart line updated with discount
Invoice totals recalculated
```

### 18.2 Invoice-Level Discount Flow

```
Cart footer → [Invoice Discount] button
  ↓
Enter: % or fixed amount applied to subtotal
  ↓
Same checks as item discount (§17.1)
Applied AFTER all line discounts (on the subtotal)
Tax Engine recalculates from new base
```

### 18.3 Service Charge / Fee Addition Flow

```
Cart → [Add Charge] button
  ↓
Select charge type: delivery / packaging / service / other
Enter amount (or auto-calculated if fixed per order type)
  ↓
charge.charge_is_taxable checked:
  If true → charge added to taxable base
  Tax Engine recalculates
  
Charge shown as separate line in cart and on receipt
```

### 18.4 Coupon Validation Flow — [MVP Extended]

```
Cart → [Enter Coupon Code]
  ↓
Submit code
  ↓
Server validates:
  Code exists in DiscountCode table?
  Code not expired (valid_from ≤ today ≤ valid_until)?
  max_uses not reached?
  minimum_invoice_amount met?
  applicable to current items/groups?
  
  ├─ Valid → apply discount (item or invoice level per code config)
  │           uses_count ↑
  │           Show: "Coupon applied: X% off"
  └─ Invalid → show specific reason:
                "Code expired" / "Not applicable" /
                "Minimum order not met" / "Usage limit reached"
```

---

## 🏆 19. Loyalty Engine Flows — [MVP Extended]

### 19.1 Loyalty Points Earn Flow

```
INSIDE posting transaction (STEP 20 of §3.2):
  If loyalty_program_active = true AND customer selected:
    Create LoyaltyOutbox record:
      {invoice_id, customer_id, 
       points_to_award: 0 (calculated after commit),
       status: pending}

AFTER commit (Celery task):
  Fetch: LoyaltyOutbox WHERE status = pending
  Check: invoice still exists and posting_status = Posted
  Check: LoyaltyOutbox not already processed (idempotent)
  
  Calculate points:
    base_amount = invoice.total_due − loyalty_discount_applied
    
    For each LoyaltyRule:
      rule_type = invoice_amount:
        points += floor(base_amount ÷ rule.amount) × rule.points_earned
      rule_type = per_item:
        For each matching item: points += qty × rule.points_earned
      rule_type = per_group:
        For each item in matching group: points += qty × rule.points_earned
    
    NOTE: Points NOT earned on loyalty_discount portion
    NOTE: earn_on_credit setting controls credit sale behavior
  
  Create LoyaltyTransaction: EARN {
    customer_id, invoice_id, points: +calculated, type: EARN,
    expires_at: today + points_expiry_days (if > 0)
  }
  
  CustomerPoints.balance ↑ by points_earned
  LoyaltyOutbox.status → processed
  
  If Celery fails → retries automatically (idempotent)
  Points cannot be permanently lost
```

### 19.2 Loyalty Redemption Flow

```
At POS payment step:
  If customer selected AND loyalty_program_active:
    Fetch: CustomerPoints.balance for this customer
    Show: loyalty discount panel
    
    max_redeemable_points = min(
      customer.balance,
      floor(invoice_total × max_redemption_percent ÷ amount_per_point_value)
    )
    
    Cashier enters: points_to_redeem (≤ max_redeemable_points)
    
    discount_value = points_to_redeem × amount_per_point_value
    
    Show: "خصم نقاط الولاء: −X جنيه"
    Show: "الباقي للسداد: Y جنيه"
    
    [Apply Loyalty Discount] → invoice recalculates

INSIDE posting transaction (STEP 18 of §3.2):
  LoyaltyRedemption record:
    {invoice_id, customer_id, points_redeemed, discount_value}
  
  CustomerPoints.balance ↓ by points_redeemed (IMMEDIATE, not outbox)
  (Redemption must be certain before invoice commits)
  
  FinancialAccountMovement:
    Loyalty Discount account ↑ (discount recorded as account entry)
    NOT Cashbox, NOT revenue reversal
  
  ShiftMovementSummary: loyalty_discount_total ↑ (informational)
  
  NOTE: Cash/Card/Wallet PaymentLines are on REMAINING amount
         (after loyalty discount applied to total)
```

### 19.3 Points Reversal on Return

```
On Sales Return (AFTER return commits, via outbox):
  Fetch original LoyaltyTransaction (EARN) for this invoice
  
  If full return:
    points_to_reverse = original earned points
  If partial return:
    points_to_reverse = earned_points × (return_amount ÷ original_paid)
  
  Create LoyaltyOutbox: REVERSE_EARN {invoice_id, return_invoice_id}
  
  AFTER commit (Celery):
    Create LoyaltyTransaction: REVERSE_EARN {points: -points_to_reverse}
    CustomerPoints.balance ↓
    
  If loyalty was REDEEMED on original invoice:
    Restore redeemed points via LoyaltyOutbox: REVERSE_REDEEM
    CustomerPoints.balance ↑ by redeemed_points
```

### 19.4 Points Expiry Flow (Nightly Batch)

```
Celery task runs: every night at 00:00

  Query LoyaltyTransaction WHERE:
    type = EARN AND
    expires_at IS NOT NULL AND
    expires_at <= today AND
    NOT already expired (check for matching EXPIRE transaction)
  
  For each batch of expiring points:
    Create LoyaltyTransaction: EXPIRE {
      points: -amount, type: EXPIRE,
      customer_id, note: "Points expired"
    }
    CustomerPoints.balance ↓
  
  [Future: send notification to customer]
```

### 19.5 Manual Points Adjustment

```
Customer profile → Loyalty → [Adjust Points]
  ↓
Permission required: loyalty.manual_adjust
  ↓
Enter: amount (+ to add, − to deduct), reason (required)
→ Manager Approval Flow (blocking)
  ↓
If approved:
  Create LoyaltyTransaction: MANUAL_ADJUST
  CustomerPoints.balance updated
  AuditLog: loyalty_manual_adjustment
```

---

## 📅 20. Opening Balances Flows

### 20.1 Cashbox Opening Balance

```
Treasury → Cashboxes → [Set Opening Balance]
  ↓
Enter: amount
  ↓
BEGIN TRANSACTION
  FinancialAccountMovement: OPENING_BALANCE for cashbox
  AuditLog: cashbox_opening_balance_set
COMMIT
```

### 20.2 Customer Opening Balance

See §12.2.

### 20.3 Supplier Opening Balance

```
Suppliers → [Supplier Name] → [Set Opening Balance]
  ↓
Enter: amount (positive = we owe supplier)
  ↓
BEGIN TRANSACTION
  SupplierAPMovement: OPENING_BALANCE
  AuditLog: supplier_opening_balance_set
COMMIT
```

### 20.4 Item Opening Stock

See §13.2.

### 20.5 Opening Balance Rules

```
All opening balances:
  Set once per entity
  Override requires Manager Approval + reason
  Immutable after first period close [MVP Extended]
  Included in all reports from day one (shown as oldest entry)
```

---

## 🔒 21. Period Lock Flow — [MVP Extended]

```
Settings → Period Lock → [Lock Period]
OR: Treasury → [Lock Day]
  ↓
Select: from date, to date, branch (or all branches)
Enter: notes
  ↓
Permission required: period.lock
  ↓
PeriodLock record created:
  {tenant_id, branch_id, lock_from, lock_to, locked_by, locked_at}

Effect on documents within locked period:
  Cancel/edit → requires permission: document.edit_locked_period
                + Manager Approval + reason
  New documents dated in locked period → blocked, must use today's date

Override:
  Manager enters reason → Manager Approval Flow
  AuditLog: locked_period_document_modified
  Document modified with note: "Modified after period lock by [user]"
```

---

## 📊 22. Report Generation Flows

### 22.1 General Report Flow

```
Reports Center → select category → select report
  ↓
Set filters: date range, branch, warehouse, cashier, etc.
  ↓
[Generate Report] → API call with filters
  ↓
Server queries from MOVEMENT LEDGERS (not document state):
  Sales → StockMovement + FinancialAccountMovement
  Customer → CustomerARMovement
  Supplier → SupplierAPMovement
  Shift → ShiftMovementSummary
  Loyalty → LoyaltyTransaction
  Assets → FixedAssetLedger
  ↓
Aggregate, calculate totals, sort
  ↓
Return: report data + metadata (date, filters applied)
  ↓
Client renders: table + KPI summary row + totals
  ↓
[Export PDF] or [Export Excel]:
  Server renders file
  AccessLog: report_exported (user, report_type, filters, timestamp)
  Download to client
```

### 22.2 P&L Calculation Flow

```
Query for date range:

Net Revenue:
  FROM FinancialAccountMovement
  WHERE account_type = 'revenue' AND date in range
  SUM(amount)

COGS:
  FROM FinancialAccountMovement
  WHERE account_type = 'cogs' AND date in range
  SUM(amount)

Inventory Loss:
  FROM FinancialAccountMovement
  WHERE account_type = 'inventory_loss' AND date in range
  SUM(amount)

Gross Profit:
  Net Revenue − COGS − Inventory Loss

Operating Expenses:
  FROM FinancialAccountMovement
  WHERE account_type = 'expense' AND date in range
  SUM(amount)

Depreciation [MVP Extended]:
  FROM FinancialAccountMovement
  WHERE account_type = 'depreciation_expense' AND date in range
  SUM(amount)

Net Profit:
  Gross Profit − Operating Expenses − Depreciation

Tax Payable (shown separately):
  FROM FinancialAccountMovement
  WHERE account_type = 'tax_payable' AND date in range
  SUM(amount)
  NOTE: NOT in P&L — shown as separate line
```

### 22.3 Shift Report Generation (Auto on Close)

```
On shift close (inside transaction):
  
  Pull all ShiftMovementSummary fields
  
  Generate report data:
    Header: branch, terminal, cashbox, user, opened_at, closed_at
    
    Sales Summary:
      Cash sales: cash_sales_total
      Customer cash receipts: customer_cash_receipts_total
      Card sales: card_sales_total
      Wallet sales: wallet_sales_total
      Credit sales: credit_sales_total
      Loyalty discounts: loyalty_discount_total
      Total invoices: invoice_count
      
    Returns:
      Cash returns: cash_returns_total
      Card returns: card_returns_total
      Return count: return_count
      
    Expenses: expense_total
    Wastage: wastage_total
    
    Cash Movement:
      Opening cash (expected): opening_cash_expected
      Opening cash (actual): opening_cash_actual
      Opening variance: opening_variance
      Cash in: cash_in_total
      Cash out: cash_out_total
      Cash drop: cash_drop_total
      Expected closing cash: expected_closing_cash
      Actual counted cash: actual_closing_cash
      Closing shortage/surplus: closing_variance
      
    Card Reconciliation:
      Expected card: card_expected
      Terminal batch: card_terminal_batch
      Variance: card_variance
      
    Wallet Reconciliation:
      [wallet totals per type]
      
    Cancelled invoices: cancel_count
    Manager approvals: [list of approvals given this shift]

Save as ShiftReport record (for later retrieval)
```

### 22.4 Negative Stock Reports

These reports are available when Negative Stock Control is enabled.

#### Negative Stock Alert Report

```
Reports → Inventory → Negative Stock Alerts
  ↓
Filters:
  date range, branch, warehouse, product, status, cashier, source document
  ↓
Query NegativeStockAlert + StockMovement
  ↓
Display:
  Product | Warehouse | Source Doc | Shortage Qty | Resulting Balance |
  Estimated Cost | Age | Status | Approved By | Settlement Status
```

#### Negative Stock Settlement Report — [MVP Extended]

```
Reports → Inventory → Negative Stock Settlements
  ↓
Query NegativeStockSettlement
  ↓
Display:
  Original Sale / Consume Movement
  Purchase Invoice that covered it
  Settled Qty
  Estimated Unit Cost
  Actual Unit Cost
  Cost Difference
  COGS Adjustment document
```

#### Estimated Cost Sales Report — [MVP Extended]

```
Reports → Sales / Inventory → Estimated Cost Sales
  ↓
Query sale lines and recipe consume movements where cost_status = estimated
  ↓
Show all sales posted while stock was negative
  Helps manager know which sales need purchase settlement or cost review
```

#### COGS Adjustment Report — [MVP Extended]

```
Reports → Finance → COGS Adjustments
  ↓
Query COGSAdjustment records
  ↓
Show:
  adjustment date, original sale, purchase invoice, product,
  estimated cost, actual cost, adjustment amount, period posted
```

---

## 📥 23. Data Import / Export Flows — [MVP Extended]

### 23.1 Import Flow

```
Settings → Data Import → [Import Products / Customers / etc.]
  ↓
Download template → fill in data → upload CSV/Excel
  ↓
Server runs validation:
  Check required fields
  Check data types (numeric, date format, etc.)
  Check duplicates (by barcode / customer_code / etc.)
  Check references (item group exists, unit exists, etc.)
  ↓
Show preview:
  Valid rows (green) — count
  Warning rows (amber) — duplicate found, will update
  Error rows (red) — cannot import
  
  Summary: "X will import, Y will update, Z errors"
  ↓
  [Proceed with Import] or [Fix Errors]
  ↓
BEGIN TRANSACTION
  Per valid row: create or update record
  Per update row: show diff, apply changes
  DataImportLog record:
    {tenant_id, import_type, rows_created, rows_updated,
     rows_failed, file_name, imported_by, imported_at}
  AuditLog: data_import_completed
COMMIT
```

### 23.2 Export Flow

```
Any report screen → [Export]
  ↓
Select format: Excel / PDF / CSV
  ↓
Server generates file with applied filters
AccessLog: export_generated
  ↓
File download to client
```

---

## 🔌 24. Offline Sync Flows

### 24.1 Offline Detection

```
Service Worker monitors: fetch to API
  If API unreachable:
    Set app state: offline = true
    Show: OfflineBanner
    Show: "○ Offline — X invoices pending"
    
  Affected behaviors:
    Settings changes → blocked, show: "Requires internet"
    Permission changes → blocked
    Purchase invoices → blocked (online only in MVP)
    Reports → blocked (show cached last data if available)
    
  Allowed offline:
    Cash POS sales → queue in IndexedDB
    Expenses (cash) → queue in IndexedDB
    Shift continuation (not new shift open if first time)
    Recipe consume → calculated from cached product data
    Customer selection → from cached customer list
```

### 24.2 Offline Queue (IndexedDB)

```
Every offline action creates an OutboxItem:
  {
    id: UUID (= idempotency_key),
    action_type: 'sale' / 'expense' / 'cash_in' / etc.,
    payload: {full document data},
    created_at: timestamp,
    status: 'pending'
  }

Visual feedback:
  Invoice created locally → shows in sales list with "⏳ Pending sync" badge
  sync_status = Pending Sync
```

### 24.3 Online Restoration Sequence

```
Service Worker detects: API reachable again
  ↓
Set app state: online = true
Show: "● Syncing..." banner
  ↓
Process OutboxItems in FIFO order:
  For each pending item:
    POST to API with idempotency_key
    Server processes (or returns existing if duplicate)
    Update OutboxItem.status → synced
    Update local document.sync_status → Synced
  ↓
Show: "✓ Sync complete — X invoices uploaded"
  ↓
Refresh: product cache, customer cache, permissions, subscription status
```

### 24.4 Conflict Resolution

```
Financial documents (invoices, receipts):
  Explicit resolution required if conflict detected
  Server compares timestamps
  If conflict: flag for manager review

Non-financial data (product cache, customer cache):
  Last-write-wins with server timestamp check
  Server version wins on conflict

Shift data:
  If shift was closed offline (pending_sync):
    Server validates on reconnect
    If another shift was opened in between for same cashbox:
      Flag for manager review
      Admin resolves manually

Stock data:
  Recalculate from server movement ledger after sync
  Local cache refreshed with server values
```

### 24.5 Offline Capability Matrix

| Action | Offline | Notes |
|--------|---------|-------|
| Cash POS sale | ✅ | Full flow, queued in IndexedDB |
| Card/Visa recording | ✅ Conditional | If setting allows offline card recording |
| Wallet recording | ✅ Conditional | If setting allows |
| Credit sale | ⚠️ Risky | Needs cached credit limit + setting allows |
| Expense entry (cash) | ✅ | Queued |
| Recipe ingredient deduction | ✅ | From product cache |
| Continue existing shift | ✅ | Local shift state |
| Open new shift (first time) | ❌ | Requires server (new shift record) |
| Open new shift (resuming) | ✅ | If shift exists in cache |
| Close shift | ⚠️ | status = pending_sync, validated on reconnect |
| Customer selection | ✅ | From cached customer list |
| Purchase invoice | ❌ | Online only in MVP |
| Inventory adjustment | ❌ | Online only (server validation required) |
| Reports | ❌ | Online only |
| Settings changes | ❌ | Online only |
| Permission changes | ❌ | Online only |
| Data export | ❌ | Online only |

---

## 👥 25. User Activity & Performance Flows

### 25.1 Login / Session Tracking

```
On successful login:
  UserSession record created:
    {user_id, tenant_id, device_id, ip_address,
     user_agent, login_timestamp, status: active}
  AuditLog: user_login

On logout or session expiry:
  UserSession.status → inactive
  UserSession.logout_timestamp = now
  AuditLog: user_logout
```

### 25.2 User Performance Aggregation

```
User performance metrics are derived from movement ledgers:

Total Sales:
  FROM FinancialAccountMovement
  WHERE source_document_type = 'sales_invoice'
  AND created by user_id = X (via shift_id or direct user_id)

Total Returns:
  FROM FinancialAccountMovement
  WHERE source_document_type = 'sales_return'

Total Discounts:
  FROM SaleItem WHERE discount > 0 AND invoice.user_id = X
  
Total Cancellations:
  FROM AuditLog WHERE action = 'invoice_cancelled' AND actor_user_id = X

Avg Transaction Value:
  Total Sales / Invoice Count

Cash Shortage/Surplus:
  FROM ShiftMovementSummary WHERE user_id = X
  SUM(closing_variance)
```

### 25.3 User Shift History

```
Users → [User Profile] → Shift History tab
  ↓
Query ShiftMovementSummary WHERE user_id = X ORDER BY opened_at DESC
  ↓
Display per shift:
  Date, opened, closed, cashbox, terminal,
  total invoices, total sales, expense total,
  opening variance, closing variance,
  card variance
```

---

## ⚙️ 26. Settings Flows

### 26.1 Settings Change Flow

```
Settings Center → [Category] → edit value
  ↓
Require: online connection (settings cannot change offline)
  ↓
Permission: settings.edit (varies by category)
  ↓
Submit change
  ↓
BEGIN TRANSACTION
  Setting value updated
  AuditLog: setting_changed {
    setting_key, old_value, new_value, user_id, timestamp
  }
COMMIT
  ↓
Notify connected clients (WebSocket push):
  "Settings updated — please refresh"
  
Note: posting_snapshot on existing documents is NOT affected
      New documents use new setting values
```

### 26.2 Invoice Designer Change Flow

```
Settings → Invoice & Receipt Designer → edit layout
  ↓
Changes saved as InvoiceDesignSettings:
  template_version ↑ (increment on each save)
  toggle values stored (show_logo, show_qr, etc.)

  Note: existing documents were posted with old template_version
        Reprint uses posting_snapshot.invoice_template_version
        (same template as at time of posting)
        
  New invoices use new template immediately
  AuditLog: invoice_designer_updated
```

### 26.3 Document Numbering Change Flow

```
Settings → Document Numbering → edit series
  ↓
Permission: numbering.manual_override (to edit next_number)
  ↓
Changes:
  Prefix can change (affects new documents only)
  next_number can increase only (cannot decrease)
  Reset policy can change (affects next reset date)
  
AuditLog: numbering_series_updated (old/new values)
```

### 26.4 Negative Stock Settings Change Flow

```
Settings → Inventory Settings → Negative Stock Control
  ↓
User toggles one or more settings:
  allow_negative_stock_sale
  require_manager_approval_for_negative_stock
  negative_stock_scope
  show_negative_stock_warning_to_cashier
  create_negative_stock_alert
  negative_stock_costing_method
  auto_settle_negative_stock_on_purchase
  create_cogs_adjustment_after_negative_stock_settlement
  block_negative_stock_for_batch_expiry_serial_items
  show_negative_stock_in_manager_dashboard
  ↓
Permission required: settings.inventory.edit
  ↓
Validation:
  If allow_negative_stock_sale = false:
    dependent settings hidden/disabled in UI
  If negative_stock_costing_method = zero_cost_require_later_adjustment:
    Show warning: "COGS may be understated until purchase settlement"
  If create_cogs_adjustment_after_negative_stock_settlement = true:
    Require default COGS account and adjustment routing to exist
  If auto_settle_negative_stock_on_purchase = true:
    Require NegativeStockSettlement feature flag enabled
  ↓
Save settings
  ↓
BEGIN TRANSACTION
  Settings updated
  AuditLog: negative_stock_settings_updated
COMMIT
  ↓
Notify all active POS clients:
  "Inventory settings changed. Refresh required before next sale."

Note:
  Existing posted invoices are not changed.
  New sales use the new settings.
  Historical negative stock movements keep their posting_snapshot.
```

### 26.5 Product-Level Negative Stock Override Flow

```
Products → [Product] → Inventory Rules
  ↓
Field: Negative Stock Override
  Options:
    Follow global setting
    Always allow negative stock for this item
    Always block negative stock for this item
  ↓
Use cases:
    Allow: common café ingredients where purchase entry may lag
    Block: expensive, serialized, controlled, or high-risk items
  ↓
Save
  ↓
AuditLog: product_negative_stock_rule_updated
```

---

## 📋 27. Business Rules Summary

### 27.1 Stock Rules

- Stock deduction is atomic (SELECT FOR UPDATE per product)
- Negative stock: blocked by default; configurable to allow or require approval
- Recipe ingredients: same rules per ingredient separately
- Damage/wastage is a financial loss (Inventory Loss account), not just a qty deduction
- avg_cost recalculates on PURCHASE_IN and OPENING_BALANCE, never on SALE_OUT
- avg_cost recalculates correctly on purchase returns (using original cost)

### 27.2 Payment Routing Rules

- Cash → Cashbox (ONLY cash goes to cashbox)
- Card → Card Settlement account (NEVER cashbox)
- Wallet → Wallet account (NEVER cashbox)
- Credit → Customer AR balance (no financial account movement)
- Loyalty Discount → Loyalty Discount account (not cashbox, not revenue)
- Mixed → Each PaymentLine routes independently
- Card refund → Card Settlement account ↓ + CardRefundReference record (manual)

### 27.3 Discount Rules

- Item discount applied per line, before invoice discount
- Invoice discount applied on subtotal, after all line discounts
- Discount before/after tax: controlled by setting
- Max discount per role: enforced, triggers Manager Approval if exceeded
- Coupon codes: server-validated (MVP Extended)
- Tier price is BASE price — discounts applied on top of tier price

### 27.4 Shift Rules

- Shift is an operational workflow — NOT a sidebar module
- Shift accessed via header profile dropdown only
- Opening: expected cash (from last close) vs actual (cashier counts)
- Closing: expected cash formula + card reconciliation + wallet reconciliation
- Shortage = expected − actual (cashier is short)
- Surplus = actual − expected (cashier has extra)
- Variance above threshold → Manager Approval
- Shift stays open on logout/session expiry/device lock
- Damage/wastage → wastage_total (not expense_total) in ShiftMovementSummary

### 27.5 COGS Rules

- Weighted average cost (MVP); FIFO (Phase 2)
- avg_cost stored immutably on SaleItem at posting time
- Recipe COGS = Σ (ingredient avg_cost × qty × wastage × conversion)
- Sales return COGS reversal uses original cost_snapshot (not current avg_cost)
- Purchase return cost basis uses original PI cost_snapshot (if linked)
- Service items: no COGS
- Fixed assets: no COGS, no expense at purchase time

### 27.6 Tax Rules

- Tax collected = Tax Payable (liability), NEVER revenue
- P&L shows Net Revenue (excluding tax)
- Tax on returns: use original snapshot rates
- Discount before tax: reduces taxable base (default behavior)
- Service charge tax: charge added to taxable base if charge_is_taxable
- Multiple rates: aggregated at invoice level, rounded at invoice level (not per line)

### 27.7 Document Status Rules (5 Fields)

- posting_status, payment_status, return_status, approval_status, sync_status
- Posted documents = read-only (cancel to correct)
- Cancelled documents = archived, number retained, NEVER deleted
- Document numbers = NEVER reused (gaps acceptable, reuse never)
- Draft numbers = temporary; permanent number assigned at posting

### 27.8 Cancellation Rules

- Draft → can delete or void
- Posted → cancel only (never delete)
- Paid → cancel triggers payment reversal
- Returned → cannot cancel (use return to correct)
- Cancellation = full reversal of all effects atomically

### 27.9 Audit Log Rules

- INSERT only — never UPDATE or DELETE
- Triggered by: state-changing actions only
- NOT triggered by: reads, views, searches, list loads
- Sensitive reads → AccessLog (not AuditLog)
- System events → OperationsLog (not AuditLog)
- Retained: minimum 7 years

### 27.10 Idempotency Rules

- Every state-changing POST carries `idempotency_key` (UUID)
- Online and offline — prevents double-submit in both cases
- Duplicate found → return existing (200 OK), never 409
- Stored permanently on every document

### 27.11 Printer Failure Rules

- Invoice posts to DB first (commits)
- Print attempted AFTER commit
- Print failure → retry dialog (no cancel invoice option)
- Invoice remains Posted regardless of print outcome
- OperationsLog entry (not AuditLog — it is a system event)

### 27.12 Settings Snapshot Rules

- Captured on every document POST
- Stored as JSON on document (immutable after posting)
- Historical display always uses snapshot
- Reprint uses snapshot's invoice_template_version
- Current settings changes never alter historical snapshots

### 27.13 Permission / Approval Rules

- Permission check: API-level (not just UI)
- No permission → element hidden in UI (not just disabled)
- Approval required → Manager Approval Modal (blocking)
- Approval stored on document (approval_user, time, reason)
- Approval written to AuditLog

### 27.14 Opening Balance Rules

- Set once per entity
- Override requires Manager Approval + reason
- Immutable after first period close [MVP Extended]
- Creates movement record (OPENING_BALANCE type)
- Included in all reports from day one

### 27.15 Period Lock Rules — [MVP Extended]

- After lock: cancel/edit within locked period → Manager Approval required
- After accounting period lock: posted documents → reversal only (Phase 2)
- Prevents report changes after owner has "closed" their day

### 27.16 Allocation Rules

- Customer Receipt / Supplier Payment: FIFO (oldest unpaid first) by default
- Manual allocation: allowed (user selects specific invoices)
- Overpayment: unallocated credit remains on customer/supplier balance
- ReceiptAllocation / PaymentAllocation records per invoice-payment link

### 27.17 Subscription Offline Rules

- POS caches subscription status with configurable TTL (default 24h)
- If offline + valid cache: allow sales within grace window
- If offline + expired cache: block new sales
- On reconnect: immediately re-validate against server

### 27.18 Recipe Ingredient Warehouse Rules

- Configurable per branch via `recipe_ingredient_warehouse_source`
- Options: branch_default / item_specific / pos_selected
- If ingredient stock insufficient → same negative stock rules apply
- One blocked ingredient blocks entire invoice (if negative stock blocked)

### 27.19 Fixed Asset Rules

- Fixed Asset purchase → Fixed Asset account (balance sheet), never expense
- Depreciation → Depreciation Expense account (P&L, not at purchase)
- Write-off → Loss account + Manager Approval (always required)
- Asset on wrong account (e.g., expensed by mistake) → requires correction + AuditLog

### 27.20 Rounding Rules

- All money stored as Decimal (not float)
- Tax rounded at invoice level (not per line)
- Cash rounding: applies to cash change only (card/wallet exact)
- Rounding amount stored in posting_snapshot and shown as separate line
- Rounding gain/loss routes to default_rounding_adjustment_account
- Rounding must not silently change revenue

### 27.21 Movement Ledger Rules

- Every posted document creates movement records
- Reports MUST query from ledgers (not document state)
- All movements atomic with parent document
- AR and AP ledgers are the source of truth for customer/supplier balances
- AR/AP account in Account Mapping is a summary/control account — no double-counting

### 27.22 Account Mapping Rules

- All financial routing through Account Mapping Layer
- Default accounts set on tenant creation
- Tenant can configure account names but NOT change routing logic
- Routing is enforced by Posting Engine (not overridable by user)

### 27.23 Item Type → Posting Behavior Rules

- Stock Item → SALE_OUT + PURCHASE_IN + avg_cost tracking
- Recipe Product → RECIPE_CONSUME (no own stock movement)
- Service/Non-Stock → no stock movement, revenue only
- Fixed Asset (purchase) → FixedAsset record, no stock
- Ingredient → PURCHASE_IN + RECIPE_CONSUME when consumed
- line_type on purchase invoice overrides product's item_type for that transaction

### 27.24 Attachment Rules

- Attachments are stored in tenant-scoped storage
- Upload/delete requires permission and writes AuditLog
- Cancelled documents remain read-only, but attachments can be added with permission
- Attachment history remains visible

### 27.25 Loyalty Rules

- Loyalty redemption = discount type (NOT a payment method)
- Points NOT earned on loyalty discount portion
- Points guaranteed via LoyaltyOutbox pattern
- Points deducted on redemption INSIDE transaction (immediate, not outbox)
- Points earned AFTER commit via Celery (outbox pattern)
- Damage/wastage: wastage_total in shift ≠ expense_total


### 27.26 Negative Stock Rules

- Negative stock sale is controlled by tenant settings, not hardcoded behavior
- Default behavior should be safe: block negative stock unless explicitly enabled
- Negative stock applies to normal Stock Items and Recipe Ingredients
- If one recipe ingredient is blocked, the whole invoice is blocked
- If allowed, StockMovement still records SALE_OUT or RECIPE_CONSUME normally
- The stock balance may become negative; this is intentional and visible
- NegativeStockAlert should be created when configured
- Manager approval can be required before posting a sale that creates negative stock
- Negative stock costing may use last known average cost, default purchase price, or zero cost requiring later adjustment
- If estimated cost is used, sale line / consume movement must store cost_status = estimated
- Later Purchase Invoice increases stock normally and can settle oldest negative balances first
- Formal NegativeStockSettlement links later purchases to old negative movements
- If actual purchase cost differs from estimated sale cost, COGS Adjustment may be posted
- Old posted invoices are never edited to fix negative stock costing
- If the old period is locked, cost adjustment is posted in the current open period
- Batch/expiry/serial-controlled items should not allow negative stock in Phase 2 unless explicitly supported

---

---

## 🍽️ 28. Table Service & Open Orders Flows

### 28.1 POS Touch Load — Table vs Product View

```
POS Touch Mode loads
  ↓
Check: table_service_enabled setting
  ├─ false → load normal Product Grid (existing flow)
  └─ true  → load Table Grid screen

Table Grid screen:
  Show all DiningTables for this branch
  Grouped by DiningSection
  Each table card shows:
    Table number, section, status, open order total, elapsed time

User taps a table:
  ├─ status = available → Open Table flow (§28.2)
  └─ status = occupied / needs_bill → Open Order Detail (§28.4)
```

### 28.2 Open Table Flow

```
Cashier/Waiter taps Available table
  ↓
Check: shift is active (if require_shift_before_selling = true)
  ↓
BEGIN TRANSACTION
  OpenOrder created:
    {tenant_id, branch_id, table_id,
     opened_by_user_id, cashier_user_id,
     shift_id: current_shift.id,
     status: open,
     opened_at: now,
     idempotency_key: UUID}
  DiningTable.status → occupied
  AuditLog: open_order_created
COMMIT
  ↓
Navigate to OpenOrder Detail screen (§28.4)
```

### 28.3 Add Items to Open Order Flow

```
On OpenOrder Detail screen:
  User taps product tile or scans barcode
    ↓
  Product has modifiers?
    ├─ Yes → Modifier Popup (same as normal POS Touch flow)
    └─ No  → add directly

  OpenOrderLine created (status: draft):
    {open_order_id, product_id, product_unit_id,
     modifier_selections (JSON), qty,
     unit_price: resolved per tier,
     status: draft, notes: optional}

  Line appears in order with draft indicator
  Total updates in real time
  No stock movement yet
  No financial posting yet

Draft line actions available:
  Edit qty → update freely
  Delete → remove freely (no approval, no AuditLog needed)
  Add notes → free text to kitchen
```

### 28.4 OpenOrder Detail Screen Content

```
Screen shows:
  Table number + section + status
  Elapsed time since order opened
  Opened by / current cashier
  
  Lines grouped by status:
    Draft items → with edit/delete controls
    Sent items  → locked, status badge
    Cancelled   → shown crossed out (for history)
  
  Kitchen Ticket history:
    #1 · 14:33 · Bar     → 2x Iced Mocha
    #2 · 14:45 · Bar     → 1x Cappuccino
    #3 · 14:50 · Kitchen → 2x Chocolate Cake
  
  Running total (sent + draft lines)
  
  Actions:
    [+ Add Items]
    [Send to Kitchen] → only if draft lines exist
    [Needs Bill]
    [Pay →]
```

### 28.5 Send to Kitchen Flow

```
Cashier/Waiter presses [Send to Kitchen]
  ↓
Check: at least one draft line exists
  ↓
Group draft lines by printer_target (bar / kitchen / none):
  item_group.printer_assignment determines target
  ↓
For each printer group:

  BEGIN TRANSACTION
    1. If stock_commit_timing = on_kitchen_send:
         For each line:
           Stock Item → StockMovement: SALE_OUT (provisional)
             negative_stock rules apply (§13.9)
           Recipe Product → StockMovement: RECIPE_CONSUME per ingredient
             negative_stock rules apply per ingredient
         ← same atomicity rules as normal sale
         If any item blocked (negative stock disabled) → rollback all
    
    2. OpenOrderLine.status → sent (for all draft lines in this batch)
    3. OpenOrderLine.sent_at = now
    
    4. KitchenTicket created:
         {open_order_id, table_id, table_number,
          ticket_number: auto-incremented per order,
          printer_target: bar / kitchen,
          lines: JSON snapshot of sent lines + modifiers + notes,
          printed_at: now,
          status: printed}
    
    5. OpenOrder.status → sent_to_kitchen
    
    6. AuditLog: kitchen_ticket_sent
    
  COMMIT
  ↓
Print ticket to target printer (ESC/POS):
  Ticket format:
    ┌──────────────────────────────┐
    │ TABLE 01 · Main Hall        │
    │ Ticket #2 · 14:45           │
    │ Opened by: Ahmed / Waiter   │
    ├──────────────────────────────┤
    │ 1× Cappuccino               │
    │   Oat milk                  │
    │   Extra shot                │
    │                             │
    │ NOTE: no sugar              │
    └──────────────────────────────┘
  
  If print fails:
    → Printer Failure dialog (retry / skip)
    → KitchenTicket remains in DB regardless
    → OperationsLog: kitchen_printer_failure
    → OpenOrder NOT rolled back
```

### 28.6 Subsequent Send to Kitchen Flow

```
Customer adds more items after first ticket was sent
  ↓
New OpenOrderLines added (status: draft)
  ↓
[Send to Kitchen] pressed again
  ↓
System includes ONLY lines with status = draft
Already-sent lines (status = sent) are NOT included again
  ↓
New KitchenTicket created (ticket_number increments)
Process identical to §28.5
```

### 28.7 Cancel Draft Item Flow (No Approval Needed)

```
User taps delete on a Draft line
  ↓
If stock_commit_timing = on_kitchen_send:
  No stock movement exists yet → nothing to reverse
  
If stock_commit_timing = on_payment:
  No stock movement exists yet → nothing to reverse

OpenOrderLine deleted (or status → voided)
Total recalculates
No AuditLog required for draft item removal
```

### 28.8 Cancel Sent Item Flow (Manager Approval Required)

```
Manager taps cancel on a Sent line
  ↓
Check: permission order.cancel_sent_item
  ↓
Check: item status
  ├─ sent (not prepared) → proceed with full reversal
  └─ prepared / served   → go to §28.9 (Remove from Bill)

Manager Approval Modal:
  Title: "Cancel Sent Item — Manager Approval"
  Item: [name + qty]
  Preparation status: Not Prepared Yet
  Reason: [required text field]
  Manager PIN / password: [required]
  [Approve] [Cancel]
  ↓
If Approved:
  BEGIN TRANSACTION
    1. If stock_commit_timing = on_kitchen_send:
         Reverse the stock movement created at kitchen send:
           Stock Item → StockMovement: ADJUSTMENT_IN (reversal)
           Recipe Product → reverse RECIPE_CONSUME per ingredient
    
    2. OpenOrderLine.status → cancelled
    
    3. Append cancel notice to KitchenTicket:
         KitchenTicket.status → cancelled_item_appended
         Print cancellation notice to same printer:
           ┌──────────────────────────────┐
           │ *** CANCEL ***               │
           │ TABLE 01 · Ticket #2         │
           │ CANCEL: 1× Cappuccino        │
           │ Reason: Customer changed mind│
           └──────────────────────────────┘
    
    4. AuditLog: sent_item_cancelled {
         line_id, reason, approved_by, approved_at,
         stock_reversed: true/false
       }
  COMMIT
  ↓
  Item does NOT appear on final invoice
  Total recalculates (cancelled line excluded)

If Rejected:
  AuditLog: cancellation_rejected
  Item remains on order
```

### 28.9 Remove Prepared/Served Item from Bill (Manager)

```
Manager taps remove on a Prepared or Served line
  ↓
Check: permission order.remove_prepared_from_bill
  ↓
Manager Approval Modal:
  Title: "Remove from Bill — Manager Approval"
  Item: [name + qty]
  Preparation status: Prepared / Served
  Warning: "Item was already prepared. Choose action:"
  
  Action choices:
    ● Mark as Complimentary (item was given to customer, not charged)
    ○ Mark as Wastage (item was made but not served / unusable)
  
  Reason: [required]
  Manager PIN / password: [required]
  [Approve] [Cancel]
  ↓
If Approved — Complimentary:
  BEGIN TRANSACTION
    Complimentary record created:
      {tenant_id, open_order_id, open_order_line_id,
       product_id, qty, unit_price,
       reason, approved_by, created_at}
    OpenOrderLine.status → cancelled (excluded from invoice)
    No stock movement reversal (item was consumed by customer)
    AuditLog: complimentary_created
  COMMIT

If Approved — Wastage:
  BEGIN TRANSACTION
    DamageWastage record created (same as normal wastage flow):
      {product_id, qty, avg_cost_at_posting, inventory_loss_value,
       reason, shift_id, created_by: manager}
    If stock_commit_timing = on_kitchen_send:
      Stock was already committed → wastage closes the loop
    If stock_commit_timing = on_payment:
      StockMovement: DAMAGE_OUT created now
    FinancialAccountMovement: Inventory Loss account ↑
    ShiftMovementSummary: wastage_total ↑
    OpenOrderLine.status → cancelled (excluded from invoice)
    AuditLog: wastage_from_table_order_created
  COMMIT
```

### 28.10 Needs Bill Flow

```
Customer requests bill
  ↓
Cashier/Waiter presses [Needs Bill]
  ↓
OpenOrder.status → needs_bill
DiningTable.status → needs_bill
  ↓
Optional: print bill preview (not a final invoice — just a preview receipt)
  ↓
Table card on Table Grid now shows needs_bill badge
  ↓
No financial posting yet
```

### 28.11 Pay (Convert OpenOrder to Sales Invoice) Flow

```
Cashier presses [Pay] on OpenOrder Detail
  ↓
System calculates billed lines:
  Include: lines with status = sent / preparing / served
  Exclude: lines with status = cancelled / voided

  Show payment panel:
    Line items + modifiers
    Subtotal (excl. tax)
    Tax
    Total
  ↓
Payment panel identical to normal POS payment (§9.7):
  Cash / Card / Wallet / Credit / Mixed
  Loyalty discount (if customer selected)
  ↓
Cashier confirms payment
  ↓
BEGIN TRANSACTION (Posting Engine §3.2)
  
  STEP A: Stock movements
    If stock_commit_timing = on_kitchen_send:
      Stock already committed at kitchen send
      Do NOT create new StockMovements for sent lines
      Only create movements for any draft lines remaining
      (edge case: draft lines exist at payment time if cashier
       added items and went straight to pay without sending)
    
    If stock_commit_timing = on_payment:
      Create StockMovements / RECIPE_CONSUME for all billed lines
      (same as normal POS sale flow)
  
  STEP B: Financial posting
    Same as normal Sales Invoice posting (§3.2 STEP 12 onwards):
      Revenue → Sales Revenue account
      Tax → Tax Payable account
      Per PaymentLine → correct account (cash/card/wallet/credit)
      CustomerARMovement if credit
      ShiftMovementSummary updated
      LoyaltyOutbox if loyalty active
      posting_snapshot stored
  
  STEP C: Document linking
    SalesInvoice.open_order_id = OpenOrder.id
    SalesInvoice.table_id = DiningTable.id
    OpenOrder.status → paid
    OpenOrder.closed_at = now
    DiningTable.status → available
    Assign document number: SI-YYYY-NNNNN
    AuditLog: open_order_converted_to_invoice

COMMIT
  ↓
Print receipt
Open cash drawer (if cash payment)
Table Grid refreshes: table now Available
```

### 28.12 Cancel Entire Open Order Flow

```
Manager cancels the entire OpenOrder (before payment)
  ↓
Check: permission order.cancel_sent_item (required even for full cancel)
  ↓
Check order state:
  ├─ All lines are draft/voided → Void order (no approval)
  └─ Any sent/prepared/served lines exist → Manager Approval required

Manager Approval Modal:
  Title: "Cancel Entire Order — Manager Approval"
  Table: [table number]
  Items sent to kitchen: [count]
  Reason: [required]
  Manager PIN: [required]
  ↓
If Approved:
  BEGIN TRANSACTION
    For each sent (not prepared) line:
      If stock_commit_timing = on_kitchen_send:
        Reverse stock movements
    
    For each prepared/served line:
      Manager chooses: Complimentary or Wastage (per line)
      Create records accordingly (§28.9 rules)
    
    OpenOrder.status → cancelled
    DiningTable.status → available
    AuditLog: open_order_cancelled {reason, approved_by, lines_affected}
  COMMIT
```

### 28.13 Orphaned Open Order Flow

```
Scenario: cashier logged out / shift ended but table still has open order
  ↓
Table remains occupied (OpenOrder.status = open or sent_to_kitchen)
Manager dashboard shows: open orders with no active cashier
  ↓
Manager options:
  [Assign to New Cashier] → select available cashier
    → OpenOrder.cashier_user_id updated
    → AuditLog: order_reassigned
  
  [Cancel Order] → follows §28.12 flow
  
  [Pay Now as Manager] → follows §28.11 flow (manager processes payment)
```

### 28.14 Business Rules Summary for Table Service

- Open Order is NOT a financial document — no revenue, no tax, no AR until payment
- One active OpenOrder per table at a time
- Any Cashier or Waiter in the branch can view and interact with any open order
- Draft lines: free to edit/delete with no approval
- Sent lines: locked, require manager approval to cancel
- Prepared/served lines: billed by default; manager must choose Complimentary or Wastage to remove
- KitchenTicket is immutable — cancel notices are appended, not edits to the original
- Stock commit at kitchen send (default) vs at payment — controlled by setting
- No duplicate stock movements under any setting combination
- Payment converts OpenOrder to Sales Invoice using the same Posting Engine as normal POS
- Split bill is Phase 2
- KDS is Phase 2