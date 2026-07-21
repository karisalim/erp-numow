/**
 * Typed API layer for the v3.6 ERP modules (customers, suppliers,
 * purchases, finance, settlements, warehouses).
 *
 * Every function maps 1:1 onto a verified backend route — see
 * superpos_backend URL modules and /api/schema/. Nothing here invents
 * endpoints or fields.
 */
import apiClient from './client';
import { generateIdempotencyKey, withIdempotencyHeaders } from './idempotency';
import type {
  AccountBalance,
  BranchLite,
  BranchPaymentMethod,
  BranchPaymentMethodPayload,
  BranchWarehouseLink,
  CategoryTreeNode,
  CategoryTreeNodePayload,
  Customer,
  CustomerARMovement,
  CustomerPayload,
  CustomerReceipt,
  CustomerReceiptPayload,
  DashboardSummaryResponse,
  DashboardTrendResponse,
  FinancialAccount,
  FinancialAccountMovement,
  FinancialAccountPayload,
  InventoryCostMovement,
  Paginated,
  PartyBalance,
  PaymentMethodPayload,
  PaymentMethodRecord,
  PriceTier,
  PriceTierPayload,
  ProductBarcodeUnit,
  ProductBarcodeUnitPayload,
  ProductUnit,
  ProductUnitPayload,
  ProductUnitTierPrice,
  ProductUnitTierPricePayload,
  PurchaseInvoice,
  PurchaseInvoicePayload,
  StandardUnitCode,
  StatementSummary,
  Supplier,
  SupplierAPMovement,
  SupplierPayload,
  SupplierPayment,
  SupplierPaymentPayload,
  Unit,
  UnitGroup,
  UnitGroupPayload,
  UnitPayload,
  Warehouse,
  WarehouseStockRow,
} from '../types/erp';

export type ListParams = Record<string, string | number | boolean | undefined>;

/* ── Customers ──────────────────────────────────────────────────────────── */

export const customersApi = {
  list: (params?: ListParams) =>
    apiClient.get<Paginated<Customer>>('/customers/', { params }).then(r => r.data),
  get: (id: number) =>
    apiClient.get<Customer>(`/customers/${id}/`).then(r => r.data),
  create: (payload: CustomerPayload) =>
    apiClient.post<Customer>('/customers/', payload).then(r => r.data),
  update: (id: number, payload: Partial<CustomerPayload>) =>
    apiClient.patch<Customer>(`/customers/${id}/`, payload).then(r => r.data),
  deactivate: (id: number) =>
    apiClient.post<Customer>(`/customers/${id}/deactivate/`).then(r => r.data),
  balance: (id: number) =>
    apiClient.get<PartyBalance>(`/customers/${id}/balance/`).then(r => r.data),
  statement: (id: number, params?: ListParams) =>
    apiClient.get<StatementSummary<CustomerARMovement>>(`/customers/${id}/statement/`, { params }).then(r => r.data),
};

/* ── Suppliers ──────────────────────────────────────────────────────────── */

export const suppliersApi = {
  list: (params?: ListParams) =>
    apiClient.get<Paginated<Supplier>>('/suppliers/', { params }).then(r => r.data),
  get: (id: number) =>
    apiClient.get<Supplier>(`/suppliers/${id}/`).then(r => r.data),
  create: (payload: SupplierPayload) =>
    apiClient.post<Supplier>('/suppliers/', payload).then(r => r.data),
  update: (id: number, payload: Partial<SupplierPayload>) =>
    apiClient.patch<Supplier>(`/suppliers/${id}/`, payload).then(r => r.data),
  deactivate: (id: number) =>
    apiClient.post<Supplier>(`/suppliers/${id}/deactivate/`).then(r => r.data),
  balance: (id: number) =>
    apiClient.get<PartyBalance>(`/suppliers/${id}/balance/`).then(r => r.data),
  statement: (id: number, params?: ListParams) =>
    apiClient.get<StatementSummary<SupplierAPMovement>>(`/suppliers/${id}/statement/`, { params }).then(r => r.data),
};

/* ── Settlements ────────────────────────────────────────────────────────── */

export const settlementsApi = {
  listCustomerReceipts: (params?: ListParams) =>
    apiClient.get<Paginated<CustomerReceipt> | CustomerReceipt[]>('/customer-receipts/', { params }).then(r => r.data),
  getCustomerReceipt: (id: number) =>
    apiClient.get<CustomerReceipt>(`/customer-receipts/${id}/`).then(r => r.data),
  createCustomerReceipt: (payload: CustomerReceiptPayload, idempotencyKey?: string) =>
    apiClient
      .post<CustomerReceipt>('/customer-receipts/', payload,
        withIdempotencyHeaders(idempotencyKey ?? generateIdempotencyKey()))
      .then(r => r.data),

  listSupplierPayments: (params?: ListParams) =>
    apiClient.get<Paginated<SupplierPayment> | SupplierPayment[]>('/supplier-payments/', { params }).then(r => r.data),
  getSupplierPayment: (id: number) =>
    apiClient.get<SupplierPayment>(`/supplier-payments/${id}/`).then(r => r.data),
  createSupplierPayment: (payload: SupplierPaymentPayload, idempotencyKey?: string) =>
    apiClient
      .post<SupplierPayment>('/supplier-payments/', payload,
        withIdempotencyHeaders(idempotencyKey ?? generateIdempotencyKey()))
      .then(r => r.data),
};

/* ── Purchases ──────────────────────────────────────────────────────────── */

export const purchasesApi = {
  list: (params?: ListParams) =>
    apiClient.get<Paginated<PurchaseInvoice>>('/purchase-invoices/', { params }).then(r => r.data),
  get: (id: number) =>
    apiClient.get<PurchaseInvoice>(`/purchase-invoices/${id}/`).then(r => r.data),
  create: (payload: PurchaseInvoicePayload, idempotencyKey?: string) =>
    apiClient
      .post<PurchaseInvoice>('/purchase-invoices/', payload,
        withIdempotencyHeaders(idempotencyKey ?? generateIdempotencyKey()))
      .then(r => r.data),
};

/* ── Finance ────────────────────────────────────────────────────────────── */

export const financeApi = {
  listAccounts: (params?: ListParams) =>
    apiClient.get<Paginated<FinancialAccount>>('/finance/accounts/', { params }).then(r => r.data),
  getAccount: (id: number) =>
    apiClient.get<FinancialAccount>(`/finance/accounts/${id}/`).then(r => r.data),
  createAccount: (payload: FinancialAccountPayload) =>
    apiClient.post<FinancialAccount>('/finance/accounts/', payload).then(r => r.data),
  updateAccount: (id: number, payload: Partial<FinancialAccountPayload>) =>
    apiClient.patch<FinancialAccount>(`/finance/accounts/${id}/`, payload).then(r => r.data),
  deactivateAccount: (id: number) =>
    apiClient.post<FinancialAccount>(`/finance/accounts/${id}/deactivate/`).then(r => r.data),
  accountBalance: (id: number) =>
    apiClient.get<AccountBalance>(`/finance/accounts/${id}/balance/`).then(r => r.data),
  accountStatement: (id: number, params?: ListParams) =>
    apiClient.get<StatementSummary<FinancialAccountMovement>>(`/finance/accounts/${id}/movements/`, { params }).then(r => r.data),
  listMovements: (params?: ListParams) =>
    apiClient.get<Paginated<FinancialAccountMovement>>('/finance/movements/', { params }).then(r => r.data),

  listPaymentMethods: (params?: ListParams) =>
    apiClient.get<Paginated<PaymentMethodRecord>>('/finance/payment-methods/', { params }).then(r => r.data),
  createPaymentMethod: (payload: PaymentMethodPayload) =>
    apiClient.post<PaymentMethodRecord>('/finance/payment-methods/', payload).then(r => r.data),
  updatePaymentMethod: (id: number, payload: Partial<PaymentMethodPayload>) =>
    apiClient.patch<PaymentMethodRecord>(`/finance/payment-methods/${id}/`, payload).then(r => r.data),
  deactivatePaymentMethod: (id: number) =>
    apiClient.post<PaymentMethodRecord>(`/finance/payment-methods/${id}/deactivate/`).then(r => r.data),

  listBranchPaymentMethods: (branchId: number) =>
    apiClient.get<BranchPaymentMethod[]>(`/branches/${branchId}/payment-methods/`).then(r => r.data),
  createBranchPaymentMethod: (branchId: number, payload: BranchPaymentMethodPayload) =>
    apiClient.post<BranchPaymentMethod>(`/branches/${branchId}/payment-methods/`, payload).then(r => r.data),
  updateBranchPaymentMethod: (branchId: number, id: number, payload: Partial<BranchPaymentMethodPayload>) =>
    apiClient.patch<BranchPaymentMethod>(`/branches/${branchId}/payment-methods/${id}/`, payload).then(r => r.data),
  deactivateBranchPaymentMethod: (branchId: number, id: number) =>
    apiClient.post<BranchPaymentMethod>(`/branches/${branchId}/payment-methods/${id}/deactivate/`).then(r => r.data),
};

/* ── Warehouses & per-warehouse stock ───────────────────────────────────── */

export const warehousesApi = {
  list: (params?: ListParams) =>
    apiClient.get<Paginated<Warehouse>>('/inventory/warehouses/', { params }).then(r => r.data),
  stockList: (params?: ListParams) =>
    apiClient.get<Paginated<WarehouseStockRow>>('/inventory/warehouse-stocks/', { params }).then(r => r.data),
  warehouseStock: (warehouseId: number, params?: ListParams) =>
    apiClient.get<Paginated<WarehouseStockRow>>(`/inventory/warehouses/${warehouseId}/stock/`, { params }).then(r => r.data),
  productBreakdown: (productId: number) =>
    apiClient.get<WarehouseStockRow[] | Paginated<WarehouseStockRow>>(`/products/${productId}/warehouse-stocks/`).then(r => r.data),
  branchLinks: (params?: ListParams) =>
    apiClient.get<Paginated<BranchWarehouseLink>>('/inventory/branch-warehouses/', { params }).then(r => r.data),
};

/* ── Inventory costing (AVCO audit trail, read-only) ─────────────────────── */

export const inventoryCostApi = {
  listMovements: (productId: number, params?: ListParams) =>
    apiClient
      .get<Paginated<InventoryCostMovement>>(`/products/${productId}/cost-movements/`, { params })
      .then(r => r.data),
  /* Sprint 4 Batch 4 — CSV/Excel/PDF export of the same audit trail. Param
   * is `export_format`, not `format` — the backend reserves the latter for
   * DRF's own content negotiation. Returns the raw blob response so the
   * caller can trigger a download (same pattern as SalesPage's CSV export). */
  exportMovements: (productId: number, exportFormat: 'csv' | 'xlsx' | 'pdf', params?: ListParams) =>
    apiClient.get(`/products/${productId}/cost-movements/export/`, {
      params: { ...params, export_format: exportFormat },
      responseType: 'blob',
    }),
};

/* ── Dashboard ──────────────────────────────────────────────────────────── */

export const dashboardApi = {
  summary: (params?: ListParams) =>
    apiClient.get<DashboardSummaryResponse>('/dashboard/summary/', { params }).then(r => r.data),
  /* Sprint 4 Batch 1 — one row per day (net_revenue/cogs/gross_profit/
   * gross_margin_pct), for the Margin/COGS trend chart. */
  trend: (params?: ListParams) =>
    apiClient.get<DashboardTrendResponse>('/dashboard/trend/', { params }).then(r => r.data),
};

/* ── Branches (legacy list shape used by Users page) ────────────────────── */

export const branchesApi = {
  list: () =>
    apiClient.get<BranchLite[] | Paginated<BranchLite>>('/accounts/branches/').then(r => r.data),
};

/** Unwrap endpoints that may return either a bare array or a DRF page. */
export function asResults<T>(data: T[] | Paginated<T>): T[] {
  return Array.isArray(data) ? data : data.results;
}

/* ── Units (Sprint 2 Batch 1 + Phase 1.5) ───────────────────────────────── */

export const unitsApi = {
  listGroups: (params?: ListParams) =>
    apiClient.get<Paginated<UnitGroup> | UnitGroup[]>('/catalog/unit-groups/', { params }).then(r => r.data),
  createGroup: (payload: UnitGroupPayload) =>
    apiClient.post<UnitGroup>('/catalog/unit-groups/', payload).then(r => r.data),
  updateGroup: (id: number, payload: Partial<UnitGroupPayload>) =>
    apiClient.patch<UnitGroup>(`/catalog/unit-groups/${id}/`, payload).then(r => r.data),
  deactivateGroup: (id: number) =>
    apiClient.post<UnitGroup>(`/catalog/unit-groups/${id}/deactivate/`).then(r => r.data),

  list: (params?: ListParams) =>
    apiClient.get<Paginated<Unit> | Unit[]>('/catalog/units/', { params }).then(r => r.data),
  create: (payload: UnitPayload) =>
    apiClient.post<Unit>('/catalog/units/', payload).then(r => r.data),
  update: (id: number, payload: Partial<UnitPayload>) =>
    apiClient.patch<Unit>(`/catalog/units/${id}/`, payload).then(r => r.data),
  deactivate: (id: number) =>
    apiClient.post<Unit>(`/catalog/units/${id}/deactivate/`).then(r => r.data),

  standardCodes: () =>
    apiClient.get<StandardUnitCode[]>('/catalog/standard-unit-codes/').then(r => r.data),
};

/* ── Per-product unit conversions & pack barcodes ───────────────────────── */

export const productUnitsApi = {
  list: (productId: number) =>
    apiClient.get<Paginated<ProductUnit> | ProductUnit[]>(`/products/${productId}/units/`).then(r => r.data),
  create: (productId: number, payload: ProductUnitPayload) =>
    apiClient.post<ProductUnit>(`/products/${productId}/units/`, payload).then(r => r.data),
  update: (productId: number, unitMappingId: number, payload: Partial<ProductUnitPayload>) =>
    apiClient.patch<ProductUnit>(`/products/${productId}/units/${unitMappingId}/`, payload).then(r => r.data),

  listBarcodes: (productId: number) =>
    apiClient.get<Paginated<ProductBarcodeUnit> | ProductBarcodeUnit[]>(`/products/${productId}/barcodes/`).then(r => r.data),
  createBarcode: (productId: number, payload: ProductBarcodeUnitPayload) =>
    apiClient.post<ProductBarcodeUnit>(`/products/${productId}/barcodes/`, payload).then(r => r.data),
};

/* ── Price Tiers & per-unit tiered pricing ──────────────────────────────── */

export const priceTiersApi = {
  list: (params?: ListParams) =>
    apiClient.get<Paginated<PriceTier> | PriceTier[]>('/catalog/price-tiers/', { params }).then(r => r.data),
  create: (payload: PriceTierPayload) =>
    apiClient.post<PriceTier>('/catalog/price-tiers/', payload).then(r => r.data),
  update: (id: number, payload: Partial<PriceTierPayload>) =>
    apiClient.patch<PriceTier>(`/catalog/price-tiers/${id}/`, payload).then(r => r.data),
  deactivate: (id: number) =>
    apiClient.post<PriceTier>(`/catalog/price-tiers/${id}/deactivate/`).then(r => r.data),

  listTierPrices: (productId: number, unitMappingId: number) =>
    apiClient
      .get<Paginated<ProductUnitTierPrice> | ProductUnitTierPrice[]>(
        `/products/${productId}/units/${unitMappingId}/tier-prices/`,
      )
      .then(r => r.data),
  createTierPrice: (productId: number, unitMappingId: number, payload: ProductUnitTierPricePayload) =>
    apiClient
      .post<ProductUnitTierPrice>(`/products/${productId}/units/${unitMappingId}/tier-prices/`, payload)
      .then(r => r.data),
  updateTierPrice: (
    productId: number, unitMappingId: number, tierPriceId: number,
    payload: Partial<ProductUnitTierPricePayload>,
  ) =>
    apiClient
      .patch<ProductUnitTierPrice>(
        `/products/${productId}/units/${unitMappingId}/tier-prices/${tierPriceId}/`, payload,
      )
      .then(r => r.data),
};

/* ── Category trees (Sprint 2 Batch 2) ──────────────────────────────────── */

export const categoriesApi = {
  listSales: (params?: ListParams) =>
    apiClient.get<Paginated<CategoryTreeNode> | CategoryTreeNode[]>('/catalog/sales-categories/', { params }).then(r => r.data),
  createSales: (payload: CategoryTreeNodePayload) =>
    apiClient.post<CategoryTreeNode>('/catalog/sales-categories/', payload).then(r => r.data),
  updateSales: (id: number, payload: Partial<CategoryTreeNodePayload>) =>
    apiClient.patch<CategoryTreeNode>(`/catalog/sales-categories/${id}/`, payload).then(r => r.data),
  deactivateSales: (id: number) =>
    apiClient.post<CategoryTreeNode>(`/catalog/sales-categories/${id}/deactivate/`).then(r => r.data),

  listInventory: (params?: ListParams) =>
    apiClient.get<Paginated<CategoryTreeNode> | CategoryTreeNode[]>('/catalog/inventory-categories/', { params }).then(r => r.data),
  createInventory: (payload: CategoryTreeNodePayload) =>
    apiClient.post<CategoryTreeNode>('/catalog/inventory-categories/', payload).then(r => r.data),
  updateInventory: (id: number, payload: Partial<CategoryTreeNodePayload>) =>
    apiClient.patch<CategoryTreeNode>(`/catalog/inventory-categories/${id}/`, payload).then(r => r.data),
  deactivateInventory: (id: number) =>
    apiClient.post<CategoryTreeNode>(`/catalog/inventory-categories/${id}/deactivate/`).then(r => r.data),
};
