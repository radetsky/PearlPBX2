# ami_listener.py
import argparse
import os
import asyncio
import json
import logging
import signal
import sys
import time

import redis.asyncio as redis

from asterisk.ami import AMIClient, SimpleAction
from datetime import datetime


class EventWrapper:
    def __init__(self, event):
        self.event = event

    def get(self, key, default=None):
        return self.event.keys.get(key, default)


class DashboardAMIListener:
    def __init__(self, **kwargs):
        self.params = kwargs
        self.logger = self.setup_logging()
        self.ami = self.ami_connect()
        self.running = True
        self.manager = None
        self.redis_client = self.connect_redis()
        self.queue_state = {}
        self.channels_state = {}  # State of all active channels
        self.event_handlers = self.set_event_handlers()

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
            # Queue events
            "QueueMemberStatus": self.handle_queue_member_status,
            "QueueMember": self.handle_queue_member,
            "QueueCallerJoin": self.handle_queue_caller_join,
            "QueueCallerLeave": self.handle_queue_caller_leave,
            "QueueCallerAbandon": self.handle_queue_caller_leave,
            "AgentConnect": self.handle_agent_connect,
        }
        return event_handlers

    def setup_logging(self):
        logger = logging.getLogger("callback")
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
        time.sleep(5)
        self.ami = self.ami_connect()

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
                state_key, 3600, json.dumps(self.queue_state.get(queue_name, {}))
            )
        except Exception as e:
            self.logger.error(f"Error updating queue state: {e}")

    async def update_channels_state(self):
        """Update all channels state in Redis."""
        try:
            await self.redis_client.setex(
                "asterisk:channels:all",
                3600,
                json.dumps(self.channels_state),
            )
        except Exception as e:
            self.logger.error(f"Error updating channels state: {e}")

    async def update_channel_state(self, channel_name, channel_data):
        """Update individual channel state in Redis."""
        try:
            await self.redis_client.setex(
                f"asterisk:channel:{channel_name}",
                3600,
                json.dumps(channel_data),
            )
        except Exception as e:
            self.logger.error(f"Error updating channel state: {e}")

    async def update_uid_state(self, uniqueid: str, channel_name: str):
        """Store uniqueid -> channel mapping for ULINE sweep."""
        try:
            await self.redis_client.setex(
                f"asterisk:uid:{uniqueid}",
                3600,
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

    # ============ CHANNEL EVENT HANDLERS ============

    async def handle_newchannel(self, event):
        """Handle new channel creation."""
        channel = event.get("Channel")
        channel_state = event.get("ChannelState")
        channel_state_desc = event.get("ChannelStateDesc")
        caller_id_num = event.get("CallerIDNum")
        caller_id_name = event.get("CallerIDName")
        connected_line_num = event.get("ConnectedLineNum")
        uniqueid = event.get("Uniqueid")
        context = event.get("Context")
        exten = event.get("Exten")

        # Store channel information
        self.channels_state[channel] = {
            "channel": channel,
            "uniqueid": uniqueid,
            "state": channel_state,
            "state_desc": channel_state_desc,
            "caller_id_num": caller_id_num,
            "caller_id_name": caller_id_name,
            "connected_line_num": connected_line_num,
            "context": context,
            "exten": exten,
            "created_at": datetime.now().isoformat(),
            "duration": 0,
            "bridged_channel": None,
            "application": None,
        }

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
        important_vars = ["ANSWEREDTIME", "DIALEDTIME", "HANGUPCAUSE", "CDR(billsec)"]

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
        if queue_name not in self.queue_state:
            self.queue_state[queue_name] = {
                "members": {},
                "calls": {},
                "stats": {"waiting": 0},
            }
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

    async def handle_queue_member_status(self, event):
        """Handle queue member status update."""

        """Event: QueueMemberStatus
            Privilege: agent,all
            Timestamp: 1765742326.994064
            Queue: DEFAULT
            MemberName: 201
            Interface: PJSIP/ppbxuser201
            StateInterface: PJSIP/ppbxuser201
            Membership: static
            Penalty: 0
            CallsTaken: 0
            LastCall: 0
            LastPause: 0
            LoginTime: 1765220918
            InCall: 0
            Status: 1
            Paused: 0
            PausedReason:
            Ringinuse: 0
            Wrapuptime: 0"""

        queue_name = event.get("Queue")
        member_name = event.get("MemberName")
        status = event.get("Status")
        paused = event.get("Paused", "0") == "1"
        calls_taken = event.get("CallsTaken", "0")

        if queue_name not in self.queue_state:
            self.queue_state[queue_name] = {
                "members": {},
                "calls": {},
                "stats": {"waiting": 0, "answered": 0},
            }

        self.queue_state[queue_name]["members"][member_name] = {
            "name": member_name,
            "status": status,
            "paused": paused,
            "calls_taken": int(calls_taken),
            "last_update": datetime.now().isoformat(),
            "logintime": event.get("LoginTime"),
            "location": event.get("Location"),
            "state_interface": event.get("StateInterface"),
            "membership": event.get("Membership"),
            "penalty": event.get("Penalty"),
            "last_call": event.get("LastCall"),
            "last_pause": event.get("LastPause"),
            "in_call": event.get("InCall"),
            "paused_reason": event.get("PausedReason"),
            "wrapup_time": event.get("Wrapuptime"),
        }

        await self.update_queue_state(queue_name)

        await self.publish_event(
            "queue_member_status",
            {
                "queue": queue_name,
                "member": member_name,
                "status": status,
                "paused": paused,
                "calls_taken": int(calls_taken),
                "last_update": datetime.now().isoformat(),
                "logintime": event.get("LoginTime"),
                "location": event.get("Location"),
                "state_interface": event.get("StateInterface"),
                "membership": event.get("Membership"),
                "penalty": event.get("Penalty"),
                "last_call": event.get("LastCall"),
                "last_pause": event.get("LastPause"),
                "in_call": event.get("InCall"),
                "paused_reason": event.get("PausedReason"),
                "wrapup_time": event.get("Wrapuptime"),
            },
        )

        self.logger.info(
            f"Queue {queue_name}: Member {member_name} status={status}, paused={paused}"
        )

    async def handle_queue_member(self, event):
        """Handle queue member event."""

        """Event: QueueMember
                Queue: check_local
                Name: rad
                Location: Local/0504139380@mobile-out
                StateInterface: Local/0504139380@mobile-out
                Membership: static
                Penalty: 0
                CallsTaken: 0
                LastCall: 0
                LastPause: 0
                LoginTime: 1765220918
                InCall: 0
                Status: 1
                Paused: 0
                PausedReason:
                Wrapuptime: 0"""

        queue_name = event.get("Queue")
        member_name = event.get("Name")
        status = event.get("Status")
        paused = event.get("Paused", "0") == "1"
        calls_taken = event.get("CallsTaken", "0")

        if queue_name not in self.queue_state:
            self.queue_state[queue_name] = {
                "members": {},
                "calls": {},
                "stats": {"waiting": 0, "answered": 0},
            }

        self.queue_state[queue_name]["members"][member_name] = {
            "name": member_name,
            "status": status,
            "paused": paused,
            "calls_taken": int(calls_taken),
            "last_update": datetime.now().isoformat(),
            "logintime": event.get("LoginTime"),
            "location": event.get("Location"),
            "state_interface": event.get("StateInterface"),
            "membership": event.get("Membership"),
            "penalty": event.get("Penalty"),
            "last_call": event.get("LastCall"),
            "last_pause": event.get("LastPause"),
            "in_call": event.get("InCall"),
            "paused_reason": event.get("PausedReason"),
            "wrapup_time": event.get("Wrapuptime"),
        }

        await self.update_queue_state(queue_name)

        await self.publish_event(
            "queue_member_status",
            {
                "queue": queue_name,
                "member": member_name,
                "status": status,
                "paused": paused,
                "calls_taken": int(calls_taken),
                "last_update": datetime.now().isoformat(),
                "logintime": event.get("LoginTime"),
                "location": event.get("Location"),
                "state_interface": event.get("StateInterface"),
                "membership": event.get("Membership"),
                "penalty": event.get("Penalty"),
                "last_call": event.get("LastCall"),
                "last_pause": event.get("LastPause"),
                "in_call": event.get("InCall"),
                "paused_reason": event.get("PausedReason"),
                "wrapup_time": event.get("Wrapuptime"),
            },
        )

        self.logger.info(
            f"Queue {queue_name}: Member {member_name} status={status}, paused={paused}"
        )

    async def handle_queue_caller_join(self, event):
        """Handle caller joining a queue."""
        queue_name = event.get("Queue")
        caller_id = event.get("CallerIDNum")
        position = event.get("Position")
        uniqueid = event.get("Uniqueid")
        channel = event.get("Channel")

        if queue_name not in self.queue_state:
            self.queue_state[queue_name] = {
                "members": {},
                "calls": {},
                "stats": {"waiting": 0},
            }

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

        self.logger.info(
            f"Queue {queue_name}: Caller {caller_id} joined (position {position})"
        )

    async def handle_queue_caller_leave(self, event):
        """Handle caller leaving a queue."""
        queue_name = event.get("Queue")
        uniqueid = event.get("Uniqueid")

        if (
            queue_name in self.queue_state
            and uniqueid in self.queue_state[queue_name]["calls"]
        ):
            del self.queue_state[queue_name]["calls"][uniqueid]

            self.queue_state[queue_name]["stats"]["waiting"] = len(
                self.queue_state[queue_name]["calls"]
            )

            await self.update_queue_state(queue_name)

        await self.publish_event(
            "queue_caller_leave", {"queue": queue_name, "unique_id": uniqueid}
        )

        self.logger.info(f"Queue {queue_name}: Call {uniqueid} left")

    async def handle_agent_connect(self, event):
        """Handle agent connecting to a call."""
        queue_name = event.get("Queue")
        member_name = event.get("MemberName")
        uniqueid = event.get("Uniqueid")
        channel = event.get("Channel")
        member_channel = event.get("MemberName")

        await self.publish_event(
            "agent_connect",
            {
                "queue": queue_name,
                "member": member_name,
                "unique_id": uniqueid,
                "channel": channel,
                "member_channel": member_channel,
            },
        )

        self.logger.info(
            f"Queue {queue_name}: Agent {member_name} connected to call {uniqueid}"
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
                self.ami.send_action(SimpleAction("Ping"))

                self.logger.debug("Health check: OK")
            except Exception as e:
                self.logger.error(f"Health check failed: {e}")

    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down...")
        self.running = False

        if self.ami:
            self.ami.logoff()

        if self.redis_client:
            await self.redis_client.aclose()

        self.logger.info("Shutdown complete")

    # Sync wrapper expected by AMI client
    def event_listener_sync(self, event, **kwargs):
        print("Received event:", event.name)
        self.loop.create_task(self.event_listener(event, **kwargs))

    async def process(self):
        self.loop = asyncio.get_running_loop()
        self.ami.add_event_listener(on_event=self.event_listener_sync)

        self.initialize_queue_state()
        self.initialize_channels_state()

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

    return {
        "ami_host": ami_host,
        "ami_port": ami_port,
        "ami_user": ami_user,
        "ami_pass": ami_pass,
        "redis_host": redis_host,
        "redis_port": redis_port,
        "loglevel": loglevel,
    }


def merge_args_env(args, env_vars):
    """Merge command line arguments with environment variables.
    Environment variables are used in priority if command line argument is not provided.
    """
    merged = {}
    for key in env_vars:
        merged[key] = env_vars[key] if env_vars[key] is not None else getattr(args, key)
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
