/**
 * Typed API layer for ModifierGroup / ModifierOption / ProductModifierGroup /
 * ModifierOptionConsumption (Sprint 5 Batch 4). Every function maps 1:1 onto
 * a verified backend route (superpos_backend/recipes/urls.py).
 */
import apiClient from '../../../api/client';
import type { Paginated } from '../../../types/erp';
import type {
  ModifierGroup, ModifierGroupPayload,
  ModifierOption, ModifierOptionPayload,
  ModifierOptionConsumption, ModifierOptionConsumptionPayload,
  ProductModifierGroup, ProductModifierGroupPayload,
} from '../types';
import type { ListParams } from './recipesApi';

/* ── Modifier Groups ───────────────────────────────────────────────────────
 * /catalog/modifier-groups/... */

export const modifierGroupsApi = {
  list: (params?: ListParams) =>
    apiClient
      .get<Paginated<ModifierGroup> | ModifierGroup[]>('/catalog/modifier-groups/', { params })
      .then(r => r.data),
  create: (payload: ModifierGroupPayload) =>
    apiClient.post<ModifierGroup>('/catalog/modifier-groups/', payload).then(r => r.data),
  get: (groupId: number) =>
    apiClient.get<ModifierGroup>(`/catalog/modifier-groups/${groupId}/`).then(r => r.data),
  update: (groupId: number, payload: Partial<ModifierGroupPayload>) =>
    apiClient.patch<ModifierGroup>(`/catalog/modifier-groups/${groupId}/`, payload).then(r => r.data),
  deactivate: (groupId: number) =>
    apiClient.post<ModifierGroup>(`/catalog/modifier-groups/${groupId}/deactivate/`).then(r => r.data),
};

/* ── Modifier Options ──────────────────────────────────────────────────────
 * /catalog/modifier-groups/{group_pk}/options/... */

export const modifierOptionsApi = {
  list: (groupId: number) =>
    apiClient
      .get<Paginated<ModifierOption> | ModifierOption[]>(`/catalog/modifier-groups/${groupId}/options/`)
      .then(r => r.data),
  create: (groupId: number, payload: ModifierOptionPayload) =>
    apiClient.post<ModifierOption>(`/catalog/modifier-groups/${groupId}/options/`, payload).then(r => r.data),
  get: (groupId: number, optionId: number) =>
    apiClient.get<ModifierOption>(`/catalog/modifier-groups/${groupId}/options/${optionId}/`).then(r => r.data),
  update: (groupId: number, optionId: number, payload: Partial<ModifierOptionPayload>) =>
    apiClient
      .patch<ModifierOption>(`/catalog/modifier-groups/${groupId}/options/${optionId}/`, payload)
      .then(r => r.data),
  deactivate: (groupId: number, optionId: number) =>
    apiClient
      .post<ModifierOption>(`/catalog/modifier-groups/${groupId}/options/${optionId}/deactivate/`)
      .then(r => r.data),
};

/* ── Modifier Option Consumptions ─────────────────────────────────────────
 * /catalog/modifier-options/{option_pk}/consumptions/...
 *
 * `entered_qty` may be negative (a removal, e.g. "No Onion") — the backend
 * accepts and preserves the sign; nothing here re-derives or re-signs it. */

export const modifierConsumptionsApi = {
  list: (optionId: number) =>
    apiClient
      .get<Paginated<ModifierOptionConsumption> | ModifierOptionConsumption[]>(
        `/catalog/modifier-options/${optionId}/consumptions/`,
      )
      .then(r => r.data),
  create: (optionId: number, payload: ModifierOptionConsumptionPayload) =>
    apiClient
      .post<ModifierOptionConsumption>(`/catalog/modifier-options/${optionId}/consumptions/`, payload)
      .then(r => r.data),
  get: (optionId: number, consumptionId: number) =>
    apiClient
      .get<ModifierOptionConsumption>(`/catalog/modifier-options/${optionId}/consumptions/${consumptionId}/`)
      .then(r => r.data),
  update: (optionId: number, consumptionId: number, payload: Partial<ModifierOptionConsumptionPayload>) =>
    apiClient
      .patch<ModifierOptionConsumption>(
        `/catalog/modifier-options/${optionId}/consumptions/${consumptionId}/`, payload,
      )
      .then(r => r.data),
};

/* ── Product ↔ Modifier Group attach/detach ───────────────────────────────
 * /products/{product_pk}/modifier-groups/...
 * Pure link table — POST attaches, DELETE on the detail view detaches. */

export const productModifierGroupsApi = {
  list: (productId: number) =>
    apiClient
      .get<Paginated<ProductModifierGroup> | ProductModifierGroup[]>(`/products/${productId}/modifier-groups/`)
      .then(r => r.data),
  attach: (productId: number, payload: ProductModifierGroupPayload) =>
    apiClient.post<ProductModifierGroup>(`/products/${productId}/modifier-groups/`, payload).then(r => r.data),
  detach: (productId: number, linkId: number) =>
    apiClient.delete(`/products/${productId}/modifier-groups/${linkId}/`),
};
