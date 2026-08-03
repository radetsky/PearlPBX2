"""CRM webhook delivery for the dashboard AMI listener.

Configuration is produced by the Django app `apps.webhooks` and read from the
Redis key `webhooks:config`. Calls announced with an incoming event are marked
in Redis (`webhook:notified:{uniqueid}`) so that ended events are sent only for
announced calls, exactly once. All failures are logged and never propagate into
the AMI event handlers.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import urllib.request
from datetime import datetime
from string import Template

WEBHOOKS_CONFIG_KEY = "webhooks:config"
NOTIFIED_KEY_PREFIX = "webhook:notified:"
NOTIFIED_TTL = 7200  # seconds; matches REDIS_STATE_TTL of the listener
SIGNATURE_HEADER = "X-PearlPBX-Signature"
RETRY_DELAY_SECONDS = 2

# Keep in sync with apps.webhooks.models.TEMPLATE_VARIABLES. A custom template
# may list any of these placeholders regardless of event type; ones not
# produced by the firing event render as empty strings rather than leaking
# the literal "${name}" text into the payload.
ALL_TEMPLATE_VARIABLES = frozenset(
    {
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
    }
)


def post_json(url, body, headers, timeout):
    """POST a JSON body (bytes); return the HTTP status code."""
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def render_template(template, variables):
    """Substitute ${placeholders} in every string value of a JSON-like object."""
    str_vars = {k: "" if v is None else str(v) for k, v in variables.items()}
    if isinstance(template, str):
        return Template(template).safe_substitute(str_vars)
    if isinstance(template, dict):
        return {k: render_template(v, variables) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(v, variables) for v in template]
    return template


class WebhookManager:
    def __init__(self, redis_client, logger=None):
        self.redis = redis_client
        self.logger = logger or logging.getLogger("dashboard")
        self.webhooks = []
        self.base_url = ""
        self._raw_config = None
        self._tasks = set()

    @property
    def enabled(self):
        return bool(self.webhooks)

    async def load_config(self):
        """Read webhooks:config from Redis; tolerate missing key or bad JSON."""
        try:
            raw = await self.redis.get(WEBHOOKS_CONFIG_KEY)
        except Exception as e:
            self.logger.error(f"Webhooks: failed to read config from Redis: {e}")
            return
        if raw == self._raw_config:
            return
        self._raw_config = raw
        if not raw:
            if self.webhooks:
                self.logger.info("Webhooks: config removed, feature disabled")
            self.webhooks = []
            self.base_url = ""
            return
        try:
            config = json.loads(raw)
            webhooks = [wh for wh in config.get("webhooks", []) if wh.get("url")]
            base_url = (config.get("base_url") or "").rstrip("/")
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.error(f"Webhooks: invalid config in Redis, ignoring: {e}")
            return
        self.webhooks = webhooks
        self.base_url = base_url
        self.logger.info(
            f"Webhooks: config loaded, {len(webhooks)} active webhook(s)"
        )

    # ============ EVENT ENTRY POINTS ============

    async def on_incoming(self, call_info):
        """Announce an incoming call. Returns names of webhooks notified now.

        call_info: uniqueid, caller_id_num, caller_id_name, exten, context,
        queue, recording_expected (True/False/None=unknown).
        """
        try:
            return await self._on_incoming(call_info)
        except Exception as e:
            self.logger.error(f"Webhooks: incoming handling failed: {e}", exc_info=True)
            return []

    async def on_abandon(self, call_info):
        """Report a missed (abandoned) queue call. Returns notified names.

        call_info: uniqueid, queue, caller_id_num, wait_time.
        exten/context are enriched from the announced-call marker, if present.
        """
        try:
            return await self._on_abandon(call_info)
        except Exception as e:
            self.logger.error(f"Webhooks: abandon handling failed: {e}", exc_info=True)
            return []

    async def on_hangup(self, hangup_info):
        """Report call end for announced calls only. Returns notified names.

        hangup_info: uniqueid, cause, cause_txt, variables (channel vars dict).
        """
        try:
            return await self._on_hangup(hangup_info)
        except Exception as e:
            self.logger.error(f"Webhooks: hangup handling failed: {e}", exc_info=True)
            return []

    async def on_agent_connect(self, call_info):
        """Report a queue call answered by an agent. Returns notified names.

        call_info: uniqueid, queue, caller_id_num, caller_id_name, member_name,
        member_interface, member_number, ringtime, holdtime.
        exten/context are enriched from the announced-call marker, if present.
        """
        try:
            return await self._on_agent_connect(call_info)
        except Exception as e:
            self.logger.error(
                f"Webhooks: agent-connect handling failed: {e}", exc_info=True
            )
            return []

    # ============ INTERNALS ============

    def _match(self, event, context=None, queue=None):
        matched = []
        for wh in self.webhooks:
            if event not in wh.get("events", []):
                continue
            if context is not None and context in wh.get("contexts", []):
                matched.append(wh)
            elif queue is not None and queue in wh.get("queues", []):
                matched.append(wh)
        return matched

    def _recording_url(self, uniqueid):
        if not self.base_url:
            return None
        return f"{self.base_url}/api/v1/recordings/{uniqueid}/"

    async def _on_incoming(self, call_info):
        uniqueid = call_info.get("uniqueid")
        if not self.enabled or not uniqueid:
            return []
        matched = self._match(
            "incoming", context=call_info.get("context"), queue=call_info.get("queue")
        )
        if not matched:
            return []

        marker = await self._get_marker(uniqueid)
        already = set(marker.get("webhooks", [])) if marker else set()
        targets = [wh for wh in matched if wh["name"] not in already]
        if not targets:
            return []

        recording_expected = call_info.get("recording_expected")
        variables = {
            "uniqueid": uniqueid,
            "caller_id_num": call_info.get("caller_id_num"),
            "caller_id_name": call_info.get("caller_id_name"),
            "exten": call_info.get("exten"),
            "context": call_info.get("context"),
            "queue": call_info.get("queue"),
            "timestamp": datetime.now().isoformat(),
            "recording_expected": recording_expected,
            "recording_url": self._recording_url(uniqueid),
        }
        for wh in targets:
            self._fire(wh, "call.incoming", variables)

        call = (marker or {}).get("call", {})
        call.update(
            {
                "caller_id_num": call_info.get("caller_id_num"),
                "caller_id_name": call_info.get("caller_id_name"),
                "exten": call_info.get("exten"),
                "context": call_info.get("context"),
                "queue": call_info.get("queue") or call.get("queue"),
                "started_at": call.get("started_at") or datetime.now().isoformat(),
            }
        )
        await self._set_marker(
            uniqueid,
            {
                "webhooks": sorted(already | {wh["name"] for wh in targets}),
                "call": call,
            },
        )
        return [wh["name"] for wh in targets]

    async def _on_abandon(self, call_info):
        uniqueid = call_info.get("uniqueid")
        if not self.enabled or not uniqueid:
            return []
        matched = self._match("missed", queue=call_info.get("queue"))
        marker = await self._get_marker(uniqueid)
        if matched:
            call = (marker or {}).get("call", {})
            variables = {
                "uniqueid": uniqueid,
                "caller_id_num": call_info.get("caller_id_num"),
                "exten": call.get("exten"),
                "context": call.get("context"),
                "queue": call_info.get("queue"),
                "wait_time": call_info.get("wait_time"),
                "timestamp": datetime.now().isoformat(),
            }
            for wh in matched:
                self._fire(wh, "call.missed", variables)

        if marker:
            marker.setdefault("call", {})["missed"] = True
            await self._set_marker(uniqueid, marker)
        return [wh["name"] for wh in matched]

    async def _on_agent_connect(self, call_info):
        uniqueid = call_info.get("uniqueid")
        if not self.enabled or not uniqueid:
            return []
        matched = self._match("answered", queue=call_info.get("queue"))
        marker = await self._get_marker(uniqueid)
        if matched:
            call = (marker or {}).get("call", {})
            variables = {
                "uniqueid": uniqueid,
                "caller_id_num": call_info.get("caller_id_num"),
                "caller_id_name": call_info.get("caller_id_name"),
                "exten": call.get("exten"),
                "context": call.get("context"),
                "queue": call_info.get("queue"),
                "member_name": call_info.get("member_name"),
                "member_interface": call_info.get("member_interface"),
                "member_number": call_info.get("member_number"),
                "ringtime": call_info.get("ringtime"),
                "holdtime": call_info.get("holdtime"),
                "timestamp": datetime.now().isoformat(),
            }
            for wh in matched:
                self._fire(wh, "call.answered", variables)

        if marker:
            marker.setdefault("call", {}).update(
                {
                    "answered_by_member": call_info.get("member_name"),
                    "answered_by_interface": call_info.get("member_interface"),
                }
            )
            await self._set_marker(uniqueid, marker)
        return [wh["name"] for wh in matched]

    async def _on_hangup(self, hangup_info):
        uniqueid = hangup_info.get("uniqueid")
        if not uniqueid:
            return []
        marker = await self._get_marker(uniqueid)
        if not marker:
            return []
        await self._delete_marker(uniqueid)
        if not self.enabled:
            return []

        by_name = {wh["name"]: wh for wh in self.webhooks}
        targets = [
            by_name[name]
            for name in marker.get("webhooks", [])
            if name in by_name and "ended" in by_name[name].get("events", [])
        ]
        if not targets:
            return []

        call = marker.get("call", {})
        channel_vars = hangup_info.get("variables") or {}
        mixmonitor = channel_vars.get("MIXMONITOR")
        recorded = None if mixmonitor is None else mixmonitor == "1"
        variables = {
            "uniqueid": uniqueid,
            "caller_id_num": call.get("caller_id_num"),
            "caller_id_name": call.get("caller_id_name"),
            "exten": call.get("exten"),
            "context": call.get("context"),
            "queue": call.get("queue"),
            "timestamp": datetime.now().isoformat(),
            "duration": self._call_duration(call.get("started_at")),
            "cause": hangup_info.get("cause"),
            "cause_txt": hangup_info.get("cause_txt"),
            "answered_time": channel_vars.get("ANSWEREDTIME"),
            "billsec": channel_vars.get("CDR(billsec)"),
            "missed": bool(call.get("missed")),
            "answered_by_member": call.get("answered_by_member"),
            "answered_by_interface": call.get("answered_by_interface"),
            "recorded": recorded,
            "recording_url": self._recording_url(uniqueid) if recorded else None,
            "recording_file": channel_vars.get("MIXMONITOR_FILENAME"),
        }
        for wh in targets:
            self._fire(wh, "call.ended", variables)
        return [wh["name"] for wh in targets]

    @staticmethod
    def _call_duration(started_at):
        if not started_at:
            return None
        try:
            return int(
                (datetime.now() - datetime.fromisoformat(started_at)).total_seconds()
            )
        except ValueError:
            return None

    # ============ MARKER (announced calls) ============

    async def _get_marker(self, uniqueid):
        try:
            raw = await self.redis.get(f"{NOTIFIED_KEY_PREFIX}{uniqueid}")
            return json.loads(raw) if raw else None
        except Exception as e:
            self.logger.error(f"Webhooks: failed to read marker for {uniqueid}: {e}")
            return None

    async def _set_marker(self, uniqueid, marker):
        try:
            await self.redis.setex(
                f"{NOTIFIED_KEY_PREFIX}{uniqueid}", NOTIFIED_TTL, json.dumps(marker)
            )
        except Exception as e:
            self.logger.error(f"Webhooks: failed to write marker for {uniqueid}: {e}")

    async def _delete_marker(self, uniqueid):
        try:
            await self.redis.delete(f"{NOTIFIED_KEY_PREFIX}{uniqueid}")
        except Exception as e:
            self.logger.error(f"Webhooks: failed to delete marker for {uniqueid}: {e}")

    # ============ DELIVERY ============

    def _build_body(self, wh, event, variables):
        template = wh.get("payload_template")
        if template:
            full_vars = {name: None for name in ALL_TEMPLATE_VARIABLES}
            full_vars.update(variables)
            full_vars["event"] = event
            payload = render_template(template, full_vars)
        else:
            payload = {"event": event, **variables}
        return json.dumps(payload).encode("utf-8")

    def _fire(self, wh, event, variables):
        try:
            body = self._build_body(wh, event, variables)
            headers = dict(wh.get("headers") or {})
            secret = wh.get("secret")
            if secret:
                signature = hmac.new(
                    secret.encode("utf-8"), body, hashlib.sha256
                ).hexdigest()
                headers[SIGNATURE_HEADER] = f"sha256={signature}"
            task = asyncio.create_task(
                self._send_with_retries(
                    wh["name"],
                    event,
                    wh["url"],
                    body,
                    headers,
                    int(wh.get("timeout", 5)),
                    int(wh.get("retries", 1)),
                )
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception as e:
            self.logger.error(f"Webhooks: failed to fire '{wh.get('name')}' {event}: {e}")

    async def _send_with_retries(self, name, event, url, body, headers, timeout, retries):
        attempts = retries + 1
        for attempt in range(1, attempts + 1):
            try:
                status = await asyncio.to_thread(post_json, url, body, headers, timeout)
                self.logger.info(f"Webhook '{name}': {event} sent (HTTP {status})")
                return
            except Exception as e:
                self.logger.warning(
                    f"Webhook '{name}': {event} attempt {attempt}/{attempts} failed: {e}"
                )
                if attempt < attempts:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        self.logger.error(
            f"Webhook '{name}': {event} delivery failed after {attempts} attempt(s)"
        )

    async def wait_pending(self, timeout=10):
        """Await in-flight deliveries (used on shutdown)."""
        if self._tasks:
            await asyncio.wait(list(self._tasks), timeout=timeout)
