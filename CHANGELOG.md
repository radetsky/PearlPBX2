# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
