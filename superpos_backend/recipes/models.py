"""Recipes, size variants, and modifiers (Sprint 5).

A separate Django app from `pos` — these are new domain concepts (not
extensions of an existing `pos` model), following the same
one-app-per-domain split `accounts`/`pos` already establish. Cross-app
references to `pos.Product`/`pos.ProductUnit` and `accounts.Branch` use
string FKs to avoid a circular import between `pos` and `recipes`.
"""

from django.db import models


class ProductVariant(models.Model):
    """A size/option variant of a parent product (D-24: "variant-of-one-
    product" — Small/Medium/Large as rows under one `Product`, each with
    its own sell price and, later, its own `Recipe`).

    Deliberately has **no barcode field** — per D-24's own recommendation,
    the primary POS flow for a variant is menu/category selection or an
    optional PLU, never routed through `pos.ProductBarcodeUnit`.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='product_variants', db_index=True,
    )
    product = models.ForeignKey(
        'pos.Product', on_delete=models.CASCADE, related_name='variants',
    )
    name = models.CharField(max_length=60)
    sku = models.CharField(max_length=40, blank=True, default='')
    plu = models.CharField(max_length=10, blank=True, default='')
    # The variant's own sell price — never a multiplier of the parent
    # product's price (the owner's explicit requirement: each size is an
    # independent price point, not a computed scale-up).
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'product', 'name'],
                name='recipes_variant_tenant_product_name_uniq',
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='recipes_variant_price_nonneg',
            ),
        ]

    def __str__(self):
        return f'{self.product_id} — {self.name}'
