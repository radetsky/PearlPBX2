*Also available in: [English](user-guide.md) | [Українська](../ua/user-guide.md) | [Español](../es/user-guide.md)*

# PearlPBX2 User Guide

**Version:** 2.7.2

---

## Contents

1. [Introduction](#1-introduction)
2. [Getting Started](#2-getting-started)
3. [Home Page](#3-home-page)
4. [Operator Dashboard](#4-operator-dashboard)
5. [ULINE Monitoring](#5-uline-monitoring)
6. [Reports](#6-reports)
7. [Analytics](#7-analytics)
8. [Lists](#8-lists)
9. [FAQ](#9-faq)

---

## 1. Introduction

PearlPBX2 is a web-based interface for managing an Asterisk PBX telephone system. It lets you:

- view the system's status in real time;
- track active calls and queues;
- view call reports and analytics;
- manage number lists (blocklist, allowlist, contacts).

A web browser is all you need to work with the system. No additional software is required.

### Who this guide is for

This guide is for **call-center operators**, **managers**, and **staff** with access via the "Report Viewer" group. These users have access to:

- the home page with system status;
- the operator dashboard (real-time mode);
- reports and analytics;
- number list management.

---

## 2. Getting Started

### Logging in

1. Open a web browser and go to your PearlPBX2 system's address.
2. You'll see a login page:
   - **Username** — your username.
   - **Password** — your password.
3. Click **Log in**.

![Login page](images/login.png)

### Logging out

Click the **Logout** button in the top menu.

### Choosing a language

The system supports three languages:

- Ukrainian (default language)
- English
- Español

Use the language switcher in the top menu, or go to `/i18n/set-language/`, to switch languages.

### Navigation

Once logged in, the top menu offers:

| Menu item | Description |
|------------|------|
| **Dashboard** (`/dashboard/`) | Operator dashboard (real-time mode) |
| **Parking** (`/dashboard/ulines/`) | Parking slot monitoring (ULINE) |
| **Reports** (`/reports/`) | Reports and analytics |
| **Lists** (`/lists/`) | Number list management |

If you have the **superuser** role, an **Admin panel** (`/admin`) item is also available — unlike the other menu items, it's visible only to superusers, not to any user with admin-level permissions.

---

## 3. Home Page

The home page (`/`) shows the overall system status.

### System statistics

The top of the page shows counts of objects in the system:

- **SIP Users** — the number of internal subscribers.
- **SIP Peers** — the number of external connections (trunks).
- **Queues** — the number of queues.
- **Routing Records** — the number of routing rules.
- **Contacts** — the number of entries in the contacts directory.
- **Blocklist** — the number of blocked numbers.

### Asterisk status

Information about Asterisk's state is shown:

- **Version** — Asterisk version (e.g. "Asterisk 22.0.0").
- **Current calls** — number of active calls.
- **Processed calls** — total number of calls processed since startup.
- **Uptime** — how long Asterisk has been running since its last start.

### Active calls and queues

- **Active calls** — the number of calls currently in progress (bridged).
- **Queues** — a list of queues with the number of waiting calls and available agents.

### CDR chart

The chart shows call counts over the last 14 days, broken down by status (ANSWERED, NO ANSWER, BUSY, FAILED).

---

## 4. Operator Dashboard

The operator dashboard (available at `/dashboard/` from the top menu, or directly at `/dashboard/live/` — both links open the same page) is a tool for monitoring the phone system in real time. It updates automatically via a WebSocket connection.

### Connection indicator

In the top right corner of the dashboard there's an indicator:

- **Connected** (green) — the WebSocket connection is active; data updates in real time.
- **Disconnected** (red) — the connection was lost. Try reloading the page.

### Dashboard tabs

#### Overview

A general system overview:

- total number of active calls;
- number of calls in queues;
- number of available agents;
- number of active PJSIP channels.

#### Queues

A list of queues with detailed information:

- queue name;
- number of calls waiting;
- number of agents (available / total);
- agent status (available / paused / busy).

Clicking a queue opens a modal with detailed information about its calls and agents.

**Pausing an agent:** each queue agent has a **Pause / Unpause** button, which pauses (or unpauses) them in the queue via AMI. This button is available only to users with **staff** rights.

#### PJSIP

A list of all SIP subscribers and trunks with their current status:

- **Online** — registered and available.
- **Offline** — not registered.

#### Bridged

A list of bridged calls (conversations in progress):

- participant channels;
- bridge identifier.

#### Channels

A complete list of all active channels with detailed information:

- channel type (PJSIP, Local, DAHDI, etc.);
- Caller ID;
- status;
- queue name (if the channel is in a queue).

### Ending a call

To end an active call, click the **Hangup** button next to the corresponding channel or call. This button is available only to users with **staff** rights.

---

## 5. ULINE Monitoring (Parking)

The **Parking** page (`/dashboard/ulines/`, the **Parking** item in the navigation menu) shows the state of parking slots.

### What is ULINE

ULINE (Unique Line Number) is a system for allocating parking slots (numbers 1–199). Each slot can be:

- **free** — available for use;
- **occupied** — a call is parked in that slot.

### How to use it

- The page updates automatically in real time.
- Occupied slots are highlighted.
- The **Flush all** button lets you free all slots. Available only to users with **superuser** rights.

---

## 6. Reports

The Reports section (`/reports/`) gives you access to call history and other data.

### CDR (Call Detail Records)

The `/reports/cdr/` page — a detailed report of all calls.

**Filters:**

- **Date range** — period (from/to).
- **Source / Destination number** — party A or B's number.
- **Source / Destination channel** — party A or B's channel (separate fields).
- **Disposition** — status: Answered, Busy, No answer, Failed.
- **Min / Max duration** — call duration (sec).
- **Call direction** — direction: Incoming, Outgoing, Internal, Transit, Unbridged Peers, Unbridged Users.

**Report columns:**

| Column | Description |
|---------|------|
| Start | Call start date/time |
| Answer | Answer date/time |
| End | End date/time |
| Duration | Call duration |
| Billsec | Conversation duration (sec) |
| Disposition | Status (ANSWERED, NO ANSWER, BUSY, FAILED) |
| Source | Party A's number |
| Destination | Party B's number |
| Context | Dialplan context |

**Export:** the **Export CSV** button lets you export the current report selection as CSV.

### Call Recordings (Monitor)

The `/reports/monitor/` page — browse and play call recordings.

- Filter by date (from/to) and party A/B number.
- Click the **Play** button to play a recording.

### Queue Log

The `/reports/queuelog/` page — a log of queue events.

- filter by queue, date (from/to), agent, event type (Abandoned, Completed by Agent, Completed by Caller, Connected, Enter Queue, Exit with Key, Exit with Timeout, Ring No Answer);
- the **Report Type** switch lets you choose the report view: Summary, Detailed, Agent Performance, Queue Performance, Lost and Found;
- the **Exclude known Contacts** checkbox lets you exclude calls from known contacts;
- view details for each call;
- an **Export CSV** button to export the report.

### Callback Report

The `/reports/callback/` page — a report on automated callback calls.

**Columns:**

- Record ID;
- Created — request date/time;
- Source — the number the callback request came from;
- Destination — the number being called back;
- status (NEW, PENDING, ANSWERED, BUSY);
- Updated — date/time of the last status update;
- Schedule — scheduled call time;
- Service — the request's service/source;
- conversation duration;
- link to the call recording (if any).

**Export:** the **Export CSV** button to export the report.

### Routing Report

The `/reports/routing/` page — call routing records, grouped by routing table (the table name is the group header, not a separate column). Each record shows:

- Prefix — the number prefix;
- Name — the routing record's name;
- Target Context — the destination context.

---

## 7. Analytics

The Analytics section (`/reports/analytics/`) contains 8 report types with Chart.js charts.

### Queue Calls

`/reports/analytics/queue-calls/` — number of calls per queue over the selected period.

### Destination Calls

`/reports/analytics/destination-calls/` — number of inbound external calls, grouped
by dialed number (B-number). Shows the total count, answers, answer rate,
unique callers, and average call duration. Filters are available for the destination number,
excluding contacts, and limiting to a top-N, along with CSV export.

### Agent Calls

`/reports/analytics/agent-calls/` — a summary of each agent's calls.

### Outbound Calls

`/reports/analytics/outbound-calls/` — outbound call statistics.

### Missed Calls

`/reports/analytics/missed-calls/` — number of missed calls over the period.

### Missed by Hour

`/reports/analytics/missed-by-hour/` — distribution of missed calls by hour of the day.

### Call Duration

`/reports/analytics/call-duration/` — distribution of calls by duration.

### Queue Activity

`/reports/analytics/queue-activity/` — queue activity by hour or day. An exclude-contacts filter is available.

### Common analytics elements

- Period selection (from/to date).
- Filtering by queue or agent.
- Chart.js-based charts (line, bar, pie).

**Note:** unlike the CDR, Queue Log, and Callback reports (section 6), the analytics pages don't have a data-export button.

---

## 8. Lists

The Lists section (`/lists/`) lets you manage number lists without needing access to the admin panel.

### Blocklist

`/lists/blocklist/` — a list of numbers whose calls are blocked.

**Adding an entry:**

1. Click **Add**.
2. Enter the **Caller ID** — the subscriber's phone number.
3. (Optional) **Destination** — a specific destination to block.
4. (Optional) **Reason** — the reason for blocking.
5. (Optional) **Expiration** — the block's expiration date.
6. Click **Save**.

**Editing:** click a row in the table — an edit modal will open.

**Deleting:** click the **Delete** button next to the entry.

### Allowlist

`/lists/allowlist/` — a list of numbers with special handling routes.

The interface is the same as the blocklist.

### Contacts

`/lists/contacts/` — a directory mapping phone numbers to subscriber names. Used to determine the Caller ID Name.

**Fields:**

- **Caller ID** — the phone number.
- **Name** — the subscriber's name.

The interface is the same as the blocklist.

---

## 9. FAQ

### How do I refresh the dashboard in real time?

The dashboard updates automatically via WebSocket. If the connection is lost (the indicator shows "Disconnected"), reload the page. If the problem persists, contact your administrator.

### Why don't I see some menu items?

Menu item visibility depends on your role in the system. If you think you need access to additional sections, contact your administrator.

### How do I listen to a call recording?

Go to **Reports → Monitor**, find the recording by date or number, and click **Play**. If the Play button is inactive, no recording is available.

### How do I add a number to the blocklist?

Go to **Lists → Blocklist**, click **Add**, enter the number, and click **Save**. Changes take effect after the administrator applies the configuration (on the next Apply Changes).

### Can I export report data?

Yes — for the **CDR**, **Queue Log**, and **Callback** reports (section 6), an **Export CSV** button is available that exports the current selection as CSV. The **Monitor**, **Routing**, and **Analytics** (section 7) pages don't have an export button — you can copy data from their tables manually.

### What should I do if the dashboard doesn't load?

1. Check your network connection.
2. Try reloading the page (F5 or Cmd+R).
3. If the problem persists, contact your administrator — Redis or the Dashboard Listener may not be running.

---

*Document created for PearlPBX2 v2.7.2. The system's interface may vary depending on the version.*
