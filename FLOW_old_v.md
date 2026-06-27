# 🔄 Cloud POS System — Business Logic & Workflows (FLOW.md)

**Version:** 2.0  
**Last Updated:** May 2026  
**Scope:** Core workflows, state management, business rules

---

## 📌 Overview

This document defines **how the system works**—not what it looks like (DESIGN.md), but how data flows, how users interact with processes, and what rules govern behavior.

**Key Principle:** Every business process is a workflow. Every workflow is a state machine.

---

## 🔐 Authentication Flow

### User Login

```
User → [Email/Password] → API Validation
                          ↓
                    Valid? 
                    ├─ YES → Check 2FA?
                    │        ├─ YES → Send OTP
                    │        │        ├─ Valid OTP → Generate JWT
                    │        │        └─ Invalid OTP → Error
                    │        └─ NO → Generate JWT
                    │        ↓
                    │     JWT Token + Refresh Token
                    │     + User Profile Data
                    │     + Permission List
                    │     ↓
                    │   Login Success → Redirect to Dashboard
                    │
                    └─ NO → Show Error Message
                           (Email not found / Password incorrect)
```

### JWT Token Management

```
Access Token (15 min expiry)
├─ Payload: user_id, tenant_id, permissions, timestamp
└─ Sent in Authorization header

Refresh Token (30 day expiry)
├─ Stored in httpOnly cookie
└─ Used to get new access token when expired
```

### Session Management

```
Login
  ↓
Create Session
  ├─ device_id (unique device identifier)
  ├─ user_id
  ├─ tenant_id
  ├─ login_timestamp
  ├─ ip_address
  ├─ browser_user_agent
  └─ status = "active"
  ↓
User actions → Session active for 24 hours
User inactive 24 hours → Auto-logout
User clicks logout → Destroy session
```

---

## 🛒 POS Sales Flow

### Complete Sale Workflow

```
╔════════════════════════════════════════════════════════════════════════════╗
║ POS TRANSACTION FLOW                                                       ║
╚════════════════════════════════════════════════════════════════════════════╝

[START NEW TRANSACTION]
        ↓
    IDLE STATE
    (Barcode input focused)
        ↓
    [SCAN BARCODE]
        ├─ Valid barcode?
        │  ├─ YES → Product exists?
        │  │        ├─ YES → Add to cart
        │  │        │        └─ qty = 1
        │  │        └─ NO → Show "Product not found" error
        │  └─ NO → Show "Invalid barcode" error
        ↓
    CART STATE
    (Items in cart)
        │
        ├─ [EDIT QUANTITY]
        │  └─ qty = manual_value (validated: 0-999)
        │
        ├─ [REMOVE ITEM]
        │  └─ Remove from cart (can undo)
        │
        ├─ [SCAN MORE ITEMS]
        │  └─ Loop back to IDLE → CART
        │
        └─ [PROCEED TO PAYMENT]
                ↓
        DISCOUNT STATE
        ├─ Apply discount?
        │  ├─ % discount (e.g., 10%)
        │  ├─ Fixed discount (e.g., $5)
        │  └─ Code-based discount (coupon)
        └─ No discount → Skip
                ↓
        PAYMENT STATE
        ├─ Select payment method:
        │  ├─ Cash
        │  ├─ Card
        │  ├─ Digital Wallet
        │  └─ Mixed (cash + card)
        │
        ├─ If CASH:
        │  ├─ Show amount due
        │  ├─ Show amount paid (manual entry or auto-calc)
        │  ├─ Calculate change
        │  └─ [CONFIRM]
        │
        ├─ If CARD:
        │  ├─ Show card reader prompt
        │  ├─ Wait for card swipe/tap
        │  ├─ [PROCESSING...]
        │  ├─ Success? → Move to RECEIPT
        │  └─ Decline? → Show error, retry or use different payment
        │
        └─ If WALLET:
             ├─ Generate QR code
             ├─ Show "Scan with wallet app"
             ├─ [WAITING...]
             ├─ Payment confirmed? → Move to RECEIPT
             └─ Timeout (60s)? → Ask to retry
                        ↓
        RECEIPT STATE
        ├─ Calculate:
        │  ├─ Subtotal = sum of items
        │  ├─ Tax = subtotal × tax_rate
        │  ├─ Total = subtotal + tax - discount
        │  └─ Change = paid - total
        │
        ├─ Print receipt
        │  ├─ Format ESC/POS commands
        │  ├─ Send to printer
        │  ├─ Success? → Continue
        │  └─ Fail? → Show "Printer offline" warning
        │
        └─ Open cash drawer
             ├─ Signal drawer
             ├─ Wait 3 seconds
             └─ Success → COMPLETE
                        ↓
        INVENTORY UPDATE
        ├─ For each item in cart:
        │  ├─ product.stock_quantity -= qty
        │  ├─ If stock < reorder_point → Create alert
        │  └─ If stock < 0 → Flag as oversold (investigate)
        │
        ├─ Save inventory movement:
        │  ├─ movement_type = "sale"
        │  ├─ product_id
        │  ├─ qty
        │  ├─ timestamp
        │  └─ branch_id
        │
        └─ Sync to server (if online)
                ↓
        TRANSACTION COMPLETE
        ├─ Save sale record:
        │  ├─ sale_id (unique UUID)
        │  ├─ items[]
        │  ├─ total
        │  ├─ discount
        │  ├─ payment_method
        │  ├─ cashier_id
        │  ├─ branch_id
        │  ├─ timestamp
        │  └─ receipt_printed = true
        │
        ├─ Log transaction
        └─ Reset to IDLE STATE
             └─ Clear cart
                Ready for next customer
```

### Edge Cases & Error Handling

#### Case: Barcode Not Found

```
[Scan unknown barcode]
  ↓
Show error dialog:
"Product not found. Options:"
├─ [Search by name] → Open product search
├─ [Manual price] → Override with manual entry
├─ [Cancel] → Clear barcode, try again
```

#### Case: Insufficient Stock

```
Product in stock list: 2 units
Cashier tries to sell: 5 units
  ↓
ALLOW SALE (oversell)
But:
├─ Show warning: "Only 2 in stock. Selling 5."
├─ Flag in inventory: oversold_qty = 3
└─ Alert manager: "Stock alert for [Product Name]"
```

#### Case: Discount Code Invalid

```
Cashier enters code: "PROMO2026"
  ↓
Validate code:
├─ Code exists?
├─ Code not expired?
├─ Quantity requirements met?
├─ Applicable to these items?
  ↓
Valid → Apply discount
Invalid → Show reason:
          "Code expired" / "Not applicable" / "Not found"
```

#### Case: Payment Declined

```
Card payment sent to processor
  ↓
Processor response:
├─ Success → Print receipt
├─ Declined → Show reason + retry option
├─ Timeout → Show "Payment service down" + retry/cash option
└─ Error → Log error, manual resolution needed
```

#### Case: Receipt Printer Offline

```
Transaction complete, printing receipt
  ↓
Printer returns error
  ↓
Show dialog:
├─ [Retry] → Try printer again
├─ [Email Receipt] → Send to customer email
├─ [SMS Receipt] → Send to customer phone
├─ [Skip] → Continue without physical receipt
└─ [Manual Print] → Print later from reports
```

---

## 📦 Product Management Flow

### Add New Product

```
Admin → Products → [+ Add Product]
  ↓
Product Type Selection:
├─ Standard (fixed price)
├─ Weighted (scale-based pricing)
└─ Variant (size/color options)
  ↓
Fill product form:
├─ Name (required)
├─ Category (required)
├─ Barcode (required if POS, unique)
├─ SKU (optional)
├─ Price (required)
├─ Cost (required for profit calc)
├─ Tax rate (%)
├─ Description (optional)
└─ Image (optional)
  ↓
Validate:
├─ Barcode unique in system?
├─ Price > 0?
├─ Category exists?
├─ Image format valid (if provided)?
  ↓
Valid → Save product
  ├─ Add to database
  ├─ Sync to cache (Redis)
  ├─ Replicate to POS devices (if online)
  └─ Success notification
  
Invalid → Show validation errors
        └─ User corrects, resubmits
```

### Product Variant Example (T-Shirt)

```
Product: "T-Shirt Blue"

Variants:
├─ Size: S
│  ├─ Barcode: 123456789001
│  ├─ Price: $15
│  └─ Stock: 20
│
├─ Size: M
│  ├─ Barcode: 123456789002
│  ├─ Price: $15
│  └─ Stock: 35
│
├─ Size: L
│  ├─ Barcode: 123456789003
│  ├─ Price: $15
│  └─ Stock: 25
│
└─ Size: XL
   ├─ Barcode: 123456789004
   ├─ Price: $16 (premium size)
   └─ Stock: 15

At POS:
├─ Scan 123456789002 → "T-Shirt Blue (M)" appears
├─ Scan 123456789004 → "T-Shirt Blue (XL)" appears
└─ Each tracked separately by variant barcode
```

### Scale Product Setup

```
Admin creates "Cheese Cheddar"
├─ Type: Weighted
├─ Price: €12.99 / kg
├─ PLU code: 1234 (on scale)
├─ Scale barcode prefix: 21 (e.g., 2112345*****)
└─ Save

Scale configuration:
├─ Upload CSV with all PLU codes
├─ Scale now knows: 1234 = Cheese Cheddar, €12.99/kg

At checkout:
├─ Customer weighs 750g of cheese on scale
├─ Scale prints barcode: 21123400750 (750 = weight in 0.1kg)
├─ Cashier scans: 21123400750
├─ POS detects prefix 21 (weighted item)
├─ Extracts: PLU=1234, weight=0.75kg
├─ Calculates: price = 0.75 × €12.99 = €9.74
└─ Item added to cart with calculated price
```

---

## 📊 Inventory Movement Flow

### Purchase Order (Stock In)

```
Supplier order created:
├─ Supplier name
├─ PO number
├─ Items[] (product_id, qty, unit_price)
├─ Total amount
├─ Expected delivery date
└─ Status = "pending"

Delivery arrives:
├─ User scans barcodes (or manual entry)
├─ System matches to PO
├─ Verify quantities
├─ [CONFIRM RECEIPT]
  ↓
For each item:
├─ stock_quantity += received_qty
├─ Create inventory_movement record:
│  ├─ type = "purchase_in"
│  ├─ product_id
│  ├─ qty
│  ├─ po_number
│  ├─ supplier_id
│  └─ timestamp
│
└─ Sync inventory to POS (if online)

PO Status = "received"
```

### Stock Adjustment (Manual)

```
Manager → Inventory → Stock Adjustment

Scenario: Physical count doesn't match system
├─ System shows: 100 units
├─ Physical count: 95 units
├─ Difference: -5 units

Adjustment:
├─ Reason: "Shrinkage investigation", "Customer return damaged", etc.
├─ Actual qty: 95
├─ Create movement:
│  ├─ type = "adjustment"
│  ├─ qty_change = -5
│  ├─ reason
│  └─ reviewed_by = manager_id
│
└─ Stock updated: 100 → 95
   Audit trail created
```

### Transfer Between Branches

```
Branch A has excess stock of "Pepsi" (200 units)
Branch B is low (5 units)

Transfer request:
├─ Source branch: A
├─ Destination branch: B
├─ Product: Pepsi
├─ Qty: 50 units
├─ Reason: "Rebalance stock"
└─ Status = "pending_approval"

Branch A manager approves:
├─ Branch A stock: 200 → 150
├─ Create movement: type = "transfer_out"
├─ Status = "in_transit"

Branch B receives:
├─ Scan items to confirm
├─ [CONFIRM RECEIPT]
├─ Branch B stock: 5 → 55
├─ Create movement: type = "transfer_in"
└─ Status = "completed"

Audit trail:
├─ Transfer ID
├─ From/to branches
├─ Item, qty
├─ Timestamps
└─ Approvers
```

---

## 💳 Payment Processing Flow

### Payment State Machine

```
AMOUNT DUE: Calculate (subtotal + tax - discount)

Payment Methods Available:
├─ CASH
│  ├─ Amount paid (manual entry or auto-suggested)
│  ├─ Calculate change = amount_paid - total
│  ├─ [CONFIRM]
│  └─ Status = "confirmed" → Move to RECEIPT
│
├─ CARD (Credit/Debit)
│  ├─ Show: "Please insert or tap card"
│  ├─ Wait for reader: [PROCESSING...]
│  ├─ Card read → Extract card details
│  ├─ Send to payment processor
│  │  ├─ Processor response:
│  │  │  ├─ Success → transaction_id + receipt
│  │  │  ├─ Declined → Reason (insufficient funds, expired, etc.)
│  │  │  └─ Error → Retry or different payment
│  │  └─ Status = "authorized" or "declined"
│  ├─ If success: [CONFIRM]
│  └─ Move to RECEIPT
│
├─ DIGITAL WALLET (Vodafone Cash, Fawry, etc.)
│  ├─ Generate QR code with amount
│  ├─ Show: "Scan with your wallet app"
│  ├─ Wait for webhook: customer scans and confirms
│  ├─ [TIMEOUT] after 60 seconds
│  ├─ Webhook received: Amount confirmed
│  └─ Status = "confirmed" → Move to RECEIPT
│
└─ MIXED (Cash + Card)
   ├─ Enter cash amount
   ├─ Calculate remaining = total - cash
   ├─ Process card for remaining
   ├─ Both confirmed?
   └─ Status = "confirmed" → Move to RECEIPT
```

### Payment Failure Handling

```
Payment attempt fails:
  ↓
Reason:
├─ Card declined
├─ Processor timeout
├─ Network error
├─ Incorrect amount
└─ Hardware error
  ↓
Show error + options:
├─ [RETRY] → Attempt same payment again
├─ [DIFFERENT METHOD] → Switch to cash/wallet
├─ [CANCEL] → Return to cart
│            (Sale not completed, inventory not updated)
└─ [MANUAL OVERRIDE] (admin only) → Force complete
                                    + Investigation flag
```

---

## 🎟️ Subscription (Gym Membership) Flow

### Member Signup

```
Customer → Purchase Membership
├─ Select plan:
│  ├─ Monthly: $50/month
│  ├─ Quarterly: $130/3 months
│  └─ Yearly: $400/year
│
├─ Personal info:
│  ├─ Name
│  ├─ Email
│  ├─ Phone
│  └─ Photo (for ID card)
│
├─ Payment method (same as POS)
├─ [CREATE MEMBERSHIP]
  ↓
System creates membership record:
├─ member_id (unique)
├─ plan = "monthly"
├─ start_date = today
├─ expiry_date = today + 30 days
├─ status = "active"
├─ auto_renew = true (if customer agreed)
└─ Generate QR code for check-in
  ↓
Member receives:
├─ Email with membership details
├─ QR code for check-in
└─ App login credentials (if available)
```

### Member Check-In

```
Member → Receptionist (or self-service kiosk)
├─ Present QR code or ID card
├─ System scans QR code
├─ OR manual ID lookup
  ↓
Check membership:
├─ Status = "active"?
├─ Expiry date > today?
├─ Frozen?
├─ Suspended?
  ↓
Valid:
├─ Log attendance
│  ├─ member_id
│  ├─ check_in_time = now
│  ├─ branch_id
│  └─ status = "checked_in"
│
└─ Show: "Welcome [Name]! ✓"
   Unlock door or show approval

Invalid:
├─ Expired: "Your membership expired [date]"
│           [Renew now?]
│
├─ Frozen: "Membership frozen until [date]"
│
├─ Suspended: "Contact reception for details"
│
└─ Not found: "Member not found"
             [Search by name?]
```

### Auto-Renewal

```
3 days before expiry:
├─ Send email: "Membership expires in 3 days"
└─ Send SMS reminder (if opted in)

Day of expiry:
├─ auto_renew = true?
│  ├─ YES:
│  │  ├─ Charge payment method on file
│  │  ├─ Success? → Extend expiry_date by plan duration
│  │  └─ Failed? → Email: "Renewal failed. Update payment"
│  │
│  └─ NO: expiry_date passes
│         ├─ status = "inactive"
│         ├─ Member can still check in?
│         │  ├─ If gym allows: log as "trial"
│         │  └─ If strict: block check-in
│         └─ Show renewal prompt
```

### Freeze/Pause Membership

```
Member contacts gym: "I want to pause for 2 months"

Request:
├─ Original expiry: June 15
├─ Pause duration: 2 months
├─ Freeze: May 15 to July 15

System action:
├─ status = "frozen"
├─ frozen_until = July 15
├─ Check-in blocked with message: "Membership frozen"
├─ Original expiry extended: June 15 → July 15 (pause doesn't count)
└─ Charge paused (if monthly recurring)

When freeze ends:
├─ status = "active"
└─ Charge resumes
```

---

## 🖥️ Admin Report Generation Flow

### Daily Sales Report

```
Admin → Reports → Daily Sales

Date selection: [Pick date]
  ↓
Query database:
├─ SELECT all sales WHERE date = selected_date
├─ AND branch_id = current_branch (or all if admin)
├─ JOIN with sale_items for details
├─ JOIN with products for names/categories
  ↓
Calculate:
├─ Total sales = SUM(total)
├─ Item count = SUM(qty)
├─ Transaction count = COUNT(sale_id)
├─ Average transaction = total_sales / transaction_count
├─ By payment method:
│  ├─ Cash: amount, %
│  ├─ Card: amount, %
│  └─ Wallet: amount, %
├─ By category:
│  ├─ Category A: sales, qty, % of total
│  └─ Category B: sales, qty, % of total
├─ By cashier:
│  ├─ Cashier 1: transactions, total, discrepancies
│  └─ Cashier 2: ...
├─ Top 10 products:
│  ├─ Product name, qty sold, revenue, avg. price
│  └─ ...
└─ Tax breakdown: VAT collected, by rate
  ↓
Display + Export:
├─ View on dashboard
├─ Download PDF
├─ Email to manager
└─ Export to Excel
```

### Inventory Alert Report

```
Admin → Inventory → Alerts

Query:
├─ WHERE stock_quantity < reorder_point
├─ AND branch_id = selected_branch
├─ OR expiry_date < 30 days from today (pharmacy)
  ↓
For each product:
├─ Current stock
├─ Reorder point
├─ Units below reorder: stock - reorder_point
├─ Last sale date
├─ Last purchase date
├─ Supplier for product
└─ Suggested action: "Reorder X units"
  ↓
Display options:
├─ [AUTO GENERATE PO] → Create purchase order
├─ [EMAIL SUPPLIER] → Populate email with suggestion
└─ [IGNORE] → Mark as reviewed, hide alert
```

---

## 🔄 Offline Sync Flow

### Offline Mode Triggered

```
User: Cashier scanning items at supermarket
Internet: Suddenly disconnects

POS App:
├─ Detects network loss (no response from API)
├─ Status badge: "OFFLINE MODE"
├─ Show banner: "No internet. Working offline."
├─ Sales continue: All transactions stored locally
│
├─ Cache available:
│  ├─ Product list (synced at last connection)
│  ├─ Prices (cached)
│  ├─ Tax rates (cached)
│  └─ User permissions (cached)
│
└─ Store locally:
   ├─ New invoices → IndexedDB
   ├─ Inventory changes → Local state
   └─ User actions → Queue for sync
```

### Online Restoration

```
Internet returns:
  ↓
POS detects connection
├─ Status: "SYNCING..."
├─ Show sync progress bar
  ↓
Sync operations (in order):
├─ 1. Upload all offline invoices
│  ├─ For each sale in offline queue:
│  │  ├─ POST /api/sales with invoice data
│  │  ├─ Server: Validate invoice
│  │  ├─ If valid: Save, return sale_id
│  │  ├─ If invalid: Log error, manual review needed
│  │  └─ Clear from local queue
│  └─ Status: "Uploaded X invoices"
│
├─ 2. Fetch latest inventory
│  ├─ GET /api/inventory?branch_id=X
│  ├─ Compare with local cache
│  ├─ If conflict (stock changed online):
│  │  ├─ Strategy: "Last write wins" (or merge)
│  │  └─ Resolve conflict
│  └─ Update local cache
│
├─ 3. Sync user permissions
│  ├─ GET /api/user/permissions
│  ├─ Check if user still has access
│  ├─ If revoked: Force logout
│  └─ Update permission cache
│
└─ 4. Verify data consistency
   ├─ Check for data gaps
   ├─ Verify all offline sales uploaded
   ├─ Re-sync if errors detected
   └─ Status: "SYNC COMPLETE"
     └─ Clear offline badge
        Return to normal operation
```

### Conflict Resolution

```
Scenario: Stock count changed both offline and online

Local (offline):        Server (online):
Pepsi stock: 100       Pepsi stock: 95
Sale: -10              Sale: -5
Final: 90              Final: 90

When syncing:
├─ Both happened same item
├─ Resolution: Last timestamp wins
│  ├─ If server timestamp > local: Use server value
│  └─ If local timestamp > server: Local supersedes
│
└─ Log discrepancy for audit
   ├─ Both transactions valid?
   └─ Investigate if mismatch >5 units
```

---

## 🔐 Permission & Role Flow

### Role-Based Access Control (RBAC)

```
User role: "Cashier"

Permissions:
├─ sales:create ✓ (can create sales)
├─ sales:view ✓ (can see own sales)
├─ products:view ✓ (can see products)
├─ products:edit ✗ (cannot modify)
├─ inventory:adjust ✗ (cannot adjust stock)
├─ reports:view ✗ (cannot access reports)
├─ users:manage ✗ (cannot manage users)
└─ settings:edit ✗ (cannot change settings)

At POS:
├─ [Sales button] → Enabled ✓
├─ [Products button] → Enabled ✓
├─ [Inventory button] → Disabled (hidden or greyed)
├─ [Reports button] → Disabled
└─ [Settings button] → Disabled

Role: "Manager"

Permissions:
├─ sales:create ✓
├─ sales:view ✓
├─ products:view ✓
├─ products:edit ✓ (can change prices)
├─ inventory:adjust ✓ (can adjust stock)
├─ reports:view ✓
├─ users:manage ✓ (can manage cashiers in branch)
└─ settings:edit ✗ (limited settings, no subscription)

Role: "Owner"

Permissions: * (all)
```

### Permission Check Flow

```
User action: "Delete product"

System:
├─ Check user role
├─ Get permissions for role
├─ Search for "products:delete"
├─ Permission exists and granted?
│  ├─ YES → Execute action
│  │        ├─ Log action for audit
│  │        └─ Show confirmation
│  │
│  └─ NO → Deny
│          ├─ Show error: "You don't have permission"
│          ├─ Log attempt (security audit)
│          └─ Alert admin if multiple denied attempts
```

---

## 📱 Offline-First Architecture

### What Happens When Offline

```
POS Screen
├─ Product barcode cache: ✓ Available
│  ├─ Barcode → Product lookup (instant)
│  ├─ Product → Price lookup (cached)
│  └─ Product → Stock check (local)
│
├─ Sales creation: ✓ Works
│  ├─ Create invoice
│  ├─ Save to IndexedDB (local database)
│  ├─ Update local inventory
│  └─ Print receipt (local)
│
├─ Inventory update: ✓ Works (local only)
│  ├─ Decrement stock locally
│  ├─ Mark for sync later
│  └─ No real-time sync
│
├─ Reports: ✗ Limited
│  ├─ Can view today's sales (cached)
│  └─ Cannot sync with other branches
│
├─ Payment: ✓ Limited
│  ├─ Cash: Works fully
│  ├─ Card: ✗ Disabled (needs processor)
│  └─ Wallet: ✗ Disabled (needs internet)
│
└─ User management: ✗ Not available
   └─ Cannot add/edit users without network
```

### IndexedDB Schema (Client Storage)

```
Database: "pos_cache"

ObjectStore: "sales"
├─ Key: sale_id (UUID)
├─ Data:
│  ├─ sale_id
│  ├─ items[]
│  ├─ total
│  ├─ discount
│  ├─ payment_method
│  ├─ cashier_id
│  ├─ timestamp
│  ├─ status = "pending" or "synced"
│  └─ receipt_printed

ObjectStore: "products"
├─ Key: product_id
├─ Data: Full product object (for lookup)

ObjectStore: "inventory"
├─ Key: product_id
├─ Data:
│  ├─ product_id
│  ├─ stock_quantity
│  ├─ last_sync_time
│  └─ local_changes[]

ObjectStore: "cache_metadata"
├─ Key: "last_sync"
├─ Value: timestamp of last sync
```

---

## 📊 State Management Architecture

### Global App State

```
AppState = {
  auth: {
    user_id,
    role,
    permissions[],
    token,
    tenant_id,
    branch_id,
    status: "logged_in" | "logged_out"
  },
  
  pos: {
    cart: {
      items: [
        { product_id, qty, price, discount },
        ...
      ],
      subtotal,
      tax,
      total,
      discount
    },
    payment: {
      method: "cash" | "card" | "wallet",
      status: "pending" | "processing" | "confirmed" | "failed"
    },
    transaction: {
      sale_id,
      status: "in_progress" | "complete"
    }
  },
  
  inventory: {
    products: { [product_id]: product_object },
    stock: { [product_id]: qty },
    last_sync: timestamp,
    sync_status: "synced" | "syncing" | "offline"
  },
  
  network: {
    is_online: boolean,
    is_syncing: boolean,
    last_sync_time: timestamp,
    pending_sync_count: number
  },
  
  ui: {
    current_screen: "pos" | "admin" | "reports",
    sidebar_collapsed: boolean,
    theme: "light" | "dark",
    language: "en" | "ar"
  }
}
```

---

## 🔄 State Transitions (Example: Sale)

```
START
  ↓
State: { cart: empty }
Action: SCAN_BARCODE
  ↓
New state: { cart: [{ product_id: 1, qty: 1 }] }
Action: SCAN_BARCODE
  ↓
New state: { cart: [{ product_id: 1, qty: 1 }, { product_id: 2, qty: 1 }] }
Action: EDIT_QUANTITY
  ↓
New state: { cart: [{ product_id: 1, qty: 2 }, { product_id: 2, qty: 1 }] }
Action: PROCEED_TO_PAYMENT
  ↓
New state: { cart: [...], payment: { status: "awaiting_method" } }
Action: SELECT_PAYMENT (method: "cash")
  ↓
New state: { ..., payment: { method: "cash", status: "processing" } }
Action: CONFIRM_PAYMENT
  ↓
New state: { ..., payment: { status: "confirmed" }, transaction: { status: "printing_receipt" } }
Action: RECEIPT_PRINTED
  ↓
New state: { ..., transaction: { status: "complete", sync_status: "queued" } }
Action: SYNC_TRANSACTION (online)
  ↓
New state: { cart: empty, transaction: { status: "synced" } }
Action: RESET
  ↓
State: { cart: empty }
READY FOR NEXT CUSTOMER
```

---

## ✅ Validation Rules

### Product Input

```
When adding product:
├─ name: required, 1-255 characters
├─ barcode: required, unique, 5-20 digits
├─ price: required, > 0, 2 decimal places max
├─ cost: optional, >= 0, <= price (for margin calc)
├─ category: required, must exist in system
├─ tax_rate: 0-100%, decimal
└─ stock_quantity: >= 0, integer
```

### Sales Input

```
When creating sale:
├─ cart: not empty (at least 1 item)
├─ Each item:
│  ├─ product_id: must exist
│  ├─ qty: > 0, <= 999
│  └─ price: > 0 (from product or override)
├─ discount: 0-100% OR fixed amount <= subtotal
├─ payment_method: one of [cash, card, wallet, mixed]
└─ No sales to inactive products
```

### Payment Input

```
When processing payment:
├─ CASH:
│  ├─ amount_paid: >= total
│  └─ calculate change: amount_paid - total
├─ CARD:
│  ├─ Card details present
│  └─ Amount > 0
├─ WALLET:
│  ├─ QR generated
│  └─ Timeout after 60s
└─ MIXED:
    ├─ cash_amount + card_amount = total
    └─ Both methods valid
```

---

## 🎯 Business Rules Summary

| Rule | Description |
|------|-------------|
| **No sale to inactive product** | Only products with status="active" can be sold |
| **No oversold without flag** | Selling beyond stock logs warning but completes |
| **Auto-open cash drawer after payment** | Every successful payment opens drawer (cash, card, wallet) |
| **Offline-first sales** | Can sell offline, sync when online |
| **Trial enforcement** | After 14 days, POS locked for non-paying customers |
| **Inventory real-time** | Stock updates immediately, no batch processing |
| **Receipt always printed** | If printer fails, receipt can be emailed/SMS |
| **Permission checks before action** | Every action verified against user role |
| **Audit log everything** | All transactions, user actions, system changes logged |
| **Conflict resolution on sync** | Last-write-wins for offline conflicts |

---
