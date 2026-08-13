from django.db import migrations


def migrate_routing_table_webhooks(apps, schema_editor):
    """Move rows that used routing_tables for outbound matching onto the new
    outgoing-chain flags (call.outgoing/outgoing_answered/outgoing_ended).

    Before this release, routing_tables were merged into the same 'contexts'
    list as inbound DialplanContexts, so a webhook with only routing_tables
    set fired send_incoming/send_ended for outbound calls. Those calls no
    longer match on the inbound side, so translate the flags accordingly.
    """
    Webhook = apps.get_model("webhooks", "Webhook")
    for webhook in Webhook.objects.prefetch_related("contexts", "routing_tables", "queues"):
        if not webhook.routing_tables.exists():
            continue
        webhook.send_outgoing = webhook.send_incoming
        webhook.send_outgoing_ended = webhook.send_ended
        webhook.send_outgoing_answered = False
        if not webhook.contexts.exists() and not webhook.queues.exists():
            webhook.send_incoming = False
            webhook.send_ended = False
            webhook.send_missed = False
            webhook.send_answered = False
        webhook.save(
            update_fields=[
                "send_outgoing",
                "send_outgoing_ended",
                "send_outgoing_answered",
                "send_incoming",
                "send_ended",
                "send_missed",
                "send_answered",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("webhooks", "0005_webhook_outgoing_events"),
    ]

    operations = [
        migrations.RunPython(migrate_routing_table_webhooks, migrations.RunPython.noop),
    ]
