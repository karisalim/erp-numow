/**
 * Typed API layer for the Sprint 5 Batch 6 recipe/food-cost reports.
 * `food_cost`, `gross_profit`, `gross_margin_pct`, `cost_consumed` etc. are
 * ALL server-computed — this file only shapes the request/response, it
 * never recomputes or re-derives any of these values.
 */
import apiClient from '../../../api/client';
import type {
  RecipeProfitabilityResponse, RecipeProfitabilityOrdering,
  IngredientConsumptionResponse, IngredientConsumptionOrdering,
} from '../types';

export interface ReportQuery {
  start_date?: string;
  end_date?: string;
  branch_id?: number;
}

export const reportsApi = {
  recipeProfitability: (params?: ReportQuery & { ordering?: RecipeProfitabilityOrdering }) =>
    apiClient
      .get<RecipeProfitabilityResponse>('/reports/recipe-profitability/', { params })
      .then(r => r.data),
  ingredientConsumption: (params?: ReportQuery & { ordering?: IngredientConsumptionOrdering }) =>
    apiClient
      .get<IngredientConsumptionResponse>('/reports/ingredient-consumption/', { params })
      .then(r => r.data),
};
