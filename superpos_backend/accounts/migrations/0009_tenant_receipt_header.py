from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_alter_user_username_alter_user_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='receipt_header',
            field=models.TextField(blank=True, default=''),
        ),
    ]
