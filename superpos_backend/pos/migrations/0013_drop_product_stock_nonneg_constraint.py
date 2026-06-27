from django.db import migrations


class Migration(migrations.Migration):
    """Drop the `stock >= 0` CHECK constraint on pos_product.

    The constraint contradicts the documented oversell policy (FLOW.md,
    SaleSerializer docstring): a cashier may sell beyond on-hand stock,
    the row goes negative, and a warning is surfaced. With the CHECK in
    place the fallback `deduct_stock(allow_oversell=True)` path raises
    CheckViolation and the whole sale rolls back with HTTP 500.
    """

    dependencies = [
        ('pos', '0012_backfill_branches_and_enforce_sale_branch'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='product',
            name='pos_product_stock_nonneg',
        ),
    ]
