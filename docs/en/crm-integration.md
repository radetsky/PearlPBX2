*Also available in: [English](crm-integration.md) | [Українська](../ua/crm-integration.md) | [Español](../es/crm-integration.md)*

# CRM Integration

**Version:** 2.7.2

---

PearlPBX2 notifies external CRM systems about calls in two ways:

- **webhooks** — the dashboard service itself sends a `POST` request to the URL configured in the CRM whenever an inbound call arrives, an operator answers a call, a call ends, or a call is missed in a queue;
- **REST API** — using a token, the CRM fetches the call recording file at a deterministic link that arrives in the webhook body.

This functionality is entirely optional: as long as no active `Webhook` record exists in the admin panel, nothing is sent and there's no extra load on the system.

## Contents

1. [How it works](#1-how-it-works)
2. [Configuring a webhook in the admin panel](#2-configuring-a-webhook-in-the-admin-panel)
3. [Message (payload) formats](#3-message-payload-formats)
4. [Call recordings: links and downloading via the API](#4-call-recordings-links-and-downloading-via-the-api)
5. [Verifying the request signature](#5-verifying-the-request-signature)
6. [Custom request body template](#6-custom-request-body-template)
7. [Behavior on delivery failure](#7-behavior-on-delivery-failure)
8. [Example: a minimal webhook handler](#8-example-a-minimal-webhook-handler)

---

## 1. How it works

The source of truth about call state is the `services/dashboard/dashboard_listener.py` service — it listens to Asterisk AMI events in real time. It sends webhooks in two independent event chains.

**Inbound chain** — calls arriving at the PBX (from a trunk, or an internal call entering a context/queue):

| Event          | When it fires | Condition |
|----------------|------------------|-------|
| `call.incoming` | a new call enters a configured context, or joins a configured queue | the call's context/queue matches the webhook's filter |
| `call.answered` | an operator picks up a call from a queue (AMI event `AgentConnect`) | the call's queue matches the webhook's filter, and "Send answered" is enabled on it |
| `call.missed`   | the caller hangs up before an operator picks up in the queue | the call's queue matches the webhook's filter, and "Send missed" is enabled on it |
| `call.ended`    | the channel finishes (hangup) | **only for calls a `call.incoming` was previously sent for** |

**Outbound chain** — calls initiated by a SIP user (an internal subscriber who picks up and dials a number), **never** a trunk:

| Event | When it fires | Condition |
|-------|------------------|-------|
| `call.outgoing` | a new channel belonging to a SIP user whose endpoint is on one of the webhook's routing tables | the channel's endpoint matches the webhook's "Routing tables" filter |
| `call.outgoing_answered` | the called party picks up (AMI event `DialEnd` with `DialStatus=ANSWER`) | **only for calls a `call.outgoing` was previously sent for** |
| `call.outgoing_ended` | the channel finishes (hangup) | **only for calls a `call.outgoing` was previously sent for** |

An important nuance: `call.ended` and `call.outgoing_ended` are deliberately sent **only** for calls the CRM was already informed about via `call.incoming` or `call.outgoing`, respectively. The system remembers in Redis (`webhook:notified:{uniqueid}`, 2-hour TTL) which webhooks were notified about a call's start (and in which chain — inbound or outbound), and checks this record when the call ends. This guarantees:
- the CRM never receives a "call ended" event for a call it was never told about;
- the CRM never receives this event twice;
- a call in the outbound chain always ends with `call.outgoing_ended`, never `call.ended`, even if the same webhook is subscribed to both chains.

The `call.missed` and `call.answered` events, by contrast, do **not** require a prior `call.incoming` — both a missed and an answered call deserve their own CRM record, even if this webhook isn't subscribed to inbound calls. If the call was announced anyway (`call.incoming` was sent for it), both events additionally set an internal marker: a miss sets `missed: true`, and an operator's answer records who exactly answered (`answered_by_member`, `answered_by_interface`). The subsequent `call.ended` will carry all of these fields — this lets the CRM correlate all events for a single call without extra requests. `call.outgoing_answered` works the same way: the marker gets a `DialStatus` and an answer timestamp, and `call.outgoing_ended` carries `answered`/`dial_status` fields, so the CRM can distinguish a successful connect from BUSY/NOANSWER/CANCEL without extra requests.

The `call.answered` event only exists for calls that go through a queue — it corresponds to Asterisk's AMI event `AgentConnect`, which doesn't occur outside queues. So "Send answered" can only be enabled if at least one queue is selected (same as `send_missed`).

**How an outbound call is distinguished from a trunk with the same routing table.** Both a SIP user and a trunk can have a PJSIP `context` equal to the routing table's name (that's how `pjsip.conf` generation works), so the channel's context alone can't tell them apart. Instead, Django serializes into Redis a map `{endpoint_name: routing_table_name}` — **for SIP users only**, trunks never end up in it. When a new channel arrives, `dashboard_listener` extracts the endpoint name from it (`PJSIP/1001-0000000a` → `1001`) and looks it up in this map. If the endpoint isn't found (it's a trunk, or anything else that isn't a configured SIP user), the outbound event chain never fires, regardless of what context or routing table are configured.

## 2. Configuring a webhook in the admin panel

Webhooks are configured in Django admin, under the **Webhooks** model (superuser only). Each row is an independent integration, so you can connect several different CRMs at once — for example, one row for the inbound chain and a separate row (with its own URL) for the outbound chain.

Form fields:

| Field | Description |
|------|------|
| `is_active` | enable/disable this webhook without deleting its configuration |
| `url` | the address the CRM receives `POST` requests at |
| `send_incoming` / `send_ended` / `send_missed` / `send_answered` | which events of the **inbound** chain this webhook is subscribed to. `send_ended` requires `send_incoming` to be enabled. `send_missed` and `send_answered` each require at least one queue to be selected. These events are matched only by `contexts`/`queues`, never by `routing_tables` |
| `send_outgoing` / `send_outgoing_answered` / `send_outgoing_ended` | which events of the **outbound** chain this webhook is subscribed to. `send_outgoing_answered` and `send_outgoing_ended` each require `send_outgoing` to be enabled. These events are matched only by `routing_tables` |
| `contexts` | a list of dialplan contexts — inbound calls into these contexts trigger `call.incoming` |
| `routing_tables` | SIP users assigned to these routing tables trigger the outbound chain when they themselves initiate a call. A trunk — never |
| `queues` | a list of queues — calls joining these queues trigger queue-related inbound-chain events |
| `headers` | extra HTTP headers as JSON, e.g. `{"X-Api-Key": "..."}` |
| `secret` | an optional shared secret for signing the request body (HMAC-SHA256), see section 5 |
| `timeout` | timeout for a single delivery attempt, in seconds (default 5) |
| `retries` | how many extra attempts to make after a failure (default 1) |
| `payload_template` | a custom JSON template for the request body, see section 6. When creating a new webhook, the admin form automatically fills in this field with a full example containing every available placeholder — you can remove the ones you don't need, or clear the field entirely to fall back to the built-in default payload |

You **must** select at least one context, routing table, or queue — otherwise the form won't save: this is what determines which call "scenarios" trigger the webhook.

Two settings apply to all webhooks at once and are set via the service's environment variables (`services/dashboard/env`), not in the admin panel:

| Variable | Default | Description |
|--------|-------------------|------|
| `WEBHOOK_SEND_SYSTEM_CHANNELS` | `false` | A channel Asterisk creates via `Dial()`/`Originate()` doesn't yet have a `Goto()` to a real number at the moment of `Newchannel` — `exten` is then the system placeholder `"s"`. By default, `call.outgoing` (and the whole `outgoing_answered`/`outgoing_ended` chain) isn't sent for such a channel — the CRM has nothing meaningful to show without a number. Set to `true` to send them anyway. |
| `WEBHOOK_CHANNEL_VARS` | `ULINE` | A comma-separated list of Asterisk channel variable names that are included in the payload as `channel_vars`. Anything not in this list is ignored. |

Changes in the admin panel take effect **without restarting the service**: on every save, Django serializes the active webhooks into the Redis key `webhooks:config`, and `dashboard_listener` re-reads this key on startup and on every health-check cycle (every 30 seconds). To force a manual config sync (e.g. after Redis data loss):

```bash
python manage.py sync_webhooks
```

## 3. Message (payload) formats

All requests are `POST` with an `application/json` body.

### `call.incoming` — call started

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "channel_vars": {}
}
```

### `call.answered` — an operator answered a queued call

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "queue": "support",
  "member_name": "Operator Petrenko",
  "member_interface": "PJSIP/101",
  "member_number": "101",
  "ringtime": "3500",
  "holdtime": "18",
  "timestamp": "2026-07-21T18:58:51.812900",
  "channel_vars": {"ULINE": "42"}
}
```

`ringtime` (milliseconds) and `holdtime` (seconds) come directly from Asterisk's AMI event `AgentConnect`: how long the operator's phone rang, and how long the caller waited in the queue before being connected.

### `call.ended` — call ended

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.814936",
  "duration": 42,
  "cause": "16",
  "cause_txt": "Normal Clearing",
  "answered_time": "38",
  "billsec": "38",
  "missed": false,
  "answered_by_member": "Operator Petrenko",
  "answered_by_interface": "PJSIP/101",
  "recorded": true,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "recording_file": "/var/spool/asterisk/monitor/2026/07/21/x.wav",
  "channel_vars": {"ULINE": "42"}
}
```

`answered_by_member` / `answered_by_interface` are filled in if a `call.answered` event arrived for this call before it ended — otherwise both fields are `null` (e.g. the call was missed, or never went through a queue at all).

### `call.missed` — a call was missed in a queue

```json
{
  "event": "call.missed",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "queue": "support",
  "wait_time": 21,
  "timestamp": "2026-07-21T18:58:51.813698",
  "channel_vars": {}
}
```

Fields that don't apply to a particular event arrive as `null` (e.g. `queue` for a call classified by context rather than by queue).

### `call.outgoing` — an outbound call started

```json
{
  "event": "call.outgoing",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:51.811673",
  "channel_vars": {}
}
```

### `call.outgoing_answered` — the called party picked up

```json
{
  "event": "call.outgoing_answered",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "dest_channel": "PJSIP/trunk1-0000002a",
  "dial_status": "ANSWER",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:56.203112",
  "channel_vars": {}
}
```

`dial_status` is the value of the AMI `DialStatus` field (`ANSWER`, `BUSY`, `NOANSWER`, `CANCEL`, ...). The event fires only when it's `ANSWER`, and only once per call, even if Asterisk tries several destinations (e.g. a backup trunk) before anyone answers.

### `call.outgoing_ended` — an outbound call ended

```json
{
  "event": "call.outgoing_ended",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "queue": null,
  "direction": "outbound",
  "dial_status": "ANSWER",
  "answered": true,
  "timestamp": "2026-08-11T18:59:24.550012",
  "duration": 28,
  "cause": "16",
  "cause_txt": "Normal Clearing",
  "answered_time": "26",
  "billsec": "26",
  "missed": false,
  "answered_by_member": null,
  "answered_by_interface": null,
  "recorded": false,
  "recording_url": null,
  "recording_file": null,
  "channel_vars": {}
}
```

`answered` is `true` only if a `call.outgoing_answered` event arrived before the call ended; otherwise it's `false`, and `dial_status` shows the reason (`BUSY`, `NOANSWER`, `CANCEL`...). This lets the CRM distinguish a successful connect from a failed one without extra requests.

## 4. Call recordings: links and downloading via the API

`recording_url` in every payload is a **deterministic** link built from the call's `uniqueid`. It can be computed before the call even ends, so it's already present in `call.incoming` — as a forecast:

- `recording_expected` — a prediction of whether the call will be recorded, taken from the Asterisk `MIXMONITOR` variable's value at the time of the event. For calls classified by queue, this value is usually already known (the AGI that decides on recording runs before `Queue()`). For calls classified only by context, the `call.incoming` event fires before that AGI runs, so the value is `null` (unknown).
- In `call.ended`, the `recorded` field is the already-confirmed fact (`true`/`false`, or `null` if the information was lost, e.g. due to an AMI reconnect mid-call). `recording_url` is filled in only when `recorded: true`.

The CRM fetches the file itself with a separate request to the REST API (not from the webhook):

```bash
curl -H "Authorization: Token <your-token>" \
  https://pbx.example.com/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

Endpoint details:

| | |
|---|---|
| Method | `GET /api/v1/recordings/<uniqueid>/` |
| Authentication | DRF token (`Authorization: Token <key>`), same as the rest of PearlPBX2's REST API |
| Access control | none beyond that — any valid API token can access any recording (same as the other API endpoints) |
| `200` / `206` | the audio file (`audio/wav` or `audio/mpeg`); `Range` requests are supported for streaming playback |
| `?download=1` | forces a file download (`Content-Disposition: attachment`) instead of an inline response |
| `401` | no token supplied, or it's invalid |
| `404` | no recording yet (the call wasn't recorded, or the file hasn't appeared on disk yet) |

The token is issued the same way as for the rest of the API — via Django admin (`Auth Token`) or with:

```bash
python manage.py drf_create_token <username>
```

> For people (not CRMs) listening in the browser, PearlPBX2's web interface offers a separate, session-authenticated link at `/reports/audio/uid/{uniqueid}/` — it's the same file, just a different authentication method.

## 5. Verifying the request signature

If a webhook has the `secret` field filled in, every request additionally carries this header:

```
X-PearlPBX-Signature: sha256=<hex HMAC-SHA256 signature of the raw request body>
```

Signature verification example (Python):

```python
import hashlib
import hmac

def verify(secret: str, body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)
```

Node.js example:

```javascript
const crypto = require("crypto");

function verify(secret, rawBody, headerValue) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}
```

**Important:** the signature is computed over the raw bytes of the request body — verify it before doing any JSON parsing.

## 6. Custom request body template

By default, the standard payload is sent (see section 3). If your CRM expects a different field format, you can set your own JSON object in the `payload_template` field. String values may contain `${variable_name}` placeholders:

When creating a new webhook in the admin panel, the **Payload template** field comes pre-filled — with a full example containing every available placeholder (one per field). This is deliberate, so you can see the whole set of options at once rather than checking the documentation. Just remove the lines you don't need, or leave everything as is — for fields that don't apply to a particular event (e.g. `${ringtime}` in `call.incoming`), the system substitutes an empty string rather than the literal placeholder text. If you don't need a custom format at all, clear the field entirely (empty/`null`), and the standard payload from section 3 will be sent.

```json
{
  "call_id": "${uniqueid}",
  "from": "${caller_id_num}",
  "direction": "${direction}",
  "recording": "${recording_url}"
}
```

Available placeholders: `event`, `uniqueid`, `linkedid`, `channel`, `caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`, `duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`, `recording_expected`, `recording_url`, `recording_file`, `missed`, `wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`, `holdtime`, `answered_by_member`, `answered_by_interface`, `direction`, `dest_channel`, `dial_status`, `answered`, `channel_vars`.

Using an unknown placeholder triggers a form validation error — the admin panel won't let you save such a template. If the field is left empty, the standard payload is sent for every event.

**`linkedid`** — Asterisk's own correlation mechanism: all channels belonging to the same logical call (e.g. the two legs of an internal call) share the same `linkedid`, equal to the `uniqueid` of the channel that initiated the call. This — not proximity of `uniqueid`/`timestamp` between two different events — is what should be used to correlate several webhook deliveries into a single call in the CRM.

**`channel_vars`** — an object with Asterisk channel variables allowed by `WEBHOOK_CHANNEL_VARS` (see section 2), e.g. `{"ULINE": "42"}`. In the template, `${channel_vars}` as the entire content of a string field is substituted as a nested JSON object; inside a larger string (`"vars: ${channel_vars}"`) it's substituted as a text representation. The field is always present (an empty object `{}` if there are no variables yet).

## 7. Behavior on delivery failure

Webhook delivery is best-effort, with no "exactly once" guarantee and no retry queue:

- the request runs asynchronously and never blocks call processing — even if the CRM server is unreachable or slow to respond, this won't affect Asterisk or the dashboard;
- each attempt is bounded by the webhook's `timeout` setting;
- on failure, up to `retries` additional attempts are made with a short pause between them;
- if all attempts fail, the event is simply logged on the server and not retried again.

It's therefore recommended that the CRM's receiving endpoint:
- respond quickly (within a couple of seconds) — slow processing on the CRM side increases the risk of a timeout;
- be idempotent by `uniqueid` — just in case the CRM system itself retries processing of incoming requests.

## 8. Example: a minimal webhook handler

A simplified Python (Flask) example — accepts events from both chains, verifies the signature, and fetches the call recording when needed:

```python
import hashlib
import hmac
import os

import requests
from flask import Flask, request, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ["PEARLPBX_WEBHOOK_SECRET"]
API_TOKEN = os.environ["PEARLPBX_API_TOKEN"]


def verify_signature(body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_value)


@app.post("/pearlpbx/webhook")
def handle_webhook():
    raw_body = request.get_data()
    if not verify_signature(raw_body, request.headers.get("X-PearlPBX-Signature")):
        abort(401)

    payload = request.get_json()
    event = payload["event"]

    if event == "call.incoming":
        create_or_update_call_card(payload)
    elif event == "call.answered":
        mark_call_card_answered(payload["uniqueid"], payload["member_name"])
    elif event == "call.missed":
        create_missed_call_task(payload)
    elif event in ("call.ended", "call.outgoing_ended"):
        close_call_card(payload)
        if payload.get("recorded"):
            fetch_recording(payload["uniqueid"], payload["recording_url"])
    elif event == "call.outgoing":
        create_or_update_call_card(payload)
    elif event == "call.outgoing_answered":
        mark_call_card_answered(payload["uniqueid"], payload["caller_id_name"])

    return "", 200


def fetch_recording(uniqueid: str, recording_url: str) -> None:
    response = requests.get(
        recording_url,
        headers={"Authorization": f"Token {API_TOKEN}"},
        timeout=10,
    )
    response.raise_for_status()
    with open(f"/data/recordings/{uniqueid}.wav", "wb") as f:
        f.write(response.content)
```

---

Related documentation:
- [API.md](API.md) — full PearlPBX2 REST API reference
- [services/dashboard/README.md](../../services/dashboard/README.md) — technical details of the dashboard service and Redis event format
