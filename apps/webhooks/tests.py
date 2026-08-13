import json
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.webhooks.admin import WebhookAdminForm
from apps.webhooks.models import (
    TEMPLATE_VARIABLES,
    Webhook,
    default_payload_template,
    validate_payload_template,
)
from apps.webhooks.sync import serialize_webhooks, sync_webhooks_config
from core.models import (
    DialplanContext,
    MusicOnHold,
    Queue,
    QueueAnnouncements,
    RoutingTable,
    SIPPeer,
    SIPTransport,
    SIPUser,
)


def make_queue(name="support"):
    moh = MusicOnHold.objects.create(name=f"moh-{name}", mode="files")
    ann = QueueAnnouncements.objects.create(name=f"ann-{name}")
    return Queue.objects.create(
        name=name, music_class=moh, queue_announcement=ann, strategy="ringall"
    )


def make_context(name="incoming"):
    return DialplanContext.objects.create(name=name)


def make_routing_table(name="outbound-users"):
    return RoutingTable.objects.create(name=name)


def make_transport(name="test-transport", protocol="udp"):
    return SIPTransport.objects.create(name=name, protocol=protocol, bind="0.0.0.0:5060")


def make_sip_user(username="1001", routing_table=None, transport=None):
    return SIPUser.objects.create(
        name=f"User {username}",
        username=username,
        extension=username,
        secret="secret",
        transport=transport or make_transport(f"transport-{username}"),
        routing_table=routing_table or make_routing_table(f"rt-{username}"),
        auth_type="userpass",
    )


def make_sip_peer(name="trunk1", routing_table=None, transport=None):
    return SIPPeer.objects.create(
        name=name,
        transport=transport or make_transport(f"transport-{name}"),
        routing_table=routing_table or make_routing_table(f"rt-{name}"),
        username="trunkuser",
        secret="secret",
    )


class PayloadTemplateValidatorTests(TestCase):
    def test_none_is_valid(self):
        validate_payload_template(None)

    def test_valid_placeholders(self):
        validate_payload_template(
            {"phone": "${caller_id_num}", "nested": {"id": "${uniqueid}"}}
        )

    def test_unknown_placeholder_rejected(self):
        with self.assertRaises(ValidationError):
            validate_payload_template({"phone": "${unknown_var}"})

    def test_non_object_rejected(self):
        with self.assertRaises(ValidationError):
            validate_payload_template(["${uniqueid}"])


class DefaultPayloadTemplateTests(TestCase):
    def test_covers_every_template_variable(self):
        template = default_payload_template()
        assert set(template.keys()) == set(TEMPLATE_VARIABLES)
        for name, placeholder in template.items():
            assert placeholder == f"${{{name}}}"

    def test_default_template_itself_is_valid(self):
        validate_payload_template(default_payload_template())

    def test_new_webhook_gets_full_template_by_default(self):
        webhook = Webhook.objects.create(name="crm", url="https://crm.example.com/hook")
        assert set(webhook.payload_template.keys()) == set(TEMPLATE_VARIABLES)

    def test_field_can_still_be_cleared_to_null(self):
        webhook = Webhook.objects.create(
            name="crm", url="https://crm.example.com/hook", payload_template=None
        )
        assert webhook.payload_template is None


@override_settings(PEARLPBX_PUBLIC_URL="https://pbx.example.com/")
class SerializeWebhooksTests(TestCase):
    def test_serialization_structure(self):
        webhook = Webhook.objects.create(
            name="crm",
            url="https://crm.example.com/hook",
            send_incoming=True,
            send_ended=True,
            send_missed=True,
            send_answered=True,
            secret="s3cret",
            timeout=7,
            retries=2,
        )
        webhook.contexts.add(make_context())
        webhook.queues.add(make_queue())
        Webhook.objects.create(name="off", url="https://x.example.com", is_active=False)

        config = serialize_webhooks()

        self.assertEqual(config["base_url"], "https://pbx.example.com")
        self.assertEqual(len(config["webhooks"]), 1)
        wh = config["webhooks"][0]
        self.assertEqual(wh["name"], "crm")
        self.assertEqual(wh["events"], ["incoming", "ended", "missed", "answered"])
        self.assertEqual(wh["contexts"], ["incoming"])
        self.assertEqual(wh["queues"], ["support"])
        self.assertEqual(wh["secret"], "s3cret")
        self.assertEqual(wh["timeout"], 7)
        self.assertEqual(wh["retries"], 2)

    def test_routing_tables_kept_separate_from_contexts(self):
        """routing_tables filter only the outgoing chain and must not leak into
        the inbound 'contexts' list (a trunk can share a routing table's name
        with a SIP user's context, so merging them would be ambiguous)."""
        webhook = Webhook.objects.create(
            name="crm",
            url="https://crm.example.com/hook",
            send_incoming=True,
            send_outgoing=True,
        )
        webhook.contexts.add(make_context("incoming"))
        webhook.routing_tables.add(make_routing_table("outbound-users"))

        config = serialize_webhooks()

        wh = config["webhooks"][0]
        self.assertEqual(wh["contexts"], ["incoming"])
        self.assertEqual(wh["routing_tables"], ["outbound-users"])
        self.assertIn("outgoing", wh["events"])

    def test_sip_users_map_excludes_trunks(self):
        routing_table = make_routing_table("rt-shared")
        transport = make_transport("shared-transport")
        user = make_sip_user(
            username="1001", routing_table=routing_table, transport=transport
        )
        make_sip_peer("trunk1", routing_table=routing_table, transport=transport)

        config = serialize_webhooks()

        self.assertEqual(config["sip_users"]["1001"], routing_table.name)
        self.assertNotIn("trunk1", config["sip_users"])
        self.assertEqual(user.username, "1001")

    def test_sip_users_map_excludes_users_without_routing_table(self):
        SIPUser.objects.create(
            name="No Routing",
            username="1002",
            extension="1002",
            secret="secret",
            transport=make_transport("transport-1002"),
            routing_table=None,
            auth_type="userpass",
        )

        config = serialize_webhooks()

        self.assertNotIn("1002", config["sip_users"])

    def test_sync_writes_redis_key(self):
        with patch("apps.webhooks.sync.redis.Redis") as redis_cls:
            client = MagicMock()
            redis_cls.from_url.return_value = client
            sync_webhooks_config()
        key, payload = client.set.call_args.args
        self.assertEqual(key, "webhooks:config")
        self.assertIn("webhooks", json.loads(payload))
        client.close.assert_called_once()


class WebhookSignalsTests(TestCase):
    def test_save_triggers_sync(self):
        with patch("apps.webhooks.sync.sync_webhooks_config") as sync:
            Webhook.objects.create(name="crm", url="https://crm.example.com/hook")
        sync.assert_called()

    def test_m2m_change_triggers_sync(self):
        webhook = Webhook.objects.create(name="crm", url="https://crm.example.com/hook")
        queue = make_queue()
        with patch("apps.webhooks.sync.sync_webhooks_config") as sync:
            webhook.queues.add(queue)
        sync.assert_called()

    def test_delete_triggers_sync(self):
        webhook = Webhook.objects.create(name="crm", url="https://crm.example.com/hook")
        with patch("apps.webhooks.sync.sync_webhooks_config") as sync:
            webhook.delete()
        sync.assert_called()

    def test_sip_user_save_triggers_sync(self):
        """The synced 'sip_users' map depends on SIPUser, not just Webhook."""
        with patch("apps.webhooks.sync.sync_webhooks_config") as sync:
            make_sip_user("2001")
        sync.assert_called()


class RoutingTableWebhookDataMigrationTests(TestCase):
    """Covers apps/webhooks/migrations/0006_migrate_routing_table_webhooks.py.

    Runs the migration's RunPython function directly against the current
    model state, which is safe here since 0006 only adds fields after 0005
    (no renames/removals in between) that would require a historical model.
    """

    def _run_migration(self):
        import importlib

        from django.apps import apps as current_apps

        migration_module = importlib.import_module(
            "apps.webhooks.migrations.0006_migrate_routing_table_webhooks"
        )
        migration_module.migrate_routing_table_webhooks(current_apps, None)

    def test_outgoing_only_webhook_translated(self):
        webhook = Webhook.objects.create(
            name="crm",
            url="https://crm.example.com/hook",
            send_incoming=True,
            send_ended=True,
        )
        webhook.routing_tables.add(make_routing_table())

        self._run_migration()
        webhook.refresh_from_db()

        self.assertTrue(webhook.send_outgoing)
        self.assertTrue(webhook.send_outgoing_ended)
        self.assertFalse(webhook.send_outgoing_answered)
        self.assertFalse(webhook.send_incoming)
        self.assertFalse(webhook.send_ended)

    def test_mixed_webhook_keeps_inbound_flags(self):
        webhook = Webhook.objects.create(
            name="crm",
            url="https://crm.example.com/hook",
            send_incoming=True,
            send_ended=True,
        )
        webhook.contexts.add(make_context())
        webhook.routing_tables.add(make_routing_table())

        self._run_migration()
        webhook.refresh_from_db()

        self.assertTrue(webhook.send_outgoing)
        self.assertTrue(webhook.send_outgoing_ended)
        self.assertTrue(webhook.send_incoming)
        self.assertTrue(webhook.send_ended)

    def test_webhook_without_routing_tables_untouched(self):
        webhook = Webhook.objects.create(
            name="crm",
            url="https://crm.example.com/hook",
            send_incoming=True,
            send_ended=True,
        )
        webhook.contexts.add(make_context())

        self._run_migration()
        webhook.refresh_from_db()

        self.assertFalse(webhook.send_outgoing)
        self.assertFalse(webhook.send_outgoing_ended)
        self.assertTrue(webhook.send_incoming)
        self.assertTrue(webhook.send_ended)


class WebhookAdminFormTests(TestCase):
    def form_data(self, **overrides):
        data = {
            "name": "crm",
            "description": "",
            "url": "https://crm.example.com/hook",
            "is_active": True,
            "send_incoming": True,
            "send_ended": True,
            "send_missed": False,
            "send_answered": False,
            "send_outgoing": False,
            "send_outgoing_answered": False,
            "send_outgoing_ended": False,
            "contexts": [],
            "routing_tables": [],
            "queues": [],
            "headers": "{}",
            "secret": "",
            "timeout": 5,
            "retries": 1,
            "payload_template": "",
        }
        data.update(overrides)
        return data

    def test_requires_context_or_queue(self):
        form = WebhookAdminForm(data=self.form_data())
        self.assertFalse(form.is_valid())

    def test_valid_with_queue(self):
        queue = make_queue()
        form = WebhookAdminForm(data=self.form_data(queues=[queue.pk]))
        self.assertTrue(form.is_valid(), form.errors)

    def test_routing_table_alone_does_not_satisfy_inbound_events(self):
        """routing_tables only matches the outgoing chain; inbound flags
        (send_incoming/ended/missed/answered, on by default here) still need
        a context or queue."""
        routing_table = make_routing_table()
        form = WebhookAdminForm(
            data=self.form_data(routing_tables=[routing_table.pk])
        )
        self.assertFalse(form.is_valid())

    def test_valid_outgoing_only_webhook(self):
        routing_table = make_routing_table()
        form = WebhookAdminForm(
            data=self.form_data(
                routing_tables=[routing_table.pk],
                send_incoming=False,
                send_ended=False,
                send_outgoing=True,
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_outgoing_requires_routing_table(self):
        queue = make_queue()
        form = WebhookAdminForm(
            data=self.form_data(
                queues=[queue.pk],
                send_incoming=False,
                send_ended=False,
                send_outgoing=True,
            )
        )
        self.assertFalse(form.is_valid())

    def test_outgoing_answered_requires_outgoing(self):
        routing_table = make_routing_table()
        form = WebhookAdminForm(
            data=self.form_data(
                routing_tables=[routing_table.pk],
                send_incoming=False,
                send_ended=False,
                send_outgoing=False,
                send_outgoing_answered=True,
            )
        )
        self.assertFalse(form.is_valid())

    def test_outgoing_ended_requires_outgoing(self):
        routing_table = make_routing_table()
        form = WebhookAdminForm(
            data=self.form_data(
                routing_tables=[routing_table.pk],
                send_incoming=False,
                send_ended=False,
                send_outgoing=False,
                send_outgoing_ended=True,
            )
        )
        self.assertFalse(form.is_valid())

    def test_outgoing_chain_valid_with_routing_table(self):
        routing_table = make_routing_table()
        form = WebhookAdminForm(
            data=self.form_data(
                routing_tables=[routing_table.pk],
                send_incoming=False,
                send_ended=False,
                send_outgoing=True,
                send_outgoing_answered=True,
                send_outgoing_ended=True,
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_ended_requires_incoming(self):
        queue = make_queue()
        form = WebhookAdminForm(
            data=self.form_data(
                queues=[queue.pk], send_incoming=False, send_ended=True
            )
        )
        self.assertFalse(form.is_valid())

    def test_missed_requires_queue(self):
        context = make_context()
        form = WebhookAdminForm(
            data=self.form_data(contexts=[context.pk], send_missed=True)
        )
        self.assertFalse(form.is_valid())

    def test_answered_requires_queue(self):
        context = make_context()
        form = WebhookAdminForm(
            data=self.form_data(contexts=[context.pk], send_answered=True)
        )
        self.assertFalse(form.is_valid())

    def test_answered_valid_with_queue(self):
        queue = make_queue()
        form = WebhookAdminForm(
            data=self.form_data(queues=[queue.pk], send_answered=True)
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_bad_template_rejected(self):
        queue = make_queue()
        form = WebhookAdminForm(
            data=self.form_data(
                queues=[queue.pk],
                payload_template=json.dumps({"x": "${nope}"}),
            )
        )
        self.assertFalse(form.is_valid())
