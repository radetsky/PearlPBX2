from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0089_dialplan_audit_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="settings",
            name="allow_monitor",
            field=models.BooleanField(
                default=True,
                help_text="Allow to monitor calls of whole system",
                verbose_name="Allow global monitor",
            ),
        ),
    ]
