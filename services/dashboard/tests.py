"""Unit tests for webhook_sender.WebhookManager (no Django, no network)."""

import asyncio
import hashlib
import hmac
import json
import logging
from unittest.mock import patch

from webhook_sender import (
    NOTIFIED_KEY_PREFIX,
    SIGNATURE_HEADER,
    WEBHOOKS_CONFIG_KEY,
    WebhookManager,
    render_template,
)

logger = logging.getLogger("test")


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


def make_config(**overrides):
    webhook = {
        "name": "crm",
        "url": "https://crm.example.com/hook",
        "events": ["incoming", "ended", "missed", "answered"],
        "contexts": ["incoming"],
        "queues": ["support"],
        "headers": {},
        "secret": "",
        "timeout": 5,
        "retries": 0,
        "payload_template": None,
    }
    webhook.update(overrides)
    return {"webhooks": [webhook], "base_url": "https://pbx.example.com"}


def make_manager(config=None):
    redis = FakeRedis()
    if config is not None:
        redis.store[WEBHOOKS_CONFIG_KEY] = json.dumps(config)
    manager = WebhookManager(redis, logger)
    return manager, redis


def run(coro):
    return asyncio.run(coro)


def fired_events(manager):
    """Patch _fire and return the captured (webhook_name, event, variables) list."""
    calls = []

    def capture(wh, event, variables):
        calls.append((wh["name"], event, dict(variables)))

    manager._fire = capture
    return calls


class TestLoadConfig:
    def test_missing_key_disables(self):
        manager, _ = make_manager(config=None)
        run(manager.load_config())
        assert manager.enabled is False

    def test_valid_config_enables(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        assert manager.enabled is True
        assert manager.base_url == "https://pbx.example.com"

    def test_invalid_json_ignored(self):
        manager, redis = make_manager()
        redis.store[WEBHOOKS_CONFIG_KEY] = "{broken"
        run(manager.load_config())
        assert manager.enabled is False

    def test_config_removal_disables(self):
        manager, redis = make_manager(make_config())
        run(manager.load_config())
        del redis.store[WEBHOOKS_CONFIG_KEY]
        run(manager.load_config())
        assert manager.enabled is False


class TestIncoming:
    def incoming_info(self, **overrides):
        info = {
            "uniqueid": "111.222",
            "caller_id_num": "380501234567",
            "caller_id_name": "Test",
            "exten": "s",
            "context": "incoming",
            "queue": None,
            "recording_expected": None,
        }
        info.update(overrides)
        return info

    def test_context_match_fires_and_marks(self):
        manager, redis = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_incoming(self.incoming_info()))

        assert notified == ["crm"]
        assert calls[0][:2] == ("crm", "call.incoming")
        assert (
            calls[0][2]["recording_url"]
            == "https://pbx.example.com/api/v1/recordings/111.222/"
        )
        marker = json.loads(redis.store[f"{NOTIFIED_KEY_PREFIX}111.222"])
        assert marker["webhooks"] == ["crm"]
        assert marker["call"]["caller_id_num"] == "380501234567"

    def test_no_match_no_marker(self):
        manager, redis = make_manager(make_config(contexts=["other"], queues=[]))
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_incoming(self.incoming_info()))

        assert notified == []
        assert fired == []
        assert f"{NOTIFIED_KEY_PREFIX}111.222" not in redis.store

    def test_queue_match_dedup_after_context_match(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        run(manager.on_incoming(self.incoming_info()))
        notified = run(
            manager.on_incoming(self.incoming_info(queue="support", context=None))
        )

        assert notified == []
        assert len(calls) == 1

    def test_recording_expected_passed_through(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        run(manager.on_incoming(self.incoming_info(recording_expected=True)))

        assert calls[0][2]["recording_expected"] is True


class TestHangup:
    def announce(self, manager):
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": "Test",
                    "exten": "s",
                    "context": "incoming",
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

    def hangup_info(self, **overrides):
        info = {
            "uniqueid": "111.222",
            "cause": "16",
            "cause_txt": "Normal Clearing",
            "variables": {},
        }
        info.update(overrides)
        return info

    def test_ended_only_for_announced(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_hangup(self.hangup_info(uniqueid="999.1")))

        assert notified == []
        assert fired == []

    def test_ended_fires_once_and_deletes_marker(self):
        manager, redis = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        first = run(manager.on_hangup(self.hangup_info()))
        second = run(manager.on_hangup(self.hangup_info()))

        assert first == ["crm"]
        assert second == []
        events = [c[1] for c in calls]
        assert events == ["call.incoming", "call.ended"]
        assert f"{NOTIFIED_KEY_PREFIX}111.222" not in redis.store

    def test_recording_fields_when_recorded(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(
            manager.on_hangup(
                self.hangup_info(
                    variables={
                        "MIXMONITOR": "1",
                        "MIXMONITOR_FILENAME": "/var/spool/asterisk/monitor/2026/07/21/x.wav",
                        "ANSWEREDTIME": "42",
                    }
                )
            )
        )

        variables = calls[-1][2]
        assert variables["recorded"] is True
        assert (
            variables["recording_url"]
            == "https://pbx.example.com/api/v1/recordings/111.222/"
        )
        assert variables["recording_file"].endswith("x.wav")
        assert variables["answered_time"] == "42"

    def test_recording_fields_when_not_recorded(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(manager.on_hangup(self.hangup_info(variables={"MIXMONITOR": "0"})))

        variables = calls[-1][2]
        assert variables["recorded"] is False
        assert variables["recording_url"] is None

    def test_recording_unknown_without_variables(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(manager.on_hangup(self.hangup_info()))

        assert calls[-1][2]["recorded"] is None

    def test_webhook_without_ended_event_not_notified(self):
        manager, _ = make_manager(make_config(events=["incoming"]))
        run(manager.load_config())
        fired = fired_events(manager)
        self.announce(manager)

        notified = run(manager.on_hangup(self.hangup_info()))

        assert notified == []
        assert [c[1] for c in fired] == ["call.incoming"]


class TestAbandon:
    def abandon_info(self, **overrides):
        info = {
            "uniqueid": "111.222",
            "queue": "support",
            "caller_id_num": "380501234567",
            "wait_time": 33,
        }
        info.update(overrides)
        return info

    def test_missed_fires_without_marker(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_abandon(self.abandon_info()))

        assert notified == ["crm"]
        assert calls[0][:2] == ("crm", "call.missed")
        assert calls[0][2]["wait_time"] == 33

    def test_missed_requires_event_subscription(self):
        manager, _ = make_manager(make_config(events=["incoming", "ended"]))
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_abandon(self.abandon_info()))

        assert notified == []
        assert fired == []

    def test_abandon_sets_missed_flag_for_ended(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": None,
                    "exten": "s",
                    "context": "incoming",
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

        run(manager.on_abandon(self.abandon_info()))
        run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                }
            )
        )

        ended = [c for c in calls if c[1] == "call.ended"][0]
        assert ended[2]["missed"] is True


class TestAgentConnect:
    def agent_connect_info(self, **overrides):
        info = {
            "uniqueid": "111.222",
            "queue": "support",
            "caller_id_num": "380501234567",
            "caller_id_name": "Customer",
            "member_name": "Operator Petrenko",
            "member_interface": "PJSIP/101",
            "member_number": "101",
            "ringtime": "3500",
            "holdtime": "18",
        }
        info.update(overrides)
        return info

    def test_answered_fires_without_marker(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_agent_connect(self.agent_connect_info()))

        assert notified == ["crm"]
        assert calls[0][:2] == ("crm", "call.answered")
        variables = calls[0][2]
        assert variables["member_name"] == "Operator Petrenko"
        assert variables["member_interface"] == "PJSIP/101"
        assert variables["member_number"] == "101"
        assert variables["ringtime"] == "3500"
        assert variables["holdtime"] == "18"

    def test_answered_requires_event_subscription(self):
        manager, _ = make_manager(make_config(events=["incoming", "ended"]))
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_agent_connect(self.agent_connect_info()))

        assert notified == []
        assert fired == []

    def test_answered_matches_by_queue_only(self):
        manager, _ = make_manager(make_config(queues=["other-queue"]))
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_agent_connect(self.agent_connect_info()))

        assert notified == []
        assert fired == []

    def test_agent_connect_stamps_marker_for_ended(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": None,
                    "exten": "s",
                    "context": "incoming",
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

        run(manager.on_agent_connect(self.agent_connect_info()))
        run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                }
            )
        )

        ended = [c for c in calls if c[1] == "call.ended"][0]
        assert ended[2]["answered_by_member"] == "Operator Petrenko"
        assert ended[2]["answered_by_interface"] == "PJSIP/101"

    def test_ended_without_agent_connect_has_null_answered_by(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": None,
                    "exten": "s",
                    "context": "incoming",
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

        run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                }
            )
        )

        ended = [c for c in calls if c[1] == "call.ended"][0]
        assert ended[2]["answered_by_member"] is None
        assert ended[2]["answered_by_interface"] is None


class TestDelivery:
    def test_default_body_and_hmac_signature(self):
        manager, _ = make_manager(
            make_config(secret="topsecret", headers={"X-Api-Key": "abc"})
        )
        run(manager.load_config())
        sent = {}

        async def fake_send(name, event, url, body, headers, timeout, retries):
            sent.update(
                {"url": url, "body": body, "headers": headers, "timeout": timeout}
            )

        manager._send_with_retries = fake_send

        async def scenario():
            await manager.on_incoming(
                {
                    "uniqueid": "1.2",
                    "caller_id_num": "100",
                    "caller_id_name": None,
                    "exten": "s",
                    "context": "incoming",
                    "queue": None,
                    "recording_expected": None,
                }
            )
            await manager.wait_pending()

        run(scenario())

        payload = json.loads(sent["body"])
        assert payload["event"] == "call.incoming"
        assert payload["caller_id_num"] == "100"
        expected = hmac.new(b"topsecret", sent["body"], hashlib.sha256).hexdigest()
        assert sent["headers"][SIGNATURE_HEADER] == f"sha256={expected}"
        assert sent["headers"]["X-Api-Key"] == "abc"

    def test_retries_on_failure(self):
        manager, _ = make_manager(make_config(retries=2))
        run(manager.load_config())
        attempts = []

        def failing_post(url, body, headers, timeout):
            attempts.append(url)
            raise OSError("connection refused")

        async def scenario():
            with patch("webhook_sender.post_json", failing_post), patch(
                "webhook_sender.RETRY_DELAY_SECONDS", 0
            ):
                await manager.on_incoming(
                    {
                        "uniqueid": "1.2",
                        "caller_id_num": "100",
                        "caller_id_name": None,
                        "exten": "s",
                        "context": "incoming",
                        "queue": None,
                        "recording_expected": None,
                    }
                )
                await manager.wait_pending()

        run(scenario())
        assert len(attempts) == 3


class TestRenderTemplate:
    def test_substitutes_in_nested_structures(self):
        result = render_template(
            {"phone": "${caller_id_num}", "list": ["${uniqueid}", 5], "n": 1},
            {"caller_id_num": "100", "uniqueid": "1.2"},
        )
        assert result == {"phone": "100", "list": ["1.2", 5], "n": 1}

    def test_none_becomes_empty_string(self):
        result = render_template({"q": "${queue}"}, {"queue": None})
        assert result == {"q": ""}

    def test_unknown_placeholder_left_as_is(self):
        result = render_template({"x": "${not_provided}"}, {})
        assert result == {"x": "${not_provided}"}


class TestExtractMemberNumber:
    def test_pjsip_interface(self):
        from dashboard_listener import extract_member_number

        assert extract_member_number("PJSIP/101") == "101"

    def test_sip_interface_case_insensitive(self):
        from dashboard_listener import extract_member_number

        assert extract_member_number("sip/202") == "202"

    def test_unrecognized_format_returned_unchanged(self):
        from dashboard_listener import extract_member_number

        assert extract_member_number("Local/303@from-queue") == "Local/303@from-queue"

    def test_none_returns_none(self):
        from dashboard_listener import extract_member_number

        assert extract_member_number(None) is None
