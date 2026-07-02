# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- **Slack notifications for missed queue calls** — the dashboard listener (`services/dashboard/`) can now optionally send an aggregated Slack message when callers abandon a queue. All abandons within a configurable debounce window (default 60 s) are grouped into a single message per queue. Configure via `SLACK_MISSED_CALL_WEBHOOK_URL` and `MISSED_CALL_DEBOUNCE_SECONDS` in `services/dashboard/env`. Feature is off by default (empty webhook URL).
- **Classic AGI scripts** — `services/agi/` now ships `missed_call.py` and `unmatched_call.py` for per-call Slack notifications from Asterisk dialplan, plus a shared `agi_common.py` library with `notify_slack()` helper. Config at `/etc/PearlPBX/AGI/env`.

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
