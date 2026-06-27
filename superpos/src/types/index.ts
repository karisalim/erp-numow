export type BadgeKind = 'gray' | 'success' | 'danger' | 'warn' | 'info' | 'brand';
export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger' | 'success' | 'dark';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'xl';
export type PaymentMethod = 'cash' | 'card' | 'wallet';
export type UserRole = 'Owner' | 'Admin' | 'Manager' | 'Cashier';
export type CardStage = 'waiting' | 'processing' | 'success' | 'declined';

/**
 * Backend serializes status as lowercase ('completed' | 'voided' | 'refunded').
 * The legacy capitalized form is kept as an alias for components that still
 * consume mock data.
 */
export type TransactionStatus =
  | 'completed' | 'voided' | 'refunded'
  | 'Completed' | 'Voided' | 'Refunded';

export type ProductUnit = 'piece' | 'kg' | 'liter' | 'carton';

/* ─────────────────────────────────────────────────────────────────────────────
 * Product — matches Django ProductSerializer.
 *
 * Backend canonical fields are listed first. The trailing block (`tax`, etc.)
 * is kept as deprecated aliases until POS / Products pages are migrated.
 * ──────────────────────────────────────────────────────────────────────────── */
export interface Product {
  // Backend canonical
  id: number | string;
  tenant?: number | null;
  barcode: string;
  sku: string;
  name: string;
  category: number | string | null;       // FK id from backend; legacy: category name string
  category_name?: string;
  price: number;
  cost: number;
  tax_rate?: number;                      // backend: Decimal as fraction (e.g. 0.14 = 14%) — optional so legacy mock data still compiles
  stock: number;
  reorder: number;
  color: string;
  weighted?: boolean;
  unit?: ProductUnit;
  unit_display?: string;
  pack_qty?: number | string;
  plu?: string;
  active?: boolean;
  margin?: number;
  created_at?: string;
  updated_at?: string;

  // ── Legacy aliases — TODO: remove once POS/Products pages are migrated ──
  /** @deprecated use `tax_rate` */
  tax?: number;
}

export interface CartItem extends Product {
  lineId: string;
  qty: number;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Sale — list/detail responses from Django SaleSerializer.
 *
 * Renamed from `Transaction` in spirit (kept as a type alias) so the
 * existing SalesPage that references `Transaction` keeps compiling.
 * ──────────────────────────────────────────────────────────────────────────── */
export interface Sale {
  // Backend canonical
  id: number | string;
  sale_uuid?: string;                     // preferred public identifier
  tenant?: number | null;
  cashier: number | string | null;        // FK id; legacy: string display name
  cashier_name?: string;
  branch?: number | null;
  branch_name?: string;
  terminal?: number | null;
  terminal_name?: string;
  subtotal?: number;
  tax_amount?: number;
  total: number;
  method: PaymentMethod;
  paid?: number;
  change?: number;
  status: TransactionStatus;
  offline?: boolean;
  created_at?: string;
  item_count?: number;

  // ── Legacy aliases — TODO: remove during sales-page migration ──
  /** @deprecated use `created_at` */
  ts?: string;
  /** @deprecated use `item_count` */
  items?: number;
}

/** Legacy alias kept for existing Sales/Dashboard pages. */
export type Transaction = Sale;

export interface SaleItem {
  id?: number;
  product: number | null;
  product_name: string;
  barcode?: string;
  qty: number;
  price_each: number;
  line_total: number;
}

export interface CompletedTransaction {
  id: string;
  sale_uuid?: string;
  items: CartItem[];
  subtotal: number;
  tax: number;                            // legacy field used by ReceiptPage; backend = tax_amount
  tax_amount?: number;
  total: number;
  method: PaymentMethod;
  paid: number;
  change: number;
  ts: Date;
  cashier: string;
  terminal: string;
  offline: boolean;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Users — admin-page representation.
 * ──────────────────────────────────────────────────────────────────────────── */
export interface AppUser {
  // Backend canonical
  id: number | string;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  role: UserRole;
  is_active: boolean;
  tenant?: number | null;
  tenant_name?: string;
  branch?: number | null;
  branch_name?: string;
  terminal?: number | null;
  terminal_name?: string;
  last_login?: string | null;

  // ── Legacy aliases for the existing Users page ──
  /** @deprecated use `full_name` */
  name?: string;
  /** @deprecated use `last_login` */
  last?: string;
  /** @deprecated use `is_active` */
  active?: boolean;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * AuthUser — the user object stored in the Zustand auth store after login.
 * Mirrors UserSerializer but adds two UI-derived fields (`name`, `initials`)
 * computed by the auth store on hydration.
 * ──────────────────────────────────────────────────────────────────────────── */
export interface AuthUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  tenant: number | null;
  tenant_name: string;
  tenant_phone?: string;
  tenant_address?: string;
  tenant_logo?: string;
  tenant_vat_number?: string;
  tenant_receipt_footer?: string;
  tenant_currency?: string;
  tenant_language?: string;
  tenant_show_tax_on_receipt?: boolean;
  tenant_scale_barcode_prefix?: string;
  branch: number | null;
  branch_name: string;
  terminal: number | null;
  terminal_name: string;

  // Derived for UI components (computed in authStore)
  name: string;       // = full_name || username
  initials: string;   // 1–2 letters from full_name or username
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Dashboard view-model types — purely client-side (not from the API).
 * ──────────────────────────────────────────────────────────────────────────── */
export interface StatCard {
  label: string;
  val: string;
  delta: string;
  up: boolean;
  spark: number[];
  color: string;
}

export interface TopProduct {
  name: string;
  qty: number;
  rev: number;
  mgn: number;
}

export interface PaymentBreakdown {
  label: string;
  pct: number;
  val: number;
  color: string;
}
