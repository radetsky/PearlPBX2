"""Unit tests for webhook_sender.WebhookManager (no Django, no network)."""

import asyncio
import hashlib
import hmac
import json
import logging
from unittest.mock import patch

from webhook_sender import (
    ALL_TEMPLATE_VARIABLES,
    NOTIFIED_KEY_PREFIX,
    SIGNATURE_HEADER,
    WEBHOOKS_CONFIG_KEY,
    WebhookManager,
    extract_endpoint,
    is_dialed_number,
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


def make_config(sip_users=None, **overrides):
    webhook = {
        "name": "crm",
        "url": "https://crm.example.com/hook",
        "events": ["incoming", "ended", "missed", "answered"],
        "contexts": ["incoming"],
        "routing_tables": [],
        "queues": ["support"],
        "headers": {},
        "secret": "",
        "timeout": 5,
        "retries": 0,
        "payload_template": None,
    }
    webhook.update(overrides)
    return {
        "webhooks": [webhook],
        "base_url": "https://pbx.example.com",
        "sip_users": sip_users or {},
    }


def make_manager(config=None, **manager_kwargs):
    redis = FakeRedis()
    if config is not None:
        redis.store[WEBHOOKS_CONFIG_KEY] = json.dumps(config)
    manager = WebhookManager(redis, logger, **manager_kwargs)
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

        notified, direction = run(manager.on_hangup(self.hangup_info(uniqueid="999.1")))

        assert notified == []
        assert direction is None
        assert fired == []

    def test_ended_fires_once_and_deletes_marker(self):
        manager, redis = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        first, first_direction = run(manager.on_hangup(self.hangup_info()))
        second, second_direction = run(manager.on_hangup(self.hangup_info()))

        assert first == ["crm"]
        assert first_direction == "inbound"
        assert second == []
        assert second_direction is None
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

        notified, direction = run(manager.on_hangup(self.hangup_info()))

        assert notified == []
        assert direction == "inbound"
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

    def announce(self, manager, exten="700", context="incoming"):
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": None,
                    "exten": exten,
                    "context": context,
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

    def test_missed_fires_without_marker(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_abandon(self.abandon_info()))

        assert notified == ["crm"]
        assert calls[0][:2] == ("crm", "call.missed")
        assert calls[0][2]["wait_time"] == 33
        assert calls[0][2]["exten"] is None
        assert calls[0][2]["context"] is None

    def test_missed_includes_exten_and_context_from_marker(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(manager.on_abandon(self.abandon_info()))

        missed = [c for c in calls if c[1] == "call.missed"][0]
        assert missed[2]["exten"] == "700"
        assert missed[2]["context"] == "incoming"

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

    def announce(self, manager, exten="700", context="incoming"):
        run(
            manager.on_incoming(
                {
                    "uniqueid": "111.222",
                    "caller_id_num": "380501234567",
                    "caller_id_name": None,
                    "exten": exten,
                    "context": context,
                    "queue": None,
                    "recording_expected": None,
                }
            )
        )

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
        assert variables["exten"] is None
        assert variables["context"] is None

    def test_answered_includes_exten_and_context_from_marker(self):
        manager, _ = make_manager(make_config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(manager.on_agent_connect(self.agent_connect_info()))

        answered = [c for c in calls if c[1] == "call.answered"][0]
        assert answered[2]["exten"] == "700"
        assert answered[2]["context"] == "incoming"

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


class TestOutgoing:
    def outgoing_info(self, **overrides):
        info = {
            "uniqueid": "111.222",
            "channel": "PJSIP/1001-0000000a",
            "caller_id_num": "1001",
            "caller_id_name": "Operator",
            "exten": "0501234567",
            "context": "outbound-users",
        }
        info.update(overrides)
        return info

    def outgoing_config(self, **overrides):
        base = {
            "events": ["outgoing", "outgoing_answered", "outgoing_ended"],
            "contexts": [],
            "queues": [],
            "routing_tables": ["outbound-users"],
        }
        base.update(overrides)
        return make_config(sip_users={"1001": "outbound-users"}, **base)

    def test_sip_user_endpoint_fires_and_marks(self):
        manager, redis = make_manager(self.outgoing_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_outgoing(self.outgoing_info()))

        assert notified == ["crm"]
        assert calls[0][:2] == ("crm", "call.outgoing")
        assert calls[0][2]["direction"] == "outbound"
        marker = json.loads(redis.store[f"{NOTIFIED_KEY_PREFIX}111.222"])
        assert marker["call"]["direction"] == "outbound"
        assert marker["webhooks"] == ["crm"]

    def test_trunk_endpoint_never_fires(self):
        """A SIPPeer/trunk channel must never trigger the outgoing chain,
        even if it shares the routing table's name with a SIP user."""
        manager, _ = make_manager(self.outgoing_config())
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(
            manager.on_outgoing(self.outgoing_info(channel="PJSIP/some-trunk-0000000b"))
        )

        assert notified == []
        assert fired == []

    def test_routing_table_not_matched_by_webhook(self):
        manager, _ = make_manager(self.outgoing_config(routing_tables=["other-rt"]))
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_outgoing(self.outgoing_info()))

        assert notified == []
        assert fired == []

    def test_unrecognized_channel_format_never_fires(self):
        manager, _ = make_manager(self.outgoing_config())
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_outgoing(self.outgoing_info(channel="Local/1001@x")))

        assert notified == []
        assert fired == []

    def test_placeholder_exten_never_fires_by_default(self):
        """A channel Originate()'d but not yet Goto()'d to a real extension
        (exten still "s") is system noise, not a dialed call — skip it."""
        manager, _ = make_manager(self.outgoing_config())
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(manager.on_outgoing(self.outgoing_info(exten="s")))

        assert notified == []
        assert fired == []

    def test_placeholder_exten_fires_when_system_channels_enabled(self):
        manager, redis = make_manager(
            self.outgoing_config(), send_system_channels=True
        )
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(manager.on_outgoing(self.outgoing_info(exten="s")))

        assert notified == ["crm"]
        assert calls[0][2]["exten"] == "s"

    def test_plus_prefixed_number_fires_by_default(self):
        manager, _ = make_manager(self.outgoing_config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(
            manager.on_outgoing(self.outgoing_info(exten="+380671112233"))
        )

        assert notified == ["crm"]
        assert calls[0][2]["exten"] == "+380671112233"

    def test_linkedid_and_channel_vars_pass_through(self):
        manager, _ = make_manager(self.outgoing_config())
        run(manager.load_config())
        calls = fired_events(manager)

        run(
            manager.on_outgoing(
                self.outgoing_info(
                    linkedid="111.111", channel_vars={"ULINE": "42"}
                )
            )
        )

        assert calls[0][2]["linkedid"] == "111.111"
        assert calls[0][2]["channel_vars"] == {"ULINE": "42"}


class TestIsDialedNumber:
    def test_placeholders_rejected(self):
        for exten in ["s", "h", "i", "t", "", None, "failed", "*72"]:
            assert is_dialed_number(exten) is False

    def test_real_numbers_accepted(self):
        for exten in ["279", "380671112233", "+380671112233"]:
            assert is_dialed_number(exten) is True


class TestOutgoingChain:
    def config(self, **overrides):
        base = {
            "events": ["outgoing", "outgoing_answered", "outgoing_ended"],
            "contexts": [],
            "queues": [],
            "routing_tables": ["outbound-users"],
        }
        base.update(overrides)
        return make_config(sip_users={"1001": "outbound-users"}, **base)

    def announce(self, manager):
        return run(
            manager.on_outgoing(
                {
                    "uniqueid": "111.222",
                    "channel": "PJSIP/1001-0000000a",
                    "caller_id_num": "1001",
                    "caller_id_name": "Operator",
                    "exten": "0501234567",
                    "context": "outbound-users",
                }
            )
        )

    def test_full_chain_outgoing_answered_ended(self):
        manager, redis = make_manager(self.config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        answered = run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk1-0000000b",
                }
            )
        )
        ended, direction = run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                }
            )
        )

        assert answered == ["crm"]
        assert ended == ["crm"]
        assert direction == "outbound"
        events = [c[1] for c in calls]
        assert events == ["call.outgoing", "call.outgoing_answered", "call.outgoing_ended"]
        ended_vars = calls[-1][2]
        assert ended_vars["answered"] is True
        assert ended_vars["dial_status"] == "ANSWER"
        assert ended_vars["direction"] == "outbound"
        assert f"{NOTIFIED_KEY_PREFIX}111.222" not in redis.store

    def test_placeholder_exten_suppresses_whole_chain(self):
        """No marker is written for a suppressed system channel, so the
        answered/ended events downstream never fire either."""
        manager, redis = make_manager(self.config())
        run(manager.load_config())
        calls = fired_events(manager)

        notified = run(
            manager.on_outgoing(
                {
                    "uniqueid": "111.222",
                    "channel": "PJSIP/1001-0000000a",
                    "caller_id_num": "1001",
                    "caller_id_name": "Operator",
                    "exten": "s",
                    "context": "outbound-users",
                }
            )
        )
        answered = run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk1-0000000b",
                }
            )
        )
        ended, direction = run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                }
            )
        )

        assert notified == []
        assert answered == []
        assert ended == []
        assert direction is None
        assert calls == []
        assert f"{NOTIFIED_KEY_PREFIX}111.222" not in redis.store

    def test_repeated_dial_end_answer_does_not_duplicate(self):
        manager, _ = make_manager(self.config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        first = run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk1-1",
                }
            )
        )
        second = run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk2-2",
                }
            )
        )

        assert first == ["crm"]
        assert second == []
        assert [c[1] for c in calls] == ["call.outgoing", "call.outgoing_answered"]

    def test_unanswered_call_ended_without_answered_event(self):
        manager, _ = make_manager(self.config())
        run(manager.load_config())
        calls = fired_events(manager)
        self.announce(manager)

        run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "BUSY",
                    "dest_channel": "PJSIP/trunk1-1",
                }
            )
        )
        run(
            manager.on_hangup(
                {
                    "uniqueid": "111.222",
                    "cause": "17",
                    "cause_txt": "User busy",
                    "variables": {},
                }
            )
        )

        events = [c[1] for c in calls]
        assert events == ["call.outgoing", "call.outgoing_ended"]
        ended_vars = calls[-1][2]
        assert ended_vars["answered"] is False
        assert ended_vars["dial_status"] == "BUSY"

    def test_dial_end_ignored_for_inbound_marker(self):
        manager, _ = make_manager(
            make_config(events=["incoming", "ended", "outgoing_answered"])
        )
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

        notified = run(
            manager.on_dial_end(
                {
                    "uniqueid": "111.222",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/101-1",
                }
            )
        )

        assert notified == []
        assert [c[1] for c in calls] == ["call.incoming"]

    def test_dial_end_without_marker_is_noop(self):
        manager, _ = make_manager(self.config())
        run(manager.load_config())
        fired = fired_events(manager)

        notified = run(
            manager.on_dial_end(
                {
                    "uniqueid": "999.1",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk1-1",
                }
            )
        )

        assert notified == []
        assert fired == []


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


class TestFullPlaceholderTemplate:
    """Mirrors apps.webhooks.models.default_payload_template(): a template
    listing every known placeholder, used unmodified for every event type.
    Must go through the real delivery path (_build_body), not `fired_events`
    (which captures pre-render variables), to see the actual JSON sent."""

    FULL_TEMPLATE = {name: f"${{{name}}}" for name in sorted(ALL_TEMPLATE_VARIABLES)}

    @staticmethod
    def capture_sent_body(manager):
        sent = {}

        async def fake_send(name, event, url, body, headers, timeout, retries):
            sent["body"] = body

        manager._send_with_retries = fake_send
        return sent

    def test_incoming_has_no_leftover_placeholders(self):
        manager, _ = make_manager(make_config(payload_template=self.FULL_TEMPLATE))
        run(manager.load_config())
        sent = self.capture_sent_body(manager)

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
        # Fields call.incoming never produces (e.g. from call.ended/answered)
        # must render empty, not leak the literal "${name}" placeholder text.
        for absent_field in ("duration", "cause", "member_name", "ringtime"):
            assert payload[absent_field] == ""
            assert "$" not in payload[absent_field]

    def test_missed_has_no_leftover_placeholders(self):
        manager, _ = make_manager(make_config(payload_template=self.FULL_TEMPLATE))
        run(manager.load_config())
        sent = self.capture_sent_body(manager)

        async def scenario():
            await manager.on_abandon(
                {
                    "uniqueid": "1.2",
                    "queue": "support",
                    "caller_id_num": "100",
                    "wait_time": 15,
                }
            )
            await manager.wait_pending()

        run(scenario())

        payload = json.loads(sent["body"])
        assert payload["event"] == "call.missed"
        assert payload["wait_time"] == "15"
        for absent_field in ("member_name", "recorded", "answered_by_member"):
            assert payload[absent_field] == ""

    def outgoing_config(self, events):
        return make_config(
            sip_users={"1001": "outbound-users"},
            events=events,
            contexts=[],
            queues=[],
            routing_tables=["outbound-users"],
            payload_template=self.FULL_TEMPLATE,
        )

    def test_outgoing_has_no_leftover_placeholders(self):
        manager, _ = make_manager(self.outgoing_config(["outgoing"]))
        run(manager.load_config())
        sent = self.capture_sent_body(manager)

        async def scenario():
            await manager.on_outgoing(
                {
                    "uniqueid": "1.2",
                    "linkedid": "1.1",
                    "channel": "PJSIP/1001-0000000a",
                    "caller_id_num": "1001",
                    "caller_id_name": "Operator",
                    "exten": "0501234567",
                    "context": "outbound-users",
                    "channel_vars": {"ULINE": "42"},
                }
            )
            await manager.wait_pending()

        run(scenario())

        payload = json.loads(sent["body"])
        assert payload["event"] == "call.outgoing"
        assert payload["direction"] == "outbound"
        assert payload["linkedid"] == "1.1"
        assert payload["channel"] == "PJSIP/1001-0000000a"
        # channel_vars is a placeholder standing in for the whole value, so it
        # must survive as a JSON object, not get stringified into "${...}".
        assert payload["channel_vars"] == {"ULINE": "42"}
        for absent_field in ("duration", "cause", "member_name", "dest_channel"):
            assert "$" not in payload[absent_field]

    def test_outgoing_answered_has_no_leftover_placeholders(self):
        manager, _ = make_manager(self.outgoing_config(["outgoing", "outgoing_answered"]))
        run(manager.load_config())
        sent = self.capture_sent_body(manager)

        async def scenario():
            await manager.on_outgoing(
                {
                    "uniqueid": "1.2",
                    "channel": "PJSIP/1001-0000000a",
                    "caller_id_num": "1001",
                    "caller_id_name": "Operator",
                    "exten": "0501234567",
                    "context": "outbound-users",
                }
            )
            await manager.on_dial_end(
                {
                    "uniqueid": "1.2",
                    "dial_status": "ANSWER",
                    "dest_channel": "PJSIP/trunk1-0000000b",
                }
            )
            await manager.wait_pending()

        run(scenario())

        payload = json.loads(sent["body"])
        assert payload["event"] == "call.outgoing_answered"
        assert payload["dest_channel"] == "PJSIP/trunk1-0000000b"
        for absent_field in ("duration", "cause", "member_name"):
            assert "$" not in payload[absent_field]

    def test_outgoing_ended_has_no_leftover_placeholders(self):
        manager, _ = make_manager(self.outgoing_config(["outgoing", "outgoing_ended"]))
        run(manager.load_config())
        sent = self.capture_sent_body(manager)

        async def scenario():
            await manager.on_outgoing(
                {
                    "uniqueid": "1.2",
                    "linkedid": "1.1",
                    "channel": "PJSIP/1001-0000000a",
                    "caller_id_num": "1001",
                    "caller_id_name": "Operator",
                    "exten": "0501234567",
                    "context": "outbound-users",
                }
            )
            await manager.on_hangup(
                {
                    "uniqueid": "1.2",
                    "cause": "16",
                    "cause_txt": "Normal Clearing",
                    "variables": {},
                    "channel_vars": {"ULINE": "42"},
                }
            )
            await manager.wait_pending()

        run(scenario())

        payload = json.loads(sent["body"])
        assert payload["event"] == "call.outgoing_ended"
        assert payload["direction"] == "outbound"
        # linkedid/channel are announced once on call.outgoing and must still
        # be present here, echoed from the marker rather than re-passed.
        assert payload["linkedid"] == "1.1"
        assert payload["channel"] == "PJSIP/1001-0000000a"
        assert payload["channel_vars"] == {"ULINE": "42"}
        for field in ("duration", "cause", "member_name", "answered", "dial_status"):
            assert "$" not in payload[field]


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

    def test_whole_placeholder_dict_value_kept_as_object(self):
        result = render_template(
            {"channel_vars": "${channel_vars}"}, {"channel_vars": {"ULINE": "42"}}
        )
        assert result == {"channel_vars": {"ULINE": "42"}}

    def test_dict_value_embedded_in_larger_string_is_stringified(self):
        """Only a template string that IS exactly one placeholder gets the
        object substitution; embedding it in surrounding text falls back to
        normal string substitution of the dict's str()."""
        result = render_template(
            {"note": "vars: ${channel_vars}"}, {"channel_vars": {"ULINE": "42"}}
        )
        assert result == {"note": "vars: {'ULINE': '42'}"}

    def test_empty_dict_value_kept_as_object(self):
        result = render_template({"channel_vars": "${channel_vars}"}, {"channel_vars": {}})
        assert result == {"channel_vars": {}}


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


class TestExtractEndpoint:
    def test_pjsip_channel(self):
        assert extract_endpoint("PJSIP/1001-0000000a") == "1001"

    def test_sip_channel_case_insensitive(self):
        assert extract_endpoint("sip/202-0000000b") == "202"

    def test_endpoint_name_with_hyphen(self):
        assert extract_endpoint("PJSIP/user-01-0000000c") == "user-01"

    def test_unrecognized_format_returns_none(self):
        assert extract_endpoint("Local/303@from-queue") is None

    def test_none_returns_none(self):
        assert extract_endpoint(None) is None
