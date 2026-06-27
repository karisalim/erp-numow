# Master Data & Configuration Contract

## Purpose

This document defines the tenant-configurable master data and configuration foundation required before Table Service / Open Orders implementation.

This is planning-only. It does not implement models, APIs, or runtime behavior yet.

---

## 1. Dynamic Financial Accounts

### 1.1 Core concepts

- FinancialAccount
- Cashbox
- MainSafe
- BankAccount
- CardSettlementAccount
- WalletAccount
- CustomerAR account target
- SupplierAP account target
- PaymentMethod
- BranchPaymentMethod

### 1.2 Business rules

- A tenant can create multiple cashboxes.
- A tenant can create multiple bank accounts.
- A tenant can create multiple card/visa settlement accounts such as Master, Meeza, American Express, Fawry.
- A tenant can create multiple wallet accounts such as Vodafone Cash, Fawry, Orange Cash.
- A branch can enable or disable specific payment methods.
- A branch payment method must define the destination account.
- Cash payment routes to a Cashbox.
- Card/Visa payment routes to a CardSettlementAccount, not Cashbox.
- Wallet payment routes to WalletAccount.
- Credit payment routes to CustomerAR and requires customer_id.
- Payment methods must be branch-aware.
- Payment methods must be active/inactive.
- Card methods may have commission percentage, fixed fee, commission expense account, and settlement bank account.

### 1.3 Suggested model shape

#### FinancialAccount

- id
- tenant_id
- branch_id nullable
- code
- name
- account_type: cashbox, main_safe, bank, card_settlement, wallet, customer_ar, supplier_ap, expense, opening_balance, other
- currency
- opening_balance
- is_active
- created_at
- updated_at

#### PaymentMethod

- id
- tenant_id
- name
- method_type: cash, card, wallet, credit, custom
- provider_name nullable
- requires_customer
- is_active

#### BranchPaymentMethod

- id
- tenant_id
- branch_id
- payment_method_id
- destination_account_id
- settlement_bank_account_id nullable
- commission_percent
- fixed_fee
- commission_expense_account_id nullable
- is_default
- is_active

### 1.4 Required endpoints

- GET /api/finance/accounts/
- POST /api/finance/accounts/
- GET /api/finance/accounts/{id}/
- PATCH /api/finance/accounts/{id}/
- GET /api/finance/payment-methods/
- POST /api/finance/payment-methods/
- PATCH /api/finance/payment-methods/{id}/
- GET /api/branches/{branch_id}/payment-methods/
- POST /api/branches/{branch_id}/payment-methods/
- PATCH /api/branches/{branch_id}/payment-methods/{id}/

### 1.5 Acceptance criteria

- User can create cashbox, bank, card settlement, and wallet accounts dynamically.
- User can link payment methods to a branch.
- Payment routing never guesses the destination account.
- Payment routing always uses the branch payment method configuration.

---

## 2. Dynamic Unit Groups and Units

### 2.1 Core concepts

- UnitGroup
- Unit
- ProductUnit
- ProductBarcodeUnit

### 2.2 Business rules

- A tenant can create unit groups such as Weight, Volume, Count, Length, Custom.
- A tenant can create units such as gram, kilogram, ml, liter, piece, box, carton, bottle, cup, large, medium, small.
- Each UnitGroup has a base unit.
- Each Unit has a conversion factor to the base unit.
- Product has a base inventory unit.
- Product can have multiple sale/purchase units.
- ProductUnit defines how each sale/purchase unit converts to the product base unit.
- Quantities must support decimal values.
- The system must prevent invalid conversions between incompatible unit groups unless explicitly allowed by a custom product unit conversion.

### 2.3 Suggested model shape

#### UnitGroup

- id
- tenant_id
- name
- base_unit_id
- is_active

#### Unit

- id
- tenant_id
- unit_group_id
- name
- symbol
- factor_to_base
- allow_decimal
- is_active

#### ProductUnit

- id
- tenant_id
- product_id
- unit_id
- conversion_to_base
- is_base
- is_sale_unit
- is_purchase_unit
- is_recipe_unit
- is_active

#### ProductBarcodeUnit

- id
- tenant_id
- product_id
- product_unit_id
- barcode
- is_default

### 2.4 Required endpoints

- GET /api/catalog/unit-groups/
- POST /api/catalog/unit-groups/
- PATCH /api/catalog/unit-groups/{id}/
- GET /api/catalog/units/
- POST /api/catalog/units/
- PATCH /api/catalog/units/{id}/
- GET /api/products/{product_id}/units/
- POST /api/products/{product_id}/units/
- PATCH /api/products/{product_id}/units/{id}/
- POST /api/products/{product_id}/barcodes/

### 2.5 Acceptance criteria

- User can create new unit groups and units from the UI.
- User can link multiple units to one product.
- System can convert purchase, sale, inventory, and recipe quantities into the product base unit.
- Unit conversion is data-driven, not hard-coded.

---

## 3. Product Categories / Groups

### 3.1 Core concepts

- ProductCategory

### 3.2 Business rules

- A tenant can create categories such as Pizzas, Appetizers, Drinks, Desserts.
- Categories can be nested.
- Categories can appear on POS touch screen.
- Categories can have display order.
- Categories may define default kitchen/bar route.
- Products belong to categories.

### 3.3 Suggested model shape

#### ProductCategory

- id
- tenant_id
- parent_id nullable
- name
- code
- show_on_pos
- sort_order
- default_station: kitchen, bar, none
- is_active

### 3.4 Required endpoints

- GET /api/catalog/categories/
- POST /api/catalog/categories/
- PATCH /api/catalog/categories/{id}/
- POST /api/catalog/categories/{id}/products/

### 3.5 Acceptance criteria

- User can create groups like Pizzas, Appetizers, Drinks.
- User can assign products to categories.
- POS can filter products by category.
- Kitchen/bar routing can use product or category route.

---

## 4. Dynamic Branch Management

### 4.1 Core concepts

- Branch
- BranchSettings
- BranchWarehouse
- BranchPaymentMethod
- BranchTerminal
- BranchUserAssignment
- BranchDocumentSequence
- BranchDefaultAccounts

### 4.2 Business rules

- A tenant can create unlimited branches depending on plan limits.
- Each branch has code, name, branch type, address, phone, tax info, currency, timezone, and active status.
- Each branch can have its own warehouses.
- Each branch can have its own cashboxes and a default cashbox.
- Each branch can enable or disable payment methods.
- Each branch payment method must route to a configured destination account.
- Each branch can have POS terminals/devices.
- Users/cashiers can be assigned to one branch, multiple branches, or all branches.
- Each branch can have its own document numbering sequence if enabled.
- Every transactional document must store branch_id:
  - SalesInvoice
  - OpenOrder
  - KitchenTicket
  - Shift
  - PurchaseInvoice
  - CustomerReceipt
  - SupplierPayment
  - WarehouseTransfer
  - StockMovement
  - FinancialAccountMovement
- Reports must be filterable by branch.
- A branch cannot be deleted if it has posted documents or movements. It should be deactivated instead.

### 4.3 Suggested model shape

#### Branch

- id
- tenant_id
- code
- name
- branch_type: main, store, warehouse_only, delivery, kiosk, other
- address
- phone
- tax_number nullable
- currency
- timezone
- is_main
- is_active
- created_at
- updated_at

#### BranchSettings

- id
- tenant_id
- branch_id
- default_sales_warehouse_id nullable
- default_purchase_warehouse_id nullable
- default_cashbox_id nullable
- default_main_safe_id nullable
- default_price_tier_id nullable
- require_shift_for_pos
- allow_negative_stock
- allow_shift_close_with_open_orders
- receipt_header
- receipt_footer

#### BranchTerminal

- id
- tenant_id
- branch_id
- name
- code
- device_identifier nullable
- default_cashbox_id nullable
- is_active

#### BranchUserAssignment

- id
- tenant_id
- branch_id
- user_id
- role_at_branch
- is_default_branch
- is_active

### 4.4 Required endpoints

- GET /api/branches/
- POST /api/branches/
- GET /api/branches/{id}/
- PATCH /api/branches/{id}/
- POST /api/branches/{id}/deactivate/
- GET /api/branches/{id}/settings/
- PATCH /api/branches/{id}/settings/
- GET /api/branches/{id}/warehouses/
- POST /api/branches/{id}/warehouses/
- GET /api/branches/{id}/payment-methods/
- POST /api/branches/{id}/payment-methods/
- GET /api/branches/{id}/terminals/
- POST /api/branches/{id}/terminals/
- GET /api/branches/{id}/users/
- POST /api/branches/{id}/users/
- GET /api/branches/{id}/document-sequences/
- POST /api/branches/{id}/document-sequences/

### 4.5 Acceptance criteria

- Customer can create branches dynamically from UI/API.
- Customer can configure each branch independently.
- Branch can have its own warehouses, cashboxes, payment methods, terminals, users, and document sequences.
- All transactional documents store branch_id.
- Reports can be filtered by branch.
- Branch delete is blocked if posted documents exist; deactivate instead.

---

## 5. Dynamic Warehouses / Stores

### 4.1 Core concepts

- Warehouse
- BranchWarehouse
- WarehouseLocation optional
- DefaultWarehouse per branch
- WarehouseTransfer
- StockMovement per warehouse

### 4.2 Business rules

- A tenant can create multiple warehouses/stores.
- A warehouse can belong to a branch or be shared depending on tenant settings.
- A branch can have a default sales warehouse and default purchase receiving warehouse.
- Products can be available in one or more warehouses.
- Inventory quantities must be tracked per product + product unit/base unit + warehouse.
- Stock transfers between warehouses must create movement records.
- Sales, purchases, returns, wastage, recipe consumption, and adjustments must all affect the correct warehouse.
- Warehouses must be active/inactive and tenant-scoped.

### 4.3 Suggested model shape

#### Warehouse

- id
- tenant_id
- branch_id nullable
- code
- name
- warehouse_type: main, branch, kitchen, bar, damaged, virtual, other
- is_default_sales
- is_default_purchase
- is_active

#### BranchWarehouse

- id
- tenant_id
- branch_id
- warehouse_id
- role: sales, purchase_receiving, kitchen, bar, returns, damaged
- is_default
- is_active

#### WarehouseTransfer

- id
- tenant_id
- from_warehouse_id
- to_warehouse_id
- status
- created_by
- approved_by nullable
- created_at

### 4.4 Required endpoints

- GET /api/inventory/warehouses/
- POST /api/inventory/warehouses/
- PATCH /api/inventory/warehouses/{id}/
- GET /api/branches/{branch_id}/warehouses/
- POST /api/branches/{branch_id}/warehouses/
- PATCH /api/branches/{branch_id}/warehouses/{id}/
- POST /api/inventory/warehouse-transfers/
- GET /api/inventory/warehouse-transfers/{id}/
- POST /api/inventory/warehouse-transfers/{id}/post/

### 4.5 Acceptance criteria

- User can create and manage warehouses dynamically.
- User can link warehouses to branches.
- Every inventory movement is warehouse-aware.
- No stock quantity is stored as a single global product number without warehouse context.

---

## 6. Universal Movement / Statement Contracts

### 6.1 Core concepts

- FinancialAccountMovement
- StockMovement
- CustomerARMovement
- SupplierAPMovement
- ShiftMovementSummary
- UserActivityLog
- CashierActivityLog
- AuditLog
- AccessLog
- OperationsLog

### 6.2 Business rules

- Every posted business document must create movement records.
- Reports and statements must read from movement records, not from UI state.
- Customer profile must show full customer statement.
- Supplier profile must show full supplier statement.
- Cashbox/bank/card/wallet account detail must show full movement statement.
- Warehouse/product detail must show full stock movement statement.
- Cashier/user profile must show actions, sales handled, voids, approvals, shift activity, and sensitive actions where authorized.
- Movements must include actor/user, branch, terminal, shift, source document, timestamp, debit/credit or in/out, and running balance where applicable.

### 6.3 Required movement field shapes

#### FinancialAccountMovement

- id
- tenant_id
- branch_id
- account_id
- source_document_type
- source_document_id
- movement_type
- debit
- credit
- balance_after
- currency
- actor_user_id
- terminal_id nullable
- shift_id nullable
- occurred_at
- notes

#### StockMovement

- id
- tenant_id
- branch_id
- warehouse_id
- product_id
- product_unit_id
- base_unit_id
- quantity_in
- quantity_out
- balance_after
- movement_type
- source_document_type
- source_document_id
- actor_user_id
- occurred_at
- notes

#### CustomerARMovement

- id
- tenant_id
- branch_id
- customer_id
- source_document_type
- source_document_id
- debit
- credit
- balance_after
- actor_user_id
- occurred_at
- notes

#### SupplierAPMovement

- id
- tenant_id
- branch_id
- supplier_id
- source_document_type
- source_document_id
- debit
- credit
- balance_after
- actor_user_id
- occurred_at
- notes

#### UserActivityLog

- id
- tenant_id
- branch_id nullable
- user_id
- actor_user_id
- action
- target_type
- target_id
- terminal_id nullable
- shift_id nullable
- ip_address nullable
- occurred_at
- metadata

### 6.4 Required endpoints

- GET /api/finance/accounts/{id}/movements/
- GET /api/customers/{id}/statement/
- GET /api/suppliers/{id}/statement/
- GET /api/inventory/products/{id}/movements/
- GET /api/inventory/warehouses/{id}/movements/
- GET /api/pos/shifts/{id}/movements/
- GET /api/users/{id}/activity/
- GET /api/logs/audit/
- GET /api/logs/access/
- GET /api/logs/operations/

### 6.5 Acceptance criteria

- User can open any customer and see all sales, payments, credit, returns, and balance.
- User can open any supplier and see purchases, payments, returns, advances, and balance.
- User can open any cashbox/bank/card/wallet and see all movements.
- User can open any cashier/user and see actions and shift-related movement.
- User can open any product/warehouse and see stock in/out movements.

---

## 7. Dynamic Document Numbering

### 6.1 Core concepts

- DocumentSequence
- BranchDocumentSequence

### 6.2 Business rules

- A tenant can configure prefixes and numbering per document type.
- A branch can have a separate sequence if needed.
- Supported document types include:
  - SalesInvoice
  - OpenOrder
  - KitchenTicket
  - PurchaseInvoice
  - PurchaseReturn
  - CustomerReceipt
  - SupplierPayment
  - WarehouseTransfer
  - WastageDocument
  - CashDrop
  - Shift
- Generated document numbers must be unique per tenant/document type/branch rule.

### 6.3 Required endpoints

- GET /api/settings/document-sequences/
- POST /api/settings/document-sequences/
- PATCH /api/settings/document-sequences/{id}/

---

## 8. Dynamic Lookup / Custom Settings Foundation

### 7.1 Core concepts

- TenantSetting
- LookupType
- LookupValue
- CustomFieldDefinition optional
- CustomFieldValue optional

### 7.2 Business rules

- A tenant can add lookup values such as cancellation reasons, wastage reasons, customer groups, supplier types, table sections, payment labels, and similar operational values.
- A tenant can activate/deactivate values.
- Custom fields are allowed only through a controlled metadata model, not by changing database schema per tenant.
- The system must not create unsafe dynamic database columns.

### 7.3 Required endpoints

- GET /api/settings/lookups/
- POST /api/settings/lookups/
- PATCH /api/settings/lookups/{id}/
- GET /api/settings/custom-fields/
- POST /api/settings/custom-fields/
- PATCH /api/settings/custom-fields/{id}/

---

## 9. Price Tiers and Customer Price Segments

### 4.1 Core concepts

- PriceTier
- Customer
- ProductUnitTierPrice

### 4.2 Business rules

- A tenant can create price tiers such as Retail, Wholesale, Half Wholesale, VIP Customer, Employee Price.
- A customer can be assigned to a default price tier.
- Product prices must support multiple tiers per product unit.
- POS should resolve sale price by customer price tier and selected product unit.
- ProductUnitTierPrice stores sale price only.
- Purchase price must not be stored in ProductUnitTierPrice.

### 8.3 Suggested model shape

#### PriceTier

- id
- tenant_id
- name
- code
- priority
- is_default
- is_active

#### Customer

- id
- tenant_id
- name
- phone
- price_tier_id nullable
- credit_limit
- is_active

#### ProductUnitTierPrice

- id
- tenant_id
- product_id
- product_unit_id
- price_tier_id
- sale_price
- currency
- effective_from nullable
- effective_to nullable
- is_active

### 8.4 Required endpoints

- GET /api/catalog/price-tiers/
- POST /api/catalog/price-tiers/
- PATCH /api/catalog/price-tiers/{id}/
- GET /api/customers/
- POST /api/customers/
- PATCH /api/customers/{id}/
- GET /api/products/{product_id}/tier-prices/
- POST /api/products/{product_id}/tier-prices/
- PATCH /api/products/{product_id}/tier-prices/{id}/

### 8.5 Acceptance criteria

- User can create price tiers dynamically.
- User can assign customer to a price tier.
- Product can have different prices per unit and per tier.
- POS resolves correct price based on customer and unit.
- ProductUnitTierPrice never stores purchase price.

---

## 10. Customer, Supplier, and AR/AP Basics

### 9.1 Core concepts

- Customer
- CustomerGroup
- CustomerARMovement
- CustomerReceipt
- CustomerAdvance
- Supplier
- SupplierGroup
- SupplierAPMovement
- SupplierPayment
- SupplierAdvance

### 9.2 Business rules

- Customer records can have a customer_group_id, price_tier_id, credit_limit, opening_balance, and active status.
- Supplier records can be grouped and support AP movements, payments, advances, and balance tracking.
- Customer and supplier statements must be derived from movement records.

### 9.3 Suggested model shape

#### Customer

- id
- tenant_id
- name
- phone
- customer_group_id nullable
- price_tier_id nullable
- credit_limit
- opening_balance
- is_active

#### CustomerGroup

- id
- tenant_id
- name
- is_active

#### Supplier

- id
- tenant_id
- name
- supplier_group_id nullable
- phone
- opening_balance
- is_active

#### SupplierGroup

- id
- tenant_id
- name
- is_active

### 9.4 Required endpoints

- GET /api/customers/
- POST /api/customers/
- PATCH /api/customers/{id}/
- GET /api/suppliers/
- POST /api/suppliers/
- PATCH /api/suppliers/{id}/
- GET /api/suppliers/{id}/statement/

---

## 11. Product Master Update

### 5.1 Product creation and update requirements

Product creation/update should support:

- category_id
- product_type: stock_item, recipe_product, ingredient_item, service, non_stock, bundle_combo, fixed_asset_purchase_only
- base_inventory_unit_id
- default_sale_unit_id
- default_purchase_unit_id
- default_price_tier_id optional
- stock_tracking_enabled
- recipe_enabled
- show_on_pos
- default_station: kitchen, bar, none
- branch/warehouse availability if needed

### 5.2 Acceptance criteria

- Product creation supports category, unit, price tier, routing, and POS visibility configuration.
- Product pricing and unit behavior are driven by data records instead of code.

---

## 12. Service Layer Planning

To avoid overly large models/views modules, implementation planning should include dedicated service modules such as:

- [superpos_backend/pos/services/open_orders.py](superpos_backend/pos/services/open_orders.py)
- [superpos_backend/pos/services/kitchen.py](superpos_backend/pos/services/kitchen.py)
- [superpos_backend/pos/services/payment_routing.py](superpos_backend/pos/services/payment_routing.py)
- [superpos_backend/pos/services/idempotency.py](superpos_backend/pos/services/idempotency.py)
- [superpos_backend/pos/services/shifts.py](superpos_backend/pos/services/shifts.py)
- [superpos_backend/pos/services/posting.py](superpos_backend/pos/services/posting.py)
- [superpos_backend/inventory/services/stock_movements.py](superpos_backend/inventory/services/stock_movements.py)
- [superpos_backend/finance/services/account_movements.py](superpos_backend/finance/services/account_movements.py)
- [superpos_backend/catalog/services/price_resolution.py](superpos_backend/catalog/services/price_resolution.py)
- [superpos_backend/catalog/services/unit_conversion.py](superpos_backend/catalog/services/unit_conversion.py)

---

## 13. Implementation Notes

- These foundation concepts must be tenant-defined and editable from the UI.
- They should not be hard-coded in backend or frontend logic.
- Table Service implementation should depend on them for:
  - product price resolution
  - product unit selection
  - category routing
  - branch-aware payment routing
