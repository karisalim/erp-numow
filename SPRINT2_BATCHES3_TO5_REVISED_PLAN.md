# SuperPOS – Revised Scope for Sprint 2 Batches 3–5

## 1) Missing or Under-Specified Items to Add

### High priority
- `ProductUnitTierPrice`
  - Purpose: support price tiers by unit (for example carton price vs piece price).
  - Must be defined as a tenant-scoped model linked to a product and a product unit.
  - Important for multi-unit pricing and POS pricing accuracy.

- `Product.default_station`
  - Purpose: define the default station/terminal where the product is usually sold.
  - Needed for POS routing and operational defaults.

- `Product.show_on_pos`
  - Purpose: control whether a product is exposed to the POS catalog.
  - Important for visibility rules and catalog management.

### Medium priority
- `ProductBarcodeUnit.scan_priority`
  - Purpose: define precedence when multiple barcode mappings exist.
  - Needed for deterministic barcode resolution during scanning.

- `ProductUnit.allow_decimal_qty`
  - Purpose: allow decimal quantities for a product unit mapping.
  - Needed for weighted or fractional quantities.

- `ProductVariant` (for sizes/colors/variants such as S/M/L)
  - This is a separate product-variant layer and should be treated as a Sprint 4 scope item.
  - It should not be mixed with the core unit foundation.

### Lower priority / future scope
- `ProductUnit.minimum_order_qty`
  - Purpose: define minimum quantity for purchase or order workflows.
  - Useful for procurement and replenishment logic.

- `Recipe` system
  - This is not part of the core product/unit foundation.
  - It should be explicitly listed as Sprint 4+ or a later phase.

---

## 2) Revised Detailed Scope

### Batch 3 – Product Foundation

#### Goal
Complete the product-level foundation so the product object is no longer only a legacy flat catalog row.

#### Deliverables
1. Product-level fields
   - Add the missing product fields:
     - `default_station`
     - `show_on_pos`
   - Keep the legacy fields intact for compatibility during rollout.

2. Product-unit linkage
   - Ensure every product can be linked to one or more `ProductUnit` records.
   - Ensure each product has a clear base unit mapping.

3. Barcode precedence
   - Implement scan resolution order:
     - first: `ProductBarcodeUnit`
     - second: legacy `Product.barcode`
   - Add `scan_priority` to support explicit precedence logic.

4. Unit-aware pricing
   - Introduce `ProductUnitTierPrice` for unit-specific pricing.
   - This should be validated against the chosen product unit and product.

5. Product-level API changes
   - Update the product serializer so it can expose:
     - base unit information
     - barcode-unit mappings
     - unit pricing data
   - Keep backward compatibility for the existing frontend shape.

#### Required validations
- Product must belong to the same tenant as its unit mappings.
- `ProductBarcodeUnit.barcode` must not collide with legacy `Product.barcode`.
- A product can have only one base `ProductUnit`.
- Base mapping must be immutable once stock history exists.
- `ProductUnitTierPrice` must be linked to a valid `ProductUnit` and valid product.

#### Required tests
- Product create/update with new fields.
- Product barcode resolution precedence.
- Product unit mapping validation.
- Tier-price validation.
- Tenant scoping for all new product-level mappings.

---

### Batch 4 – Seeding and Data Model Expansion

#### Goal
Populate the new data structures safely and make them usable for real operational scenarios.

#### Deliverables
1. Seed logic
   - Seed unit groups and units per tenant.
   - Seed base mappings for existing products.
   - Seed barcode-unit mappings for pack-size barcodes.

2. Product-level defaulting
   - Backfill `default_station` and `show_on_pos` for existing products.
   - Default missing values safely.

3. Unit-specific quantity rules
   - Support `allow_decimal_qty` for relevant units.
   - Support `minimum_order_qty` for purchase/replenishment flows.

4. Variant support (deferred but explicitly planned)
   - Add `ProductVariant` support for size/color/variant handling.
   - This should be isolated so it does not destabilize the base product foundation.

#### Required validations
- Seed data must not create duplicate unit mappings.
- Seed data must preserve existing legacy product behavior.
- Products with historical stock movements must maintain a consistent base mapping.

#### Required tests
- Seed creates correct unit mappings for existing products.
- Backfill preserves compatibility for legacy barcodes.
- Product with no mapping still behaves in legacy mode until seeded.

---

### Batch 5 – POS Integration

#### Goal
Make the new product/unit foundation active inside the POS workflow.

#### Deliverables
1. POS scan integration
   - Make scanner resolution use `ProductBarcodeUnit` first.
   - Fall back to legacy `Product.barcode` only when no pack barcode exists.

2. POS sale flow integration
   - Apply unit-aware quantity conversion when a sale line uses a non-base unit.
   - Use the correct price source for the selected unit.

3. POS catalog visibility
   - Respect `show_on_pos` when rendering the product catalog.
   - Respect `default_station` for station-specific defaults.

4. Purchase/replenishment integration
   - Use `minimum_order_qty` and unit-aware quantities in ordering flows.

#### Required validations
- Scan result must resolve to the correct product and unit.
- Sale line quantities must convert correctly to base units for stock ledger updates.
- POS catalog must hide products marked not visible on POS.

#### Required tests
- End-to-end scan flow with a pack barcode.
- Sales posting with unit conversion.
- Catalog visibility based on `show_on_pos`.
- Default station selection and fallback behavior.

---

## 3) Validation Checklist for the Full Scope

### Data integrity validations
- Tenant scoping for every new mapping.
- Unique constraints across tenant and relevant business keys.
- No barcode collision between legacy product barcode and barcode-unit records.
- One base mapping per product.
- Positive conversion factors.

### Business rule validations
- Base mapping immutability after stock history exists.
- Unit-specific pricing must belong to a valid product unit.
- Decimal quantities must be allowed only when supported by the unit.
- Products hidden from POS should not appear in the active sale catalog.

---

## 4) Test Coverage Required

### Backend tests
- Model tests for new fields and relations.
- Serializer validation tests.
- API tests for product detail/list and barcode scan.
- Stock conversion tests for sales/purchases.
- Migration/seed tests for existing data compatibility.

### Integration tests
- Scan → resolve product → add to cart.
- Sale create → deduce stock movement → update inventory.
- Product hidden from POS should not appear in catalog.

---

## 5) Recommended Implementation Priority

1. Batch 3: product foundation + barcode precedence + tier pricing
2. Batch 4: seeding + data backfill + variant preparation
3. Batch 5: POS integration + visibility + station defaults

This sequencing keeps the foundation stable before the POS and retail workflows consume it.
