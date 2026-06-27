"""Backfill `Sale.branch` + `StockMovement.branch` and enforce NOT NULL on
`Sale.branch`.

Strategy:
1. For every tenant that owns at least one Sale or StockMovement, ensure a
   branch exists; create a "Main" branch if not.
2. Set `Sale.branch_id` for any row where it's NULL, picking the tenant's
   earliest branch (deterministic).
3. Backfill `StockMovement.branch_id` — prefer the related Sale's branch when
   the movement is a sale-out, otherwise use the tenant's Main branch.
4. Alter Sale.branch to NOT NULL with PROTECT on delete.
"""

from django.db import migrations, models


def backfill_branches(apps, schema_editor):
    Tenant   = apps.get_model('accounts', 'Tenant')
    Branch   = apps.get_model('accounts', 'Branch')
    Sale     = apps.get_model('pos', 'Sale')
    Movement = apps.get_model('pos', 'StockMovement')

    # Ensure each tenant has at least one branch we can default to.
    tenants_needing_default = {}
    for tenant in Tenant.objects.all():
        first = tenant.branches.order_by('created_at', 'id').first()
        if first is None:
            first = Branch.objects.create(tenant=tenant, name='Main', address='', phone='', active=True)
        tenants_needing_default[tenant.id] = first.id

    # Sales: pick the tenant default for any NULL branch.
    null_sales = Sale.objects.filter(branch__isnull=True)
    for sale in null_sales.only('id', 'tenant_id'):
        default_id = tenants_needing_default.get(sale.tenant_id)
        if default_id is None:
            continue
        Sale.objects.filter(pk=sale.pk).update(branch_id=default_id)

    # Stock movements: inherit from the sale when possible, else tenant default.
    null_movements = Movement.objects.filter(branch__isnull=True).select_related('sale')
    for mv in null_movements.only('id', 'tenant_id', 'sale_id'):
        target = None
        if mv.sale_id:
            # Re-fetch a single field to avoid relying on stale select_related state.
            sale_branch_id = Sale.objects.filter(pk=mv.sale_id).values_list('branch_id', flat=True).first()
            target = sale_branch_id
        if not target:
            target = tenants_needing_default.get(mv.tenant_id)
        if target:
            Movement.objects.filter(pk=mv.pk).update(branch_id=target)


def noop_reverse(apps, schema_editor):
    # Backfill is forward-only; rolling back is a manual operation.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_alter_user_username_alter_user_unique_together'),
        ('pos',      '0011_auditlog_discountcode_payment_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_branches, reverse_code=noop_reverse),
        migrations.AlterField(
            model_name='sale',
            name='branch',
            field=models.ForeignKey(
                to='accounts.branch',
                on_delete=models.deletion.PROTECT,
                related_name='sales',
            ),
        ),
    ]
