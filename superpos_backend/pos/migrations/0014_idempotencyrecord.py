"""Additive migration: create pos_idempotencyrecord.

Phase 1 — Foundation Slice. The model is purely additive: no existing tables
are altered, no data is touched. Existing migrations are not edited.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_tenant_receipt_header'),  # latest accounts migration
        ('pos', '0013_drop_product_stock_nonneg_constraint'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotencyRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, max_length=255)),
                ('method', models.CharField(max_length=10)),
                ('path', models.CharField(max_length=255)),
                ('request_hash', models.CharField(max_length=64)),
                ('response_status', models.PositiveSmallIntegerField()),
                ('response_body', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='idempotency_records',
                    to='accounts.tenant',
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name='idempotency_records',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='idempotencyrecord',
            constraint=models.UniqueConstraint(
                fields=['tenant', 'key'],
                name='pos_idem_tenant_key_uniq',
            ),
        ),
        migrations.AddIndex(
            model_name='idempotencyrecord',
            index=models.Index(fields=['tenant', 'key'], name='pos_idem_tenant_key_idx'),
        ),
    ]
