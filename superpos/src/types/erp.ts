/* ─────────────────────────────────────────────────────────────────────────────
 * ERP module types — mirror the committed backend OpenAPI schema
 * (/api/schema/). Decimals arrive as strings on the wire; keep them as
 * strings in state and convert only for display/math via utils/money.
 * ──────────────────────────────────────────────────────────────────────────── */

/** DRF PageNumberPagination envelope. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/* ── Parties ────────────────────────────────────────────────────────────── */

export interface Customer {
  id: number;
  tenant?: number;
  code: string;
  name: string;
  phone: string;
  email: string;
  tax_number: string;
  default_branch: number | null;
  price_tier_id: number | null;
  credit_limit: string;
  opening_balance: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CustomerPayload {
  code?: string;
  name: string;
  phone?: string;
  email?: string;
  tax_number?: string;
  default_branch?: number | null;
  credit_limit?: string;
  opening_balance?: string;
  is_active?: boolean;
}

export interface Supplier {
  id: number;
  tenant?: number;
  code: string;
  name: string;
  phone: string;
  email: string;
  tax_number: string;
  default_branch: number | null;
  opening_balance: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SupplierPayload {
  code?: string;
  name: string;
  phone?: string;
  email?: string;
  tax_number?: string;
  default_branch?: number | null;
  opening_balance?: string;
  is_active?: boolean;
}

/* ── Ledger movements & statements ──────────────────────────────────────── */

/** Shared shape of AR / AP / financial-account movement rows. */
export interface LedgerMovement {
  id: number;
  branch: number | null;
  source_document_type: string;
  source_document_id: number | null;
  movement_type: string;
  debit: string;
  credit: string;
  balance_before: string | null;
  balance_after: string;
  currency: string;
  actor_user: number | null;
  actor_user_username: string;
  occurred_at: string;
  notes: string;
  created_at: string;
}

export interface CustomerARMovement extends LedgerMovement {
  customer: number;
  customer_name: string;
}

export interface SupplierAPMovement extends LedgerMovement {
  supplier: number;
  supplier_name: string;
}

export interface FinancialAccountMovement extends LedgerMovement {
  account: number;
  account_name: string;
  account_type: string;
  terminal_id: number | null;
  shift_id: number | null;
}

/** Envelope returned by /statement/ and /movements/ summary endpoints. */
export interface StatementSummary<M extends LedgerMovement = LedgerMovement> {
  opening_balance: string;
  total_debit: string;
  total_credit: string;
  net_change: string;
  closing_balance: string;
  date_from: string | null;
  date_to: string | null;
  filters: Record<string, unknown>;
  movements: M[];
}

export interface PartyBalance {
  opening_balance: string;
  balance: string;
  customer_id?: number;
  customer_name?: string;
  supplier_id?: number;
  supplier_name?: string;
}

/* ── Finance ────────────────────────────────────────────────────────────── */

export type AccountType =
  | 'cashbox' | 'main_safe' | 'bank' | 'card_settlement' | 'wallet'
  | 'customer_ar' | 'supplier_ap' | 'expense' | 'opening_balance' | 'other';

export interface FinancialAccount {
  id: number;
  branch: number | null;
  code: string;
  name: string;
  account_type: AccountType;
  currency: string;
  opening_balance: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FinancialAccountPayload {
  branch?: number | null;
  code?: string;
  name: string;
  account_type: AccountType;
  currency?: string;
  opening_balance?: string;
  is_active?: boolean;
}

export interface AccountBalance {
  account_id: number;
  account_name: string;
  opening_balance: string;
  balance: string;
}

export type PaymentMethodType = 'cash' | 'card' | 'wallet' | 'credit' | 'custom';

export interface PaymentMethodRecord {
  id: number;
  name: string;
  method_type: PaymentMethodType;
  provider_name: string;
  requires_customer: boolean;
  is_active: boolean;
}

export interface PaymentMethodPayload {
  name: string;
  method_type: PaymentMethodType;
  provider_name?: string;
  requires_customer?: boolean;
  is_active?: boolean;
}

export interface BranchPaymentMethod {
  id: number;
  tenant: number;
  branch: number;
  payment_method: number;
  payment_method_name: string;
  payment_method_type: PaymentMethodType;
  destination_account: number;
  destination_account_name: string;
  destination_account_type: AccountType;
  settlement_bank_account: number | null;
  commission_percent: string;
  fixed_fee: string;
  commission_expense_account: number | null;
  is_default: boolean;
  is_active: boolean;
}

export interface BranchPaymentMethodPayload {
  payment_method: number;
  destination_account: number;
  settlement_bank_account?: number | null;
  commission_percent?: string;
  fixed_fee?: string;
  commission_expense_account?: number | null;
  is_default?: boolean;
  is_active?: boolean;
}

/**
 * v3.6 method→destination compatibility (mirrors backend
 * BranchPaymentMethodSerializer validation).
 */
export const COMPATIBLE_DESTINATIONS: Record<PaymentMethodType, AccountType[] | null> = {
  cash: ['cashbox', 'main_safe'],
  card: ['card_settlement'],
  wallet: ['wallet'],
  credit: ['customer_ar'],
  custom: null, // any destination
};

/* ── Settlements ────────────────────────────────────────────────────────── */

export interface CustomerReceipt {
  id: number;
  branch: number | null;
  customer: number;
  customer_name: string;
  payment_method: number;
  payment_method_name: string;
  payment_method_type: string;
  destination_account: number;
  destination_account_name: string;
  destination_account_type: string;
  amount: string;
  reference: string;
  notes: string;
  status: string;
  posted_at: string;
  actor_user: number | null;
  actor_user_username: string;
  created_at: string;
}

export interface CustomerReceiptPayload {
  branch?: number | null;
  customer: number;
  payment_method: number;
  destination_account: number;
  amount: string;
  reference?: string;
  notes?: string;
}

export interface SupplierPayment {
  id: number;
  branch: number | null;
  supplier: number;
  supplier_name: string;
  payment_method: number;
  payment_method_name: string;
  payment_method_type: string;
  source_account: number;
  source_account_name: string;
  source_account_type: string;
  amount: string;
  reference: string;
  notes: string;
  status: string;
  posted_at: string;
  actor_user: number | null;
  actor_user_username: string;
  created_at: string;
}

export interface SupplierPaymentPayload {
  branch?: number | null;
  supplier: number;
  payment_method: number;
  source_account: number;
  amount: string;
  reference?: string;
  notes?: string;
}

/* ── Purchases ──────────────────────────────────────────────────────────── */

export type PurchaseLineType = 'stock_item' | 'expense' | 'fixed_asset' | 'service' | 'non_stock';

export interface PurchaseInvoiceLine {
  id: number;
  product: number | null;
  product_name: string;
  warehouse: number | null;
  line_type: PurchaseLineType;
  qty: string;
  unit_cost: string;
  discount_amount: string;
  tax_amount: string;
  line_total: string;
  notes: string;
}

export interface PurchaseInvoice {
  id: number;
  branch: number;
  branch_name: string;
  supplier: number;
  supplier_name: string;
  reference: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total_amount: string;
  paid_amount: string;
  credit_amount: string;
  payment_method: number | null;
  source_account: number | null;
  posting_status: 'draft' | 'posted' | 'cancelled' | 'void';
  payment_status: 'unpaid' | 'partially_paid' | 'paid' | 'n_a';
  posted_at: string | null;
  actor_user: number | null;
  notes: string;
  lines: PurchaseInvoiceLine[];
  created_at: string;
  updated_at: string;
}

export interface PurchaseInvoiceLinePayload {
  product: number;
  warehouse?: number | null;
  line_type: 'stock_item';
  // Legacy base-unit shape — either this…
  qty?: string;
  // …or the unit-aware shape (Sprint 2 Batch 5a): server derives qty via
  // convert_to_base and enforces product_unit.minimum_order_qty.
  product_unit?: number;
  entered_qty?: string;
  unit_cost: string;
  discount_amount?: string;
  tax_amount?: string;
  notes?: string;
}

export interface PurchaseInvoicePayload {
  branch: number;
  supplier: number;
  reference?: string;
  paid_amount?: string;
  payment_method?: number | null;
  source_account?: number | null;
  notes?: string;
  lines: PurchaseInvoiceLinePayload[];
}

/* ── Warehouses & stock ─────────────────────────────────────────────────── */

export interface Warehouse {
  id: number;
  code: string;
  name: string;
  warehouse_type: string;
  warehouse_type_display: string;
  description: string;
  is_active: boolean;
}

export interface WarehouseStockRow {
  id: number;
  product: number;
  product_name: string;
  product_sku: string;
  warehouse: number;
  warehouse_name: string;
  warehouse_code: string;
  quantity: string;
  updated_at: string;
}

export interface BranchWarehouseLink {
  id: number;
  branch: number;
  warehouse: number;
  role: string;
  role_display: string;
  is_default: boolean;
  is_active: boolean;
}

/* ── Misc master data ───────────────────────────────────────────────────── */

export interface BranchLite {
  id: number;
  name: string;
}

/* ── Units (Sprint 2 Batch 1 + Phase 1.5) ───────────────────────────────── */

export interface UnitGroup {
  id: number;
  name: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UnitGroupPayload {
  name: string;
  is_active?: boolean;
}

export interface StandardUnitCode {
  code: string;
  label: string;
}

export interface Unit {
  id: number;
  unit_group: number;
  unit_group_name: string;
  name: string;
  symbol: string;
  /** Optional UN/CEFACT Rec 20 code — metadata only, never required. */
  standard_code: string;
  standard_code_display: string;
  factor_to_base: string;
  allow_decimal: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UnitPayload {
  unit_group: number;
  name: string;
  symbol?: string;
  standard_code?: string;
  factor_to_base?: string;
  allow_decimal?: boolean;
  is_active?: boolean;
}

/** Per-product unit conversion mapping (nested under /products/:id/units/). */
export interface ProductUnit {
  id: number;
  unit: number;
  unit_name: string;
  unit_symbol: string;
  allow_decimal: boolean;
  conversion_to_base: string;
  is_base: boolean;
  is_sale_unit: boolean;
  is_purchase_unit: boolean;
  is_recipe_unit: boolean;
  minimum_order_qty: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ProductUnitPayload {
  unit: number;
  conversion_to_base?: string;
  is_base?: boolean;
  is_sale_unit?: boolean;
  is_purchase_unit?: boolean;
  is_recipe_unit?: boolean;
  minimum_order_qty?: string | null;
  is_active?: boolean;
}

/** Per-pack barcode (nested under /products/:id/barcodes/). */
export interface ProductBarcodeUnit {
  id: number;
  product_unit: number;
  unit_name: string;
  conversion_to_base: string;
  barcode: string;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ProductBarcodeUnitPayload {
  product_unit: number;
  barcode: string;
  is_default?: boolean;
}

/* ── Price Tiers (Sprint 2 Batch 4 remainder) ───────────────────────────── */

export interface PriceTier {
  id: number;
  name: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PriceTierPayload {
  name: string;
  is_active?: boolean;
}

/** Price of one product-unit at one tier (nested under
 * /products/:id/units/:unitId/tier-prices/). */
export interface ProductUnitTierPrice {
  id: number;
  price_tier: number;
  price_tier_name: string;
  price: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ProductUnitTierPricePayload {
  price_tier: number;
  price: string;
  is_active?: boolean;
}

/* ── Category trees (Sprint 2 Batch 2) ──────────────────────────────────── */

export interface CategoryTreeNode {
  id: number;
  name: string;
  parent: number | null;
  parent_name: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CategoryTreeNodePayload {
  name: string;
  parent?: number | null;
  is_active?: boolean;
}

/* ── Product classification (Sprint 2 Batch 3) ──────────────────────────── */

export type ProductTypeValue =
  | 'stock_item' | 'ingredient' | 'prep_item' | 'recipe_product'
  | 'resale' | 'packaging' | 'service' | 'bundle' | 'fixed_asset';

export interface ProductTypeBehavior {
  can_sell: boolean;
  can_purchase: boolean;
  track_inventory: boolean;
  affects_stock: boolean;
  requires_cost: boolean;
  can_have_recipe: boolean;
}

/* ── Inventory costing (AVCO audit trail — read-only) ─────────────────────
 * Mirrors `InventoryCostMovement`/`InventoryCostMovementSerializer` on the
 * backend exactly: every field is server-computed, nothing here is ever
 * written from the frontend. */
export interface InventoryCostMovement {
  id: number;
  product: number;
  quantity_before: string | null;
  quantity_received: string | null;
  unit_cost_received: string | null;
  avg_cost_before: string;
  avg_cost_after: string;
  source_document_type: string;
  source_document_id: number | null;
  actor_user: number | null;
  note: string;
  occurred_at: string;
}

/* ── Dashboard summary (/api/dashboard/summary/) ──────────────────────────
 * `*_trend` keys are always present but currently hardcoded to 0.0 by the
 * backend for every KPI (no real trend math exists yet) — callers should
 * treat a present-but-zero trend as "no trend data", not "flat". */
export interface DashboardKPIs {
  revenue: number;
  transactions: number;
  avg_basket: number;
  items_sold: number;
  net_revenue: number;
  cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
  revenue_trend?: number;
  transactions_trend?: number;
  avg_basket_trend?: number;
  items_sold_trend?: number;
}

export interface DashboardTopProduct {
  name: string;
  units_sold: number;
  revenue: number;
  cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
}

export interface DashboardPaymentMethodSummary {
  label: string;
  count: number;
  total: number;
  pct: number;
}

export interface DashboardLowStockEntry {
  id: number;
  name: string;
  color: string;
  stock: number;
  reorder_point: number;
  unit: string;
}

export interface DashboardSummaryResponse {
  range: { start_date: string; end_date: string };
  kpis: DashboardKPIs;
  top_products: DashboardTopProduct[];
  payment_methods: Record<string, DashboardPaymentMethodSummary>;
  low_stock: DashboardLowStockEntry[];
  low_stock_count: number;
}
