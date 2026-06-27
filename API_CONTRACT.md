# API Contract — Table Service / Open Orders MVP Core

## Purpose

This document defines the first implementation contract for the MVP Core feature slice: table service and open orders.

This is a planning-only contract. It does not implement backend or frontend behavior yet.

---

## 1. Scope and Principles

### Core product intent

- An OpenOrder is a draft, mutable, table-bound order.
- An OpenOrder is not a SalesInvoice.
- An OpenOrder is not a credit sale.
- A final payment converts one OpenOrder into one final SalesInvoice.

### Core business rules

- Add Item creates a Draft / Unsent OpenOrderLine.
- Send to Kitchen / Bar sends only unsent lines.
- Pay is blocked if any Draft / Unsent lines still exist.
- Request Bill changes table/order status to Needs Bill but does not create SalesInvoice.
- Cash routes to Cashbox.
- Card/Visa routes to Card Settlement.
- Wallet routes to Wallet Account.
- Credit routes to Customer AR.
- Sent line cancellation requires manager approval.
- Prepared removed item routes to Wastage / Complimentary / Inventory Loss.
- Shift close is blocked if open tables exist unless the tenant setting allows it.
- Critical POST endpoints must support idempotency keys.

### Master Data & Configuration Foundation

The Table Service MVP depends on tenant-defined master data and configuration, not hard-coded enums.

The detailed contract for these entities is in [MASTER_DATA_CONTRACT.md](MASTER_DATA_CONTRACT.md).

Required foundation concepts:

- FinancialAccount, Cashbox, MainSafe, BankAccount, CardSettlementAccount, WalletAccount, CustomerAR, SupplierAP
- PaymentMethod and BranchPaymentMethod
- UnitGroup, Unit, ProductUnit, ProductBarcodeUnit
- ProductCategory
- PriceTier, Customer, ProductUnitTierPrice
- Product master update fields for unit, category, pricing, routing, and POS visibility

Required behavior:

- Payment routing must always use BranchPaymentMethod configuration, never guessed by code.
- Product line pricing must be resolved server-side using ProductUnitTierPrice and customer price tier.
- Product and pricing configuration must be branch/tenant-aware and editable from the UI.

---

## 2. Common Conventions

### Authentication

- All endpoints require a valid authenticated session.
- The authenticated user must belong to a tenant.

### Idempotency

The following POST endpoints must accept an `Idempotency-Key` header:

- POST /api/pos/tables/{table_id}/open/
- POST /api/pos/tables/{table_id}/clear/
- POST /api/pos/open-orders/{id}/lines/
- POST /api/pos/open-orders/{id}/send-to-kitchen/
- POST /api/pos/open-orders/{id}/request-bill/
- POST /api/pos/open-orders/{id}/pay/
- POST /api/pos/open-orders/{id}/lines/{line_id}/void/
- POST /api/pos/shifts/open/
- POST /api/pos/shifts/{id}/close/
- POST /api/pos/kitchen-tickets/{id}/retry-print/

### Idempotency behavior

- The backend stores the idempotency key, request hash, endpoint, tenant, actor, response snapshot, and status.
- Repeating the same request with the same key and same payload returns the original response.
- Reusing the same key with a different payload returns a 409 conflict.

### Common response envelope

Success responses may return a resource object directly or a JSON object containing a `data` field.

Example:

```json
{
  "data": {
    "id": 101,
    "status": "open"
  }
}
```

---

## 3. Endpoint Contracts

### 3.1 GET /api/pos/tables/

Get the list of tables for the current tenant and branch context.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": [
    {
      "id": 1,
      "name": "T01",
      "section_id": 10,
      "section_name": "Floor A",
      "status": "available",
      "open_order_id": null,
      "guest_count": 0,
      "current_order_summary": null
    },
    {
      "id": 2,
      "name": "T02",
      "section_id": 10,
      "section_name": "Floor A",
      "status": "occupied",
      "open_order_id": 501,
      "guest_count": 4,
      "current_order_summary": {
        "item_count": 3,
        "subtotal": "45.00",
        "status": "draft"
      }
    }
  ]
}
```

#### Validation rules

- The caller must be authorized for the tenant.

#### Business rules

- A table may be available, occupied, sent_to_kitchen, needs_bill, paid_clearing, or out_of_service.

---

### 3.2 POST /api/pos/tables/{table_id}/open/

Open a table and create a new OpenOrder.

#### Request

```json
{
  "guest_count": 4,
  "notes": "Window seat"
}
```

#### Success response

Status: `201 Created`

```json
{
  "data": {
    "id": 501,
    "table_id": 2,
    "table_name": "T02",
    "status": "draft",
    "guest_count": 4,
    "notes": "Window seat",
    "item_count": 0,
    "subtotal": "0.00",
    "created_at": "2026-06-27T10:00:00Z"
  }
}
```

#### Validation rules

- `table_id` must exist and belong to the tenant.
- `guest_count` must be an integer greater than 0.
- `notes` must be a string if provided.
- An `Idempotency-Key` header must be present for the request to be accepted.

#### Business rules

- A table that is already occupied cannot be opened again.
- Creating the order creates an OpenOrder in a draft state.

#### Error responses

- `400 Bad Request` for invalid payload
- `409 Conflict` for idempotency reuse with a different payload
- `409 Conflict` for already-open table
- `404 Not Found` for unknown table

---

### 3.3 GET /api/pos/open-orders/{id}/

Retrieve the current state of an OpenOrder.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 501,
    "table_id": 2,
    "table_name": "T02",
    "status": "draft",
    "guest_count": 4,
    "notes": "Window seat",
    "item_count": 3,
    "subtotal": "45.00",
    "lines": [
      {
        "id": 701,
        "product_id": 12,
        "product_name": "Cappuccino",
        "quantity": "2.00",
        "unit_price": "15.00",
        "line_total": "30.00",
        "status": "draft",
        "sent_to_kitchen": false,
        "notes": ""
      },
      {
        "id": 702,
        "product_id": 15,
        "product_name": "Sandwich",
        "quantity": "1.00",
        "unit_price": "15.00",
        "line_total": "15.00",
        "status": "draft",
        "sent_to_kitchen": false,
        "notes": ""
      }
    ],
    "created_at": "2026-06-27T10:00:00Z"
  }
}
```

#### Validation rules

- `id` must exist and belong to the tenant.

#### Business rules

- The response must expose draft and sent line state clearly.
- The order must not be treated as a final invoice.

---

### 3.4 POST /api/pos/open-orders/{id}/lines/

Add a line to an OpenOrder.

#### Request

```json
{
  "product_id": 12,
  "product_unit_id": 25,
  "quantity": "2.00",
  "notes": "",
  "customer_id": null
}
```

#### Success response

Status: `201 Created`

```json
{
  "data": {
    "id": 701,
    "open_order_id": 501,
    "product_id": 12,
    "product_name": "Cappuccino",
    "quantity": "2.00",
    "unit_price": "15.00",
    "line_total": "30.00",
    "status": "draft",
    "sent_to_kitchen": false,
    "notes": "",
    "created_at": "2026-06-27T10:05:00Z"
  }
}
```

#### Validation rules

- `product_id` must exist and be active.
- `product_unit_id` must reference a valid product unit for the product.
- `quantity` must be a positive decimal string value.
- `notes` must be a string if present.
- `customer_id` must be valid if provided.
- An `Idempotency-Key` header must be present.

#### Business rules

- New lines are created as Draft / Unsent.
- The server resolves the sale price using ProductUnitTierPrice and the customer price tier when applicable.
- The order subtotal updates after the line is added.

#### Error responses

- `400 Bad Request` for invalid payload
- `404 Not Found` for missing order or product
- `409 Conflict` for idempotency reuse with a different payload

---

### 3.5 PATCH /api/pos/open-orders/{id}/lines/{line_id}/

Update an existing OpenOrderLine.

#### Request

```json
{
  "quantity": "3.00",
  "notes": "extra shot"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 701,
    "open_order_id": 501,
    "product_id": 12,
    "product_name": "Cappuccino",
    "quantity": "3.00",
    "unit_price": "15.00",
    "line_total": "45.00",
    "status": "draft",
    "sent_to_kitchen": false,
    "notes": "extra shot"
  }
}
```

#### Validation rules

- `quantity` must be a positive decimal string if present.
- `notes` must be a string if present.
- The line must belong to the target order.

#### Business rules

- Updating a line does not make it final or sent.
- Once sent, update restrictions should be limited to approved exceptions.

---

### 3.6 POST /api/pos/open-orders/{id}/send-to-kitchen/

Send only unsent lines to kitchen or bar.

#### Request

```json
{
  "line_ids": [701, 702],
  "destination": "kitchen"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "open_order_id": 501,
    "sent_line_ids": [701, 702],
    "kitchen_ticket_id": 9001,
    "status": "sent",
    "message": "Unsent lines sent to kitchen"
  }
}
```

#### Validation rules

- `line_ids` must be a non-empty array.
- `destination` must be one of `kitchen` or `bar`.
- Each line must belong to the order.
- An `Idempotency-Key` header must be present.

#### Business rules

- Only unsent lines are sent.
- Sent lines become `sent` / `prepared_pending` state depending on downstream workflow.
- Draft lines remain unchanged.

#### Error responses

- `400 Bad Request` if no valid unsent lines are provided
- `409 Conflict` for idempotency reuse with a different payload

---

### 3.7 POST /api/pos/open-orders/{id}/request-bill/

Request the bill for an OpenOrder without creating a SalesInvoice.

#### Request

```json
{
  "notes": "Guest requested bill"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "open_order_id": 501,
    "table_id": 2,
    "status": "needs_bill",
    "message": "Bill requested"
  }
}
```

#### Validation rules

- `notes` must be a string if present.
- An `Idempotency-Key` header must be present.

#### Business rules

- Request Bill is blocked if Draft / Unsent lines still exist.
- The order status changes to `needs_bill`.
- The table status changes to `needs_bill`.
- No SalesInvoice is created.
- No revenue, tax, payment, or stock movements are posted.

---

### 3.8 POST /api/pos/open-orders/{id}/pay/

Finalize an OpenOrder into a SalesInvoice and record payment routing.

#### Request

```json
{
  "payments": [
    {
      "branch_payment_method_id": 44,
      "amount": "100.00"
    },
    {
      "branch_payment_method_id": 45,
      "amount": "50.00"
    }
  ],
  "customer_id": null,
  "tip": "0.00",
  "notes": ""
}
```

#### Success response

Status: `201 Created`

```json
{
  "data": {
    "sales_invoice_id": 8001,
    "invoice_number": "INV-20260627-0001",
    "open_order_id": 501,
    "table_id": 2,
    "posting_status": "posted",
    "payment_status": "paid",
    "return_status": "none",
    "approval_status": "approved",
    "sync_status": "synced",
    "payment_lines": [
      {
        "payment_line_id": 1,
        "branch_payment_method_id": 44,
        "method_type": "cash",
        "amount": "100.00",
        "destination_account_id": 12,
        "destination_account_name": "Main Cashbox"
      },
      {
        "payment_line_id": 2,
        "branch_payment_method_id": 45,
        "method_type": "card",
        "amount": "50.00",
        "destination_account_id": 18,
        "destination_account_name": "Meeza Settlement"
      }
    ],
    "payment_routes": [
      "cashbox",
      "card_settlement"
    ],
    "receipt_id": 9201,
    "table_status_after_payment": "paid_clearing",
    "message": "OpenOrder converted to SalesInvoice"
  }
}
```

#### Validation rules

- Each payment line must use an active BranchPaymentMethod.
- Each payment amount must be a positive decimal string.
- `tip` must be zero or greater and expressed as a decimal string.
- `customer_id` is required when any selected payment method is credit-based.
- An `Idempotency-Key` header must be present.
- The order must not contain any Draft / Unsent lines.

#### Business rules

- Pay is blocked if any Draft / Unsent line exists.
- One OpenOrder converts into one final SalesInvoice.
- Routing uses each selected branch payment method's destination account and related settlement configuration.
- Mixed payment creates multiple PaymentLine records.
- The total payments must equal the invoice total unless credit handles the remaining balance explicitly.
- Cash routes to Cashbox via the configured account.
- Card/Visa routes to Card Settlement via the configured account.
- Wallet routes to Wallet Account via the configured account.
- Credit routes to Customer AR and requires `customer_id`.

#### Error responses

- `400 Bad Request` if the order still has unsent lines
- `404 Not Found` if the order is missing
- `409 Conflict` for idempotency reuse with a different payload

---

### 3.9 POST /api/pos/open-orders/{id}/lines/{line_id}/void/

Void a line from an OpenOrder.

#### Request

```json
{
  "reason": "sent_item_cancelled",
  "removal_action": "wastage",
  "manager_pin": "1234",
  "manager_approval_token": null,
  "manager_credentials": null,
  "notes": "Customer changed mind"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "open_order_id": 501,
    "line_id": 701,
    "status": "voided",
    "removal_action": "wastage",
    "requires_manager_approval": true,
    "message": "Line voided and routed"
  }
}
```

#### Validation rules

- `reason` must be provided.
- If the line was already sent, the backend must validate manager approval and derive the approver from the authenticated manager identity.
- `removal_action` must be one of `wastage`, `complimentary`, or `inventory_loss`.
- An `Idempotency-Key` header must be present.

#### Business rules

- Sent line cancellation requires manager approval.
- Removed items route to the configured downstream handling path.

---

### 3.10 POST /api/pos/shifts/open/

Open a new shift.

#### Request

```json
{
  "opening_cash": "1000.00",
  "notes": "Start of day"
}
```

#### Success response

Status: `201 Created`

```json
{
  "data": {
    "id": 1001,
    "status": "open",
    "opening_cash": "1000.00",
    "notes": "Start of day",
    "opened_at": "2026-06-27T10:00:00Z",
    "opened_by": 5
  }
}
```

#### Validation rules

- `opening_cash` must be a decimal string.
- An `Idempotency-Key` header must be present.

#### Business rules

- There must not already be an active shift for the same terminal or user context.

---

### 3.11 POST /api/pos/shifts/{id}/close/

Close an active shift.

#### Request

```json
{
  "closing_cash": "1100.00",
  "notes": "End of day"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 1001,
    "status": "closed",
    "opening_cash": "1000.00",
    "closing_cash": "1100.00",
    "notes": "End of day",
    "closed_at": "2026-06-27T22:00:00Z"
  }
}
```

#### Validation rules

- `closing_cash` must be a decimal string.
- An `Idempotency-Key` header must be present.

#### Business rules

- Shift close is blocked if open tables exist unless the tenant setting allows it.
- The shift cannot be closed twice.

#### Error responses

- `400 Bad Request` if the close is blocked by open tables or invalid totals
- `409 Conflict` for idempotency reuse with a different payload

---

### 3.12 GET /api/pos/shifts/current/

Get the currently active shift for the current terminal or user context.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 1001,
    "status": "open",
    "opening_cash": "1000.00",
    "opened_at": "2026-06-27T10:00:00Z"
  }
}
```

#### Validation rules

- The response may return `null` if no shift is currently open.

---

### 3.13 GET /api/pos/kitchen-tickets/

List kitchen and bar tickets for the current branch context.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": [
    {
      "id": 9001,
      "open_order_id": 501,
      "table_id": 2,
      "status": "queued",
      "destination": "kitchen",
      "line_count": 2,
      "created_at": "2026-06-27T10:10:00Z"
    }
  ]
}
```

#### Validation rules

- The caller must be authorized for the tenant and branch context.

#### Business rules

- This is basic MVP ticket tracking, not full KDS Phase 2.

---

### 3.14 GET /api/pos/kitchen-tickets/{id}/

Retrieve a kitchen or bar ticket.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 9001,
    "open_order_id": 501,
    "table_id": 2,
    "status": "printed",
    "destination": "kitchen",
    "lines": [
      {
        "line_id": 701,
        "product_name": "Cappuccino",
        "quantity": "2.00"
      }
    ],
    "created_at": "2026-06-27T10:10:00Z"
  }
}
```

#### Validation rules

- The ticket must exist and belong to the tenant.

---

### 3.15 PATCH /api/pos/kitchen-tickets/{id}/status/

Update a kitchen or bar ticket status.

#### Request

```json
{
  "status": "ready",
  "notes": "Beverage ready for service"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 9001,
    "status": "ready",
    "updated_at": "2026-06-27T10:12:00Z"
  }
}
```

#### Validation rules

- `status` must be one of `queued`, `printed`, `print_failed`, `preparing`, `ready`, `served`, or `voided`.
- The update must log the actor/user and timestamp.

#### Business rules

- Status changes are audit-tracked and visible to downstream staff views.

---

### 3.16 POST /api/pos/kitchen-tickets/{id}/retry-print/

Retry printing a kitchen or bar ticket.

#### Request

No body.

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "id": 9001,
    "status": "queued",
    "message": "Print re-queued"
  }
}
```

#### Validation rules

- The ticket must exist and belong to the tenant.
- An `Idempotency-Key` header must be present.

#### Business rules

- Retry-print must not create a duplicate ticket; it re-queues the existing print job.

---

### 3.17 POST /api/pos/tables/{table_id}/clear/

Clear a table after payment, cancellation, or explicit reset.

#### Request

```json
{
  "reason": "payment_completed",
  "notes": "Table reset after settlement"
}
```

#### Success response

Status: `200 OK`

```json
{
  "data": {
    "table_id": 2,
    "status": "available",
    "open_order_id": null,
    "message": "Table cleared"
  }
}
```

#### Validation rules

- `reason` must be provided and be a supported clear action.
- `notes` must be a string if present.
- An `Idempotency-Key` header must be present.

#### Business rules

- In MVP, clear is allowed only when the table status is `paid_clearing`.
- Clear sets the table status to `available`.
- Clear must not modify the already-created SalesInvoice.
- Clear must create an audit log entry.
- Cancellation/reset should be separate manager-approved flows, not the default clear action.

---

## 4. Shared Validation Rules

- All IDs must reference resources within the caller's tenant.
- Every transactional request must resolve branch context either from the authenticated terminal/session or explicit branch_id where allowed.
- Every transactional document and movement must store branch_id.
- Users can only access branches allowed by BranchUserAssignment or global permission.
- All numeric monetary values must be expressed as decimal strings.
- All quantities must be expressed as decimal strings.
- All timestamps should be ISO-8601 strings.
- All POST requests should return a stable resource representation.
- All error responses should include a machine-readable `code` and a human-readable `detail` where possible.

---

## 5. Shared Business Rules

- Open orders are mutable until payment conversion.
- Open orders can be closed by payment conversion or explicit cancellation rules.
- Table state must reflect the current order state.
- Sent lines are not editable in the same way as draft lines.
- Payment routing depends on method.
- Manager approval is required for some cancellation scenarios.
- Movement and posting records must be created after final payment conversion.

---

## 6. Suggested Response Error Shape

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "detail": "Order still contains unsent lines"
  }
}
```
