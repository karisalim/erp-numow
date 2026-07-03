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
  qty: string;
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
