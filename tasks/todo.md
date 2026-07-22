# CRM Web-hooks — Implementation Plan (Variant A, approved)

## Context

CRM users need HTTP push notifications for: (1) incoming call — optionally filtered by
specific scenarios, (2) call ended — only for calls we already notified about.
Approved architecture: extend `services/dashboard/dashboard_listener.py` (single source
of truth for call state), configuration as a Django model in a new `apps/webhooks` app,
config delivered to the service via Redis (no ORM/psycopg2 in the listener). Feature is
fully optional: no active `Webhook` rows → zero runtime overhead.

## Design decisions (pinned)

- **Config key**: Django writes serialized active webhooks to Redis key `webhooks:config`
  (plain `SET`, no TTL). Listener `GET`s it at startup and re-reads on every
  `health_check_loop` tick (≤30 s to apply changes, no service restart).
- **Notified-call marker**: `webhook:notified:{uniqueid}` — `SETEX` with
  `REDIS_STATE_TTL` (7200 s). Value: JSON `{"webhooks": ["<name>", ...], "call":
  {caller_id_num, caller_id_name, exten, context, queue, started_at}}`.
  "Ended" webhook fires only if this marker exists; marker is deleted after firing
  (guarantees at-most-once "ended" and only for calls we announced).
- **Incoming classification** (server-side, config-driven):
  - `handle_newchannel`: event `Context` ∈ webhook's selected contexts;
  - `handle_queue_caller_join`: event `Queue` ∈ webhook's selected queues;
  - a webhook already listed in the marker for this uniqueid is skipped (dedup when
    both a context and a queue match the same call).
- **Missed call event** (`call.missed`): fired from `handle_queue_caller_abandon`
  (same place as the Slack hook) for webhooks with `send_missed=True` whose queues
  match. Sent **immediately per call** — no debounce/aggregation (that stays
  Slack-only; CRM needs one activity per missed call). Does NOT require the
  `webhook:notified` marker (a missed call is worth a CRM record even if no
  "incoming" was sent). Payload: `event="call.missed"`, uniqueid, queue, caller_id,
  wait_time (now − join_time from queue state, when known), timestamp. The abandon
  also updates the marker (if present) with `missed: true`, so the subsequent
  "ended" payload carries `missed: true` and CRM can correlate.
- **Shared HTTP transport**: one low-level `_post_json(url, body, headers, timeout)`
  in `webhook_sender.py` used by BOTH the webhook sender and `_post_to_slack`
  (Slack keeps its own debounce/aggregation and text format on top). Future option
  (not now): reimplement Slack notifications as a Webhook row with a template.
- **Duration for "ended"**: `now - started_at` from the marker (the channel-state
  `duration` field is never updated — always 0). Include `ANSWEREDTIME` /
  `CDR(billsec)` from `channels_state[channel]["variables"]` when present.
- **Payload**: default JSON; optional per-webhook custom template — a JSON object whose
  string values may contain `${var}` placeholders (`string.Template.safe_substitute`;
  `$`-syntax chosen because `{}` collides with JSON). Variables: `event, uniqueid,
  caller_id_num, caller_id_name, exten, context, queue, timestamp, duration, cause,
  cause_txt, answered_time, billsec, recorded, recording_expected, recording_url,
  recording_file, missed, wait_time`.
- **Delivery**: `asyncio.create_task` → `asyncio.to_thread(urllib.request...)` (same
  pattern as `_post_to_slack`), per-webhook timeout, N retries with short async sleep
  between attempts, all errors logged, never propagate into event handlers.
- **Auth/security**: optional custom headers (JSONField) + optional `secret` → HMAC-SHA256
  of the body in `X-PearlPBX-Signature: sha256=<hexdigest>` header.
- **Bonus semantic events**: when a webhook matches, also `publish_event("call_incoming",
  ...)` / `publish_event("call_ended", ...)` to `asterisk:events`.
- **Call recording link** (new requirement, priority: "ended" first):
  - Recording is started by the FastAGI service (`services/fastagi/fastagi.py:
    mixmonitor()`), which sets channel variable `MIXMONITOR=1/0`; Asterisk itself sets
    `MIXMONITOR_FILENAME` when MixMonitor starts. Listener captures both via `VarSet`
    by adding them to `important_vars` in `handle_varset()`.
  - The recording URL is **deterministic from uniqueid** and known at call start, hence
    usable as the predicted URL. Payload `recording_url` points to the **token-protected
    API endpoint**: `{base_url}/api/v1/recordings/{uniqueid}/` (CRM is a machine
    consumer; DRF defaults `TokenAuthentication` + `IsAuthenticated` apply — no
    permission granularity for now, per user decision). The session-protected UI URL
    `/reports/audio/uid/{uniqueid}/` stays for humans.
  - "Ended" payload: `recorded` (true/false; null if unknown, e.g. after AMI reconnect
    the variables are lost), `recording_url` (absolute; null when not recorded),
    `recording_file` (relative path from `MIXMONITOR_FILENAME`, optional).
  - "Incoming" payload (prediction): `recording_expected` (true/false from `MIXMONITOR`
    var if already set — for queue-matched calls AGI runs before `Queue()` so it usually
    is; null = unknown for context-matched `Newchannel`, which fires before AGI) and
    `recording_url` (always the deterministic URL; CRM combines it with the flag).
  - `base_url` comes from a new setting `PEARLPBX_PUBLIC_URL` (env), serialized into
    `webhooks:config` by Django — the listener itself has no Django settings access.
  - **Required fix**: `AudioFileByUniqueidView` (`apps/reports/views.py`) currently only
    probes legacy flat paths `{MONITOR_DIR}/{uniqueid}.wav|.mp3`; add a fallback lookup
    `MonitorFilenames.objects.filter(cdr_uniqueid=uniqueid)` → `get_audio_file_path()`
    so the predicted URL serves new-style `YYYY/MM/DD/...` recordings.
  - Token issuance: existing `rest_framework.authtoken` (token created in Django admin,
    same as for the rest of the API) — no new auth machinery.
- All code text in English. No git add/commit (user commits manually).

## Tasks

### 1. New app `apps/webhooks`
- [x] `apps/webhooks/apps.py` — `WebhooksConfig` (template: `apps/callback/apps.py`);
      `ready()` does a best-effort config re-sync to Redis (try/except, so `migrate`
      and offline-Redis don't break).
- [x] `apps/webhooks/models.py` — model `Webhook`:
      `name` (unique), `description` (blank), `is_active` (default True),
      `url` (URLField), `send_incoming` (bool, default True), `send_ended` (bool,
      default True), `send_missed` (bool, default False),
      `contexts` (M2M → `core.DialplanContext`, blank),
      `queues` (M2M → `core.Queue`, blank), `headers` (JSONField, default dict, blank),
      `secret` (CharField, blank), `timeout` (PositiveSmallIntegerField, default 5),
      `retries` (PositiveSmallIntegerField, default 1), `payload_template`
      (JSONField, null/blank = default payload). `db_table = "webhook"`.
- [x] `apps/webhooks/sync.py` — `serialize_webhooks()` + `sync_webhooks_config()`:
      builds `{"webhooks": [...], "base_url": settings.PEARLPBX_PUBLIC_URL,
      "updated_at": iso}` from active rows and `SET`s `webhooks:config` via
      `redis.Redis.from_url(settings.REDIS_URL)`.
- [x] `pbx/settings.py` + `env.sample`: new `PEARLPBX_PUBLIC_URL` (default
      `http://localhost:8000`) — public base URL for building recording links.
- [x] `apps/webhooks/signals.py` — `post_save`, `post_delete`, `m2m_changed`
      (contexts, queues) → `sync_webhooks_config()`; connected in `WebhooksConfig.ready()`.
- [x] `apps/webhooks/admin.py` — `WebhookAdmin`: list_display
      `["name", "url", "is_active", "send_incoming", "send_ended"]`,
      `filter_horizontal = ["contexts", "queues"]`; form: `secret` uses
      `PasswordWithToggleInput` (`core/widgets.py`); `clean()` requires at least one
      of contexts/queues selected and validates `payload_template` placeholders.
- [x] Migration (`makemigrations webhooks`), add `"apps.webhooks"` to `INSTALLED_APPS`
      (`pbx/settings.py`).
- [x] Management command `sync_webhooks` (manual re-sync after Redis data loss).

### 2. Sender module `services/dashboard/webhook_sender.py`
- [x] `_post_json(url, body_bytes, headers, timeout)` — stdlib urllib POST, returns status.
- [x] `WebhookManager(redis_client, logger)`:
      - `async load_config()` — GET `webhooks:config`, parse, cache list; tolerant to
        missing key / bad JSON (feature off).
      - `async on_incoming(source, call_info)` — match by context or queue, dedup via
        marker, build payloads, fire sends, upsert marker (`SETEX`), return matched names.
      - `async on_hangup(uniqueid, hangup_info)` — GET+DEL marker, fire "ended" sends
        for webhooks still active, return matched names.
      - `async on_abandon(queue, call_info)` — match by queue + `send_missed`, fire
        "missed" sends immediately (no marker required), set `missed: true` in the
        marker when one exists.
      - payload builder: default schema (incoming: `event="call.incoming"`, uniqueid,
        caller fields, exten, context, queue, timestamp; ended: `event="call.ended"`,
        + duration, cause, cause_txt, answered_time, billsec) or custom template
        substitution; HMAC signing; `enabled` property (non-empty config).
      - `_send_with_retries(...)` — create_task + to_thread + retries; log result.

### 3. Integrate into `services/dashboard/dashboard_listener.py`
- [x] `__init__`: `self.webhooks = WebhookManager(self.redis_client, self.logger)`.
- [x] `process()`: `await self.webhooks.load_config()` before main loop.
- [x] `health_check_loop()`: add `await self.webhooks.load_config()` per tick.
- [x] `handle_newchannel()`: after `publish_event`, if `self.webhooks.enabled` →
      `on_incoming("context", ...)`; on match → `publish_event("call_incoming", ...)`.
- [x] `handle_queue_caller_join()`: same via `on_incoming("queue", ...)` (queue name,
      caller info from event; started_at now).
- [x] `handle_queue_caller_abandon()`: next to the Slack block →
      `await self.webhooks.on_abandon(queue_name, {...})` (caller_id, uniqueid,
      wait_time from queue-state `join_time`); on match →
      `publish_event("call_missed", ...)`.
- [x] `_post_to_slack()` refactored onto the shared `_post_json` transport from
      `webhook_sender.py` (behavior unchanged: debounce, aggregation, text format).
- [x] `handle_varset()`: extend `important_vars` with `MIXMONITOR` and
      `MIXMONITOR_FILENAME` (recording signal + file path on the caller channel).
- [x] `handle_hangup()`: before deleting state → collect `variables` from
      `channels_state` (incl. MIXMONITOR vars), `await self.webhooks.on_hangup(uniqueid,
      {...})`; on match → `publish_event("call_ended", ...)`.
- [x] `WebhookManager`: build `recording_*` payload fields — ended: `recorded` /
      `recording_url` / `recording_file`; incoming: `recording_expected` /
      `recording_url` (deterministic `{base_url}/reports/audio/uid/{uniqueid}/`).
- [x] All webhook calls wrapped so failures never break dashboard handlers.

### 3a. Recording access: reports fix + token API endpoint
- [x] Shared helper `find_recording_path_by_uniqueid(uniqueid) -> str | None` in
      `apps/reports/` (or reuse point agreed during implementation): legacy flat probe
      `{MONITOR_DIR}/{uniqueid}.mp3|.wav` + fallback lookup `MonitorFilenames` by
      `cdr_uniqueid` → `get_audio_file_path()`.
- [x] `AudioFileByUniqueidView` (`apps/reports/views.py`): use the shared helper
      (fixes new-style `YYYY/MM/DD/...` filenames for the UI URL).
- [x] New API view `apps/api/views/recordings.py` — `GET /api/v1/recordings/
      <uniqueid>/`: DRF `APIView` with default token auth, validates uniqueid format,
      resolves file via the shared helper, serves via `_serve_audio_file_response`
      (Range support already there); 404 when no recording. Register in
      `apps/api/urls.py`; annotate for drf-spectacular schema.

### 4. Tests
- [x] `apps/webhooks/tests.py`: serialization format; signals call sync (mock redis);
      admin form validation (filters required, bad template rejected); template
      substitution happy path.
- [x] `services/dashboard/tests.py`: WebhookManager matching (context/queue/dedup),
      marker lifecycle (incoming → marker set; hangup → ended only when marker exists,
      fired once), default & templated payloads, HMAC signature, config reload,
      disabled-feature no-op, recording fields (MIXMONITOR=1 → recorded+url;
      MIXMONITOR=0 → recorded=false, url=null; vars absent → recorded=null;
      incoming prediction true/false/unknown), missed event (queue match +
      send_missed, fires without marker, immediate, marker gets missed=true and
      "ended" carries it). Mock redis client + patch `_post_json`.
- [x] `apps/reports/tests.py`: AudioFileByUniqueidView falls back to MonitorFilenames
      by cdr_uniqueid for new-style `YYYY/MM/DD/...` filenames.
- [x] `apps/api/tests.py`: `/api/v1/recordings/<uniqueid>/` — 200 with valid token,
      401 without, 404 when no file, invalid uniqueid rejected.
- [x] `pytest.ini`: add `services/dashboard` to `testpaths`.
- [x] Run: `pytest apps/webhooks services/dashboard` + full `pytest`.

### 5. Docs
- [x] `services/dashboard/README.md`: new "CRM Webhooks" section (flow, Redis keys,
      payload schemas, signature verification example).
- [x] `env.sample`: no new vars needed (note in README).

## Verification (end-to-end, without Asterisk)
1. `python manage.py migrate && python manage.py test` / `pytest`.
2. Start a local catcher (scratchpad script printing POST bodies on :8099).
3. In admin create a Webhook (url=http://127.0.0.1:8099, context=incoming) →
   check `redis-cli GET webhooks:config`.
4. Unit-level simulation: feed fake `Newchannel`/`Hangup` events into handlers
   (as in existing app tests) and assert catcher received incoming+ended, and
   `webhook:notified:*` marker created/removed.
5. On a live system: place a real inbound call, watch
   `journalctl -u <dashboard unit> -f` for "Webhook sent" lines.

## Review

Implemented as planned, no scope changes during implementation.

**New files**: `apps/webhooks/` (models, admin, signals, sync, management
command `sync_webhooks`, migrations, tests), `services/dashboard/webhook_sender.py`
+ `services/dashboard/tests.py`, `apps/reports/services/recordings.py`,
`apps/api/views/recordings.py`.

**Modified**: `services/dashboard/dashboard_listener.py` (webhook hooks in
`handle_newchannel`, `handle_queue_caller_join`, `handle_queue_caller_abandon`,
`handle_hangup`, `handle_varset`, `health_check_loop`, `process`, `shutdown`;
`_post_to_slack` now delegates to the shared `post_json` transport, behavior
unchanged), `apps/reports/views.py` (`AudioFileByUniqueidView` uses the shared
recording-lookup helper), `apps/api/urls.py`, `pbx/settings.py`
(`PEARLPBX_PUBLIC_URL`, `INSTALLED_APPS`, spectacular description),
`env.sample`, `pytest.ini` (added `services/dashboard` to testpaths).

**Verification performed**:
- `python manage.py check`, `makemigrations --check --dry-run` — clean.
- `python manage.py migrate webhooks` — applies cleanly against local Postgres.
- Full `pytest` suite: 217 passed (98 in the new/touched areas: webhooks,
  api, reports, dashboard service).
- `python manage.py spectacular --file /dev/null` — schema generates without
  errors (new `recordings` endpoint included).
- Manual end-to-end smoke test (scratchpad script, removed after use): real
  `redis-server` on a throwaway port + a local HTTP catcher server + a real
  `WebhookManager` instance driven through `on_incoming` → `on_abandon` →
  `on_hangup`. Confirmed: `call.incoming` fires with a deterministic
  `recording_url` and `recording_expected: null` for a context-matched call;
  `call.missed` fires immediately without requiring the marker; `call.ended`
  fires with `recorded: true`, the populated `recording_url`/`recording_file`,
  and `missed: true` correlated from the abandon event; HMAC signature
  verified against the raw body; the `webhook:notified:*` marker was created
  on incoming and deleted after hangup (confirmed via `redis-cli`-equivalent
  GET).

**Not covered by this task** (deliberately, per plan / user scope): running
against a live Asterisk instance with real AMI events; a UI/admin page beyond
the Django admin `Webhook` model; guaranteed-delivery/persistent retry queue
for webhooks (best-effort only, matches the existing Slack notification
pattern); per-token permission scoping for the recordings API (explicitly
declined by the user for this iteration).

## Follow-up: `call.answered` event (added 2026-07-22)

Prompted by analyzing `/Users/rad/git/projects/Customers/ExpressT/express_agi.py`
(their Express Taxi AGI, fired from the `Queue()` `agi` param when a member
answers) — PearlPBX2 already has the AMI-level equivalent (`AgentConnect`,
handled in `handle_agent_connect`), just never wired into the webhook system.
Also found and fixed a latent bug: `handle_agent_connect` read a non-existent
`DestChannel` field (AgentConnect has no such field — always `None`, silently
unused since the frontend never read `member_channel` either); replaced with
`Member`/`Interface`.

**Added**: fourth event `call.answered`, fired from `handle_agent_connect`
(queue-based only, like `call.missed`; new `send_answered` model field,
requires ≥1 queue). Payload: `member_name`, `member_interface`,
`member_number` (extracted via the same `SIP|PJSIP/` regex pattern as
`express_agi.py`'s `extract_member_number`), `ringtime`, `holdtime` (both
straight from the AMI event, previously unused). Does not require the
`webhook:notified` marker (same rationale as `call.missed`). When a marker
exists, stamps it with `answered_by_member`/`answered_by_interface`, which
`call.ended` then carries.

**Modified**: `apps/webhooks/models.py` (`send_answered` field + new
template variables), `apps/webhooks/admin.py` (validation: requires a queue),
`apps/webhooks/sync.py` (serializes `answered` event), new migration
`0002_webhook_send_answered.py`, `services/dashboard/webhook_sender.py`
(`on_agent_connect`, `answered_by_*` in `_on_hangup`),
`services/dashboard/dashboard_listener.py` (`extract_member_number()` helper,
fixed `handle_agent_connect`, wired into `WebhookManager`).

**Tests**: `apps/webhooks/tests.py` (serialization, admin validation),
`services/dashboard/tests.py` (`TestAgentConnect` — matching, event
subscription requirement, marker correlation into `call.ended`, `null` when
never answered; `TestExtractMemberNumber`). Full suite: 228 passed.
Manual smoke test (real Redis + HTTP catcher, script discarded after use):
confirmed `call.answered` fires and `call.ended` correctly carries
`answered_by_member`/`answered_by_interface` from the marker.

**Docs updated**: `services/dashboard/README.md`, `docs/ua/crm-integration.md`,
`docs/ua/crm-integrator-guide.md` (event table, payload examples, template
variable list, code samples, FAQ, checklist all extended for the 4th event).

**Out of scope**: `Customers/ExpressT/express_agi.py` itself is untouched —
it remains a separate, Express-Taxi-specific integration; this only adds a
general, configurable PearlPBX2-side equivalent.
