import type { ProductTypeValue, ProductTypeBehavior } from './erp';

export type BadgeKind = 'gray' | 'success' | 'danger' | 'warn' | 'info' | 'brand' | 'violet';
export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger' | 'success' | 'dark';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'xl';
export type PaymentMethod = 'cash' | 'card' | 'wallet' | 'credit';
export type UserRole = 'Owner' | 'Admin' | 'Manager' | 'Cashier';

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

  // ── Sprint 2 Batch 3 classification (additive, all optional) ──
  product_type?: ProductTypeValue;
  product_type_display?: string;
  /** Read-only, server-computed from product_type — never edit directly. */
  behavior?: ProductTypeBehavior;
  sales_category?: number | null;
  sales_category_name?: string;
  inventory_category?: number | null;
  inventory_category_name?: string;
  show_on_pos?: boolean;
  is_discountable?: boolean;

  // ── Legacy aliases — TODO: remove once POS/Products pages are migrated ──
  /** @deprecated use `tax_rate` */
  tax?: number;
}

export interface CartItem extends Product {
  lineId: string;
  /** Quantity in whichever unit this line is denominated in (base unit, or
   * `unitLabel` below when a non-base ProductUnit was picked). */
  qty: number;
  /** Set only when the cashier chose a non-base ProductUnit (e.g. a carton
   * pack). `price` on this CartItem is then the resolved price for ONE of
   * this unit, not the product's base-unit price. */
  productUnitId?: number;
  unitLabel?: string;
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
  /** Backend-computed invoice discount (subtotal + tax − total when > 0). */
  discount?: number;
  total: number;
  method: PaymentMethod;
  paid: number;
  change: number;
  ts: Date;
  cashier: string;
  terminal: string;
  /** Present on credit sales — who owes the balance. */
  customer_name?: string;
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

/* ─────────────────────────────────────────────────────────────────────────────
 * Shared v3.6 status vocabularies — mirror of
 * `superpos_backend/pos/domain/statuses.py` STATUS_REGISTRY.
 *
 * These are the wire values exchanged with the backend. Keep this file and
 * `pos/domain/statuses.py` in lock-step: dropping or renaming a value here
 * is a breaking change to the API contract.
 *
 * Phase 1 slice ships the types only — no UI screens consume them yet.
 * They unblock typed payload/response shapes for Phase 2+ work without
 * forcing a refactor of existing pages.
 * ──────────────────────────────────────────────────────────────────────────── */

// §5.2 Five-Status Document Model
export type PostingStatus  = 'draft' | 'posted' | 'cancelled' | 'void';
export type DocPaymentStatus = 'unpaid' | 'partially_paid' | 'paid' | 'n_a';
export type ReturnStatus   = 'not_returned' | 'partially_returned' | 'returned';
export type ApprovalStatus = 'not_required' | 'pending' | 'approved' | 'rejected';
export type SyncStatus     = 'synced' | 'pending_sync' | 'sync_failed';

// §41 Table Service / Open Orders
export type OpenOrderStatus =
  | 'draft' | 'sent' | 'needs_bill' | 'paid_clearing' | 'paid' | 'cancelled';

export type OpenOrderLineStatus =
  | 'draft' | 'sent' | 'prepared_pending' | 'preparing'
  | 'ready' | 'served' | 'billed' | 'voided' | 'cancelled';

export type TableStatus =
  | 'available' | 'occupied' | 'sent_to_kitchen'
  | 'needs_bill' | 'paid_clearing' | 'out_of_service';

export type KitchenTicketStatus =
  | 'queued' | 'printed' | 'print_failed'
  | 'preparing' | 'ready' | 'served' | 'voided';

// §14 Shift
export type ShiftStatus = 'open' | 'closed' | 'force_closed' | 'reconciling';

/** Aggregate map mirroring backend `STATUS_REGISTRY` keys. */
export interface StatusRegistry {
  posting_status:         PostingStatus;
  payment_status:         DocPaymentStatus;
  return_status:          ReturnStatus;
  approval_status:        ApprovalStatus;
  sync_status:            SyncStatus;
  open_order_status:      OpenOrderStatus;
  open_order_line_status: OpenOrderLineStatus;
  table_status:           TableStatus;
  kitchen_ticket_status:  KitchenTicketStatus;
  shift_status:           ShiftStatus;
}
