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

| Event          | Fired from                | Trigger                                                            |
|----------------|----------------------------|---------------------------------------------------------------------|
| `call.incoming`| `handle_newchannel` / `handle_queue_caller_join` | A new call enters a configured context, or joins a configured queue |
| `call.answered`| `handle_agent_connect`                           | A queue member answers the call (AMI `AgentConnect`) |
| `call.missed`  | `handle_queue_caller_abandon`                    | A caller abandons a configured queue (same trigger point as the Slack missed-call notification) |
| `call.ended`   | `handle_hangup`                                  | The channel hangs up — **only** for calls that were already announced with a `call.incoming` event |

`call.ended` is intentionally scoped to announced calls: a Redis marker
(`webhook:notified:{uniqueid}`, TTL 7200s) is written when `call.incoming`
fires and consumed (read + deleted) on hangup, so CRM never receives a "call
ended" for a call it was never told about, and never receives it twice.

`call.missed` and `call.answered` do not require that marker — an abandoned or
answered queue call is still worth a CRM record even if no incoming event
matched. If the call was later announced too (or already was), the abandon
event stamps the marker with `missed: true`, and `call.answered` stamps it
with the responding agent (`answered_by_member` / `answered_by_interface`);
the subsequent `call.ended` payload carries both so CRM can correlate all of
it without extra lookups.

`call.answered` is queue-based only (it corresponds to Asterisk's `AgentConnect`
AMI event, which only fires for queue calls) — enabling it requires selecting
at least one queue, same as `call.missed`.

### Configuration

Configure webhooks in the Django admin (`apps.webhooks.Webhook`, superuser
only). Each row is independent, so multiple CRMs can be wired up at once:

- **URL** — where the JSON POST is sent.
- **Send incoming / Send ended / Send missed / Send answered** — which events
  this webhook subscribes to. `Send ended` requires `Send incoming` (see
  scoping above); `Send missed` and `Send answered` each require at least one
  selected queue.
- **Contexts** / **Queues** — at least one of the two must be set; these
  define which calls this webhook fires for ("specific scenarios").
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
  template is safe to use unmodified across all four events.

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

Template variables available for `payload_template`: `event`, `uniqueid`,
`caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`,
`duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`,
`recording_expected`, `recording_url`, `recording_file`, `missed`,
`wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`,
`holdtime`, `answered_by_member`, `answered_by_interface`. Fields not
relevant to a given event are `null`.

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

