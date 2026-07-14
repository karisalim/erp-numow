"""Unit conversion service (Sprint 2 Batch 1 — MASTER_DATA_CONTRACT §2).

Pure conversion layer over the dynamic-unit models. Nothing here mutates
stock: inventory quantities are stored ONLY in the product's base unit
(directive R-B), and this service is how every future document line
(purchase/sale/recipe — Sprint 3+) turns an entered quantity into that base
denomination.

    convert_to_base(product=milk, qty=3, product_unit=<carton x12000>)
        -> Decimal('36000')   # ml

Quantize policy: converted BASE quantities are quantized to 3 decimal places
HALF_UP via `quantize_qty` — matching every existing quantity column
(Product.stock 10/3, StockMovement/WarehouseStock 14/3). Conversion factors
themselves are Decimal(16,6) per the approved Sprint 2 design (D-13 working
proposal; revisit at G2 sign-off).

Base-unit immutability: once StockMovements exist for a product, its base
mapping must not change — every historical movement number is denominated in
that base, and editing it would silently reinterpret history. Re-denomination
is a future explicit document, not an edit (`assert_base_mapping_mutable`).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from pos.models import ProductUnit, StockMovement


#: One base-unit quantity step — matches the 3dp of every stock column.
QTY_STEP = Decimal('0.001')


class UnitConversionError(Exception):
    """A conversion rule violation (wrong product, inactive mapping, bad qty).

    `code` is a stable machine-readable identifier for API layers that want
    to surface it (same convention as SalePostingError / GA-8).
    """

    code = 'unit_conversion_invalid'


def quantize_qty(value: Decimal) -> Decimal:
    """Quantize a base-unit quantity to the canonical 3dp, HALF_UP."""
    return Decimal(value).quantize(QTY_STEP, rounding=ROUND_HALF_UP)


def get_base_product_unit(product) -> Optional[ProductUnit]:
    """The product's base ProductUnit mapping, or None while unconfigured.

    Legacy products (no ProductUnit rows yet) return None — their behavior
    keeps reading the legacy `Product.unit` enum until the seed batch confirms
    a base mapping.
    """
    return (
        ProductUnit.objects
        .filter(product=product, is_base=True)
        .select_related('unit')
        .first()
    )


def convert_to_base(*, product, qty, product_unit: ProductUnit) -> Decimal:
    """Convert `qty` entered in `product_unit` to the product's base unit.

    Validates that the mapping actually belongs to this product and is
    active, and that the quantity is positive. Returns the base quantity
    quantized to 3dp (`quantize_qty`).

    3 cartons of milk (carton conversion 12000, base ml) -> Decimal('36000.000').
    """
    if product_unit is None:
        raise UnitConversionError('product_unit is required for conversion')
    if product_unit.product_id != product.pk:
        raise UnitConversionError(
            f'ProductUnit {product_unit.pk} belongs to product '
            f'{product_unit.product_id}, not product {product.pk}',
        )
    if not product_unit.is_active:
        raise UnitConversionError(
            f'ProductUnit {product_unit.pk} is inactive and cannot be used '
            f'for new quantities',
        )
    amount = Decimal(str(qty))
    if amount <= 0:
        raise UnitConversionError('qty must be > 0')
    return quantize_qty(amount * product_unit.conversion_to_base)


def product_has_stock_history(product) -> bool:
    """True when any StockMovement exists for the product.

    The signal that the product's base denomination is locked in history.
    """
    return StockMovement.objects.filter(product=product).exists()


def assert_base_mapping_mutable(product) -> None:
    """Guard: the base mapping of a product with stock history is immutable.

    Raises `UnitConversionError` when the product BOTH already has a base
    ProductUnit AND has StockMovements. Creating the FIRST base mapping for a
    legacy product is always allowed (that is exactly what the seed command
    does) — history stays denominated in the same legacy unit the mapping
    mirrors 1:1.
    """
    has_base = ProductUnit.objects.filter(product=product, is_base=True).exists()
    if has_base and product_has_stock_history(product):
        raise UnitConversionError(
            f'Product {product.pk} has stock movements denominated in its '
            f'current base unit; the base mapping is immutable. '
            f'Re-denomination requires an explicit future document, not an edit.',
        )


__all__ = [
    'QTY_STEP',
    'UnitConversionError',
    'quantize_qty',
    'get_base_product_unit',
    'convert_to_base',
    'product_has_stock_history',
    'assert_base_mapping_mutable',
]
