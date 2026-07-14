import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0074_alter_managerusers_secret_alter_sipuser_secret'),
    ]

    operations = [
        migrations.AddField(
            model_name='whitelist',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='Created at'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='whitelist',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='%(class)s_created',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Created by',
            ),
        ),
        migrations.AddField(
            model_name='whitelist',
            name='modified_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Modified at'),
        ),
        migrations.AddField(
            model_name='whitelist',
            name='modified_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='%(class)s_modified',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Modified by',
            ),
        ),
    ]
