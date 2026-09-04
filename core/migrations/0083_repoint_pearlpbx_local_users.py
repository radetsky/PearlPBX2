from django.conf import settings
from django.db import migrations

# The PEARLPBX table's "_2XX" RoutingRecord was created by 0016_first_users.py
# pointed at "pearlpbx-local-users" — a static context with a single
# "Dial(PJSIP/ppbxuser${EXTEN},...)" catch-all, correct only for a user
# literally named "ppbxuser<extension>". Repoints it at
# settings.PEARLPBX_DEFAULT_ROUTING_RECORD ("PEARLPBX-Users"), which
# core.conf.make_local_users_context() now generates live from SIPUser data
# (one literal extension per active user, correct regardless of username).
# Runs on every migrate, so this also repairs already-provisioned bare-metal
# and Docker installs, not just fresh ones.


def repoint_pearlpbx_local_users(apps, schema_editor):
    DialplanContext = apps.get_model("core", "DialplanContext")
    RoutingRecord = apps.get_model("core", "RoutingRecord")

    context, _ = DialplanContext.objects.get_or_create(
        name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD,
        defaults={"description": "Default local users context"},
    )

    RoutingRecord.objects.filter(
        routing_table__name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE,
        prefix="_2XX",
    ).update(context=context)


def revert_pearlpbx_local_users(apps, schema_editor):
    DialplanContext = apps.get_model("core", "DialplanContext")
    RoutingRecord = apps.get_model("core", "RoutingRecord")

    legacy_context = DialplanContext.objects.filter(name="pearlpbx-local-users").first()
    if not legacy_context:
        return

    RoutingRecord.objects.filter(
        routing_table__name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE,
        prefix="_2XX",
    ).update(context=legacy_context)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0082_settings_local_users_dial_template"),
    ]

    operations = [
        migrations.RunPython(repoint_pearlpbx_local_users, revert_pearlpbx_local_users),
    ]
