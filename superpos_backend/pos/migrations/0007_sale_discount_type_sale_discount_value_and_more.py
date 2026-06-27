import uuid

from django.db import migrations, models


def populate_sale_uuids(apps, schema_editor):
    Sale = apps.get_model('pos', 'Sale')
    for sale in Sale.objects.filter(sale_uuid__isnull=True).iterator():
        sale.sale_uuid = uuid.uuid4()
        sale.save(update_fields=['sale_uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0006_category_created_at_category_updated_at_and_more'),
    ]

    operations = [
        # Non-UUID fields — simple adds with defaults, safe for existing rows
        migrations.AddField(
            model_name='sale',
            name='discount_type',
            field=models.CharField(
                blank=True, choices=[('percent', 'Percent'), ('fixed', 'Fixed')],
                max_length=10, null=True,
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='discount_value',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='sale',
            name='receipt_printed',
            field=models.BooleanField(default=False),
        ),

        # UUID — add nullable first, populate per-row, then lock it down
        migrations.AddField(
            model_name='sale',
            name='sale_uuid',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_sale_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='sale',
            name='sale_uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
