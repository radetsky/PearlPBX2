import django.core.validators
from django.db import migrations, models

import core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0067_add_tls_verify_server_allow_reload'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siptransport',
            name='name',
            field=models.CharField(
                default='',
                help_text='Example: transport-udp-nat',
                max_length=32,
                unique=True,
                validators=[core.validators.validate_asterisk_context],
                verbose_name='Name',
            ),
        ),
    ]
