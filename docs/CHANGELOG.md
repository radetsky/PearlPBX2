# Changelog

All notable changes to PearlPBX2 are documented here.

---

## [Unreleased]

### Added

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
