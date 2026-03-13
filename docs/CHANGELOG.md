# Changelog

All notable changes to PearlPBX2 are documented here.

---

## [2.1.0] — 2026-03-13

### Added

**Welcome page** — home page (`/`) redesigned into a live system status dashboard:

- **DB Stats row** — 6 cards showing counts: SIP Users, Trunks, Queues, Routes, Contacts, Blocklist
- **Live Status** — Asterisk version, uptime, active calls count, and per-queue occupancy; loaded asynchronously via `/api/homepage-status/` with graceful fallback (`—`) when AMI or Redis is unavailable
- **CDR chart** — Chart.js bar chart showing total and answered calls for the last 14 days, rendered from server-side data (no extra request); shows placeholder text if no CDR data exists
- **Quick Links** — navigation cards to Dashboard, Reports, Lists, Admin Panel, SIP Users, Trunks, Queues, Routing (admin-only cards visible to superusers only)

New JSON endpoint `GET /api/homepage-status/` returns Asterisk `CoreStatus` (via AMI, 3 s timeout) and Redis channel/queue data.

---

**Lists section** — new `/lists/` section accessible to the "Report Viewer" group (no admin rights required):

| Page | URL | Description |
|------|-----|-------------|
| Hub | `/lists/` | Overview with links to all three lists |
| Blocklist | `/lists/blocklist/` | CRUD for blocked caller IDs |
| Allowlist | `/lists/allowlist/` | CRUD for allowed caller IDs |
| Contacts | `/lists/contacts/` | CRUD for caller ID → name mappings |

Each list page includes:
- Inline Add/Edit via UIKit modal (no page reload)
- Delete with confirmation
- Search by number (blocklist/allowlist: callerid, destination, reason; contacts: callerid and name)
- Sorted by `callerid` ascending

New permissions added to the "Report Viewer" group: `edit_blocklist`, `edit_allowlist`, `edit_contacts`.

---

**Analytics reports** — new section on the Reports page with 7 interactive reports (table + Chart.js bar chart):

| Report | URL | Description |
|--------|-----|-------------|
| Calls by Queue | `/reports/analytics/queue-calls/` | Answered calls per queue; optional unique callers column |
| Calls by Agent in Queue | `/reports/analytics/agent-calls/` | Answered calls per agent per queue |
| Outbound Calls by Agent | `/reports/analytics/outbound-calls/` | Outbound calls grouped by agent |
| Missed Calls by Queue | `/reports/analytics/missed-calls/` | Abandoned calls with called-back / handled-by-operator breakdown |
| Missed Calls by Hour | `/reports/analytics/missed-by-hour/` | Hourly distribution of abandoned calls |
| Call Duration by Operator | `/reports/analytics/call-duration/` | Total and average talk time per agent |
| Queue Activity | `/reports/analytics/queue-activity/` | Answered / missed / total per hour (same day) or per day (multiple days) |

**Other improvements:**

- Callback report: audio recording link added to each row
- Reports page: two-column layout (General | Analytics)
- All analytics forms use `uk-border-rounded` inputs (consistent with CDR form)
- Unique callers checkbox on "Calls by Queue" report
- Composite DB index `(event, callid)` on `queue_log` table for faster analytics queries

### Fixed

- Missed calls logic: per-call loop correctly distinguishes called-back (re-entered queue) vs handled-by-operator (outbound CDR) — mutually exclusive, searching only events after the abandon time

---

## [2.0.0] — 2026-02-14

Initial public release of PearlPBX2.

### Features

- SIP management: PJSIP transports, endpoints (users), trunks (peers)
- Dialplan editor: contexts and extensions in Asterisk AEL syntax with validation
- Call routing: prefix-based routing tables with report view
- Queue management: queues, members, rules, announcements
- Real-time operator dashboard via WebSocket (Django Channels + Redis + AMI)
- CDR report with CSV export
- Call recordings browser with audio playback
- Queue log report (5 types: summary, detailed, agent performance, queue performance, lost and found)
- Callback queue: automated outbound callback system with daemon service
- Phone provisioning: TFTP-based autoconfiguration
- REST API: blacklist/whitelist management
- Apply Changes: one-click config regeneration and Asterisk reload
- ULINE monitor: parking slot dashboard
