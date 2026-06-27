# 📋 Cloud POS System — Product Requirements Document (PRD)

**Version:** 2.0  
**Last Updated:** May 2026  
**Status:** MVP Phase (Phases 1-2)

---

## 🎯 Executive Summary

A cloud-native SaaS retail operating system designed to handle **sales, inventory, subscriptions, and multi-branch management** for supermarkets, pharmacies, restaurants, gyms, and retail stores.

**Core Promise:** Any business owner can set up, manage, and scale their POS in minutes—not months.

**Not just a cashier app. A complete retail operating system.**

---

## 📊 Product Vision

### What We're Building

A unified platform where business owners can:

- Manage point-of-sale transactions (fast, keyboard-optimized)
- Track real-time inventory across branches
- Handle subscriptions (gyms, memberships)
- Connect to physical hardware (barcode scanners, printers, scales, cash drawers)
- Work offline without data loss
- Monitor business analytics and insights
- Manage multiple branches from a single dashboard

### Target Outcome

**By Year 2:** A household name in emerging markets (MENA, Africa, Asia) for retail POS.

**By Year 5:** Evolve into a full ERP system with supply chain, purchasing, and AI analytics.

---

## 👥 Target Markets & Business Segments

### 1. 🛒 Supermarkets & Grocery Stores

**Market Size:** ~2M globally  
**Key Needs:**
- Barcode scanning at scale
- Weight-based product support (scales)
- High-speed checkout (3 items/second)
- Huge inventory management (10K+ SKUs)
- Price label generation
- Supplier management

**Willingness to Pay:** $300-500/month per POS terminal

---

### 2. 💊 Pharmacies

**Market Size:** ~500K globally  
**Key Needs:**
- Expiration date tracking
- Batch/serial number support
- Prescription workflow integration
- Tax rule compliance (medicine taxes)
- Supplier management
- Reorder automation

**Willingness to Pay:** $250-400/month

---

### 3. 🍔 Restaurants & Cafes

**Market Size:** ~1M globally  
**Key Needs:**
- Table management
- Kitchen display system (KDS)
- Bill splitting
- Modifiers (extra toppings, etc.)
- Delivery integration
- Waiter management
- Rush hour speed

**Willingness to Pay:** $200-350/month per POS

---

### 4. 👕 Clothing & Fashion Stores

**Market Size:** ~300K globally  
**Key Needs:**
- Size/color variants (S, M, L, XL)
- Per-variant barcodes
- Exchange/return flows
- Seasonal inventory clearance
- Visual product details

**Willingness to Pay:** $200-300/month

---

### 5. 🏋️ Gyms & Fitness Centers

**Market Size:** ~200K globally  
**Key Needs:**
- Membership subscriptions
- Expiry tracking
- QR-based member check-in
- Attendance logging
- Renewal reminders
- Freeze/pause memberships
- Class-based billing

**Willingness to Pay:** $150-250/month

---

## 💰 SaaS Business Model

### Pricing Strategy

| Plan | Price/Month | Branches | Cashiers | Features | Target |
|------|------------|----------|----------|----------|--------|
| **Starter** | $99 | 1 | 2 | Basic POS, Products, Sales | Solo stores, small cafes |
| **Growth** | $299 | Unlimited | 10 | Reports, Inventory, Branches | Growing supermarkets |
| **Enterprise** | Custom | Unlimited | Unlimited | APIs, Custom integrations, AI | Large chains |

### Trial & Onboarding

- **14-day free trial** (no credit card required)
- Full feature access during trial
- After trial: POS locked, warnings shown, owner access maintained
- Conversion target: 15-20% trial-to-paid

### Revenue Model

- **Recurring SaaS:** 80% (subscription plans)
- **Hardware integration fees:** 10% (printer, scale, scanner integration support)
- **Premium add-ons:** 10% (advanced analytics, AI forecasting, API access)

### Unit Economics (Target)

| Metric | Target |
|--------|--------|
| CAC (Customer Acquisition Cost) | $200 |
| LTV (Lifetime Value) | $3,600 (3-year average) |
| LTV:CAC Ratio | 18:1 |
| Churn Rate | <5% monthly |
| Gross Margin | 75% |

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────┐
│         Frontend Applications           │
├─────────────────────────────────────────┤
│ • POS PWA (Cashier Interface)          │
│ • Admin Dashboard (Management)          │
│ • Customer Display (Optional 2nd Screen)│
│ • Mobile Apps (Future)                 │
└──────────────────┬──────────────────────┘
                   │ REST API + WebSockets
                   ▼
┌─────────────────────────────────────────┐
│      Django REST API + FastAPI          │
│      (Real-time, High Performance)      │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼
    PostgreSQL   Redis    Background   S3
                Caching   Workers      Storage
        
        │
        ▼
┌─────────────────────────────────────────┐
│  Hardware Integration Layer             │
├─────────────────────────────────────────┤
│ • Barcode Scanner (Keyboard emulation) │
│ • Receipt Printer (ESC/POS)            │
│ • Electronic Scale (Barcode parsing)   │
│ • Cash Drawer (Signal trigger)         │
│ • Customer Display (2nd screen)        │
└─────────────────────────────────────────┘
```

---

## 🧩 Core Applications

### 1. POS App (Cashier Interface)

**Purpose:** Fast, distraction-free checkout in under 3 clicks

**Critical Design Rules:**
- Barcode scanner always has focus
- Keyboard-first workflow (no mouse required for experienced cashiers)
- Huge buttons (easy to tap with finger/glove)
- No animations or distracting elements
- Dark mode support
- Works offline with auto-sync

**Key Flows:**
1. Scan barcode → Product appears
2. Edit quantity (if needed)
3. Apply discount (if needed)
4. Select payment method
5. Print receipt
6. Cash drawer opens
7. Next transaction

**Performance Targets:**
- Page load: <1s
- Barcode scan → product display: <300ms
- Add/remove item: <200ms
- Payment processing: <5s

---

### 2. Admin Dashboard

**Purpose:** Complete business management interface

**Core Sections:**
- **Dashboard:** Sales overview, top products, alerts
- **Products:** Inventory, categories, pricing, barcodes
- **Sales:** Transaction history, daily reports, cashier performance
- **Branches:** Multi-branch management, transfers, sync status
- **Users:** Roles, permissions, activity logs
- **Reports:** Profit, inventory, subscription renewals
- **Settings:** Printer config, scale setup, payment methods

---

### 3. Customer Display (Optional)

**Purpose:** Second screen showing customer what they're buying

**Shows:**
- Items added (with prices)
- Running total
- Discount applied
- Payment status
- QR code for wallet payments

---

## 🧠 Core Modules

### Module 1: Products

Handles all product types: standard, weighted, variants

**Product Types:**

| Type | Examples | Key Features |
|------|----------|--------------|
| Standard | Pepsi, Chips | Fixed price, fixed quantity |
| Weighted | Meat, Cheese, Fruits | Price changes based on weight from scale |
| Variant | T-Shirt (S/M/L/XL) | Multiple barcodes, different prices per variant |
| Subscription | Gym membership | Expiry dates, renewal tracking |

**Key Fields:**
- `id` — Unique identifier
- `barcode` — EAN-13 or custom
- `sku` — Stock keeping unit
- `name` — Product name
- `category` — Categorization
- `unit` — kg, L, piece, etc.
- `price` — Selling price
- `cost` — Purchase cost
- `tax` — Tax percentage
- `weight_enabled` — Boolean for scale products
- `scale_barcode_prefix` — For scale barcode parsing
- `stock_quantity` — Current stock level

---

### Module 2: Inventory

Tracks stock movements across branches and operations

**Stock Operations:**
- Purchase In (supplier delivery)
- Sale Out (customer purchase)
- Return In (customer return or damage correction)
- Damage Out (loss/waste)
- Transfer Between Branches (internal movement)

**Key Tracking:**
- Real-time stock levels
- FIFO for expiry dates
- Low stock alerts
- Expiry date alerts (critical for pharmacy)

---

### Module 3: Sales (POS Core)

The heart of the system — transaction handling

**Transaction Flow:**
1. Barcode scanned
2. Product appears with quantity = 1
3. Cashier can adjust quantity
4. Add more items (repeat)
5. Optional discount (% or fixed amount)
6. Select payment method (cash, card, wallet, mixed)
7. Process payment
8. Print receipt
9. Update inventory
10. Log transaction

**Payment Methods:**
- Cash
- Card (credit/debit)
- Digital Wallet (Vodafone Cash, Fawry, PayPal)
- Mixed payment (cash + card)
- Prepaid credit (store account)

**Receipt:**
- QR code (for digital receipt)
- Tax breakdown (VAT details)
- Store logo and info
- Timestamp and cashier ID
- Item-by-item breakdown

---

### Module 4: Subscriptions (Gym/Membership)

For recurring revenue from memberships

**Membership Types:**
- Monthly
- Quarterly (3 months)
- Yearly
- Pay-per-visit

**Features:**
- Expiry tracking with renewal reminders
- Attendance logging
- QR-code based member check-in
- Freeze/pause memberships (e.g., vacation)
- Auto-renewal configuration

---

### Module 5: Restaurant Module (Future)

For restaurants, cafes, QSR

**Features:**
- Table management (dine-in only)
- Kitchen display system (KDS) — orders sent to kitchen
- Bill splitting (separate tabs)
- Modifiers (toppings, dressing, etc.)
- Delivery integration (order delivery tracking)
- Waiter/server management

---

### Module 6: Reports

Automated insights and analytics

**Standard Reports:**
- Daily sales by hour
- Top 10 best-selling products
- Cashier performance (sales, discrepancies)
- Profit margin by category
- Inventory alerts (low stock, expiry dates)
- Subscription renewals due
- Payment method breakdown

**Report Export:**
- PDF download
- Email scheduling
- Integrations (Google Sheets export)

---

### Module 7: Users & Roles

Role-based access control (RBAC)

**Roles:**
| Role | Permissions | Use Case |
|------|-------------|----------|
| Owner | Full access, all settings, subscription | Business owner |
| Admin | All except subscription/billing | Store manager |
| Manager | Sales, reports, user management | Shift supervisor |
| Cashier | Sales only (POS) | Front-line staff |
| Waiter | Table orders, split bills (restaurant) | Restaurant staff |
| Gym Receptionist | Check-ins, membership renewals | Gym staff |

**Audit Logs:** All actions logged for compliance

---

## ⚖️ Electronic Scale Integration

Critical for supermarkets selling by weight

### Scale Barcode Format

**Example:** `211234500750`

| Segment | Length | Meaning |
|---------|--------|---------|
| Prefix | 2 | Weighted item marker (e.g., 21) |
| Product Code | 5 | PLU code (12345) |
| Weight/Price | 5 | Weight in 0.1kg units or price (00750 = 750 = 7.50 kg or €7.50) |
| Check Digit | - | Validation digit |

### PLU System

PLU (Product Lookup Code) = unique identifier on the scale

Each weighted product has:
- PLU code (e.g., 1001)
- Name (e.g., "Cheese Cheddar")
- Price per kg (e.g., €12.99/kg)

### Scale Workflow

1. Customer weighs meat on scale
2. Scale prints barcode with:
   - Product code
   - Actual weight
   - Calculated price
3. Cashier scans barcode
4. POS detects scale barcode prefix
5. Extracts weight → calculates price
6. Transaction proceeds

### Price Updates

When admin changes price for scaled product:

**Method A (Manual):**
- Export CSV with updated PLU prices
- Admin uploads to scale software
- Scale updates locally

**Method B (Direct Sync - Future):**
- POS communicates directly to scale
- Real-time price updates

---

## 🖨️ Hardware Integration

### Supported Hardware

| Device | Protocol | Purpose |
|--------|----------|---------|
| Barcode Scanner | Keyboard emulation (HID) | Product input |
| Receipt Printer | ESC/POS over USB/Network | Physical receipts |
| Cash Drawer | RJ11 signal | Auto-open after payment |
| Electronic Scale | Serial/USB barcode output | Weight-based pricing |
| Customer Display | HDMI/Network | Show customer what they're buying |

### Hardware Configuration

Admin can configure per device:
- Device type
- Connection method (USB, network, serial)
- Port settings
- Test connectivity

---

## 📱 Offline PWA Strategy

### Why Offline Matters

If internet dies in middle of business:
> Supermarket must continue selling. Can't turn away customers.

### Offline Capabilities

**What Works Offline:**
- Barcode scanning
- Product lookup (cached)
- Transaction creation
- Receipt printing (local)

**What's Synced:**
- Product prices (cached on device)
- Inventory counts (synced when online)
- User permissions (cached)

**What Happens Online:**
- All pending invoices uploaded
- Inventory levels updated
- Stock conflicts resolved (last-write-wins with conflict resolution)

### Sync Engine

When internet returns:

1. **Push invoices:** All offline sales pushed to server
2. **Sync inventory:** Local stock adjusted for online changes
3. **Resolve conflicts:** If product was modified online, merge intelligently
4. **Verify:** All transactions confirmed

**Target:** Full sync within 30 seconds of reconnection

---

## 🔐 Security Model

### Authentication

- **JWT tokens** for stateless auth
- **Refresh tokens** for session management
- **Device sessions** to track logged-in devices
- **Two-factor authentication** optional for admin accounts

### Authorization

- **Role-based access control (RBAC)** per user
- **Branch isolation:** Users only see their assigned branches
- **Tenant isolation:** Strict data separation in shared database

### Compliance

- **Audit logs:** Every transaction, user action logged
- **PCI compliance:** No card data stored locally
- **GDPR ready:** Data export, deletion capabilities
- **Tax compliance:** VAT/Tax calculations configurable per region

---

## 📈 MVP Roadmap

### Phase 1 (Month 1-2) — Core POS

**Deliverables:**
- ✅ Authentication & user login
- ✅ Product management (standard products only)
- ✅ Sales transactions (barcode scan, payment)
- ✅ Basic inventory tracking
- ✅ Receipt printing
- ✅ Multi-tenant database setup

**Success Metrics:**
- Can sell items in <3 clicks
- Inventory updates in real-time
- Receipt prints correctly
- 99.9% uptime in testing

---

### Phase 2 (Month 3-4) — Admin & Multi-Branch

**Deliverables:**
- ✅ Admin dashboard (products, inventory, sales history)
- ✅ Reports (daily sales, top products)
- ✅ Multi-branch support
- ✅ Offline mode (PWA)
- ✅ Role-based access control
- ✅ Trial/subscription enforcement

**Success Metrics:**
- Can manage multiple branches
- Offline transactions sync correctly
- Reports generate in <5 seconds

---

### Phase 3 (Month 5-6) — Advanced Inventory

**Deliverables:**
- ✅ Electronic scale integration
- ✅ Weighted products
- ✅ Advanced inventory (transfers, adjustments)
- ✅ Expiry date tracking
- ✅ Supplier management
- ✅ Price labels generation

---

### Phase 4 (Month 7-8) — Vertical Solutions

**Deliverables:**
- ✅ Pharmacy module (batch numbers, expiry)
- ✅ Restaurant module (tables, KDS)
- ✅ Gym module (memberships, check-in)

---

### Phase 5 (Month 9-12) — AI & Analytics

**Deliverables:**
- ✅ AI-powered sales forecasting
- ✅ Inventory optimization
- ✅ Anomaly detection (fraud, errors)
- ✅ Business recommendations

---

## 🤖 AI-First Development

This project is designed to be built with AI-assisted tools:

- **Claude Code** (with MCP servers)
- **Replit** (for cloud development)
- **Cursor** (AI-powered IDE)
- **Google Stitch** (AI design generation)
- **v0** (component generation)
- **Lovable** (AI web builder)

**Key Principle:** AI handles the mechanical work. Engineers focus on architecture, edge cases, and optimization.

---

## 📁 Supporting Documentation

| File | Purpose |
|------|---------|
| **DESIGN.md** | UI/UX system, components, design tokens |
| **FLOW.md** | Business logic, workflows, state management |
| **DOMAIN.md** | Business rules per vertical (pharmacy, gym, etc.) |
| **ARCHITECTURE.md** | Technical implementation, database schema |
| **API.md** | REST endpoints, request/response contracts |

---

## 📊 Success Metrics (MVP Launch)

| Metric | Target |
|--------|--------|
| Checkout time | <30 seconds for 5 items |
| System uptime | 99.9% |
| Barcode scan latency | <300ms |
| Mobile responsiveness | Pixel-perfect on 5.5" screens |
| Offline sync | <30 seconds on reconnection |
| Trial conversion | 15-20% |
| Customer support satisfaction | >4.5/5 stars |

---

## 💡 Vision & Long-Term Roadmap

**Year 1:** Become the go-to POS for emerging markets

**Year 2-3:** Expand to full ERP with purchasing, HR, analytics

**Year 5:** AI-powered retail operating system that optimizes entire business

**Outcome:** Supermarkets, pharmacies, restaurants use our platform to run entire businesses—not just process sales.

---
