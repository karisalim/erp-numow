"""Unit-aware price resolution (Sprint 2 Batch 4 remainder).

Single authority for "what does this product_unit cost at this price tier."
Nothing else in the codebase may derive a unit price by scaling
`Product.price` with `ProductUnit.conversion_to_base` — a carton price is a
real business decision (`ProductUnitTierPrice`), never `piece_price * 12`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pos.models import PriceTier, ProductUnit, ProductUnitTierPrice


def resolve_unit_price(
    *, product_unit: ProductUnit, price_tier: Optional[PriceTier] = None,
) -> Decimal:
    """The price for `product_unit`, optionally at `price_tier`.

    Lookup order: an active `ProductUnitTierPrice` row for
    (product_unit, price_tier) when `price_tier` is given and a row exists;
    otherwise `product_unit.product.price` (the default/fallback retail
    price). Never computed from `conversion_to_base`.
    """
    if price_tier is not None:
        tier_price = (
            ProductUnitTierPrice.objects
            .filter(product_unit=product_unit, price_tier=price_tier, is_active=True)
            .first()
        )
        if tier_price is not None:
            return tier_price.price
    return product_unit.product.price


__all__ = ['resolve_unit_price']
