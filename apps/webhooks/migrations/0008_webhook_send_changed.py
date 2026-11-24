from django.db import migrations, models

# Frozen snapshots of the default payload template before/after this release.
# Deliberately not imported from apps.webhooks.models.TEMPLATE_VARIABLES, which
# keeps evolving — migrations must stay pinned to the state they migrate between.
_OLD_VARIABLES = [
    "event",
    "uniqueid",
    "caller_id_num",
    "caller_id_name",
    "exten",
    "context",
    "queue",
    "timestamp",
    "duration",
    "cause",
    "cause_txt",
    "answered_time",
    "billsec",
    "recorded",
    "recording_expected",
    "recording_url",
    "recording_file",
    "missed",
    "wait_time",
    "member_name",
    "member_interface",
    "member_number",
    "ringtime",
    "holdtime",
    "answered_by_member",
    "answered_by_interface",
    "direction",
    "dest_channel",
    "dial_status",
    "answered",
    "linkedid",
    "channel",
    "channel_vars",
]
_NEW_VARIABLES = _OLD_VARIABLES + [
    "previous_exten",
    "previous_context",
    "original_exten",
    "original_context",
]

_OLD_DEFAULT_TEMPLATE = {name: f"${{{name}}}" for name in sorted(_OLD_VARIABLES)}
_NEW_DEFAULT_TEMPLATE = {name: f"${{{name}}}" for name in sorted(_NEW_VARIABLES)}


def add_exten_change_fields(apps, schema_editor):
    """Upgrade payload_template rows that still hold the untouched old default.
    Customized templates are left alone."""
    Webhook = apps.get_model("webhooks", "Webhook")
    for webhook in Webhook.objects.all():
        if webhook.payload_template == _OLD_DEFAULT_TEMPLATE:
            webhook.payload_template = _NEW_DEFAULT_TEMPLATE
            webhook.save(update_fields=["payload_template"])


def remove_exten_change_fields(apps, schema_editor):
    Webhook = apps.get_model("webhooks", "Webhook")
    for webhook in Webhook.objects.all():
        if webhook.payload_template == _NEW_DEFAULT_TEMPLATE:
            webhook.payload_template = _OLD_DEFAULT_TEMPLATE
            webhook.save(update_fields=["payload_template"])


class Migration(migrations.Migration):

    dependencies = [
        ("webhooks", "0007_add_correlation_fields_to_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhook",
            name="send_changed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Send an event when an announced call (incoming or outgoing) "
                    "moves to another extension, e.g. via Goto()."
                ),
            ),
        ),
        migrations.RunPython(add_exten_change_fields, remove_exten_change_fields),
    ]
