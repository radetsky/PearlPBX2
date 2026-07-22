import json
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.webhooks.admin import WebhookAdminForm
from apps.webhooks.models import Webhook, validate_payload_template
from apps.webhooks.sync import serialize_webhooks, sync_webhooks_config
from core.models import DialplanContext, MusicOnHold, Queue, QueueAnnouncements


def make_queue(name="support"):
    moh = MusicOnHold.objects.create(name=f"moh-{name}", mode="files")
    ann = QueueAnnouncements.objects.create(name=f"ann-{name}")
    return Queue.objects.create(
        name=name, music_class=moh, queue_announcement=ann, strategy="ringall"
    )


def make_context(name="incoming"):
    return DialplanContext.objects.create(name=name)


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
            "contexts": [],
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
