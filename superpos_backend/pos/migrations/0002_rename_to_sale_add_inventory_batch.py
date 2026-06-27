from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Rename Transaction → Sale ──────────────────────────────────────
        migrations.RenameModel('Transaction', 'Sale'),

        # ── 2. Rename TransactionItem → SaleItem ─────────────────────────────
        migrations.RenameModel('TransactionItem', 'SaleItem'),

        # ── 3. Rename FK column transaction_id → sale_id on SaleItem ─────────
        migrations.RenameField(
            model_name='saleitem',
            old_name='transaction',
            new_name='sale',
        ),

        # ── 4. Add InventoryBatch ─────────────────────────────────────────────
        migrations.CreateModel(
            name='InventoryBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('batch_number', models.CharField(max_length=100)),
                ('remaining_quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('cost_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='batches',
                    to='pos.product',
                )),
            ],
            options={
                'verbose_name': 'inventory batch',
                'verbose_name_plural': 'inventory batches',
                'ordering': ['expiry_date'],
            },
        ),
    ]
