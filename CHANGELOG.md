# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- **CRM webhooks: separate outgoing-call event chain** — new events `call.outgoing` / `call.outgoing_answered` / `call.outgoing_ended`, fired for calls placed by a SIP user (never a trunk), independent of the existing inbound chain (`call.incoming` / `call.answered` / `call.missed` / `call.ended`). `Webhook` gained `send_outgoing`, `send_outgoing_answered`, `send_outgoing_ended` (migration `0005_webhook_outgoing_events.py`); each requires at least one selected routing table, mirroring how inbound events require a context or queue. New payload fields `direction` (`"inbound"`/`"outbound"`), `dest_channel`, `dial_status`, `answered`. Outgoing-call detection is endpoint-based, not context-based: both a SIP user and a trunk can end up with a PJSIP context equal to a routing table's name, so `apps/webhooks/sync.py` now serializes a `sip_users` map (`{endpoint: routing_table}`, SIP users only) into `webhooks:config`, and `webhook_sender.extract_endpoint()` resolves the AMI channel's endpoint against it — a trunk's channel never matches, even sharing a routing table's name with a SIP user. `services/dashboard/dashboard_listener.py` wires `AMI DialEnd` (`DialStatus=ANSWER`) to `call.outgoing_answered`, closing a gap noted in the previous release (direct/non-queue calls previously had no "answered" signal at all).

### Changed

- **BREAKING for existing `Webhook` rows that use `routing_tables`** — before this release, `routing_tables` were merged into the same `contexts` list used for `call.incoming` matching (added in 2.7.1), so a webhook configured with only a routing table fired `call.incoming`/`call.ended` for outbound calls. Migration `0006_migrate_routing_table_webhooks.py` translates existing rows automatically (`send_outgoing = send_incoming`, `send_outgoing_ended = send_ended`; inbound flags are cleared only if the row had no `contexts`/`queues` of its own), but **the CRM-side handler must be updated** to expect `call.outgoing*` instead of `call.incoming`/`call.ended` for those calls. Deploy order: `migrate` + `sync_webhooks` first, then restart `dashboard-listener` — an old listener process doesn't know the new `webhooks:config` keys (`sip_users`, separate `routing_tables`) and won't fire the outgoing chain during the rollout window.
- `apps/webhooks/models.Webhook.routing_tables` help text and admin validation updated to reflect that routing tables now filter only the outgoing chain, never the inbound one.

## [2.7.1] - 2026-08-11

### Added

- **CRM webhooks: outbound calls now match via routing table** — `Webhook` gained a `routing_tables` M2M field (migration `0004_webhook_routing_tables.py`); a SIP user's PJSIP context is its routing table's name, so outbound calls were never matched by webhooks that only listed inbound `DialplanContext`s. `apps/webhooks/sync.py` merges routing table names into the same `contexts` list sent to the dashboard listener; admin form, m2m signals, and tests updated accordingly.
- **Public release files** — `LICENSE` (PolyForm Shield 1.0.0 — permits any use, including commercial, except operating a competing product/service), `NOTICE`, `CONTRIBUTING.md`, `QUICKSTART.md` (Ansible and Docker Compose install paths), SPDX headers (`LicenseRef-PolyForm-Shield-1.0.0`) in `core/models.py`, `core/conf.py`, `manage.py`, `pbx/settings.py`.
- **Full Docker Compose stack** — new `services/fastagi/Dockerfile`, `services/dashboard/Dockerfile`, `services/callback/Dockerfile`; `docker-compose.yml` gained `fastagi`, `dashboard-listener`, `callback-service` (opt-in via `--profile callback`), and `asterisk-init`, which seeds a minimal AMI-enabled `manager.conf` and patches `modules.conf` to load `res_crypto.so` before Asterisk's first boot — the vendor `andrius/asterisk:22` image ships both AMI disabled and `res_crypto` unloaded (the latter breaks the image's own healthcheck). `docker-entrypoint.sh` runs `migrate`/`collectstatic` idempotently on every `django` container start. `docker-compose.override.yml` gives `django` a source bind mount + `uvicorn --reload` for local development, picked up automatically by `docker compose up`.
- **`PARKING_ULINE_MIN`/`PARKING_ULINE_MAX`** explicitly declared in `pbx/settings.py` (previously only read via `getattr(..., default)` in `apps/dashboard/views.py`); documented in `env.sample`.
- **`FASTAGI_HOST`/`FASTAGI_PORT` env vars** for `services/fastagi/fastagi.py` — the server previously always bound `127.0.0.1:4573`, unreachable from a separate Asterisk container; defaults unchanged for existing bare-metal/systemd installs.

### Changed

- **License**: the project is released under **PolyForm Shield 1.0.0** (source-available) — permits any use, including your own commercial deployment, except building a competing product or service on the code. See `LICENSE`/`NOTICE`/README `## License`.
- **README** rewritten: license badge + Quick Start badge, `## Quick Start` now points to `QUICKSTART.md`, `## License` and `## Contributing` sections rewritten for the new license and `CONTRIBUTING.md`.
- **`DJANGO_SECRET_KEY` generation hint** switched from a Django management-command one-liner to `openssl rand -hex 50` (`env.sample`, `pbx/settings.py`) — the former assumed Django was already installed locally, which isn't true for the Docker-first setup path.
- **`.gitignore`**: added `.env`, `*.env`, `staticfiles/`, `*.pyc`, `.idea/`, `local_settings.py`, `tasks/`.
- **`docs/` reorganised**: `CHANGELOG.md` moved to the repository root; `docs/en/install_asterisk.md` and `docs/en/INSTALL.md` removed (superseded by `ansible/install.yml`, which already automates everything they described by hand — including the `/etc/asterisk` ownership fix); `docs/en/realtime_in_future.md` moved to the (git-untracked) `tasks/` directory as an internal roadmap note. `tasks/` itself removed from git tracking (internal planning docs, not part of the public release) — files kept on disk.

### Fixed

- **Static files not served under Docker** — `DEBUG` is `False` even in `DEVMODE=Development` here (only `without_asterisk_on_localhost` flips it), so Django wasn't serving `/static/` itself and there is no nginx in front of the `django` container in Docker Compose. Added `whitenoise` + `WhiteNoiseMiddleware`; no effect on bare-metal/Ansible installs where nginx already serves `/static/` first.
- **`django` service `REDIS_URL` misconfigured in `docker-compose.yml`** — it was set via unused `REDIS_HOST`/`REDIS_PORT` variables (a pattern only the standalone services read); Django itself only reads a single `REDIS_URL`, which was silently falling back to `redis://localhost:6379` inside the container. Fixed to `REDIS_URL=redis://redis:6379`; this was breaking the `/dashboard/ulines/` page and would also have broken the WebSocket dashboard (`channels_redis` uses the same setting).
- **Broken `docs/openapi.yaml` link in README** — the file lives at `docs/en/openapi.yaml`; README now links to both `docs/en/API.md` and `docs/en/openapi.yaml`.

## [2.7.0] - 2026-08-10

### Added

- **AEL global variables** — new `DialplanGlobalVariable` model (`core/models.py`, migration `0080`) lets an admin define named `globals { }` entries via the Django admin, emitted at the top of the generated `extensions.ael` by `make_dialplan_globals()` in `core/conf.py`. Name/value are validated with new `validate_ael_variable_name`/`validate_ael_variable_value` validators in `core/validators.py` (identifier syntax; no `;` or line breaks in the value). Covered by new tests in `core/tests.py`.
- **Calls by Destination Number report** — `AnalyticsDestinationCallsView` (`apps/reports/views.py`), template `analytics_destination_calls.html`, and `AnalyticsDestinationCallsForm`, registered at `/reports/analytics/destination-calls/`. Counts answered/total external inbound calls grouped by destination (B-number) — inbound leg must belong to a `SIPPeer` — with unique-caller counts, average talk time, filters for destination/exclude-contacts/top-N, and CSV export. Gated by `view_analytics_reports`. Translations updated for en/es/uk.
- **`backup_asterisk.sh`** — daily `tar.gz` backup of `/etc/asterisk` with configurable retention (`RETENTION_DAYS`, default 14 days) and a Slack alert on failure. Configured via `/etc/PearlPBX/backup_asterisk/env` (templated from `backup_asterisk.env.j2` in the `system` Ansible role), backing up into `/var/backups/asterisk-etc`; installed as a daily cron job (02:30) by the `pearlpbx2` role.

### Changed

- **English-only API responses** — new `core.middleware.ForceEnglishAPIMiddleware` forces the `en` locale for any request under `/api/`, regardless of `Accept-Language` or the caller's session locale, so external integrations get stable English messages.
- **Channel-classification helpers extracted** — new `apps/reports/services/channels.py` module (`peer_channel_regex()`/`user_channel_regex()`) replaces the inline regex-building previously duplicated in `CDRReportView`; regexes are now computed lazily and memoized, and an empty SIPPeer/SIPUser list yields `Q(pk__in=[])` instead of a malformed regex.
- **`pg_backup_pearlpbx2` moved from `cron.daily` to an explicit cron entry** — now runs daily at 01:30; the legacy `/etc/cron.daily/pg_backup_pearlpbx2` script is removed during install.
- **`syncmp3.sh`** — `BACKUP_MP3_DAYS=0` now disables backup-directory cleanup instead of deleting every file in it.

### Fixed

- **CRM webhook `call.answered`/`call.missed` missing destination number** — `services/dashboard/webhook_sender.py`'s `_on_agent_connect`/`_on_abandon` now enrich their payloads with `exten`/`context` from the `webhook:notified:{uniqueid}` marker (the same data already included in `call.incoming`/`call.ended`), so CRM integrations can see which number the caller dialed for answered/missed queue calls too. Covered by new tests in `services/dashboard/tests.py`.
- **Ansible update playbook** — `manage.py showmigrations`/`migrate`/`collectstatic` steps in `ansible/update.yml` now run with `--skip-checks`, so Django system checks unrelated to the update (e.g. warnings from in-progress model changes) no longer abort the update process.
- **Env-file parsing in Ansible update/rollback** — `ansible/update.yml` and `ansible/rollback.yml` no longer read `/etc/PearlPBX/PearlPBX2/env` via `slurp` + base64 decode; `update.yml` now uses `lookup('file', …)` with a regex that correctly handles digits in variable names and strips surrounding quotes from values.

## [2.6.0] - 2026-07-24

### Added

- **Ansible rollback procedure** — `rollback.sh` plus `ansible/rollback.yml` and `bin/pearlpbx2_resolve_rollback_target.py` let an admin roll a deployment back N steps using a deploy-state ledger written by `update.yml`: it resolves the target commit/migration state, reverts Django migrations while the newer migration files are still on disk, checks out and syncs the rolled-back code (aborting if the source repo has uncommitted changes), reinstalls dependencies for the main app and the `callback`/`dashboard`/`fastagi` services, and restarts them. `ansible/update.yml` now also ensures the deploy-state directory exists before writing the ledger.
- **`sync_manager_users` management command** (`core/management/commands/sync_manager_users.py`) — creates/updates the AMI `ManagerUsers` records for the built-in `callback`, `dashboard_listener`, and `fastagi` services from fixed scopes, mirroring `manager.conf.j2`; wired into the Ansible `pearlpbx2` role install so these accounts are (re)provisioned automatically instead of requiring manual `manager.conf` edits. Covered by new tests in `core/tests.py`.
- **Token authentication for dashboard WebSocket and read-only JSON API** — `apps/dashboard/consumers.py`'s `AsteriskEventsConsumer.connect()` now also accepts a DRF auth token (via `?token=` query param or `Authorization: Token <key>` header) when there is no authenticated session; a matching `token_or_login_required` decorator in `apps/dashboard/views.py` extends the same fallback to the read-only endpoints (`get_sip_endpoints`, `get_queue_state`, `get_all_queues`, `get_all_channels`, `get_channel`, `get_active_calls`, `get_missed_calls`, `get_channels_by_type`), enabling CRM/external integrations that can't rely on Django sessions. `docs/ua/crm-integrator-guide.md` updated accordingly.

### Changed

- **`ALLOWED_HOSTS` during install** now includes the host's FQDN, `localhost`, and all detected IPv4 interface addresses (in addition to the short hostname and `127.0.0.1`), so the admin UI is no longer rejected with a 400 when reached via a secondary network interface's IP.
- **`CHANNEL_LAYERS` Redis backend** given explicit `capacity` (256) and `expiry` (60s) settings instead of relying on channels_redis defaults.
- **Ansible install playbook simplified** — removed the interactive timezone-confirmation preflight step and the PostgreSQL system-timezone-sync task (`ansible/install.yml`, `ansible/roles/postgres/tasks/main.yml`); the `asterisk` role now pre-seeds `/etc/asterisk` with PearlPBX2's own baseline configs before running `make basic-pbx`, so Asterisk's demo queues/agents are never installed in their place; `collectstatic` now runs with AMI connection settings and `CSRF_TRUSTED_ORIGINS` in its environment.



### Added

- **CRM webhooks** (`apps/webhooks/`) — new `Webhook` model lets an admin register one or more CRM endpoints that receive JSON POST notifications for call events (incoming, answered, ended/missed), driven from `services/dashboard/dashboard_listener.py` via the new `services/dashboard/webhook_sender.py`. Payloads are built from a configurable, validated `payload_template` (JSON object with `${variable}` placeholders such as `caller_id_num`, `queue`, `recording_url`, `wait_time`, etc.), added in a follow-up migration (`0003_alter_webhook_payload_template.py`). A `sync_webhooks` management command and `apps/webhooks/sync.py` keep webhook definitions in sync. Documented in `docs/ua/crm-integration.md` and `docs/ua/crm-integrator-guide.md`.
- **Call recording lookup API** — `GET /api/v1/recordings/<uniqueid>/` (`apps/api/views/recordings.py`, backed by `apps/reports/services/recordings.py`) serves the recorded audio (wav/mp3, Range-request support) for a given Asterisk uniqueid; this is the deterministic URL delivered to CRMs as `recording_url` in webhook payloads.
- **ConfBridge conference calling** — new `POST /api/v1/calls/conference/` endpoint (`apps/api/views/calls.py`, `ConferenceSerializer`) originates multiple parties (e.g. operator, client, driver) concurrently into a shared ConfBridge room, alongside the existing single-leg `/calls/originate/`. `core/ami.py` gained non-blocking `send_originate()` split out from `originate()` so conference legs dial in parallel instead of sequentially. `core/conf.py` / `pbx/admin.py` generate `confbridge.conf` default profiles; a reserved `"conference"` `DialplanContext`/`DialplanExtension` (migration `0079`) and a `core/checks.py` system check prevent an admin from creating a colliding context or routing table name. `core/validators.py` whitelists ConfBridge in the dialplan AEL validator.
- Repository docs reorganised under `docs/en/` (English) and `docs/ua/` (Ukrainian); new `docs/en/realtime_in_future.md`, `docs/ua/crm-integration.md`, `docs/ua/crm-integrator-guide.md`. `bin/rename_pearlpbx2_services.sh` added to rename legacy systemd units to the `pearlpbx2-*` naming scheme.

### Fixed

- **PJSIP outbound registration AOR contact** — `__build_aor_contact_line()` in `core/conf.py` now falls back to `registration_uri` when `contact_uri` is not set (with a warning, since registrar and media host may differ), instead of silently emitting no contact. For trunks with `registrationThere` (registering to a remote provider), the AOR now seeds a static bootstrap contact so calls aren't blackholed in the window before the first successful `REGISTER`; once registration succeeds, `remove_existing=yes` replaces it with the learned contact.

## [2.4.0] - 2026-07-16

### Added

- **Slack notifications for missed queue calls** — the dashboard listener (`services/dashboard/`) can now optionally send an aggregated Slack message when callers abandon a queue. All abandons within a configurable debounce window (default 60 s) are grouped into a single message per queue. Configure via `SLACK_MISSED_CALL_WEBHOOK_URL` and `MISSED_CALL_DEBOUNCE_SECONDS` in `services/dashboard/env`. Feature is off by default (empty webhook URL).
- **Classic AGI scripts** — `services/agi/` now ships `missed_call.py` and `unmatched_call.py` for per-call Slack notifications from Asterisk dialplan, plus a shared `agi_common.py` library with `notify_slack()` helper. Config at `/etc/PearlPBX/AGI/env`.
- **REST API migrated to Django REST Framework** — `apps/api/` endpoints for lists/blacklist/whitelist/contacts are now DRF `ViewSet`s registered via `DefaultRouter`, with proper serializers (`apps/api/serializers.py`) replacing hand-rolled `JsonResponse` views. New call-control endpoints under `apps/api/views/calls.py`, a machine-readable `docs/openapi.yaml` spec, and `docs/API.md` updated to match. `AGENTS.md` added documenting the API for agent/automation consumers.
- **Pause/unpause queue members from the dashboard** — the new live dashboard (`apps/dashboard/views.py`, `new_dashboard.html`) can send AMI `QueuePause`/`QueueUnpause` for a given interface directly from the Queues tab; restricted to staff users.
- **Queue member import management commands** — `core/management/commands/add_queue_members.py` and `import_pbx1_users.py` for bulk-importing queue members and migrating users from a legacy PBX1 install.
- **`manage.sh` helper script** for common day-to-day operational commands, alongside improvements to `install.sh` / `update.sh`.
- **Extended SIP Peer (trunk) configuration** — `host_port` replaced with three explicit fields: `registration_uri`, `contact_uri`, and `match_hosts` (migrations `0069`–`0072`), giving independent control over the registration server, AOR contact, and `identify` match hosts. Added `contact_user` and `auth_type` (plaintext/MD5) fields (migration `0073`) for trunks that require a distinct contact user or MD5 authentication.
- **Admin warning for skipped PJSIP users** — the Apply Changes page now lists SIP users excluded from `pjsip.conf` generation (e.g. due to validation failures) so misconfigurations aren't silently dropped.
- **`bin/asterisk_logrotate.sh`** — daily logrotate script for Asterisk logs, wired into the `asterisk` Ansible role.
- **`system_monitor.sh` startup Slack alert** — sends a one-time "monitoring started" message to Slack on first run per host.
- **Ansible: PostgreSQL timezone configuration** during install, and a new `manager.conf.j2` template plus expanded `docs/admin-guide.md` / `docs/user-guide.md`.
- Queue config generation now emits `maxlen`, `weight`, `setqueuevar`, `random-periodic-announce`, and `force_longest_waiting_caller` options in `queues.conf`.

### Fixed

- **CDR report timestamps** — `CDRReportView` no longer raises when a stored datetime is naive; it now falls back to formatting it as-is instead of only handling timezone-aware values.
- **Permission checks in `apps/reports/mixins.py`** simplified and corrected — removed ~70 lines of redundant/incorrect logic.
- **`queues.conf` `announce-holdtime`** now emitted as its configured numeric value instead of being coerced to a boolean.
- **PostgreSQL backup script renamed and fixed** — `bin/pg_backup_asterisk.sh` → `bin/pg_backup_pearlpbx2.sh`, with corrected environment handling in the `system` Ansible role.
- **`wav2mp3_monitor.sh` and related scripts** no longer redirect their own output into the log they monitor; `pg_backup`/`syncmp3`/`system_monitor` scripts had assorted reliability fixes.
- **`custom_list_names` table reference typo** in `services/fastagi/fastagi.py` fixed (was querying the plural `custom_lists_names`).
- **Callback scheduling** — FastAGI callback insert now uses `make_interval()` instead of string-interpolating the delay into the `INTERVAL` literal.
- **`ConfigurationFileAdmin`** no longer silently discards name/description/path edits when file content is unchanged — it now saves the row and informs the admin that no new version was created.
- **`DialplanContext` / `RoutingTable` uniqueness** — added `clean()` validation (in addition to the existing `save()` check) so the "name already used in the other model" conflict surfaces as a normal form error.
- **Phone provisioning config directory auto-created** if missing when writing a device config file; removed a dead/no-op `apply_all_configurations` view from `apps/provision/`.
- **`HomepageStatusView` AMI client** is now always logged off via `finally`, even when connecting or querying it raises.
- **`MusicOnHold.mode` / `.sort` defaults** corrected to use the actual enum members instead of a raw integer (migration `0078`).

### Changed

- **`SIPUser.md5_cred`** now computes HA1 as `MD5(username:realm:password)` per RFC 2617 (previously the realm and password were swapped).
- **`AllowedHostsIPMixin.get_client_ip`** only trusts `X-Forwarded-For` when the direct peer's address is listed in the new `PEARLPBX_API_TRUSTED_PROXIES` setting; otherwise it falls back to `REMOTE_ADDR`, closing an IP-allowlist bypass via a spoofed header.
- **`ApplyChangesView`** config file paths are now built with `os.path.join`/`os.path.normpath` and validated to stay inside `ASTERISK_ROOT_DIR`, rejecting a crafted `ConfigurationFile.path` that could otherwise escape the sandbox; the AMI connection used to apply changes is now always logged off in a `finally` block.
- **`PasswordWithToggleInput` widget** escapes field name/value/attrs before interpolating into HTML, and its "generate password" JS now draws from `crypto.getRandomValues` instead of `Math.random()`.
- **`SIPUser.secret` / `ManagerUsers.secret`** no longer require database-level uniqueness (removed `unique=True`) — multiple endpoints legitimately sharing a secret is not an error condition.
- **No committed default secrets** — `ASTERISK_MANAGER_SECRET` and `DJANGO_SECRET_KEY` no longer ship with a real fallback value; both are required via environment variables in any network-reachable `DEVMODE` (Development/Staging/Production) and raise `ImproperlyConfigured` if missing, falling back to an obviously-fake value only for `without_asterisk_on_localhost`.
- **Cookie security flags** (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) are now also enforced in Staging, not just Production.
- **Default log level lowered from DEBUG to INFO** for `core`/`apps`/`__main__` loggers to avoid leaking AMI event payloads (caller IDs, PII) into journald by default.
- **`/moh/<path>` static file serving** now requires an authenticated session (`login_required`), since the MOH tree is writable by admins.
- **Dashboard queue-control endpoints** (`hangup_channel`, `pause_queue_member`) now require `request.user.is_staff`, not just login.
- **`merge_args_env`** in the callback and dashboard services now correctly prioritises CLI arguments over environment defaults (previous logic had the priority inverted).
- **`features.conf`** default template simplified/updated.
- **Ansible**: `asterisk` role now manages `logger.conf` defaults and logrotate; `ansible.cfg` and `update.sh` fixes for the update playbook.

### Security

- **TLS/AMI/API hardening pass** ("fix the critical/high/medium issues" commits) covering: IP-spoofing via `X-Forwarded-For`, HA1 credential hash order, committed default secrets for AMI and Django, insecure `Math.random()` password generation, unescaped HTML in the password widget, a path-traversal vector in Apply Changes' config writer, missing staff checks on dashboard AMI control endpoints, dialplan validation bypass on programmatic writes (management commands/imports), and open static-file serving of the MOH directory. See details above under Fixed/Changed.

## [2.3.3] - 2026-05-24

### Security

- **TLS private key TOCTOU race fixed** — `_write_cert_file` now creates files with `0o640` permissions atomically via `os.open()`, eliminating the window where a private key was world-readable between `open()` and `chmod()`.
- **Path traversal in cert filenames blocked** — `SIPTransport.name` now validates against `[a-zA-Z_][a-zA-Z0-9_-]*` (migration `0068`); `_write_cert_file` also strips path components with `os.path.basename()` as a second line of defence.

### Fixed

- **TLS cert writes no longer trigger on config preview** — `make_pjsip_conf_transports()` is now a pure function (string only); cert files are written by the new `write_tls_cert_files()` called exclusively during Apply Changes (POST), not on the preview GET request.
- **`cert_write_dir` path normalisation** — replaced raw string concatenation with `os.path.normpath()` to handle trailing slashes in `ASTERISK_ROOT_DIR` correctly.

### Added

- **`verify_server` and `allow_reload` TLS transport options** — new boolean fields on `SIPTransport` (migration `0067`) emitted to `pjsip.conf` for TLS transports.
- **TLS certificate content stored in DB** — `cert_file`, `priv_key_file`, `ca_list_file` contents are now written to `ASTERISK_CONFIG_DIR/certificate/` on Apply Changes.

## [2.3.2] - 2026-04-27

### Fixed 
- **Queues.conf** generation - ringinuse and timeoutrestart was generated incorrect. 


## [2.3.0] — 2026-04-12

### Added

- **Queue agent info in dashboard call modal** — when a bridged call involves a queue agent, the agent name and extension are now shown in the call details modal.
- **Dashboard agent panel improvements** — queue agents tab enhanced with clearer status indicators and layout tweaks.
- **Agent state restoration after Asterisk restart** — the dashboard service now automatically re-queues paused agents when Asterisk reconnects, so pause states survive restarts.
- **AMI timeout configurable** — callback service `--ami_timeout` flag added; default raised to 60 s for more reliable trunk connections.
- **Queue activity report — exclude contacts filter** — the queue analytics report now supports filtering out specific contacts from results.
- **Link from missed-calls analytics to queue log** — the missed-calls report now includes a direct link to the queue activity log for the relevant queue.

### Fixed

- **Callback service reliability** — extensive rework: removed auto-reconnect loop (service now exits cleanly on AMI disconnect and relies on systemd restart), improved error handling and state machine for outbound callback calls.
- **Callback report links** — fixed broken links between the callback report view and individual callback records.
- **PJSIP `identify` section removed when IP:Port not defined** — `core/conf.py` no longer emits an empty `identify` block for endpoints without a static IP, preventing Asterisk config warnings.
- **CSS for wide screens (1600 px+)** — dashboard layout no longer overflows on large monitors; responsive breakpoints added.

### Changed

- **Dashboard improvements** — new API endpoint `GET /dashboard/api/queues/` supplies queue member data; dashboard listener publishes richer queue-member events to Redis; CDR report row link updated for consistency.
- **`ManageUsers.write_timeout` migration** — corrected default value in migration `0065`.

## [2.2.0] — 2026-03-29

### Added

- **New live operator dashboard** (`/dashboard/live/`) — fully rewritten dark-theme dashboard with five tabs: Overview, Queues, PJSIP, Bridged, Channels.
- WebSocket connection status indicator (LED pill showing CONNECTING / LIVE state).
- Real-time summary stats: active channels, bridged pairs, queues, waiting callers.
- Old dashboard preserved and accessible at `/dashboard/old/`; `/dashboard/` now redirects to the new dashboard.
- `GET /dashboard/api/endpoints/` — returns lists of internal SIPUser usernames and external SIPPeer names from the database, used by the frontend to classify PJSIP channels.
- `POST /dashboard/api/channels/hangup/` — terminates a call via AMI; CSRF-protected, channel name validated against allowlist regex.

### Fixed

- **CDR report — outgoing direction filter**: the query now correctly matches both `channel` (user pattern) and `dstchannel` (peer pattern). Previously only `channel` was checked, causing outgoing calls to trunk to be missed or incorrectly included.
- Audio player now stops automatically when the CDR details modal is closed.

### Changed

- **CDR table**: a "click for details" hint appears on row hover to improve discoverability.
- **Home page queue list**: rebuilt with CSS Grid (3 columns: name / waiting badge / agents) replacing the previous flex layout.
- **Media player progress bar**: click target enlarged to 20 px tall while the visible track remains 6 px with a background rail, improving seek accuracy.

## [2.1.4] — 2025-04-01

Previous stable release. See git history for details.
