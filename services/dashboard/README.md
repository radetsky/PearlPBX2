# Operator Dashboard 

This is a idea of Flash Operator Panel, but implemented with my vision.

## Architecture 

AMI -> Listener -> Redis -> Django Channels -> WebSocket -> User 


### Redis 

```
sudo apt install redis-server
```

Python code 
```
pip install redis channels-redis
```

## CRM Webhooks

The dashboard listener can push HTTP notifications about calls to one or more
external CRM systems. The feature is fully optional: with no active `Webhook`
row configured in the Django admin, nothing runs.

> For a CRM-integrator-facing guide with request/response examples (curl,
> Python, Node.js), see [docs/ua/crm-integration.md](../../docs/ua/crm-integration.md)
> (Ukrainian). This section documents the internal implementation.

### Events

There are two independent event chains. The **inbound chain** covers calls
arriving at the PBX (from a trunk/SIPPeer, or an internal call ringing into a
context/queue); the **outbound chain** covers calls placed by a SIP user
(`apps.webhooks.models.SIPUser` extension picking up and dialing out) — never
by a trunk, even if the trunk shares a routing table's name with a SIP user.

| Event                    | Fired from                                       | Trigger                                                            |
|---------------------------|--------------------------------------------------|---------------------------------------------------------------------|
| `call.incoming`           | `handle_newchannel` / `handle_queue_caller_join` | A new call enters a configured context, or joins a configured queue |
| `call.answered`           | `handle_agent_connect`                           | A queue member answers the call (AMI `AgentConnect`) |
| `call.missed`             | `handle_queue_caller_abandon`                    | A caller abandons a configured queue (same trigger point as the Slack missed-call notification) |
| `call.ended`              | `handle_hangup`                                  | The channel hangs up — **only** for calls that were already announced with a `call.incoming` event |
| `call.outgoing`           | `handle_newchannel`                              | A SIP user's channel is created and its endpoint belongs to one of the webhook's routing tables |
| `call.outgoing_answered`  | `handle_dial_end`                                | The dialed party answers (AMI `DialEnd` with `DialStatus=ANSWER`) — **only** for calls already announced with `call.outgoing` |
| `call.outgoing_ended`     | `handle_hangup`                                  | The channel hangs up — **only** for calls already announced with `call.outgoing` |

`call.ended` and `call.outgoing_ended` are each scoped to calls announced on
their own chain: a Redis marker (`webhook:notified:{uniqueid}`, TTL 7200s) is
written when `call.incoming` or `call.outgoing` fires and consumed (read +
deleted) on hangup, so CRM never receives an "ended" event for a call it was
never told about, and never receives it twice. The marker's `direction` field
(`"inbound"`/`"outbound"`) is how `handle_hangup` knows which chain — and
therefore which webhooks and which event name — to fire.

`call.missed` and `call.answered` do not require that marker — an abandoned or
answered queue call is still worth a CRM record even if no incoming event
matched. If the call was later announced too (or already was), the abandon
event stamps the marker with `missed: true`, and `call.answered` stamps it
with the responding agent (`answered_by_member` / `answered_by_interface`);
the subsequent `call.ended` payload carries both so CRM can correlate all of
it without extra lookups. `call.outgoing_answered` behaves the same way on
the outbound side: it stamps the marker with `answered_at` and the
`DialStatus`, and `call.outgoing_ended` carries `answered` / `dial_status` so
CRM can tell a picked-up call from BUSY/NOANSWER/CANCEL without extra lookups.

`call.answered` is queue-based only (it corresponds to Asterisk's `AgentConnect`
AMI event, which only fires for queue calls) — enabling it requires selecting
at least one queue, same as `call.missed`.

**How outbound calls are told apart from a trunk sharing the same routing
table:** both a SIP user's endpoint and a trunk's endpoint can end up with a
PJSIP `context` equal to a routing table's name (see `core/conf.py`), so
context alone cannot tell them apart. Instead, `apps/webhooks/sync.py`
serializes a `sip_users` map (`{endpoint_name: routing_table_name}`, SIPUser
only — trunks are never included) into `webhooks:config`, and
`webhook_sender.extract_endpoint()` pulls the endpoint name out of the AMI
`Channel` (`PJSIP/1001-0000000a` → `1001`) to look it up. A channel whose
endpoint isn't in that map — a trunk, a queue's internal leg, anything that
isn't a configured SIP user — never triggers the outbound chain.

### Configuration

Configure webhooks in the Django admin (`apps.webhooks.Webhook`, superuser
only). Each row is independent, so multiple CRMs can be wired up at once —
including one row for the inbound chain and a separate row (own URL) for the
outbound chain, per the two-chain split above.

- **URL** — where the JSON POST is sent.
- **Send incoming / Send ended / Send missed / Send answered** — which
  inbound-chain events this webhook subscribes to. `Send ended` requires
  `Send incoming`; `Send missed` and `Send answered` each require at least one
  selected queue. These events are matched by **Contexts**/**Queues**, never
  by **Routing tables**.
- **Send outgoing / Send outgoing answered / Send outgoing ended** — which
  outbound-chain events this webhook subscribes to. `Send outgoing answered`
  and `Send outgoing ended` each require `Send outgoing`. These events are
  matched only by **Routing tables**.
- **Contexts** — inbound `DialplanContext`s that trigger `call.incoming`.
- **Routing tables** — SIP users assigned to these routing tables trigger the
  outbound chain when they place a call. Never matches a trunk.
- **Queues** — queues that trigger the inbound-chain queue events.
  At least one of Contexts/Routing tables/Queues must be set overall.
- **Headers** — extra HTTP headers as JSON, e.g. `{"Authorization": "Bearer ..."}`.
- **Secret** — optional; when set, every request carries an HMAC-SHA256
  signature of the raw body.
- **Timeout / Retries** — per-request timeout and extra delivery attempts.
- **Payload template** — JSON object overriding the default body. String
  values may use `${placeholder}` syntax (see Template variables below). The
  admin "Add Webhook" form pre-fills this field with every available
  placeholder as a starting point (`default_payload_template()` in
  `apps/webhooks/models.py`) — trim it down to the fields you need, or clear
  the field entirely (empty/null) to fall back to the built-in per-event
  default payload shape shown below. Placeholders not produced by the firing
  event (e.g. `${ringtime}` on `call.incoming`) always render as an empty
  string rather than leaking the literal `${...}` text, so the full default
  template is safe to use unmodified across all seven events.

Changes take effect without restarting the service: Django serializes the
active configuration into the Redis key `webhooks:config` on every save
(via signals), and the listener re-reads that key on startup and on every
health-check tick (every 30 seconds). To force a re-sync manually (e.g. after
a Redis flush), run:

```
python manage.py sync_webhooks
```

### Default payload

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/"
}
```

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "queue": "support",
  "member_name": "Operator Petrenko",
  "member_interface": "PJSIP/101",
  "member_number": "101",
  "ringtime": "3500",
  "holdtime": "18",
  "timestamp": "2026-07-21T18:58:51.812900"
}
```

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
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
  "recording_file": "/var/spool/asterisk/monitor/2026/07/21/x.wav"
}
```

```json
{
  "event": "call.missed",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "queue": "support",
  "wait_time": 21,
  "timestamp": "2026-07-21T18:58:51.813698"
}
```

`ringtime` (milliseconds) and `holdtime` (seconds) come straight from
Asterisk's `AgentConnect` AMI event: how long the phone rang for the agent,
and how long the caller waited in the queue before being connected.

Outbound chain — fired for a call placed by a SIP user:

```json
{
  "event": "call.outgoing",
  "uniqueid": "1753000000.55",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:51.811673"
}
```

```json
{
  "event": "call.outgoing_answered",
  "uniqueid": "1753000000.55",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "dest_channel": "PJSIP/trunk1-0000002a",
  "dial_status": "ANSWER",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:56.203112"
}
```

```json
{
  "event": "call.outgoing_ended",
  "uniqueid": "1753000000.55",
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
  "recording_file": null
}
```

`dial_status` mirrors Asterisk's `DialStatus` from the AMI `DialEnd` event
(`ANSWER`, `BUSY`, `NOANSWER`, `CANCEL`, ...). `call.outgoing_answered` fires
only when it's `ANSWER`, and only once per call even if Asterisk tries several
destinations (e.g. a trunk failover) before one answers. `call.outgoing_ended`
always carries the last known `dial_status` and `answered` (`true` only if
`call.outgoing_answered` fired), so an unanswered outgoing call still gets a
correctly-flagged ended event with no answered event before it.

Template variables available for `payload_template`: `event`, `uniqueid`,
`caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`,
`duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`,
`recording_expected`, `recording_url`, `recording_file`, `missed`,
`wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`,
`holdtime`, `answered_by_member`, `answered_by_interface`, `direction`,
`dest_channel`, `dial_status`, `answered`. Fields not relevant to a given
event are `null`.

### Call recordings

`recording_url` always points at the token-protected API endpoint
`{PEARLPBX_PUBLIC_URL}/api/v1/recordings/{uniqueid}/` and is deterministic —
it can be built from the uniqueid alone, before the call even ends, so it is
present in `call.incoming` as a prediction:

- `recording_expected` reflects Asterisk's `MIXMONITOR` channel variable at
  the moment the event fires. For queue calls it is usually known (the
  recording decision AGI runs before `Queue()`); for calls classified purely
  by context it fires before that AGI runs, so it is `null` (unknown).
- On `call.ended`, `recorded` is the confirmed outcome (`true`/`false`, or
  `null` if the variable was lost — e.g. after an AMI reconnect mid-call),
  and `recording_url` is only populated when `recorded` is `true`.

CRM systems fetch the file with:

```
GET /api/v1/recordings/{uniqueid}/
Authorization: Token <api-token>
```

Tokens are issued the same way as for the rest of the REST API (Django admin
→ Auth Token, `rest_framework.authtoken`). Access is not scoped further: any
valid API token can fetch any recording (the same tokens already used for
`/api/v1/calls/originate/` etc.). The endpoint supports HTTP Range requests
for streaming/seeking and returns 404 when no recording exists yet.

Humans use the session-authenticated `/reports/audio/uid/{uniqueid}/` view
instead — same file, different auth mechanism.

### Signature verification

When a webhook has a `secret` configured, requests carry:

```
X-PearlPBX-Signature: sha256=<hex-encoded HMAC-SHA256 of the raw request body>
```

Verify it (Python example):

```python
import hashlib
import hmac

def verify(secret: str, body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)
```

### Delivery semantics

Deliveries are best-effort: `asyncio.to_thread` + stdlib `urllib` (same
pattern as the existing Slack missed-call notification), fire-and-forget from
the AMI event handlers so a slow or unreachable CRM endpoint never blocks
call processing. Each attempt has the configured timeout; failed attempts are
retried up to `retries` times with a short delay, and a final failure is only
logged — there is no persistent delivery queue or guaranteed-once semantics.

