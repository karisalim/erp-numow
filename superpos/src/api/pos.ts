/**
 * Typed API layer for POS-specific calls (product catalog scoped to the
 * checkout screen, barcode/scale scanning, sale submission). Mirrors the
 * `api/erp.ts` convention — every function maps 1:1 onto a verified backend
 * route (see superpos_backend/pos/urls.py + views.py).
 */
import apiClient from './client';
import { withIdempotencyHeaders } from './idempotency';
import type { Product } from '../types';
import type { ListParams } from './erp';

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Unwrap a paginated DRF list response (or accept a bare array). */
export function unwrapList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  const obj = payload as PaginatedResponse<T> | undefined;
  return obj?.results ?? [];
}

interface CategoryDto { id: number; name: string; }

/** `product_unit` echo returned by /products/scan/ for a non-base-unit pack barcode. */
export interface ScanProductUnit {
  id: number;
  unit_id: number;
  unit_name: string;
  conversion_to_base: string;
  is_base: boolean;
}

export type ScanResult =
  | { type: 'barcode'; product: Product; product_unit?: ScanProductUnit }
  | {
      type: 'weight_encoded';
      product: Product;
      plu: string;
      quantity: string;
      price_each: string;
      line_total: string;
    };

export interface SaleItemPayload {
  product: number;
  warehouse?: number | null;
  // Legacy base-unit shape — either this pair…
  qty?: number;
  price_each?: number;
  // …or the unit-aware shape (server derives qty/price_each).
  product_unit?: number;
  entered_qty?: number;
}

export interface CreateSalePayload {
  method: 'cash' | 'card' | 'wallet' | 'credit';
  paid: number;
  items: SaleItemPayload[];
  customer?: number;
  price_tier?: number;
  discount_type?: 'percent' | 'fixed';
  discount_value?: number;
}

export interface SaleResponseDto {
  id: number;
  sale_uuid?: string;
  cashier_name?: string;
  branch_name?: string;
  terminal_name?: string;
  subtotal: string | number;
  tax_amount: string | number;
  total: string | number;
  paid: string | number;
  change: string | number;
  method: 'cash' | 'card' | 'wallet' | 'credit';
  offline?: boolean;
  status: string;
  created_at?: string;
  warnings?: string[];
}

export const posApi = {
  /** Product catalog for the checkout screen — always scoped to `show_on_pos=true`. */
  listPosProducts: (params?: ListParams) =>
    apiClient
      .get<PaginatedResponse<Product> | Product[]>('/products/', {
        params: { show_on_pos: 'true', active: 'true', ...params },
      })
      .then(r => unwrapList<Product>(r.data)),

  listCategories: () =>
    apiClient
      .get<PaginatedResponse<CategoryDto> | CategoryDto[]>('/categories/')
      .then(r => unwrapList<CategoryDto>(r.data)),

  /** Weight-encoded-aware, unit-aware scanner entry point (`/products/scan/`). */
  scanBarcode: (code: string) =>
    apiClient.get<ScanResult>(`/products/scan/${encodeURIComponent(code)}/`).then(r => r.data),

  /** PLU fallback used only when a scale barcode's prefix doesn't match tenant config. */
  lookupByPlu: (plu: string) =>
    apiClient
      .get<PaginatedResponse<Product> | Product[]>('/products/', { params: { plu, weighted: 'true' } })
      .then(r => unwrapList<Product>(r.data)),

  createSale: (payload: CreateSalePayload, idempotencyKey: string) =>
    apiClient
      .post<SaleResponseDto>('/sales/', payload, withIdempotencyHeaders(idempotencyKey))
      .then(r => r.data),
};
