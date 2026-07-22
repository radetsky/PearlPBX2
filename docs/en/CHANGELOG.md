# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
