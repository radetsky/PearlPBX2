# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] — feature/new_dashboard

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
