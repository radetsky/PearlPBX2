# ami_listener.py
import argparse
import os
import asyncio
import json
import logging
import signal
import sys
import time
from collections import defaultdict

import threading

import redis.asyncio as redis

from asterisk.ami import AMIClient, SimpleAction
from datetime import datetime

import re

from webhook_sender import WebhookManager, post_json

_MEMBER_INTERFACE_RE = re.compile(r"^(?:SIP|PJSIP)/(.+)$", re.IGNORECASE)


def extract_member_number(member_interface):
    """Extract the plain extension/number from a queue member interface,
    e.g. "PJSIP/101" -> "101". Returns the input unchanged if it doesn't match."""
    if not member_interface:
        return None
    match = _MEMBER_INTERFACE_RE.match(member_interface)
    return match.group(1) if match else member_interface


def _post_to_slack(webhook_url, text, username, timeout):
    """Send a plain-text message to a Slack incoming webhook."""
    payload = json.dumps({"text": text, "username": username}).encode("utf-8")
    return post_json(webhook_url, payload, {}, timeout)


def _build_missed_slack_text(entries):
    """Format a list of missed-call buffer entries into a Slack message string."""
    by_queue = defaultdict(list)
    for e in entries:
        by_queue[e["queue"]].append((e["caller_id"], e["time_hhmm"]))
    sections = []
    for q, calls in by_queue.items():
        lines = "\n".join(f"• {cid}  {t}" for cid, t in calls)
        sections.append(f"*Missed calls (queue: {q})*\n{lines}")
    return "\n\n".join(sections)


class EventWrapper:
    def __init__(self, event):
        self.event = event

    def get(self, key, default=None):
        return self.event.keys.get(key, default)


REDIS_STATE_TTL = (
    7200  # seconds; health check refreshes every 30s, so 2h gives ample recovery window
)
MEMBER_PAUSED_KEY_PREFIX = "asterisk:member_paused:"


class DashboardAMIListener:
    def __init__(self, **kwargs):
        self.params = kwargs
        self.logger = self.setup_logging()
        self.ami = self.ami_connect()
        self.running = True
        self.manager = None
        self._reconnecting = False
        self._reconnect_lock = threading.Lock()
        self.redis_client = self.connect_redis()
        self.queue_state = {}
        self.channels_state = {}  # State of all active channels
        self.event_handlers = self.set_event_handlers()
        self.webhooks = WebhookManager(self.redis_client, self.logger)

        self.slack_webhook_url = self.params.get("slack_missed_call_webhook_url", "")
        self.slack_timeout = int(self.params.get("slack_timeout", 4))
        self.slack_username = self.params.get("slack_username", "PearlPBX2")
        self.missed_debounce = int(self.params.get("missed_call_debounce_seconds", 60))
        self._missed_buffer = []
        self._missed_flush_task = None

    def set_event_handlers(self):
        event_handlers = {
            # Channel events
            "Newchannel": self.handle_newchannel,
            "Newstate": self.handle_newstate,
            "DialBegin": self.handle_dial_begin,
            "DialEnd": self.handle_dial_end,
            "BridgeCreate": self.handle_bridge_create,
            "BridgeEnter": self.handle_bridge_enter,
            "BridgeLeave": self.handle_bridge_leave,
            "Hangup": self.handle_hangup,
            "Newexten": self.handle_newexten,
            "VarSet": self.handle_varset,
            # CoreShowChannels response (used for state restore after reconnect)
            "CoreShowChannel": self.handle_core_show_channel,
            "CoreShowChannelsComplete": self.handle_core_show_channels_complete,
            # Queue events
            "QueueParams": self.handle_queue_params,
            "QueueMemberStatus": self.handle_queue_member_status,
            "QueueMemberPause": self.handle_queue_member_status,
            "QueueMemberUnpause": self.handle_queue_member_status,
            "QueueMember": self.handle_queue_member,
            "QueueCallerJoin": self.handle_queue_caller_join,
            "QueueCallerLeave": self.handle_queue_caller_leave,
            "QueueCallerAbandon": self.handle_queue_caller_abandon,
            "AgentConnect": self.handle_agent_connect,
        }
        return event_handlers

    def setup_logging(self):
        logger = logging.getLogger("dashboard")
        loglevel = self.params.get("loglevel", logging.DEBUG)
        logging.basicConfig(
            level=loglevel, format="%(asctime)s %(process)d %(levelname)s %(message)s"
        )
        return logger

    def ami_connect(self):
        self.logger.debug("Connecting to the asterisk manager interface")
        ami_host = self.params.get("ami_host", "127.0.0.1")
        ami_port = int(self.params.get("ami_port", 5038))
        ami_user = self.params.get("ami_user")
        ami_pass = self.params.get("ami_pass")

        client = AMIClient(address=ami_host, port=ami_port, timeout=3600)
        client.login(username=ami_user, secret=ami_pass)
        client.add_event_listener(
            on_disconnect=self.on_disconnect,
        )
        return client

    def on_disconnect(self):
        self.logger.warning("AMI disconnected (callback triggered)")
        self._start_reconnect()

    def _start_reconnect(self):
        with self._reconnect_lock:
            if self._reconnecting:
                return
            self._reconnecting = True
        t = threading.Thread(
            target=self._reconnect_loop, daemon=True, name="ami-reconnect"
        )
        t.start()

    def _reconnect_loop(self):
        self.logger.warning("AMI reconnect loop started, retrying every 5s...")
        while self.running:
            try:
                self.ami = self.ami_connect()
                if not self.loop.is_closed():
                    self.ami.add_event_listener(on_event=self.event_listener_sync)
                    asyncio.run_coroutine_threadsafe(self._on_reconnected(), self.loop)
                self.logger.info("AMI reconnected successfully")
                break
            except Exception as e:
                self.logger.error(f"Reconnect attempt failed: {e}, retrying in 5s...")
                time.sleep(5)
        with self._reconnect_lock:
            self._reconnecting = False

    async def _on_reconnected(self):
        """Clear stale state and reinitialize after AMI reconnect."""
        self.logger.info("Clearing stale state after AMI reconnect...")
        self.channels_state.clear()
        self.queue_state.clear()
        await self.update_channels_state()
        await self.publish_event("system_reset", {})
        await self.restore_pause_states()
        await asyncio.sleep(
            1
        )  # allow QueuePause actions to propagate before state refresh
        self.initialize_queue_state()
        self.initialize_channels_state()
        self.logger.info("State reinitialized after AMI reconnect")

    def connect_redis(self):
        """Connect to Redis."""
        redis_client = redis.from_url(
            f"redis://{self.params['redis_host']}:{self.params['redis_port']}",
            decode_responses=True,
        )
        self.logger.info("Connected to Redis")
        return redis_client

    async def publish_event(self, event_type, data):
        """Publish event to Redis Pub/Sub."""
        try:
            message = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

            await self.redis_client.publish("asterisk:events", json.dumps(message))

            self.logger.debug(f"Published event: {event_type} {data}")
        except Exception as e:
            self.logger.error(f"Error publishing event: {e}")

    async def update_queue_state(self, queue_name):
        """Update queue state in Redis."""
        try:
            state_key = f"asterisk:queue:{queue_name}"
            await self.redis_client.setex(
                state_key,
                REDIS_STATE_TTL,
                json.dumps(self.queue_state.get(queue_name, {})),
            )
        except Exception as e:
            self.logger.error(f"Error updating queue state: {e}")

    async def update_channels_state(self):
        """Update all channels state in Redis."""
        try:
            await self.redis_client.setex(
                "asterisk:channels:all",
                REDIS_STATE_TTL,
                json.dumps(self.channels_state),
            )
        except Exception as e:
            self.logger.error(f"Error updating channels state: {e}")

    async def update_channel_state(self, channel_name, channel_data):
        """Update individual channel state in Redis."""
        try:
            await self.redis_client.setex(
                f"asterisk:channel:{channel_name}",
                REDIS_STATE_TTL,
                json.dumps(channel_data),
            )
        except Exception as e:
            self.logger.error(f"Error updating channel state: {e}")

    async def update_uid_state(self, uniqueid: str, channel_name: str):
        """Store uniqueid -> channel mapping for ULINE sweep."""
        try:
            await self.redis_client.setex(
                f"asterisk:uid:{uniqueid}",
                REDIS_STATE_TTL,
                channel_name,
            )
        except Exception as e:
            self.logger.error(f"Error updating uid state: {e}")

    async def delete_uid_state(self, uniqueid: str):
        """Delete uniqueid mapping on Hangup."""
        try:
            await self.redis_client.delete(f"asterisk:uid:{uniqueid}")
        except Exception as e:
            self.logger.error(f"Error deleting uid state: {e}")

    def _build_channel_state(self, event):
        return {
            "channel": event.get("Channel"),
            "uniqueid": event.get("Uniqueid"),
            "state": event.get("ChannelState"),
            "state_desc": event.get("ChannelStateDesc"),
            "caller_id_num": event.get("CallerIDNum"),
            "caller_id_name": event.get("CallerIDName"),
            "connected_line_num": event.get("ConnectedLineNum"),
            "context": event.get("Context"),
            "exten": event.get("Exten"),
            "created_at": datetime.now().isoformat(),
            "duration": 0,
            "bridge_id": event.get("BridgeId"),
            "application": event.get("Application"),
        }

    def _ensure_queue_state(self, queue_name):
        if queue_name not in self.queue_state:
            self.queue_state[queue_name] = {
                "members": {},
                "calls": {},
                "stats": {"waiting": 0, "answered": 0},
            }

    # ============ CHANNEL EVENT HANDLERS ============

    async def handle_newchannel(self, event):
        """Handle new channel creation."""
        channel = event.get("Channel")
        uniqueid = event.get("Uniqueid")
        caller_id_num = event.get("CallerIDNum")
        caller_id_name = event.get("CallerIDName")
        channel_state_desc = event.get("ChannelStateDesc")
        context = event.get("Context")
        exten = event.get("Exten")

        self.channels_state[channel] = self._build_channel_state(event)

        await self.update_channel_state(channel, self.channels_state[channel])
        await self.update_uid_state(uniqueid, channel)
        await self.update_channels_state()

        await self.publish_event(
            "channel_new",
            {
                "channel": channel,
                "uniqueid": uniqueid,
                "caller_id_num": caller_id_num,
                "caller_id_name": caller_id_name,
                "state": channel_state_desc,
                "context": context,
                "exten": exten,
            },
        )

        if self.webhooks.enabled:
            notified = await self.webhooks.on_incoming(
                {
                    "uniqueid": uniqueid,
                    "caller_id_num": caller_id_num,
                    "caller_id_name": caller_id_name,
                    "exten": exten,
                    "context": context,
                    "queue": None,
                    # AGI that decides on recording has not run yet at Newchannel
                    "recording_expected": None,
                }
            )
            if notified:
                await self.publish_event(
                    "call_incoming",
                    {
                        "uniqueid": uniqueid,
                        "channel": channel,
                        "caller_id_num": caller_id_num,
                        "caller_id_name": caller_id_name,
                        "context": context,
                        "exten": exten,
                        "webhooks": notified,
                    },
                )

            outgoing_notified = await self.webhooks.on_outgoing(
                {
                    "uniqueid": uniqueid,
                    "channel": channel,
                    "caller_id_num": caller_id_num,
                    "caller_id_name": caller_id_name,
                    "exten": exten,
                    "context": context,
                }
            )
            if outgoing_notified:
                await self.publish_event(
                    "call_outgoing",
                    {
                        "uniqueid": uniqueid,
                        "channel": channel,
                        "caller_id_num": caller_id_num,
                        "caller_id_name": caller_id_name,
                        "context": context,
                        "exten": exten,
                        "webhooks": outgoing_notified,
                    },
                )

        self.logger.info(
            f"New channel: {channel} ({caller_id_num}) - {channel_state_desc}"
        )

    async def handle_newstate(self, event):
        """Handle channel state change."""
        channel = event.get("Channel")
        channel_state = event.get("ChannelState")
        channel_state_desc = event.get("ChannelStateDesc")
        uniqueid = event.get("Uniqueid")

        if channel in self.channels_state:
            self.channels_state[channel]["state"] = channel_state
            self.channels_state[channel]["state_desc"] = channel_state_desc

            await self.update_channel_state(channel, self.channels_state[channel])
            await self.update_channels_state()

        # Always update uid mapping regardless of in-memory state (restart-safety)
        await self.update_uid_state(uniqueid, channel)

        await self.publish_event(
            "channel_state_change",
            {"channel": channel, "uniqueid": uniqueid, "state": channel_state_desc},
        )

        self.logger.info(f"Channel state change: {channel} -> {channel_state_desc}")

    async def handle_dial_begin(self, event):
        """Handle dial begin."""
        channel = event.get("Channel")
        destination = event.get("DestChannel")
        caller_id_num = event.get("CallerIDNum")
        dest_caller_id_num = event.get("DestCallerIDNum")
        uniqueid = event.get("Uniqueid")
        dest_uniqueid = event.get("DestUniqueid")

        # Update both channels
        if channel in self.channels_state:
            self.channels_state[channel]["dialing_to"] = destination
            self.channels_state[channel]["dest_uniqueid"] = dest_uniqueid
            await self.update_channel_state(channel, self.channels_state[channel])

        if destination in self.channels_state:
            self.channels_state[destination]["dialed_by"] = channel
            await self.update_channel_state(
                destination, self.channels_state[destination]
            )

        await self.update_channels_state()

        await self.publish_event(
            "channel_dial_begin",
            {
                "channel": channel,
                "destination": destination,
                "caller_id_num": caller_id_num,
                "dest_caller_id_num": dest_caller_id_num,
                "uniqueid": uniqueid,
                "dest_uniqueid": dest_uniqueid,
            },
        )

        self.logger.info(
            f"Dial begin: {channel} -> {destination} ({caller_id_num} -> {dest_caller_id_num})"
        )

    async def handle_dial_end(self, event):
        """Handle dial end (answered or rejected)."""
        channel = event.get("Channel")
        destination = event.get("DestChannel")
        # ANSWER, BUSY, NOANSWER, CANCEL, etc.
        dial_status = event.get("DialStatus")
        uniqueid = event.get("Uniqueid")

        if channel in self.channels_state:
            self.channels_state[channel]["dial_status"] = dial_status
            await self.update_channel_state(channel, self.channels_state[channel])

        await self.update_channels_state()

        await self.publish_event(
            "channel_dial_end",
            {
                "channel": channel,
                "destination": destination,
                "dial_status": dial_status,
                "uniqueid": uniqueid,
            },
        )

        if self.webhooks.enabled:
            notified = await self.webhooks.on_dial_end(
                {
                    "uniqueid": uniqueid,
                    "dial_status": dial_status,
                    "dest_channel": destination,
                }
            )
            if notified:
                await self.publish_event(
                    "call_outgoing_answered",
                    {
                        "uniqueid": uniqueid,
                        "channel": channel,
                        "destination": destination,
                        "dial_status": dial_status,
                        "webhooks": notified,
                    },
                )

        self.logger.info(
            f"Dial end: {channel} -> {destination} (status: {dial_status})"
        )

    async def handle_bridge_create(self, event):
        """Handle bridge creation (two channels joined)."""
        bridge_uniqueid = event.get("BridgeUniqueid")
        bridge_type = event.get("BridgeType")
        bridge_technology = event.get("BridgeTechnology")

        await self.publish_event(
            "bridge_create",
            {
                "bridge_id": bridge_uniqueid,
                "bridge_type": bridge_type,
                "bridge_technology": bridge_technology,
            },
        )

        self.logger.info(f"Bridge created: {bridge_uniqueid} ({bridge_type})")

    async def handle_bridge_enter(self, event):
        """Handle channel entering a bridge."""
        channel = event.get("Channel")
        bridge_uniqueid = event.get("BridgeUniqueid")
        uniqueid = event.get("Uniqueid")

        if channel in self.channels_state:
            self.channels_state[channel]["bridge_id"] = bridge_uniqueid
            self.channels_state[channel]["bridged_at"] = datetime.now().isoformat()
            await self.update_channel_state(channel, self.channels_state[channel])

        await self.update_channels_state()

        await self.publish_event(
            "channel_bridge_enter",
            {"channel": channel, "bridge_id": bridge_uniqueid, "uniqueid": uniqueid},
        )

        self.logger.info(f"Channel entered bridge: {channel} -> {bridge_uniqueid}")

    async def handle_bridge_leave(self, event):
        """Handle channel leaving a bridge."""
        channel = event.get("Channel")
        bridge_uniqueid = event.get("BridgeUniqueid")
        uniqueid = event.get("Uniqueid")

        if channel in self.channels_state:
            self.channels_state[channel]["bridge_id"] = None
            await self.update_channel_state(channel, self.channels_state[channel])

        await self.update_channels_state()

        await self.publish_event(
            "channel_bridge_leave",
            {"channel": channel, "bridge_id": bridge_uniqueid, "uniqueid": uniqueid},
        )

        self.logger.info(f"Channel left bridge: {channel} <- {bridge_uniqueid}")

    async def handle_hangup(self, event):
        """Handle channel hangup."""
        channel = event.get("Channel")
        uniqueid = event.get("Uniqueid")
        cause = event.get("Cause")
        cause_txt = event.get("Cause-txt")

        channel_data = self.channels_state.get(channel, {})

        await self.publish_event(
            "channel_hangup",
            {
                "channel": channel,
                "uniqueid": uniqueid,
                "cause": cause,
                "cause_txt": cause_txt,
                "duration": channel_data.get("duration", 0),
            },
        )

        notified, direction = await self.webhooks.on_hangup(
            {
                "uniqueid": uniqueid,
                "cause": cause,
                "cause_txt": cause_txt,
                "variables": channel_data.get("variables", {}),
            }
        )
        if notified:
            event_name = "call_outgoing_ended" if direction == "outbound" else "call_ended"
            await self.publish_event(
                event_name,
                {
                    "uniqueid": uniqueid,
                    "channel": channel,
                    "cause": cause,
                    "cause_txt": cause_txt,
                    "webhooks": notified,
                },
            )

        # Remove channel from in-memory state
        if channel in self.channels_state:
            del self.channels_state[channel]

        # Remove from Redis
        try:
            await self.redis_client.delete(f"asterisk:channel:{channel}")
        except Exception as e:
            self.logger.error(f"Error deleting channel from Redis: {e}")

        # Remove uniqueid mapping (used by ULINE sweep)
        await self.delete_uid_state(uniqueid)

        # Release ULINE if one was allocated for this call
        try:
            n_str = await self.redis_client.get(f"parking:uid:{uniqueid}")
            if n_str:
                await self.redis_client.delete(
                    f"parking:uline:{n_str}",
                    f"parking:uid:{uniqueid}",
                )
                self.logger.info(
                    f"Released ULINE {n_str} for {channel} (uniqueid={uniqueid})"
                )
        except Exception as e:
            self.logger.error(f"Error releasing ULINE for {uniqueid}: {e}")

        await self.update_channels_state()

        self.logger.info(f"Channel hangup: {channel} (cause: {cause_txt})")

    async def handle_newexten(self, event):
        """Handle dialplan execution (application/exten)."""
        channel = event.get("Channel")
        context = event.get("Context")
        exten = event.get("Extension")
        application = event.get("Application")
        app_data = event.get("AppData")
        uniqueid = event.get("Uniqueid")

        if channel in self.channels_state:
            self.channels_state[channel]["context"] = context
            self.channels_state[channel]["exten"] = exten
            self.channels_state[channel]["application"] = application
            self.channels_state[channel]["app_data"] = app_data
            await self.update_channel_state(channel, self.channels_state[channel])

        await self.publish_event(
            "channel_application",
            {
                "channel": channel,
                "uniqueid": uniqueid,
                "context": context,
                "exten": exten,
                "application": application,
                "app_data": app_data,
            },
        )

        self.logger.debug(
            f"Channel {channel}: {application}({app_data}) in {context},{exten}"
        )

    async def handle_varset(self, event):
        """Handle channel variable set."""
        channel = event.get("Channel")
        variable = event.get("Variable")
        value = event.get("Value")
        uniqueid = event.get("Uniqueid")

        # Track only important variables
        important_vars = [
            "ANSWEREDTIME",
            "DIALEDTIME",
            "HANGUPCAUSE",
            "CDR(billsec)",
            "MIXMONITOR",
            "MIXMONITOR_FILENAME",
        ]

        if variable in important_vars:
            if channel in self.channels_state:
                if "variables" not in self.channels_state[channel]:
                    self.channels_state[channel]["variables"] = {}
                self.channels_state[channel]["variables"][variable] = value
                await self.update_channel_state(channel, self.channels_state[channel])

            await self.publish_event(
                "channel_variable",
                {
                    "channel": channel,
                    "uniqueid": uniqueid,
                    "variable": variable,
                    "value": value,
                },
            )

    async def handle_core_show_channel(self, event):
        """Handle CoreShowChannel event — restores channel state after reconnect."""
        channel = event.get("Channel")
        uniqueid = event.get("Uniqueid")
        if not channel or channel in self.channels_state:
            return

        self.channels_state[channel] = self._build_channel_state(event)

        await asyncio.gather(
            self.update_channel_state(channel, self.channels_state[channel]),
            self.update_uid_state(uniqueid, channel),
        )
        self.logger.debug(f"Restored channel from CoreShowChannels: {channel}")

    async def handle_core_show_channels_complete(self, event):
        """Flush aggregate channel state to Redis once CoreShowChannels bulk is done."""
        await self.update_channels_state()
        await self.publish_event("channels_ready", {})
        self.logger.debug("CoreShowChannels complete, snapshot published to browser")

    # ============ QUEUE EVENT HANDLERS ============

    async def handle_queue_params(self, event):
        """Handle queue parameters event."""
        # Event: QueueParams
        # Queue: DEFAULT
        # Max: 0
        # Strategy: ringall
        # Calls: 0
        # Holdtime: 0
        # TalkTime: 33
        # Completed: 3
        # Abandoned: 0
        # ServiceLevel: 0
        # ServicelevelPerf: 66.7
        # ServicelevelPerf2: 66.7
        # Weight: 0

        queue_name = event.get("Queue")
        self._ensure_queue_state(queue_name)
        # Store additional queue parameters if needed
        self.queue_state[queue_name]["params"] = {
            "max": event.get("Max"),
            "strategy": event.get("Strategy"),
            "calls": event.get("Calls"),
            "holdtime": event.get("Holdtime"),
            "talktime": event.get("TalkTime"),
            "completed": event.get("Completed"),
            "abandoned": event.get("Abandoned"),
            "service_level": event.get("ServiceLevel"),
            "service_level_perf": event.get("ServicelevelPerf"),
            "service_level_perf2": event.get("ServicelevelPerf2"),
            "weight": event.get("Weight"),
        }
        self.logger.debug(f"Queue {queue_name} parameters updated")

    async def persist_member_pause(self, interface, paused):
        key = f"{MEMBER_PAUSED_KEY_PREFIX}{interface}"
        try:
            if paused:
                await self.redis_client.set(key, "1")
            else:
                await self.redis_client.delete(key)
        except Exception as e:
            self.logger.error(f"Failed to persist pause state for {interface}: {e}")

    async def load_paused_members(self):
        paused = []
        try:
            async for key in self.redis_client.scan_iter(
                match=f"{MEMBER_PAUSED_KEY_PREFIX}*"
            ):
                paused.append(key.removeprefix(MEMBER_PAUSED_KEY_PREFIX))
        except Exception as e:
            self.logger.error(f"Failed to load paused members from Redis: {e}")
        return paused

    async def restore_pause_states(self):
        paused_interfaces = await self.load_paused_members()
        for interface in paused_interfaces:
            try:
                action = SimpleAction("QueuePause", Interface=interface, Paused="true")
                self.ami.send_action(action)
                self.logger.info(f"Restored pause state for {interface}")
            except Exception as e:
                self.logger.error(f"Failed to restore pause for {interface}: {e}")
        if paused_interfaces:
            self.logger.info(
                f"Restored pause state for {len(paused_interfaces)} members"
            )

    async def _upsert_queue_member(self, queue_name, member_name, event):
        self._ensure_queue_state(queue_name)
        status = event.get("Status")
        paused = event.get("Paused", "0") == "1"
        calls_taken = int(event.get("CallsTaken", "0"))
        last_update = datetime.now().isoformat()

        old_member = self.queue_state[queue_name]["members"].get(member_name, {})
        location = event.get("Location") or event.get("StateInterface")
        if location and old_member.get("paused") != paused:
            await self.persist_member_pause(location, paused)

        existing = self.queue_state[queue_name]["members"].get(member_name, {})
        member = {
            "name": member_name,
            "status": status,
            "paused": paused,
            "calls_taken": calls_taken,
            "last_update": last_update,
            "logintime": event.get("LoginTime"),
            "location": event.get("Location") or event.get("Interface") or existing.get("location"),
            "state_interface": event.get("StateInterface") or existing.get("state_interface"),
            "membership": event.get("Membership"),
            "penalty": event.get("Penalty"),
            "last_call": event.get("LastCall"),
            "last_pause": event.get("LastPause"),
            "in_call": event.get("InCall"),
            "paused_reason": event.get("PausedReason"),
            "wrapup_time": event.get("Wrapuptime"),
        }
        self.queue_state[queue_name]["members"][member_name] = member

        await self.update_queue_state(queue_name)
        await self.publish_event("queue_member_status", {"queue": queue_name, **member})

        self.logger.info(
            f"Queue {queue_name}: Member {member_name} status={status}, paused={paused}"
        )

    async def handle_queue_member_status(self, event):
        """Handle queue member status update (live event)."""
        await self._upsert_queue_member(
            event.get("Queue"), event.get("MemberName"), event
        )

    async def handle_queue_member(self, event):
        """Handle queue member event (bulk QueueStatus response)."""
        await self._upsert_queue_member(event.get("Queue"), event.get("Name"), event)

    async def handle_queue_caller_join(self, event):
        """Handle caller joining a queue."""
        queue_name = event.get("Queue")
        caller_id = event.get("CallerIDNum")
        position = event.get("Position")
        uniqueid = event.get("Uniqueid")
        channel = event.get("Channel")

        self._ensure_queue_state(queue_name)

        self.queue_state[queue_name]["calls"][uniqueid] = {
            "caller_id": caller_id,
            "channel": channel,
            "position": position,
            "join_time": datetime.now().isoformat(),
            "wait_time": 0,
        }

        self.queue_state[queue_name]["stats"]["waiting"] = len(
            self.queue_state[queue_name]["calls"]
        )

        await self.update_queue_state(queue_name)

        await self.publish_event(
            "queue_caller_join",
            {
                "queue": queue_name,
                "caller_id": caller_id,
                "channel": channel,
                "position": position,
                "unique_id": uniqueid,
            },
        )

        if self.webhooks.enabled:
            channel_data = self.channels_state.get(channel, {})
            mixmonitor = channel_data.get("variables", {}).get("MIXMONITOR")
            notified = await self.webhooks.on_incoming(
                {
                    "uniqueid": uniqueid,
                    "caller_id_num": caller_id,
                    "caller_id_name": event.get("CallerIDName"),
                    "exten": channel_data.get("exten"),
                    "context": channel_data.get("context"),
                    "queue": queue_name,
                    # AGI usually runs before Queue(), so MIXMONITOR is known here
                    "recording_expected": None if mixmonitor is None else mixmonitor == "1",
                }
            )
            if notified:
                await self.publish_event(
                    "call_incoming",
                    {
                        "uniqueid": uniqueid,
                        "channel": channel,
                        "caller_id_num": caller_id,
                        "queue": queue_name,
                        "webhooks": notified,
                    },
                )

        self.logger.info(
            f"Queue {queue_name}: Caller {caller_id} joined (position {position})"
        )

    @staticmethod
    def _queue_wait_time(call):
        join_time = (call or {}).get("join_time")
        if not join_time:
            return None
        try:
            return int((datetime.now() - datetime.fromisoformat(join_time)).total_seconds())
        except ValueError:
            return None

    async def _remove_caller_from_queue(self, queue_name, uniqueid):
        call = self.queue_state.get(queue_name, {}).get("calls", {}).pop(uniqueid, None)
        if call is not None:
            self.queue_state[queue_name]["stats"]["waiting"] = len(
                self.queue_state[queue_name]["calls"]
            )
            await self.update_queue_state(queue_name)
        return call

    async def handle_queue_caller_leave(self, event):
        """Handle caller leaving a queue."""
        queue_name = event.get("Queue")
        uniqueid = event.get("Uniqueid")
        await self._remove_caller_from_queue(queue_name, uniqueid)
        await self.publish_event(
            "queue_caller_leave", {"queue": queue_name, "unique_id": uniqueid}
        )
        self.logger.info(f"Queue {queue_name}: Call {uniqueid} left")

    async def handle_queue_caller_abandon(self, event):
        queue_name = event.get("Queue")
        uniqueid = event.get("Uniqueid")
        call = await self._remove_caller_from_queue(queue_name, uniqueid)
        caller_id = call.get("caller_id") if call else None
        await self.publish_event(
            "queue_caller_abandon",
            {"queue": queue_name, "unique_id": uniqueid, "caller_id": caller_id},
        )
        self.logger.info(
            f"Queue {queue_name}: Call {uniqueid} abandoned (caller: {caller_id})"
        )

        if self.webhooks.enabled:
            notified = await self.webhooks.on_abandon(
                {
                    "uniqueid": uniqueid,
                    "queue": queue_name,
                    "caller_id_num": caller_id,
                    "wait_time": self._queue_wait_time(call),
                }
            )
            if notified:
                await self.publish_event(
                    "call_missed",
                    {
                        "uniqueid": uniqueid,
                        "queue": queue_name,
                        "caller_id_num": caller_id,
                        "webhooks": notified,
                    },
                )

        if self.slack_webhook_url:
            self._missed_buffer.append({
                "queue": queue_name or "unknown",
                "caller_id": caller_id or "unknown",
                "time_hhmm": datetime.now().strftime("%H:%M"),
            })
            if self._missed_flush_task is None or self._missed_flush_task.done():
                self._missed_flush_task = asyncio.create_task(
                    self._flush_missed_after_window()
                )

    async def _flush_missed_after_window(self):
        """Wait for debounce window, then send aggregated missed-call message to Slack."""
        try:
            await asyncio.sleep(self.missed_debounce)

            entries, self._missed_buffer = self._missed_buffer, []
            if not entries:
                return

            text = _build_missed_slack_text(entries)
            try:
                status = await asyncio.to_thread(
                    _post_to_slack,
                    self.slack_webhook_url,
                    text,
                    self.slack_username,
                    self.slack_timeout,
                )
                self.logger.info(f"Slack missed-call notification sent (HTTP {status})")
            except Exception as e:
                self.logger.error(f"Failed to send Slack missed-call notification: {e}")
        finally:
            self._missed_flush_task = None

    async def handle_agent_connect(self, event):
        """Handle agent connecting to a call."""
        queue_name = event.get("Queue")
        member_name = event.get("MemberName")
        uniqueid = event.get("Uniqueid")
        channel = event.get("Channel")
        # AgentConnect carries the member interface as "Member" (falling back to
        # "Interface" for older Asterisk versions); it never has "DestChannel".
        member_interface = event.get("Member") or event.get("Interface")
        member_number = extract_member_number(member_interface)
        ringtime = event.get("Ringtime")
        holdtime = event.get("Holdtime")

        await self.publish_event(
            "agent_connect",
            {
                "queue": queue_name,
                "member": member_name,
                "unique_id": uniqueid,
                "channel": channel,
                "member_interface": member_interface,
            },
        )

        if self.webhooks.enabled:
            channel_data = self.channels_state.get(channel, {})
            notified = await self.webhooks.on_agent_connect(
                {
                    "uniqueid": uniqueid,
                    "queue": queue_name,
                    "caller_id_num": channel_data.get("caller_id_num"),
                    "caller_id_name": channel_data.get("caller_id_name"),
                    "member_name": member_name,
                    "member_interface": member_interface,
                    "member_number": member_number,
                    "ringtime": ringtime,
                    "holdtime": holdtime,
                }
            )
            if notified:
                await self.publish_event(
                    "call_answered",
                    {
                        "uniqueid": uniqueid,
                        "channel": channel,
                        "queue": queue_name,
                        "member_name": member_name,
                        "member_interface": member_interface,
                        "webhooks": notified,
                    },
                )

        self.logger.info(
            f"Queue {queue_name}: Agent {member_name} ({member_interface}) connected to call {uniqueid}"
        )

    # ============ INITIALIZATION ============

    def initialize_queue_state(self):
        action = SimpleAction("QueueStatus")
        self.ami.send_action(action)
        self.logger.info("Loaded initial queue state from Asterisk")

    def initialize_channels_state(self):
        action = SimpleAction("CoreShowChannels")
        self.ami.send_action(action)
        self.logger.info("Loaded initial channels state from Asterisk")

    # ============ MAIN LOOP ============
    async def event_listener(self, event, **kwargs):
        if event.name in self.event_handlers:
            try:
                event_wrapper = EventWrapper(event)
                await self.event_handlers[event.name](event_wrapper)
            except Exception as e:
                self.logger.error(f"Error handling {event.name}: {e}", exc_info=True)

    async def health_check_loop(self):
        """Periodic health check for connections."""
        while self.running:
            try:
                await asyncio.sleep(30)

                await self.redis_client.ping()  # type: ignore
                await self.webhooks.load_config()
                await self.update_channels_state()
                if self.queue_state:
                    async with self.redis_client.pipeline(transaction=False) as pipe:
                        for queue_name, state in list(self.queue_state.items()):
                            pipe.setex(
                                f"asterisk:queue:{queue_name}",
                                REDIS_STATE_TTL,
                                json.dumps(state),
                            )
                        await pipe.execute()
                self.logger.debug("Health check: OK")
            except Exception as e:
                self.logger.error(f"Health check failed: {e}")

            try:
                self.ami.send_action(SimpleAction("Ping"))
            except Exception:
                self.logger.warning("AMI Ping failed, triggering reconnect")
                self._start_reconnect()

    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down...")
        self.running = False

        if self._missed_flush_task and not self._missed_flush_task.done():
            self._missed_flush_task.cancel()
        if self.slack_webhook_url and self._missed_buffer:
            entries, self._missed_buffer = self._missed_buffer, []
            text = _build_missed_slack_text(entries)
            try:
                await asyncio.to_thread(
                    _post_to_slack, self.slack_webhook_url, text, self.slack_username, self.slack_timeout
                )
                self.logger.info("Slack flush on shutdown: sent")
            except Exception as e:
                self.logger.error(f"Slack flush on shutdown failed: {e}")

        try:
            await self.webhooks.wait_pending()
        except Exception as e:
            self.logger.error(f"Webhook flush on shutdown failed: {e}")

        if self.ami:
            self.ami.logoff()

        if self.redis_client:
            await self.redis_client.aclose()

        self.logger.info("Shutdown complete")

    # Sync wrapper expected by AMI client (called from AMI's background thread)
    def event_listener_sync(self, event, **kwargs):
        asyncio.run_coroutine_threadsafe(
            self.event_listener(event, **kwargs), self.loop
        )

    async def process(self):
        self.loop = asyncio.get_running_loop()
        self.ami.add_event_listener(on_event=self.event_listener_sync)

        await self.webhooks.load_config()
        await self.restore_pause_states()
        await asyncio.sleep(
            1
        )  # allow QueuePause actions to propagate before state refresh
        self.initialize_queue_state()
        self.initialize_channels_state()

        # Write liveness key immediately so sweep knows dashboard is running
        await self.update_channels_state()

        asyncio.create_task(self.health_check_loop())

        self.logger.info("AMI Listener started successfully")

        # Main loop: nothing blocking, the event loop runs freely
        try:
            while True:
                await asyncio.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            await self.shutdown()


######################### Main #########################
def parse_args():
    """Parse command line arguments.
    CLI Parameters override environment variables.
    """
    parser = argparse.ArgumentParser(description="Dashboard AMI Listener Service")
    parser.add_argument(
        "--ami_host", required=False, help="Asterisk Manager Interface host"
    )
    parser.add_argument(
        "--ami_port", type=int, required=False, help="Asterisk Manager Interface port"
    )
    parser.add_argument(
        "--ami_user", required=False, help="Asterisk Manager Interface user"
    )
    parser.add_argument(
        "--ami_pass", required=False, help="Asterisk Manager Interface password"
    )
    parser.add_argument("--redis_host", required=False, help="Redis host")
    parser.add_argument("--redis_port", type=int, required=False, help="Redis port")
    parser.add_argument(
        "--loglevel",
        type=int,
        default=logging.INFO,
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--dump_config", action="store_true", help="Dump configuration and exit"
    )
    return parser.parse_args()


def read_env_vars(args):
    """Read environment variables and return as a dictionary."""
    ami_host = os.getenv("AMI_HOST", "127.0.0.1")
    ami_port = int(os.getenv("AMI_PORT", "5038"))
    ami_user = os.getenv("AMI_USER", "ami_user")
    ami_pass = os.getenv("AMI_PASS", "ami_pass")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    loglevel = int(os.getenv("LOGLEVEL", str(logging.INFO)))
    slack_missed_call_webhook_url = os.getenv("SLACK_MISSED_CALL_WEBHOOK_URL", "")
    slack_timeout = int(os.getenv("SLACK_TIMEOUT", "4"))
    slack_username = os.getenv("SLACK_USERNAME", "PearlPBX2")
    missed_call_debounce_seconds = int(os.getenv("MISSED_CALL_DEBOUNCE_SECONDS", "60"))

    return {
        "ami_host": ami_host,
        "ami_port": ami_port,
        "ami_user": ami_user,
        "ami_pass": ami_pass,
        "redis_host": redis_host,
        "redis_port": redis_port,
        "loglevel": loglevel,
        "slack_missed_call_webhook_url": slack_missed_call_webhook_url,
        "slack_timeout": slack_timeout,
        "slack_username": slack_username,
        "missed_call_debounce_seconds": missed_call_debounce_seconds,
    }


def merge_args_env(args, env_vars):
    """Merge command line arguments with environment variables.
    Command line arguments take priority; environment variables (which always carry a
    default) are used only when the corresponding CLI argument was not provided.
    Some keys (e.g. slack_*) exist only in the environment and have no CLI argument.
    """
    merged = {}
    for key in env_vars:
        arg_val = getattr(args, key, None)
        merged[key] = arg_val if arg_val is not None else env_vars[key]
    return merged


def handle_signal(signum, frame):
    """Handle OS signals for graceful shutdown."""
    print(f"Received signal {signum}")
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    args = parse_args()
    env_vars = read_env_vars(args)
    params = merge_args_env(args, env_vars)
    if args.dump_config:
        print(json.dumps(params, indent=4))
        exit(0)

    listener = DashboardAMIListener(**params)

    try:
        asyncio.run(listener.process())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
