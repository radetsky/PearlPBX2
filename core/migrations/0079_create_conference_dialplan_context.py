# Generated manually.

from django.db import migrations

CONFERENCE_CONTEXT_NAME = "conference"
CONFERENCE_EXTENSION_PATTERN = "_X."
CONFERENCE_EXTENSION_DIALPLAN = "ConfBridge(${EXTEN});"


def create_conference_context(apps, schema_editor):
    """
    Reserve the "conference" name in DialplanContext (landing context for
    POST /api/v1/calls/conference/) so an admin cannot create a colliding
    RoutingTable/DialplanContext with the same name. See
    settings.PEARLPBX_CONFERENCE_CONTEXT for the operational caveat if this
    name is ever changed.
    """
    DialplanContext = apps.get_model("core", "DialplanContext")
    DialplanExtension = apps.get_model("core", "DialplanExtension")

    context, _created = DialplanContext.objects.get_or_create(
        name=CONFERENCE_CONTEXT_NAME,
        defaults={
            "description": "Auto-created ConfBridge context. Do not rename/delete.",
        },
    )

    DialplanExtension.objects.get_or_create(
        context=context,
        ext=CONFERENCE_EXTENSION_PATTERN,
        defaults={
            "dialplan": CONFERENCE_EXTENSION_DIALPLAN,
            "description": "ConfBridge room entry (room = dialed extension)",
        },
    )


def remove_conference_context(apps, schema_editor):
    DialplanContext = apps.get_model("core", "DialplanContext")
    DialplanContext.objects.filter(name=CONFERENCE_CONTEXT_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0078_fix_moh_mode_sort_defaults"),
    ]

    operations = [
        migrations.RunPython(
            create_conference_context,
            remove_conference_context,
        ),
    ]
