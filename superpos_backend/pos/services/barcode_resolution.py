"""Barcode scan resolution (Sprint 2 Batch 5a — POS integration).

Single authority for turning a scanned code into `(Product, ProductUnit)`.
The chain is mandatory and ordered — nothing else in the codebase may look
up a product by barcode outside this function once callers adopt it:

    1. `ProductBarcodeUnit` (pack-level codes, Sprint 2 Batch 1) — a code
       registered here always resolves through its `product_unit`, never
       straight to the product, even if the code happens to also collide
       with `Product.barcode` (the two namespaces are cross-checked for
       collisions at write time in `ProductBarcodeUnitSerializer`/
       `ProductSerializer`, so this ordering is unambiguous by construction).
    2. `Product.barcode` (legacy single-code field) — fallback, paired with
       the product's base `ProductUnit` (`None` when the product has no
       configured unit substrate yet, e.g. it predates Batch 1).

No `scan_priority` field is needed: uniqueness within each table plus this
fixed two-step precedence is sufficient (documented simplification carried
over from the Batch 4 planning notes).
"""

from __future__ import annotations

from typing import Optional, Tuple

from pos.models import Product, ProductBarcodeUnit, ProductUnit
from pos.services.units import get_base_product_unit


def resolve_barcode(*, tenant, code: str) -> Optional[Tuple[Product, Optional[ProductUnit]]]:
    """Resolve a scanned `code` to `(product, product_unit)` for `tenant`.

    Returns `None` when nothing matches either namespace. `product_unit` in
    the returned tuple may itself be `None` for a legacy-barcode match on a
    product with no base `ProductUnit` configured yet — callers that need a
    unit (e.g. to convert a quantity) must handle that case explicitly.
    """
    if not code:
        return None

    pack = (
        ProductBarcodeUnit.objects
        .filter(tenant=tenant, barcode=code)
        .select_related('product', 'product_unit', 'product_unit__unit')
        .first()
    )
    if pack is not None:
        return pack.product, pack.product_unit

    product = Product.objects.filter(tenant=tenant, barcode=code, active=True).first()
    if product is not None:
        return product, get_base_product_unit(product)

    return None


__all__ = ['resolve_barcode']
