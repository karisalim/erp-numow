# 🎯 Cloud POS System — Domain Knowledge (DOMAIN.md)

**Version:** 2.0  
**Last Updated:** May 2026  
**Scope:** Business-specific rules per vertical

---

## 📋 Overview

This document captures **how different businesses are different**. Same platform, different rules.

**Key Principle:** Core POS is identical. Domains add vertical-specific features, workflows, and constraints.

---

## 🛒 Supermarket Domain

### Core Identity

**Market:** High-volume, high-SKU retail  
**Key Metric:** Transactions per hour  
**Typical Setup:** 1-5 cashiers, 2,000-50,000 SKUs  
**Hardware:** Barcode scanner, receipt printer, cash drawer, scales

---

### Supermarket-Specific Features

#### 1. Electronic Scale Integration

**Why:** Meat, cheese, fruits sold by weight

**Workflow:**
```
Customer → Weigh product on scale
         → Scale prints barcode with weight + calculated price
         → Cashier scans barcode
         → POS detects weight prefix (e.g., "21")
         → Extracts weight from barcode
         → Calculates final price
         → Adds to cart
```

**Scale Barcode Format:**
```
21 = Prefix (weighted item)
12345 = PLU code (1001-9999)
00750 = Weight in 0.1kg units (750 = 7.5kg)

Example: 21123450750
├─ Prefix: 21
├─ PLU: 12345
└─ Weight: 750 (= 7.5kg)
```

**PLU Database:**
```
PLU 1001 = Cheese Cheddar, €12.99/kg
PLU 1002 = Beef Steak, €18.50/kg
PLU 1003 = Apples Red, €2.99/kg
PLU 1004 = Chicken Breast, €8.99/kg
...
```

**Price Update Flow:**
```
Admin changes price: Cheese €12.99/kg → €13.49/kg
  ↓
Option A (Manual):
├─ Export PLU list to CSV
├─ Upload to scale via scale software
├─ Scale updates locally
└─ New labels print with updated price

Option B (Future - Direct Sync):
├─ POS sends price update to scale
├─ Scale updates in real-time
└─ New labels print immediately
```

**Constraints:**
- Scale supports max 5-digit PLU codes (max 9999 products per scale)
- Barcode length depends on scale type (12-13 digits typical)
- Weight precision: 0.1kg minimum (100g)
- Price updates take effect next label print

---

#### 2. Price Labels

**Purpose:** Print shelf labels for products

**Label Contents:**
```
┌─────────────────────────┐
│ Product Name: Cheese    │
│ Price: €12.99           │
│ Price per Unit: €12.99  │
│ Barcode: 123456789012   │
│ Valid from: 2026-05-15  │
│ Valid to: 2026-06-14    │
└─────────────────────────┘
```

**Label Generation:**
- Admin: Bulk update prices
- System: Generate label batch
- Print: Label printer (80mm thermal)
- Update: Labels on shelves daily

**Bulk Price Change:**
```
Admin: "Reduce dairy prices by 10%"
  ↓
System:
├─ Find all products in "Dairy" category
├─ Apply 10% discount
├─ Generate labels for all
├─ Queue for printing
└─ Show: "Generating 127 labels"
```

---

#### 3. High-Speed Checkout

**Challenge:** Supermarkets move fast. Checkout must be <30 seconds for 10+ items.

**Optimization Rules:**

| Rule | Implementation |
|------|-----------------|
| Barcode always focused | Auto-focus barcode input, no mouse |
| Minimal clicks | Scan → Qty (if needed) → Payment |
| Large buttons | 48px minimum height for fast tapping |
| No animations | Speed = no visual delay |
| Keyboard shortcuts | Alt+P = Proceed, Alt+D = Discount |
| Auto-advance | After payment, auto-clear cart |
| Voice feedback | "Item added", "Total €45.50" (optional) |

---

#### 4. Inventory at Scale

**Challenge:** Managing 10,000+ SKUs

**Features:**

```
Inventory Management:
├─ Real-time stock tracking
│  ├─ Every sale updates instantly
│  ├─ Stock alerts at reorder point
│  └─ Critical stock: red highlight
│
├─ Supplier integration
│  ├─ Auto-create PO at reorder point
│  ├─ Track delivery status
│  └─ Receiving workflow (scan barcodes)
│
├─ Stock by location
│  ├─ Main shelf: 500 units
│  ├─ Back room: 100 units
│  └─ Return to shelf automatically
│
├─ Expiry date tracking
│  ├─ FIFO enforcement (first expiry on top)
│  ├─ 30-day warning alerts
│  └─ Auto-discount aging stock
│
└─ Cycle counting
   ├─ Physical count verification
   ├─ Scan barcodes in store
   ├─ System highlights discrepancies
   └─ Adjust inventory in real-time
```

---

#### 5. Category Management

**Hierarchy:**

```
Grocery (Department)
├─ Dairy
│  ├─ Cheese
│  ├─ Milk
│  └─ Yogurt
├─ Meat
│  ├─ Beef
│  ├─ Chicken
│  └─ Pork
└─ Produce
   ├─ Fruits
   └─ Vegetables

Each product belongs to ONE category
Categories used for:
├─ Navigation (browsing)
├─ Reports (sales by category)
├─ Pricing (bulk updates)
└─ Margin analysis
```

---

#### 6. Multi-Checkout Synchronization

**Challenge:** Multiple cashiers, shared inventory

**Requirement:**
- Cashier 1 sells item at 2pm → Stock updates
- Cashier 2's app (synced) sees updated stock instantly
- No overselling (unless flagged)

**Implementation:**
```
Backend: Single inventory source (PostgreSQL)
Cache: Redis for real-time sync
WebSocket: Broadcast stock changes to all POS devices
Update: <100ms latency for all cashiers
```

---

### Supermarket-Specific Reports

| Report | Key Metrics |
|--------|-------------|
| **Daily Sales** | Total revenue, item count, avg transaction, by cashier |
| **Category Performance** | Sales per category, margin, trend |
| **Stock Status** | Low stock alerts, turnover, shrinkage |
| **Cashier Performance** | Sales, discrepancies, speed, customer feedback |
| **Expiry Alerts** | Aging stock, discounts applied, waste |

---

## 💊 Pharmacy Domain

### Core Identity

**Market:** Regulated retail with compliance requirements  
**Key Metric:** Prescription accuracy, compliance  
**Typical Setup:** 1-3 cashiers, 2,000-5,000 SKUs  
**Hardware:** Barcode scanner, receipt printer, optional prescription printer

---

### Pharmacy-Specific Features

#### 1. Expiry Date Tracking

**Requirement:** Drugs expire. Must not sell expired medication.

**Workflow:**

```
Product Master:
├─ Product name: "Aspirin 500mg"
├─ Batch tracking: ENABLED (required for drugs)
├─ Stock tracking: BY BATCH
└─ Each batch has:
   ├─ Batch number (e.g., "A2026-0534")
   ├─ Expiry date (e.g., "2027-12-31")
   ├─ Quantity (e.g., 100 units)
   ├─ Cost
   └─ Status: "active" / "expired" / "recalled"

Receiving:
├─ Supplier: Pharma Co
├─ PO: #1234
├─ Item: Aspirin 500mg
│  ├─ Batch: A2026-0534
│  ├─ Qty: 100
│  ├─ Expiry: 2027-12-31
│  ├─ Cost: $0.50/unit
│  └─ [RECEIVE]
│
└─ Stock added: 100 Aspirin (Batch A2026-0534)

At Checkout:
├─ Cashier scans: Aspirin 500mg
├─ System check:
│  ├─ Multiple batches in stock?
│  │  ├─ YES: Show available batches
│  │  │  ├─ Batch A2026-0534 (100 units, expires 2027-12-31)
│  │  │  ├─ Batch B2025-1234 (50 units, expires 2027-08-15) ← Sell this first
│  │  │  └─ Auto-select earliest expiry (FIFO)
│  │  └─ NO: Use only batch
│  ├─ Expiry check: 2027-12-31 > TODAY? YES ✓
│  └─ Add to cart with batch reference
│
└─ Receipt shows:
   ├─ Item: Aspirin 500mg
   ├─ Batch: A2026-0534
   ├─ Expiry: 12/31/2027
   └─ Qty: 2 tablets
```

**Expiry Alerts:**

```
System runs daily check:
├─ Find all products with expiry <= TODAY
│  ├─ Status: "EXPIRED"
│  ├─ Block from sale
│  ├─ Prevent checkout (error: "Product expired")
│  └─ Alert manager: "5 items expired"
│
├─ Find all products with expiry <= 30 days
│  ├─ Status: "EXPIRING SOON"
│  ├─ Yellow badge in inventory
│  ├─ Auto-discount (20% off)
│  └─ Alert manager: "20 items expiring in 30 days"
│
└─ Generate report:
   ├─ Expired items (cannot sell)
   ├─ Expiring items (discount)
   └─ Recommendation: "Prepare disposal for 5 items"
```

---

#### 2. Batch Number Tracking

**Why:** Drugs may be recalled. Must track which batches sold to which customers.

**Implementation:**

```
Receiving:
├─ Batch number recorded in system
├─ Linked to PO
├─ Supplier info saved
└─ Cost per unit stored

Selling:
├─ Each sale item includes batch number
├─ Sale record:
│  ├─ sale_id: 12345
│  ├─ item: "Aspirin 500mg"
│  ├─ batch: "A2026-0534"
│  ├─ qty: 2
│  ├─ customer: optional
│  ├─ date: 2026-05-15
│  └─ payment_id: card.xxx
│
└─ Stored in sales_items_pharmaceutical_batch table

Recall Scenario:
├─ FDA: "Batch A2026-0534 contaminated. RECALL."
├─ Pharmacy admin finds batch in system
├─ Query: "Which customers bought batch A2026-0534?"
│  ├─ Result: Customer 1 (contact info)
│  ├─ Result: Customer 2 (contact info)
│  └─ Result: 5 total customers
├─ Auto-generate recall notice
├─ Send email/SMS to affected customers
├─ Log recall event for compliance
└─ Block batch from future sales (status = "recalled")
```

---

#### 3. Prescription Management

**Challenge:** Pharmacy sells prescription drugs. Prescriptions must be verified.

**Workflow:**

```
Customer brings prescription:
├─ Prescription paper or digital
├─ Doctor name, signature
├─ Medicine name, dosage, qty
├─ Patient name
├─ Date issued (must be <1 year old)
└─ Refills remaining

Pharmacist verification:
├─ Check prescription validity
├─ Check patient allergies (if in system)
├─ Check drug interactions with other meds
├─ Verify dosage is safe
├─ Approve or deny

If approved:
├─ Add prescription to system
├─ Flag in POS: "Prescription item"
├─ Cashier cannot sell without pharmacist OK
├─ System requires pharmacist code to complete sale
│  ├─ Input code
│  ├─ Verify code
│  └─ Allow checkout
└─ Log prescription fill

If denied:
├─ Note reason (allergy, interaction, etc.)
├─ Contact doctor for clarification
└─ Do not sell
```

**Optional POS Features:**

```
If pharmacy has POS integration with prescription module:
├─ Show prescription items with "Rx" badge
├─ Pharmacist code required (2-factor)
├─ Cannot sell prescription items without:
│  ├─ Valid prescription on file
│  ├─ Pharmacist approval code
│  └─ Interaction check passed
└─ Print receipt with "Rx" and refills remaining
```

---

#### 4. Tax Complexity

**Challenge:** Drug tax varies by type and country

**Rules:**

```
Over-the-counter drugs: 5% tax (e.g., Aspirin)
Prescription drugs: 0% tax (reimbursed by insurance)
Medical devices: 0% tax (e.g., bandages)
Cosmetics (not drugs): 17% tax (e.g., sunscreen)
Dietary supplements: 5% tax

In system:
├─ Product field: tax_classification
│  ├─ "otc_drug" → 5%
│  ├─ "prescription_drug" → 0%
│  ├─ "medical_device" → 0%
│  ├─ "cosmetic" → 17%
│  └─ "supplement" → 5%
│
└─ At checkout:
   ├─ Combine items by tax rate
   ├─ Calculate tax separately per rate
   ├─ Show breakdown on receipt
   └─ Comply with local regulations
```

---

#### 5. Insurance Copay Handling

**Challenge:** Insurance companies reimburse partially. Pharmacy receives less than price.

**Workflow:**

```
OTC Item (no insurance):
├─ Price: $20.00
├─ Customer pays: $20.00

Prescription Item (with insurance):
├─ List price: $100.00
├─ Insurance copay: $15.00
├─ Insurance pays: $85.00
├─ Customer pays: $15.00
│
├─ At checkout:
│  ├─ System recognizes as insurance item
│  ├─ Shows customer copay: $15.00
│  ├─ Customer pays: $15.00
│  └─ Separate invoice sent to insurance
│
└─ Accounting:
   ├─ Revenue: $100 (full price)
   ├─ Customer payment: $15
   ├─ Insurance receivable: $85
   └─ Track insurance payments separately
```

---

### Pharmacy-Specific Reports

| Report | Key Metrics |
|--------|-------------|
| **Expiry Report** | Expired items, expiring soon, aging stock |
| **Batch Tracking** | All batches in stock, expiry timeline |
| **Compliance Report** | Prescription fills, pharmacist approvals |
| **Insurance Receivables** | Amount owed by insurance, aging AR |
| **Recall Tracking** | Recalled batches, customer notifications sent |

---

## 🏋️ Gym / Fitness Domain

### Core Identity

**Market:** Membership-based recurring revenue  
**Key Metric:** Member retention, attendance  
**Typical Setup:** 1-2 reception staff, 100-5,000 members  
**Hardware:** Optional: QR code scanner for check-in

---

### Gym-Specific Features

#### 1. Membership Management

**Membership Types:**

```
Monthly Subscription:
├─ Price: $49/month (e.g.)
├─ Auto-renew: Every 30 days
├─ Cancel anytime (with notice period)
├─ No lock-in contract

Quarterly Subscription:
├─ Price: $130/3 months
├─ Saves 10% vs monthly
├─ Auto-renew: Every 90 days

Annual Subscription:
├─ Price: $400/year
├─ Saves 30% vs monthly
├─ Auto-renew: Every 365 days

Pay-as-you-go:
├─ Price: $20/visit
├─ No membership
├─ Check-in = automatic charge
```

**Membership Lifecycle:**

```
Sign up:
├─ Select plan (monthly/quarterly/annual)
├─ Enter personal info
├─ First payment processed
├─ Start date = today
├─ Expiry date = today + plan duration
└─ Status = "active"

Active member:
├─ Unlimited gym access
├─ QR code for check-in
├─ App login (if available)
└─ Notifications for upcoming expiry

30 days before expiry:
├─ Send email: "Your membership expires in 30 days"
├─ Send SMS: "Renew now to keep your benefits"
└─ Show renewal option in app

Day of expiry:
├─ Check auto-renew flag
│  ├─ YES: Charge member → Renew automatically
│  │       └─ New expiry = expiry + plan duration
│  │
│  └─ NO: Status = "inactive"
│          └─ Member can still renew manually
│
└─ Send notification: "Your membership renewed"

Renewal failed (payment declined):
├─ Send email: "Renewal failed. Update payment."
├─ Status = "renewal_failed"
├─ Allow access for 3 days (grace period)
├─ Retry payment in 3 days
└─ If still fails: Block access
```

---

#### 2. Attendance Tracking

**Purpose:** Track who comes to the gym (for analytics and engagement)

**Check-In Workflow:**

```
Member arrives at gym:
├─ Receptionist: "Scan your QR code or tell me your name"
├─ Option A: Scan QR code
│  ├─ Barcode scanner reads QR
│  ├─ POS looks up member
│  ├─ Check status:
│  │  ├─ Active? → Log check-in
│  │  ├─ Expired? → Show "Membership expired"
│  │  │             [Renew now?]
│  │  └─ Frozen? → Show "Membership paused until [date]"
│  │
│  └─ Log attendance:
│     ├─ member_id
│     ├─ check_in_time = now
│     ├─ branch_id
│     └─ date
│
└─ Option B: Manual lookup
   ├─ Type member name
   ├─ Select from dropdown
   ├─ Same check as above
   └─ Log attendance

Attendance benefits:
├─ Analytics: Peak hours, member engagement
├─ Engagement: "You've been 8x this month!"
├─ Churn prediction: "Member hasn't been in 30 days" → Outreach
└─ Retention: Loyalty points for attendance (future)
```

---

#### 3. Freeze/Pause Memberships

**Why:** Members go on vacation, injury, etc. Want to pause, not cancel.

**Workflow:**

```
Member requests: "I'm going on vacation for 3 months"

Process:
├─ Admin creates freeze request
├─ Freeze start: Today
├─ Freeze end: 3 months from today
├─ Status = "frozen"
│
├─ Effect:
│  ├─ Check-in blocked (with message: "Membership frozen")
│  ├─ Original expiry EXTENDED by freeze duration
│  │  ├─ Original expiry: June 15
│  │  ├─ Freeze duration: 3 months
│  │  └─ New expiry: Sept 15 (original + 3 months)
│  │
│  └─ Recurring charge PAUSED
│     └─ If monthly: No charge during freeze
│
└─ When freeze ends:
   ├─ Status = "active"
   ├─ Check-in allowed again
   └─ Recurring charge resumes

Freeze rules:
├─ Max freeze duration: 6 months
├─ Can freeze up to 2x per year
├─ Freeze shows on member dashboard
└─ Notification before freeze ends
```

---

#### 4. Cancellation & Retention

**Workflow:**

```
Member wants to cancel:
├─ Process cancellation request
├─ Ask reason: (dropdown)
│  ├─ "Moving away"
│  ├─ "Can't afford"
│  ├─ "Not using"
│  ├─ "Found better gym"
│  └─ "Other"
│
├─ Show retention offer:
│  ├─ "We understand. How about 50% off next 3 months?"
│  ├─ "Or pause your membership instead?"
│  └─ "Member since Jan 2024 - we'll miss you!"
│
├─ If insists on cancel:
│  ├─ Check notice period:
│  │  ├─ If notice required (contractual): Show "Cancel from [date]"
│  │  └─ If no notice: Cancel immediately
│  │
│  ├─ Final charge on cancellation date
│  ├─ Status = "cancelled"
│  ├─ Expiry date = cancellation date
│  └─ Check-in blocked
│
└─ Post-cancellation:
   ├─ Send email: "We'd love to have you back"
   ├─ Show re-join offer: "Come back for 30% off first month"
   └─ Mark for outreach (future win-back campaign)
```

---

#### 5. Class Scheduling (Future Feature)

**Overview (not in MVP, but domain knowledge):**

```
Gym offers classes:
├─ Yoga (Mon, Wed, Fri 9am)
├─ Spin (Tue, Thu 6pm)
├─ CrossFit (Mon-Fri 5pm)
└─ Boxing (Sat 10am)

Member can:
├─ Book class spots
├─ Cancel booking (24h notice)
├─ Receive class reminders
└─ Earn points for attendance

Gym can:
├─ Track capacity
├─ Waitlist overbooked classes
├─ Send class reminders
└─ Track instructor workload
```

---

### Gym-Specific Reports

| Report | Key Metrics |
|--------|-------------|
| **Member Retention** | Active members, cancellations, churn rate |
| **Attendance** | Daily/weekly attendance, peak hours, trends |
| **Revenue** | MRR (monthly recurring revenue), ARR, renewal rate |
| **Member Engagement** | Check-in frequency, at-risk members (no activity 30d+) |
| **Renewal Rate** | % members renewing, cancellation reasons |

---

## 🍔 Restaurant Domain

### Core Identity

**Market:** Table-based service with kitchen coordination  
**Key Metric:** Table turnover, speed of service  
**Typical Setup:** 3-10 waiters, 5-20 tables, 1 kitchen  
**Hardware:** POS terminal, kitchen display, optional table tablets

---

### Restaurant-Specific Features

#### 1. Table Management

**Purpose:** Track orders by table, coordinate with kitchen

**Workflow:**

```
Waiter → Customer seated at Table 5
         → Opens order in POS

Current state:
├─ Table: Table 5
├─ Covers: 4 (customers)
├─ Opened: 14:32
├─ Status: "Open"
└─ Items: (none yet)

Waiter takes order:
├─ Item 1: Margherita Pizza
├─ Item 2: Caesar Salad
├─ Item 3: Coca Cola
├─ Item 4: Water
└─ [SEND TO KITCHEN]

Items tagged per type:
├─ Hot items: Margherita Pizza → Kitchen
├─ Cold items: Caesar Salad → Kitchen (separate line)
├─ Beverages: Drinks → Bar
└─ Items marked with table number and time

Kitchen display:
┌─────────────────┐
│ Table 5, 14:36  │
├─────────────────┤
│ Margherita      │  ← Start cooking
│ Caesar Salad    │
│ Water (hold)    │
└─────────────────┘

Waiter checks kitchen:
├─ Items ready?
├─ If yes: Deliver to table
├─ Mark delivered in POS
└─ Check if more items coming
```

---

#### 2. Kitchen Display System (KDS)

**Purpose:** Show kitchen what to cook, in what order

**Display Format:**

```
KITCHEN SCREEN (TV size monitor)

[TABLE 5, 14:36] [TABLE 3, 14:40] [TABLE 7, 14:42]
├─ Margherita    ├─ Pasta         ├─ Steak
├─ Caesar Salad  ├─ Risotto       └─ Fries
└─ Water (hold)  └─ Tiramisu

Rules:
├─ Show open orders
├─ Color-code by urgency:
│  ├─ Green: Just ordered (<5 min)
│  ├─ Yellow: Waiting (5-15 min)
│  └─ Red: Late (>15 min target)
│
├─ Sorting: Oldest first (FIFO)
├─ Updates: Real-time when waiter adds items
├─ Actions: Chef marks [DONE] when complete
│           Item disappears from display
│
└─ Queue system:
   ├─ Pasta → 8 min
   ├─ Pizza → 12 min
   ├─ Burger → 6 min
   └─ Chef prioritizes based on cook times
```

---

#### 3. Bill Splitting

**Challenge:** Multiple payment methods from one table

**Workflow:**

```
Table 5: 4 customers, total bill $120

Waiter: "How many bills?"
Customer: "Two"

Breakdown:
├─ Customer 1 + 2: Pizza + Salad + 2 drinks = $60
├─ Customer 3 + 4: Steak + Fries + 2 drinks = $60
└─ [SELECT ITEMS PER BILL]

Payment:
├─ Bill 1: $60 cash
├─ Bill 2: $60 card
└─ [PROCESS BOTH PAYMENTS]

POS handles as:
├─ Sale 1: $60 (marked as part of Table 5)
├─ Sale 2: $60 (marked as part of Table 5)
└─ Table 5 status: "Paid and closed"
```

**Alternative: Open-Ended Bill:**

```
Waiter doesn't know split upfront
├─ Keep table open
├─ Customer runs tab
├─ At end: "Split 4 ways or 2 ways?"
├─ Manually divide items
└─ Process payments
```

---

#### 4. Modifiers (Customizations)

**Purpose:** Customer can customize items (toppings, dressing, temperature, etc.)

**Workflow:**

```
Item: Burger
Modifiers available:
├─ Cheese: +$2 (cheddar, swiss, blue cheese)
├─ Bacon: +$1 (yes/no)
├─ Sauce: (mayo, ketchup, mustard)
├─ Temperature: (rare, medium, well)
└─ Extras: +$0.50 each (lettuce, tomato, onion)

Customer order:
├─ Burger
├─ + Cheese (Swiss)
├─ + Bacon
├─ Sauce: Mayo
├─ Temperature: Medium
└─ + Tomato

Price calculation:
├─ Base burger: $12
├─ Cheese: +$2
├─ Bacon: +$1
├─ Tomato: +$0.50
└─ Total: $15.50

KDS note:
├─ "Burger" [Table 5]
├─ Swiss cheese
├─ Bacon
├─ Medium
├─ Extra tomato
└─ No mayo, yes ketchup
```

---

#### 5. Delivery Integration (Future)

**Overview (not in MVP):**

```
Third-party delivery (UberEats, DoorDash):

Order comes in via app:
├─ Customer orders from restaurant via Uber app
├─ Order syncs to restaurant POS
├─ Kitchen sees: "[DELIVERY] Table 22"
├─ Chef cooks, marks done
├─ Waiter bags order
├─ Driver arrives, picks up
└─ Delivery complete

POS tracks:
├─ Delivery app order ID
├─ Delivery platform commission
├─ Delivery address (optional)
└─ Delivery status (ready/picked/complete)
```

---

### Restaurant-Specific Reports

| Report | Key Metrics |
|--------|-------------|
| **Table Turnover** | Avg time per table, tables per hour |
| **Menu Performance** | Most ordered items, margin per item |
| **Kitchen Efficiency** | Avg prep time, peak time load |
| **Waiter Performance** | Orders per shift, upsell rate, tips |
| **Rush Hour Analysis** | Peak hours, max capacity, wait times |

---

## 🎪 Event/Venue Domain

### Core Identity

**Market:** Bars, clubs, event spaces  
**Key Metric:** Drinks per hour, cover charge  
**Typical Setup:** 3-5 bartenders, 1-2 servers  
**Hardware:** Fast barcode scanner, loud-proof system

---

### Venue-Specific Features

#### 1. Bar Tab / Running Tab

**Concept:** Customer orders drinks throughout evening, pays at end

**Workflow:**

```
Customer 1: "Start a tab"
├─ POS creates tab (linked to customer or card)
├─ Tab ID: TAB-001
└─ Open tab shown on bartender screen

Drinks ordered:
├─ 19:30 - Beer: $6 → Running total: $6
├─ 19:45 - Shot: $5 → Running total: $11
├─ 20:15 - Cocktail: $12 → Running total: $23
├─ 21:00 - Beer: $6 → Running total: $29
└─ 21:30 - "Close tab"

Payment:
├─ Total: $29
├─ Payment method: Card
├─ Tip option: (0% / 15% / 20% / custom)
│  ├─ Customer adds 18% = $5.22 tip
│  ├─ Final total: $34.22
│  └─ Credit card charged
│
└─ Receipt printed with itemized drinks
```

**Running Tab Screen (Bartender View):**

```
┌─────────────────────────────────┐
│ TAB-001: $29.00                 │
├─────────────────────────────────┤
│ Beer (x2)          $12          │
│ Shot               $5           │
│ Cocktail           $12          │
├─────────────────────────────────┤
│ [ADD ITEM] [CLOSE] [TRANSFER]   │
└─────────────────────────────────┘
```

---

#### 2. Cover Charge / Flat Fee

**Purpose:** Venue charges per person to enter

**Workflow:**

```
Bouncer at door:
├─ Customer enters
├─ Bouncer scans wristband QR or name
├─ POS records: 1 cover
├─ Running total: X covers tonight

At night end:
├─ Covers = 150
├─ Cover charge = $15/person
├─ Total revenue from covers = $2,250
└─ Plus drink sales = additional revenue
```

---

#### 3. Happy Hour Specials

**Challenge:** Dynamic pricing at certain times

**Workflow:**

```
Happy hour: 17:00 - 19:00
Special prices:
├─ Beer: $4 (normally $6)
├─ Cocktails: $8 (normally $12)
└─ Wine: $5 (normally $7)

POS setup:
├─ Create pricing rule
├─ Day: Mon-Fri
├─ Time: 17:00-19:00
├─ Apply to: Products with tag "happyhour"
├─ Price override: Set new price

At 17:00:
├─ System activates happy hour
├─ Menu shows happy hour prices
├─ Discounts apply automatically
└─ At 19:00: Prices revert

Report:
├─ Happy hour vs regular revenue
├─ Margin impact
└─ Customer count by period
```

---

### Venue-Specific Reports

| Report | Key Metrics |
|--------|-------------|
| **Daily Covers** | Number of customers, cover charge revenue |
| **Drink Sales** | Top drinks, average per customer |
| **Rush Hour** | Peak times, max capacity, staff load |
| **Staff Tips** | Tip percentages by bartender, trends |
| **Happy Hour Impact** | Discounted vs regular revenue |

---

## 🧪 Quick Comparison: All Verticals

| Aspect | Supermarket | Pharmacy | Gym | Restaurant |
|--------|-------------|----------|-----|------------|
| **Key Revenue** | Sales | Sales + Compliance | Recurring membership | Food/Drinks |
| **Inventory** | High volume | Expiry critical | None | Food recipes |
| **Checkout** | Fast, high-volume | Regulated, slower | Recurring, QR | Order-based |
| **Hardware** | Scanner, scale, printer | Barcode, prescription | QR scanner | Kitchen display |
| **Key Constraint** | Speed | Compliance | Member retention | Kitchen coordination |
| **Multi-location** | Common | Single store | Common | Common |
| **Special Features** | Scales, labels | Batch tracking, recall | Attendance tracking | Delivery integration |
| **Offline Support** | Critical | Important | Not critical | Important |

---

## 🔄 Domain Switching

### Is One Instance Enough?

**Question:** Can a restaurant also sell retail products (e.g., wine bottles to take home)?

**Answer:** YES

**Implementation:**

```
Product types:
├─ Dine-in only: Burgers, pasta (not retail)
├─ Retail only: Bottled wine, packaged goods
└─ Both: Bottled wine (dine-in + retail)

At checkout:
├─ Dine-in items → Add to table
├─ Retail items → Separate transaction or split bill
└─ System tracks both

Reports:
├─ Food service revenue
├─ Retail revenue
└─ Total combined
```

---

## 📊 Domain Customization Checklist

When setting up a new tenant, determine:

- [ ] **Primary domain:** Supermarket / Pharmacy / Gym / Restaurant / Other?
- [ ] **Features needed:** Scale support? Expiry tracking? Memberships? Tables?
- [ ] **Hardware:** Which devices will be connected?
- [ ] **Inventory model:** Count-based? Batch-based? Infinite (services)?
- [ ] **Payment types:** Cash / Card / Wallet / Insurance / Membership?
- [ ] **Reporting:** Which domain-specific reports?
- [ ] **Compliance:** Any regulatory requirements?
- [ ] **Multi-location:** Single store or multiple branches?
- [ ] **Integrations:** Third-party systems (delivery, reservation, etc.)?

---
