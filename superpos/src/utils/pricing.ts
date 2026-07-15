import { priceTiersApi, asResults } from '../api/erp';

/**
 * Preview price for a product-unit at an optional tier — mirrors the
 * backend's own `resolve_unit_price` fallback (active tier price if one
 * matches, else the product's base price). Display-only: the server is
 * always the authoritative source for what a sale actually charges.
 */
export async function previewUnitPrice(
  productId: number,
  unitMappingId: number,
  priceTierId: number | null,
  fallbackPrice: number,
): Promise<number> {
  try {
    const data = await priceTiersApi.listTierPrices(productId, unitMappingId);
    const rows = asResults(data);
    const match = priceTierId != null
      ? rows.find((r) => r.price_tier === priceTierId && r.is_active)
      : undefined;
    return match ? Number(match.price) : fallbackPrice;
  } catch {
    return fallbackPrice;
  }
}
