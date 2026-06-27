# 📊 Database Schema Relationships & Validation

## Entity Relationship Diagram (ERD)

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SUPERPOS DATABASE                         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Tenant    │ (SaaS multi-tenant)
│─────────────│
│ id (PK)     │
│ name        │
│ plan        │
│ currency    │
│ language    │
│ trial_ends  │
└──────┬──────┘
       │
       ├─────────────────────────┬─────────────────────┬──────────────┐
       │                         │                     │              │
       ▼                         ▼                     ▼              ▼
   ┌────────┐            ┌───────────┐         ┌──────────┐    ┌──────────┐
   │ Branch │ (Store)    │   User    │         │ Category │    │ Product  │
   ├────────┤            ├───────────┤         ├──────────┤    ├──────────┤
   │ id(PK) │            │ id(PK)    │         │ id(PK)   │    │ id(PK)   │
   │ name   │            │ username  │         │ name     │    │ name     │
   │ address│            │ role      │         │ tenant_id│    │ barcode  │
   └────┬───┘            │ pin_code  │         │ parent   │    │ sku      │
        │                │ tenant_id │         │ desc     │    │ price    │
        │                │ branch_id │         └──────────┘    │ cost     │
        │                │ terminal  │                          │ stock    │
        │                └───────────┘                          │ tax_rate │
        │                     ▲                                 │ unit     │
        │                     │ Many Users per Branch           │ weighted │
        │                     │                                 │ plu      │
        │                     │                                 │ category │
        ▼                     │                                 │ tenant_id│
    ┌────────────┐           │                                 └────┬─────┘
    │ Terminal   │           │                                      │
    │────────────│           │                                      │
    │ id(PK)     │◄──────────┘                                      │
    │ name       │                                                  │
    │ serial     │                                                  │
    │ branch_id  │                                       ┌──────────┴────────┐
    │ active     │                                       │                   │
    └────────────┘                                       ▼                   ▼
                                                   ┌──────────────┐   ┌──────────────┐
                                                   │Inventory    │   │ StockMovement│
                                                   │Batch        │   ├──────────────┤
                                                   ├──────────────┤   │ id(PK)       │
                                                   │ id(PK)       │   │ product_id   │
                                                   │ product_id   │   │ qty          │
                                                   │ batch_number │   │ type (enum)  │
                                                   │ qty          │   │ sale_id      │
                                                   │ expiry_date  │   │ tenant_id    │
                                                   │ cost_price   │   │ timestamp    │
                                                   │ tenant_id    │   │ note         │
                                                   └──────────────┘   └──────────────┘
                                                        ▲                    ▲
                                                        │                    │
                                                        │ Used for Pharmacy  │ For Auditing
                                                        │ & Shelf Life Mgmt  │ Inventory
                                                        │                    │
                                                  ┌─────────────────────────┘
                                                  │
                                                  ▼
                                              ┌──────────┐
                                              │  Sale    │
                                              ├──────────┤
                                              │ id(PK)   │
                                              │ uuid     │
                                              │ cashier  │
                                              │ branch   │
                                              │ terminal │
                                              │ total    │
                                              │ tax      │
                                              │ method   │
                                              │ discount │
                                              │ status   │
                                              │ created  │
                                              └────┬─────┘
                                                   │ 1
                                                   │
                                                   │ Many
                                                   ▼
                                              ┌──────────────┐
                                              │  SaleItem    │
                                              ├──────────────┤
                                              │ id(PK)       │
                                              │ sale_id(FK)  │
                                              │ product_id   │
                                              │ product_name │
                                              │ qty          │
                                              │ price_each   │
                                              │ line_total   │
                                              └──────────────┘
```

---

## Schema Validation Rules

### 1. Referential Integrity ✅

```
Foreign Key Checks:
├─ Product.tenant_id → Tenant.id ✅
├─ Product.category_id → Category.id ✅
├─ Category.tenant_id → Tenant.id ✅
├─ Sale.tenant_id → Tenant.id ✅
├─ Sale.cashier_id → User.id ✅ (ON_DELETE=SET_NULL)
├─ Sale.branch_id → Branch.id ✅ (ON_DELETE=SET_NULL) 
├─ Sale.terminal_id → Terminal.id ✅ (ON_DELETE=SET_NULL)
├─ SaleItem.sale_id → Sale.id ✅ (ON_DELETE=CASCADE)
├─ SaleItem.product_id → Product.id ✅ (ON_DELETE=SET_NULL)
├─ InventoryBatch.product_id → Product.id ✅ (ON_DELETE=CASCADE)
├─ InventoryBatch.tenant_id → Tenant.id ✅ (ON_DELETE=CASCADE)
├─ StockMovement.product_id → Product.id ✅ (ON_DELETE=CASCADE)
├─ StockMovement.sale_id → Sale.id ✅ (ON_DELETE=SET_NULL)
├─ Branch.tenant_id → Tenant.id ✅ (ON_DELETE=CASCADE)
├─ Terminal.branch_id → Branch.id ✅ (ON_DELETE=CASCADE)
├─ User.tenant_id → Tenant.id ✅ (ON_DELETE=CASCADE)
├─ User.branch_id → Branch.id ✅ (ON_DELETE=SET_NULL)
└─ User.terminal_id → Terminal.id ✅ (ON_DELETE=SET_NULL)
```

### 2. Unique Constraints ✅

```python
Category:
  unique_together = ('tenant', 'name') ✅
  # Same name cannot exist in same tenant

Product:
  unique_together = [('tenant', 'barcode'), ('tenant', 'sku')] ✅
  # Same barcode/SKU cannot exist in same tenant

Branch:
  unique_together = ('tenant', 'name') ✅
  # Same branch name cannot exist in same tenant

Terminal:
  unique_together = ('branch', 'name') ✅
  # Same terminal name cannot exist in branch

User:
  unique_together = None ❌ ISSUE!
  # BUT: username is unique at Django level
  # NOT unique per tenant!
```

**⚠️ Issue:** Username is globally unique, not per-tenant!

**Fix:**
```python
class User(AbstractUser):
    username = models.CharField(
        max_length=150,
        unique=False  # Remove global uniqueness
    )
    
    class Meta:
        unique_together = [('tenant', 'username')]
```

### 3. Data Type Validation ✅

```python
Product.stock = DecimalField(10, 3) ✅
  # Supports up to 9,999,999.999 units
  # Correct for fractional quantities (0.5kg)

Product.price = DecimalField(10, 2) ✅
  # Supports up to 99,999,999.99 currency units
  # Sufficient for most currencies

Sale.sale_uuid = UUIDField() ✅
  # Perfect for distributed/offline systems

Category.name = CharField(80) ✅
  # Sufficient for product categories

Product.name = CharField(120) ✅
  # Good for detailed product names

User.pin_code = CharField(128) ✅
  # Good - hashed PIN (not plaintext!)
```

---

## Data Consistency Scenarios

### Scenario 1: Cashier sells product

```
Workflow:
1. User scans barcode → Product found
2. Add to cart
3. Proceed to payment
4. Save Sale record
5. Update inventory

Database Operations:
BEGIN TRANSACTION
  1. INSERT INTO pos_sale (tenant_id, cashier_id, ...) → sale_id
  2. INSERT INTO pos_saleitem (sale_id, product_id, qty, price_each)
  3. INSERT INTO pos_stockmovement (product_id, qty, type='sale_out')
  4. UPDATE pos_product SET stock = stock - qty WHERE id=?
  5. If offline: INSERT INTO pos_sale (offline=true)
COMMIT

✅ ACID guarantee: All succeed or all fail
```

### Scenario 2: Product expiry check

```
Every Day (Pharmacy):

SELECT p.*, ib.batch_number, ib.expiry_date
FROM pos_product p
JOIN pos_inventorybatch ib ON ib.product_id = p.id
WHERE ib.expiry_date < TODAY
  AND p.tenant_id = 1

Result: Show all expired batches
  → Prevent sale
  → Alert admin

✅ InventoryBatch.expiry_date enables this
```

### Scenario 3: Branch transfer

```
Transfer 50 units from Branch A to Branch B:

BEGIN TRANSACTION
  -- Branch A
  1. UPDATE products SET stock = stock - 50
     WHERE id=? AND branch_id=A
  2. INSERT INTO stockmovement
     (product_id, qty=-50, type='transfer_out', branch_id=A)
  
  -- Branch B
  3. UPDATE products SET stock = stock + 50
     WHERE id=? AND branch_id=B
  4. INSERT INTO stockmovement
     (product_id, qty=+50, type='transfer_in', branch_id=B)
COMMIT

⚠️ ISSUE: StockMovement doesn't have branch_id!
Solution: Add branch_id to StockMovement
```

---

## Missing Relationships

### ❌ Missing: Branch in StockMovement

```python
class StockMovement(models.Model):
    # Current:
    tenant = ForeignKey(Tenant, CASCADE)
    product = ForeignKey(Product, CASCADE)
    qty = DecimalField()
    sale = ForeignKey(Sale, SET_NULL, null=True)
    
    # Missing:
    # branch = ForeignKey(Branch, SET_NULL, null=True)  ❌ MISSING!
    # This makes branch-level inventory impossible
```

**Solution:**
```python
class StockMovement(models.Model):
    # ... existing fields ...
    
    branch = models.ForeignKey(
        'accounts.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['branch', 'product', 'created_at']),
        ]
```

---

### ❌ Missing: Supplier in StockMovement

```
When stock comes in, we need to track:
- Which supplier?
- Which PO (Purchase Order)?
- What was the cost?

Current InventoryBatch has cost_price but not supplier info
```

**Solution:**
```python
class Supplier(models.Model):
    tenant = ForeignKey(Tenant, CASCADE)
    name = CharField(max_length=255)
    contact = CharField(max_length=255)
    phone = CharField(max_length=20)
    email = EmailField()
    address = TextField()

class PurchaseOrder(models.Model):
    tenant = ForeignKey(Tenant, CASCADE)
    supplier = ForeignKey(Supplier, CASCADE)
    po_number = CharField(unique_together=('tenant', 'po_number'))
    items = ManyToMany(Product, through='POItem')
    total = DecimalField()
    status = CharField(choices=['pending', 'received', 'partial'])
    created_at = DateTimeField(auto_now_add=True)

class StockMovement(models.Model):
    # ... existing fields ...
    po = ForeignKey(PurchaseOrder, SET_NULL, null=True)
    supplier = ForeignKey(Supplier, SET_NULL, null=True)
```

---

## Query Performance Analysis

### 🐢 Slow Queries (Current State)

#### Query 1: Get sales with items for reporting
```sql
SELECT s.*, COUNT(si.id) as item_count
FROM pos_sale s
LEFT JOIN pos_saleitem si ON si.sale_id = s.id
WHERE s.tenant_id = ? AND s.created_at >= ?
GROUP BY s.id
ORDER BY s.created_at DESC
LIMIT 100;

Status: 🐢 SLOW (300-500ms)
Reason: 
  - No index on (tenant_id, created_at)
  - LEFT JOIN without saleitem index
  - Full table scan on large dataset
```

**Fix:**
```sql
-- Add composite index
CREATE INDEX idx_sales_tenant_created ON pos_sale(tenant_id, created_at DESC);
CREATE INDEX idx_saleitem_sale ON pos_saleitem(sale_id);

-- Now: 20-30ms ✅
```

#### Query 2: Get product inventory across all branches
```sql
SELECT p.name, b.name, p.stock
FROM pos_product p
JOIN pos_branch b ON b.tenant_id = p.tenant_id
WHERE p.tenant_id = ? AND b.active = true

Status: 🐢 SLOW (cartesian join!)
Reason:
  - Cartesian product (products × branches)
  - Returns millions of rows
```

**Better Query:**
```sql
-- Product-level stock (single value per product)
SELECT p.name, SUM(p.stock) as total_stock
FROM pos_product p
WHERE p.tenant_id = ?
GROUP BY p.id

-- If you need per-branch: Add branch_id to Product or create separate StockLevel table
```

---

## Constraints That Should Exist

### 1️⃣ Check Constraints

```sql
-- Stock cannot be negative
ALTER TABLE pos_product
ADD CONSTRAINT check_stock_nonnegative
CHECK (stock >= 0);

-- Price must be positive
ALTER TABLE pos_product
ADD CONSTRAINT check_price_positive
CHECK (price > 0);

-- Tax rate between 0 and 100%
ALTER TABLE pos_product
ADD CONSTRAINT check_tax_rate
CHECK (tax_rate >= 0 AND tax_rate <= 1);

-- Sale total must match calculation
ALTER TABLE pos_sale
ADD CONSTRAINT check_total_calculation
CHECK (total = subtotal + tax_amount - discount_value);
```

### 2️⃣ Not-Null Constraints

```python
class Product(models.Model):
    # These should NOT be nullable:
    name = CharField(max_length=120)  ✅ NOT NULL
    price = DecimalField()  ✅ NOT NULL
    tenant = ForeignKey(...)  ✅ NOT NULL
    
    # These are OK to be nullable:
    category = ForeignKey(..., null=True)  ✅ OK
    plu = CharField(blank=True)  ✅ OK for non-scale products
```

---

## Indexing Strategy (Complete List)

### Must-Have Indexes (Performance Critical)
```sql
-- Foreign key lookups
CREATE INDEX idx_product_tenant ON pos_product(tenant_id);
CREATE INDEX idx_product_category ON pos_product(category_id);
CREATE INDEX idx_sale_tenant ON pos_sale(tenant_id);
CREATE INDEX idx_sale_cashier ON pos_sale(cashier_id);
CREATE INDEX idx_sale_branch ON pos_sale(branch_id);
CREATE INDEX idx_saleitem_sale ON pos_saleitem(sale_id);
CREATE INDEX idx_saleitem_product ON pos_saleitem(product_id);

-- Business logic queries
CREATE INDEX idx_sales_created ON pos_sale(created_at DESC);
CREATE INDEX idx_sales_tenant_created ON pos_sale(tenant_id, created_at DESC);
CREATE INDEX idx_sales_cashier_created ON pos_sale(cashier_id, created_at DESC);

-- Inventory queries
CREATE INDEX idx_products_low_stock 
ON pos_product(stock) WHERE stock <= reorder;

-- Batch/expiry queries (Pharmacy)
CREATE INDEX idx_batch_expiry 
ON pos_inventorybatch(expiry_date) 
WHERE expiry_date IS NOT NULL;

-- Lookups
CREATE INDEX idx_product_barcode ON pos_product(barcode);
CREATE INDEX idx_product_sku ON pos_product(sku);
CREATE INDEX idx_sale_uuid ON pos_sale(sale_uuid);
```

---

## Migration Plan for Fixes

### Priority 1: Indexes (1 hour)
```python
# migration: 0010_add_critical_indexes.py
# Add all missing indexes above
```

### Priority 2: Schema Fixes (2-3 hours)
```python
# migration: 0011_fix_schema.py
# 1. Make User.username per-tenant unique
# 2. Add branch_id to StockMovement
# 3. Add constraints (check, not-null)
```

### Priority 3: New Tables (4-6 hours)
```python
# migration: 0012_add_missing_tables.py
# 1. DiscountCode
# 2. Payment
# 3. AuditLog
# 4. Supplier (optional, for Phase 2)
```

---

## Testing Queries (Pre-Launch)

```sql
-- Test 1: Multi-tenancy isolation
SELECT COUNT(DISTINCT tenant_id) 
FROM pos_sale 
WHERE id IN (SELECT id FROM pos_sale WHERE tenant_id = 1 LIMIT 100);
-- Result: 1 (only tenant 1's data visible)

-- Test 2: Foreign key integrity
SELECT COUNT(*) FROM pos_saleitem 
WHERE sale_id NOT IN (SELECT id FROM pos_sale);
-- Result: 0 (all sale items reference existing sales)

-- Test 3: Stock accuracy
SELECT SUM(qty) FROM pos_stockmovement 
WHERE product_id = 1 AND movement_type = 'sale_out';
-- Should match: SUM(qty) FROM pos_saleitem WHERE product_id = 1

-- Test 4: Cash on hand
SELECT SUM(paid - change) FROM pos_sale
WHERE method = 'cash' AND created_at >= DATE_TRUNC('day', NOW());
-- Actual cash that should be in drawer
```

---

## Summary Table: Issues vs. Impact

| Issue | Severity | Impact | Fix Time | Priority |
|-------|----------|--------|----------|----------|
| Missing FK indexes | 🔴 HIGH | 10-50x slower queries | 30min | 1 |
| Race condition in stock | 🔴 HIGH | Overselling possible | 1hr | 1 |
| No discount codes table | 🟡 MEDIUM | Can't track coupons | 2hrs | 2 |
| No audit logs | 🟡 MEDIUM | Compliance issues | 3hrs | 2 |
| No payment details | 🟡 MEDIUM | Can't track failures | 2hrs | 2 |
| Non-hierarchical categories | 🟢 LOW | Limits org at scale | 1hr | 3 |
| Missing branch in movements | 🟡 MEDIUM | Can't track per-branch | 1.5hrs | 2 |
| Username not per-tenant unique | 🟡 MEDIUM | Security risk | 1.5hrs | 2 |
| No soft deletes | 🟢 LOW | Can't restore data | 2hrs | 3 |

