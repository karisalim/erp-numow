from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0002_rename_to_sale_add_inventory_batch'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty', models.DecimalField(decimal_places=3, max_digits=8)),
                ('movement_type', models.CharField(
                    choices=[
                        ('sale_out',    'Sale Out'),
                        ('purchase_in', 'Purchase In'),
                        ('return_in',   'Return In'),
                        ('adjustment',  'Adjustment'),
                    ],
                    max_length=20,
                )),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='movements',
                    to='pos.product',
                )),
                ('sale', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='movements',
                    to='pos.sale',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
