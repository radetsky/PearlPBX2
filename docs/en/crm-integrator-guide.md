*Also available in: [English](crm-integrator-guide.md) | [Українська](../ua/crm-integrator-guide.md) | [Español](../es/crm-integrator-guide.md)*

# Integrating a CRM system with PearlPBX2: a technical guide

**Version:** 2.7.2

---

This document describes the procedure for integrating an external CRM system with the PearlPBX2 platform. It's written for developers who have no prior experience with telephony systems, and contains everything needed to implement the integration: the event model, the format of the transmitted data, a complete description of the REST API (including initiating outbound calls), the mechanism for retrieving call recordings, and the requirements for verifying request authenticity.

Working with this document requires only basic skills in implementing HTTP handlers (webhook endpoints) and making authenticated REST API requests. No additional telephony domain knowledge is required.

This document is a self-contained source of information: everything needed to implement the integration is laid out below, with no need to consult additional sources.

---

## Contents

1. [General interaction overview](#1-general-interaction-overview)
2. [Terminology](#2-terminology)
3. [Division of responsibilities](#3-division-of-responsibilities)
4. [Call lifecycle](#4-call-lifecycle)
5. [Events and their fields](#5-events-and-their-fields)
6. [Retrieving a call recording](#6-retrieving-a-call-recording)
7. [PearlPBX2 REST API](#7-pearlpbx2-rest-api)
8. [Dashboard API and WebSocket: a real-time channel (optional)](#8-dashboard-api-and-websocket-a-real-time-channel-optional)
9. [Verifying request authenticity](#9-verifying-request-authenticity)
10. [Configuring a custom JSON format](#10-configuring-a-custom-json-format)
11. [System behavior on delivery failures](#11-system-behavior-on-delivery-failures)
12. [Example receiver server implementation](#12-example-receiver-server-implementation)
13. [Frequently asked questions](#13-frequently-asked-questions)
14. [Integration checklist](#14-integration-checklist)

---

## 1. General interaction overview

PearlPBX2 is an enterprise telephony management system: it accepts inbound calls, distributes them among operators via service queues, and records calls. For integration purposes, a CRM system needs three pieces of information: when a call started, when it ended, and where its recording is located (if the call was recorded).

The integration is built on two mechanisms:

- **Webhooks** — PearlPBX2 sends a message to the URL specified by the CRM system at the moment an event occurs (call start, call end, a call missed in a queue). The request is a `POST` with a JSON body. No request needs to be initiated from the CRM side — it's enough to accept incoming requests at a designated endpoint.
- **REST API** — the recording audio file isn't sent directly via the webhook, given its size. Instead, the webhook contains a link to it. The file itself is fetched with a separate API request using an access token.

The sections below describe each mechanism in detail.

## 2. Terminology

- **Call** — a phone call from the moment it arrives to the moment it ends.
- **uniqueid** — a unique identifier for a **single** Asterisk channel, e.g.: `1753000000.42`. It is not a phone number or a customer identifier. It's assigned when the channel is created. It's the key for correlating events belonging to the same chain (`call.incoming` → `call.answered`/`call.missed` → `call.ended`, or `call.outgoing` → `call.outgoing_answered` → `call.outgoing_ended`) — all of them refer to the same channel and carry the same `uniqueid`.
- **linkedid** — an identifier shared by **all channels of a single logical call** (e.g. both legs of an internal call between two employees — each leg has its own `uniqueid`, but the same `linkedid`, equal to the `uniqueid` of the channel that initiated the call). If the CRM needs to merge several separate webhook events (e.g. two `call.outgoing` from two different SIP users) into a single call record, it should compare `linkedid`, not rely on `uniqueid`/`timestamp` proximity.
- **Caller ID** — the number (and, if available, the name) of the party placing the call. Carried in the `caller_id_num` / `caller_id_name` fields.
- **Context and extension (exten)** — internal PBX routing parameters that determine the call's direction and endpoint. For CRM integration purposes, it's usually enough to know these fields exist, without going into the dialplan logic.
- **Queue** — if the company distributes calls among several operators, a call first enters a service queue, from which it's handed to a free operator. If the call is made directly, without a queue, the `queue` field will be `null`.
- **Call recording** — the audio file for a call, provided the recording feature is enabled in that particular PBX's settings (it isn't always applied, and not to every call).
- **Hangup cause** — a code and text description of why a call ended (normal clearing, busy line, no answer, etc.). Used mainly for analytics purposes.
- **SIP user** — an employee's internal extension (a phone, a softphone) registered on the PBX. When such an employee initiates a call themselves, this generates outbound-chain events (`call.outgoing`, section 5.5).
- **Trunk** — the PBX's connection to an external telephone provider, through which calls arrive from customers and go out to regular numbers. Calls arriving via a trunk always belong to the inbound chain (`call.incoming`), even if technically it's an outbound call from the provider's point of view — what matters for CRM integration is who initiates the call inside the PBX (an employee or an external caller), not the physical direction of the signal on the line.

## 3. Division of responsibilities

- **The PearlPBX2 administrator** creates the webhook configuration in the PBX's admin panel: specifies the CRM server's URL, the list of events to send, and, if needed, a secret key for signing requests. This action is done entirely on the PBX side; the CRM developer only needs to provide the URL and, if needed, agree on the secret key.
- **The CRM developer** implements an HTTP endpoint to receive `POST` requests with a JSON body, and, if needed, makes requests to the PearlPBX2 API to fetch recording files — a separate access token is issued for this.

So the interaction happens in two directions: inbound (webhooks arriving from the PBX) and outbound (the CRM's requests to the API to fetch recordings).

## 4. Call lifecycle

Let's walk through the sequence of events for a single call. A customer places a call to the company's support line.

**Step 1.** The call arrives at the system. If it matches criteria set by the administrator (a particular inbound direction or queue), a `call.incoming` event is sent to the CRM server. The message contains the `uniqueid`, the caller's number, and a preliminary prediction of whether the call will be recorded (details in section 6).

At this point, the CRM system typically shows a card for the ongoing call — for example, a pop-up notification to an operator, or a draft entry in the customer interaction history.

**Step 2.** The call enters a service queue, and the caller waits to be connected to an operator. Two outcomes are possible.

Option A: **an operator picks up the call.** A `call.answered` event is sent, containing the operator's name, their extension, how long the call rang before being answered, and how long the caller waited in the queue. This event is meant for showing the customer's card to the operator at the moment they connect.

Option B: **the caller hangs up before anyone answers.** A `call.missed` event (missed call) is sent. This event arrives regardless of whether the CRM system is subscribed to `call.incoming` — a missed call is treated as significant in its own right.

**Step 3.** After the conversation ends (regardless of whether it happened immediately or after step 2A), a `call.ended` event is sent. It contains the conversation's duration, the reason it ended, data about the operator who took the call (if a `call.answered` event occurred), and a link to the audio recording, if the call was recorded.

**A key rule:** the `call.ended` event is sent exclusively for calls a `call.incoming` was previously sent for. The system tracks this state internally, so receiving an end event without a prior start event is impossible, as is sending an end event twice for the same call. The `call.missed` and `call.answered` events, by contrast, are independent and arrive regardless of any subscription to `call.incoming`.

The chain described above (`call.incoming` → `call.answered`/`call.missed` → `call.ended`) applies to calls **arriving** at the company. For calls an employee **initiates** (e.g. an operator calling a customer back), there's a separate, fully independent chain of events.

**Step 1' (outbound call).** An employee picks up and dials a number. A `call.outgoing` event is sent to the CRM server — the counterpart of `call.incoming`, but for a call initiated from inside the PBX.

**Step 2' (outbound call).** If the called party picks up, a `call.outgoing_answered` event is sent, with the time it was answered. If the line is busy, nobody answers, or the call is cancelled — this event is never sent at all.

**Step 3' (outbound call).** After the call ends (regardless of whether it was answered or not), a `call.outgoing_ended` event is sent. It contains an `answered` field that directly states whether the call connected, so the CRM doesn't have to guess the outcome from the hangup cause code.

These two event sequences — inbound and outbound — always arrive separately from one another, under different event names (`call.ended` vs `call.outgoing_ended`), even if only a single webhook is configured in the admin panel and it's subscribed to both chains at once. The `uniqueid` identifier lets you trace all the events for a single call regardless of which chain it belongs to.

Section 5 gives a detailed description of each of the seven events.

## 5. Events and their fields

All requests are `POST` with a body in `application/json` format. The event type is determined by the value of the `event` field.

### 5.1. `call.incoming` — call started

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "John Smith",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "channel_vars": {}
}
```

Field details:
- `queue` is `null` if the call was classified by direction (context) rather than by queue. If the call came in through a queue, its name will be here, e.g. `"support"`.
- The `recording_url` field is already present at this stage, before the recording file actually exists. This isn't an error: the link is built deterministically from the `uniqueid` ahead of time (details in section 6). The file at this link becomes available later, provided the call ends up being recorded.
- `recording_expected` — a preliminary estimate of the likelihood of recording. In some cases the system already has a definite answer (`true`/`false`); in others, the value is `null`, reflecting an intermediate state of uncertainty rather than an error.

### 5.2. `call.answered` — an operator picked up the call

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "John Smith",
  "queue": "support",
  "member_name": "Operator Petrenko",
  "member_interface": "PJSIP/101",
  "member_number": "101",
  "ringtime": "3500",
  "holdtime": "18",
  "timestamp": "2026-07-21T18:58:51.812900",
  "channel_vars": {"ULINE": "42"}
}
```

Field descriptions:
- `member_name` — the operator's name, as configured in PearlPBX2 for that queue member.
- `member_interface` — the operator's technical Asterisk identifier, e.g. `PJSIP/101`.
- `member_number` — the same value in a simplified form (`101`); usually more convenient for looking up the operator in the CRM system.
- `ringtime` — how long the operator's device rang before answering, in milliseconds.
- `holdtime` — how long the customer waited in the queue before being answered, in seconds (conceptually corresponds to the `wait_time` field in a missed call, but for a successful connection).

This event is generated exclusively for calls that went through a service queue; a direct connection outside a queue never triggers it.

### 5.3. `call.missed` — a call was missed in a queue

```json
{
  "event": "call.missed",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "queue": "support",
  "wait_time": 21,
  "timestamp": "2026-07-21T18:58:51.813698",
  "channel_vars": {}
}
```

The customer waited in the `support` queue for `wait_time` seconds (21 seconds in this example) and hung up before an operator answered. This event is intended, among other things, for automatically creating a callback task in the CRM system.

### 5.4. `call.ended` — call ended

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "John Smith",
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
  "recording_file": "/var/spool/asterisk/monitor/2026/07/21/x.wav",
  "channel_vars": {"ULINE": "42"}
}
```

This event carries the most data. Key fields:
- `duration` — the call's total duration in seconds, from start to end.
- `cause_txt` — a text description of why the call ended. The value `"Normal Clearing"` corresponds to a routine end of the conversation. Values like `"Busy"` or `"No Answer"` are also valid outcomes, not a sign of a system error.
- `missed` — `true` if this call was already recorded as missed (a `call.missed` event occurred).
- `answered_by_member` / `answered_by_interface` — the name and interface of the operator who took the call, provided a `call.answered` event occurred earlier. The system correlates the data between events automatically. If the call went unanswered (e.g. missed), both fields are `null`.
- `recorded` — the confirmed fact that the call was recorded (as opposed to the earlier `recording_expected` estimate). Possible values: `true`, `false`, occasionally `null` (if the recording status couldn't be determined for technical reasons).
- `recording_url` — a link to the recording file, provided `recorded: true`. If there's no recording, this is `null`, and there's no point requesting this link.
- `recording_file` — the path to the recording file on the PBX's file system, shown in the example above with a `.wav` value, since that's the format Asterisk creates the recording in right after the call ends. This field reflects the internal path at the moment the event was generated, and isn't meant for the CRM system to use: the file may later be automatically converted to `.mp3` on a schedule on the PBX side (details in section 6). Only `recording_url` should be used to fetch the audio.

Note: not every field is necessarily filled in for every call — for example, `queue` will often be `null` for direct calls. It's recommended to design event handling with possible `null` values in mind.

### 5.5. `call.outgoing` — an outbound call started

```json
{
  "event": "call.outgoing",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:51.811673",
  "channel_vars": {}
}
```

Field details:
- `caller_id_num` / `caller_id_name` here are the **employee's** number and name — the one initiating the call — not the customer's (unlike `call.incoming`, where these fields belong to the person calling in).
- `exten` — the number the employee dialed (the customer's number).
- `direction` — always `"outbound"` for this event; the field is present on every event in both chains and lets you determine which chain an event belongs to with a single check, without parsing the `event` name itself.
- This event is only sent when the call is initiated by an internal SIP user (an employee), not by a trunk (a connection to a telephone provider). Calls arriving from outside via a trunk always go through `call.incoming`, never `call.outgoing`.
- By default the PBX also doesn't send `call.outgoing` for an internal channel Asterisk has just created (via `Dial()`/`Originate()`) but hasn't yet connected to a specific number — at that point `exten` equals the system placeholder `"s"`, not a real number, and there's no point showing the CRM such an event. If this behavior needs to change, ask the PBX administrator (the `WEBHOOK_SEND_SYSTEM_CHANNELS` setting).

### 5.6. `call.outgoing_answered` — the called party picked up

```json
{
  "event": "call.outgoing_answered",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "dest_channel": "PJSIP/trunk1-0000002a",
  "dial_status": "ANSWER",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:56.203112",
  "channel_vars": {}
}
```

Field descriptions:
- `dest_channel` — the technical identifier of the route the call took (e.g. a particular trunk). This field is informational; for most CRM integrations, `exten` alone is enough to know who was called.
- `dial_status` — the value of Asterisk's AMI `DialStatus` field at the moment of the answer; here always `"ANSWER"` (values for other outcomes are described in section 5.7).

This event only arrives if the call was answered. If the line was busy, nobody answered, or the call was cancelled before it was answered — this event is never sent at all, and the sequence goes straight to `call.outgoing_ended`.

### 5.7. `call.outgoing_ended` — an outbound call ended

```json
{
  "event": "call.outgoing_ended",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operator Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "queue": null,
  "direction": "outbound",
  "dial_status": "ANSWER",
  "answered": true,
  "timestamp": "2026-08-11T18:59:24.550012",
  "duration": 28,
  "cause": "16",
  "cause_txt": "Normal Clearing",
  "answered_time": "26",
  "billsec": "26",
  "missed": false,
  "answered_by_member": null,
  "answered_by_interface": null,
  "recorded": false,
  "recording_url": null,
  "recording_file": null,
  "channel_vars": {}
}
```

This event structurally mirrors `call.ended` (section 5.4) — the same `duration`, `cause`, `cause_txt`, `recorded`/`recording_url`/`recording_file` fields for the recording, if it's enabled for outbound calls too. It additionally has two fields specific to the outbound chain:
- `answered` — a boolean: `true` if a `call.outgoing_answered` occurred before this event, `false` otherwise. This is the simplest way to determine the call's outcome without parsing the hangup cause code.
- `dial_status` — the last known `DialStatus` value: `"ANSWER"` on a successful connection, or `"BUSY"` / `"NOANSWER"` / `"CANCEL"`, etc. on a failed attempt.

The `answered_by_member` / `answered_by_interface` fields here are always `null` — they apply exclusively to a queue operator in the inbound chain (section 5.4) and have no meaning for a call an employee initiates directly.

## 6. Retrieving a call recording

**The recording file isn't sent together with the webhook.** Given the size of audio data, the webhook only contains a link to the file, which the CRM system can request separately at the moment it's actually needed (e.g. when an operator opens a call card to listen to it).

The link is built deterministically from the `uniqueid`, so it's already present in the very first `call.incoming` event, well before the call ends and the file actually appears on disk.

**Important note on file format.** On the PBX side, recordings are first created in WAV format, then converted to MP3 on a schedule (a periodic background task), after which the original WAV file is deleted. So at the moment the CRM system requests the recording, its actual file format is not known in advance and depends on whether the conversion task has already run. The endpoint accounts for this automatically: the server determines on its own which file exists on disk (`.mp3` or `.wav`) and returns the corresponding `Content-Type` (`audio/mpeg` or `audio/wav`) and `Content-Disposition` headers, with a filename that carries the actual extension. The CRM system should not (and is advised not to) assume a fixed extension — a correct implementation should determine the received file's format from the response's `Content-Type` header, not from the URL or a pre-assumed filename.

To fetch the file, make a `GET` request with an authorization header:

```bash
curl -H "Authorization: Token YOUR_TOKEN" \
  https://pbx.example.com/api/v1/recordings/1753000000.42/ \
  -o call_recording
```

The token is issued once by the PBX administrator, similar to API keys for other services, and should be stored with the same level of protection as a password.

Possible server responses:

| Response code | Meaning |
|---|---|
| `200` or `206` with the audio file | the request succeeded; `206` is returned for a partial-file request (seeking/streaming) |
| `401` | the token is missing or invalid — check the request header |
| `404` | no recording exists (the call wasn't recorded, or the file hasn't finished appearing on disk yet) |

If the request is made right after `call.ended` and returns `404`, this doesn't necessarily mean an error: writing the file to disk may lag slightly behind sending the JSON message. In that case, it's recommended to retry the request after a few seconds.

To force the browser to download the file (instead of playing it inline), add the `?download=1` parameter to the URL.

## 7. PearlPBX2 REST API

Besides receiving webhooks, the CRM system can also call the PearlPBX2 REST API directly — in particular to initiate outbound calls, bring several participants into a single conference, and (if needed) work with number lists. All endpoints are under the `/api/v1/` prefix and require authentication.

### 7.1. Authentication

The API uses token authentication. The token is sent in the `Authorization` header of every request:

```
Authorization: Token YOUR_TOKEN
```

The token is issued by the PBX administrator separately from the token used to fetch call recordings (section 6) — it's a good idea to check with the administrator whether a shared token is used, or a separate one is issued for each purpose. A request without a token, or with an invalid one, returns `401 Unauthorized`.

### 7.2. Interactive documentation (Swagger / ReDoc)

Besides this document, PearlPBX2 automatically generates a machine-readable API specification (based on `drf-spectacular`) and provides two ready-made web interfaces for it. This is useful both as a reference with an up-to-date field list, and as a tool for manually testing requests without writing any code:

- `GET /api/v1/schema/` — the OpenAPI specification itself, in JSON/YAML format. Suitable for importing into Postman, Insomnia, or for automatically generating client code (an SDK) in your programming language.
- `GET /api/v1/docs/` — the interactive **Swagger UI**. Lets you browse all endpoints, their parameters, and example responses, and run test requests right from the browser via the "Try it out" button.
- `GET /api/v1/redoc/` — the same underlying data, presented as a static, easy-to-read reference page (**ReDoc**), without the ability to run requests.

**An important note on access.** These pages aren't exempt from the general authentication requirement — like the rest of the API, they're protected by token authentication (see section 7.1), not Django session authentication. This means simply opening `/api/v1/docs/` in a browser without further action returns `401 Unauthorized`, since the browser doesn't add the `Authorization` header automatically. To use the Swagger UI, you need a browser plugin or extension that lets you add an `Authorization: Token YOUR_TOKEN` header to the page's requests, or you can view the specification through a tool like Postman/Insomnia, where the token can be set in the request configuration. For a one-off check of the specification without a browser, a plain request with a token is enough:

```bash
curl -H "Authorization: Token YOUR_TOKEN" https://pbx.example.com/api/v1/schema/
```

It's recommended to consult these sources whenever you're unsure about the current version of the API — they're generated directly from the server's code and always match its current state.

### 7.3. Initiating an outbound call

**`POST /api/v1/calls/originate/`**

This endpoint queues an outbound call for execution via the Asterisk Manager Interface (AMI). A typical use case from the CRM side is a "two-step" call (click-to-call): first the operator's internal extension is called (`channel`), and only once the operator picks up does the PBX connect them to the customer's number (`exten`).

**Request body fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `channel` | string (up to 256 characters) | Yes | — | The channel the PBX calls first, e.g. `Local/0503856087@default` or `PJSIP/0504139380@mega-provider`. |
| `exten` | string (up to 128 characters) | Yes | — | The extension or number the `channel` channel is connected to after answering, e.g. `0675653380`. |
| `context` | string (up to 128 characters) | No | `"default"` | The dialplan context the connection to `exten` is made in (detailed explanation below). |
| `priority` | integer | No | `1` | The dialplan priority (minimum value `1`). |
| `callerid` | string (up to 128 characters) | No | — | The Caller ID the called party will see, in `name<number>` format, e.g. `380443333333<0675653380>`. |
| `variable` | object (string → string pairs) | No | — | Arbitrary Asterisk channel variables, e.g. `{"userId": "0"}`. |
| `timeout_ms` | integer | No | `30000` | The maximum time to wait for the call to be answered, in milliseconds (from `1000` to `120000`). |

**What `context` means in this request.** The `"default"` value in the table above is just a placeholder example, not a system constant. In reality, `context` is the name of a routing table (`RoutingTable`) or a dialplan context (`DialplanContext`) configured by the PearlPBX2 administrator specifically for that installation, in the admin panel. Such context names are arbitrary (e.g. `Incoming`, `Outgoing`, `internal-users`) and don't follow any universal convention — each PBX installation may have its own set of names depending on how many providers, trunks, and routing scenarios are configured. **Before implementing the integration, be sure to check with the PBX administrator for the exact context names to use for your scenarios, and ask them for ready-made `channel`/`exten`/`context` request examples specific to your installation** — it's not possible to guess these values on your own.

**Example 1: a "two-step" (click-to-call) call through an internal operator.**

The PBX first calls the operator's internal extension (`channel`), and only once the operator picks up does it connect them to the customer's number (`exten`):

```bash
curl -X POST https://pbx.example.com/api/v1/calls/originate/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "Local/0503856087@default",
    "exten": "0675653380",
    "context": "default",
    "callerid": "380443333333<0675653380>",
    "variable": {"userId": "0"}
  }'
```

**Example 2: a direct call through a specific provider trunk, without a Local channel.**

In some scenarios a Local channel isn't needed at all: `channel` can point directly to a real provider channel, and `exten`/`context`/`priority` is the dialplan point Asterisk will land that channel on right after the provider answers the call. This is the standard behavior of the AMI `Originate` command — a Local channel is only needed when the first "step" is itself an internal extension (as in example 1), not when `channel` is already the call's final channel.

For example: you need to call `0504139380` directly through the `mega-provider` trunk, and route the result (once answered) to internal extension `222` in the `Incoming` routing table, with CallerID `0442222222`:

```bash
curl -X POST https://pbx.example.com/api/v1/calls/originate/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "PJSIP/0504139380@mega-provider",
    "exten": "222",
    "context": "Incoming",
    "priority": 1,
    "callerid": "0442222222<0442222222>",
    "timeout_ms": 30000
  }'
```

Here `PJSIP/0504139380@mega-provider` means "dial number `0504139380` via the SIP trunk (peer) named `mega-provider`"; `mega-provider` and `Incoming` are names that must actually exist on that particular PBX installation (agreed with the administrator, as described above).

**An important note on `callerid` in the direct trunk-call scenario.** Unlike click-to-call through an internal extension (example 1), where the CallerID is usually just informational and may be overwritten by the default dialplan logic, in the direct trunk-call scenario (example 2) the `callerid` value **is actually passed on to the provider/network** as the number the call supposedly originates from. This isn't a cosmetic field: if the specified number doesn't belong to your number pool, or isn't allowed by the provider for substitution, the call may be rejected by the carrier, flagged as spam/suspicious, or — depending on the law and the provider's policy — this could be treated as caller ID spoofing (CLI spoofing). Before using this scenario, be sure to check with the PBX administrator and the provider which numbers are allowed to be set as the CallerID for a particular trunk.

**Successful response (`200 OK`):**

```json
{
  "status": "originated",
  "message": "Originate successfully queued"
}
```

Important: a `200` status and `"status": "originated"` only mean that the command to establish the connection was accepted and passed on to AMI. This is not confirmation that the call actually happened or that the party answered — the CRM system gets that information separately via webhooks (`call.answered`, `call.ended`), correlated by the `uniqueid` of the call that resulted from the `originate`.

**Possible errors:**

| Code | Response body | Reason |
|---|---|---|
| `400 Bad Request` | `{"channel": ["This field is required."]}` (example for the `channel` field; the same applies to any other required field) | A required field wasn't filled in, or a constraint was violated (e.g. `timeout_ms` outside the `1000`–`120000` range). |
| `401 Unauthorized` | `{"detail": "Authentication credentials were not provided."}` | No authentication token, or it's invalid. |
| `502 Bad Gateway` | `{"detail": "AMI unavailable."}` | The PBX couldn't establish or maintain a connection to the Asterisk Manager Interface. |
| `502 Bad Gateway` | `{"detail": "AMI originate timed out."}` | No response from AMI within `timeout_ms` (plus a small service margin). |
| `502 Bad Gateway` | `{"detail": "Extension does not exist"}` (example; the text corresponds to the AMI message) | AMI returned an error executing the `Originate` command — the message text comes directly from Asterisk's response and can vary depending on the failure reason. |
| `503 Service Unavailable` | `{"detail": "Asterisk is disabled in this DEVMODE."}` | The PBX is running in development mode without a real Asterisk connection (test benches only, never seen in production). |

There's no separate rate limiting for this endpoint — the practical limit is defined by the throughput of the PBX's own line/trunks, so it's recommended that the CRM system control the rate of call initiation on its own, in line with agreements with the PBX administrator.

### 7.4. Initiating a conference (three or more participants)

**`POST /api/v1/calls/conference/`**

The `calls/originate/` endpoint (section 7.3) always connects exactly two participants. If you need to bring three or more people into a single conversation at once (e.g. Operator, Customer, and Driver), use `calls/conference/`: this endpoint accepts a list of channels and brings each of them into a shared conference room based on `ConfBridge`.

**The conference model.** Rooms don't need to be created ahead of time: a room comes into existence the moment the first channel joins it, and disappears when the last one leaves. The room number is an arbitrary numeric string; all participants landing on the same number hear each other.

**Request body fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `parties` | list of strings (at least 2) | Yes | — | The participants' channels, e.g. `["PJSIP/101", "PJSIP/0504139380@mega-provider", "Local/2222@internal"]`. |
| `room` | string (up to 64 characters) | No | generated automatically | The conference room number. If not specified, the server generates one and returns it in the response. |
| `context` | string (up to 128 characters) | No | the conference context configured on the PBX | The dialplan context that lands each leg in `ConfBridge`. Most integrations don't need to change this. |
| `callerid` | string (up to 128 characters) | No | — | The Caller ID applied to each of the originate legs. |
| `timeout_ms` | integer | No | `30000` | The maximum time to wait for each leg to answer, in milliseconds (from `1000` to `120000`). |

As in the driver example in section 7.3, a channel that should land on an internal extension with multi-device/fallback support should be specified via a `Local` channel (e.g. `Local/2222@internal`), not directly — this lets the dialplan logic (multiple devices, follow-me) decide where the call ultimately ends up.

**Example request** (Operator, Customer through a provider trunk, Driver through an internal extension with fallback):

```bash
curl -X POST https://pbx.example.com/api/v1/calls/conference/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parties": [
      "PJSIP/101",
      "PJSIP/0504139380@mega-provider",
      "Local/2222@internal"
    ]
  }'
```

**Response (`202 Accepted`):**

```json
{
  "room": "184920573",
  "results": [
    {"channel": "PJSIP/101", "queued": true, "detail": "Originate successfully queued"},
    {"channel": "PJSIP/0504139380@mega-provider", "queued": true, "detail": "Originate successfully queued"},
    {"channel": "Local/2222@internal", "queued": true, "detail": "Originate successfully queued"}
  ]
}
```

A `202` code and `"queued": true` mean only that the corresponding `Originate` command was queued in AMI — all legs are dialed **in parallel**, not one after another.

This is not confirmation of an answer or of the conversation being established: the CRM gets that information separately via webhooks (`call.answered`, `call.ended`) for each leg, using its own `uniqueid`.

A partial failure is possible: if one leg failed to connect while the others joined successfully, the corresponding `results` item will have `"queued": false` with an explanation in `detail`, and the rest will have `"queued": true`.

**Possible errors:**

| Code | Response body | Reason |
|---|---|---|
| `400 Bad Request` | `{"parties": ["Ensure this field has at least 2 elements."]}` | Fewer than two participants were passed, or another field constraint was violated. |
| `401 Unauthorized` | `{"detail": "Authentication credentials were not provided."}` | No authentication token, or it's invalid. |
| `502 Bad Gateway` | `{"detail": "AMI unavailable."}` | The PBX couldn't establish a connection to the Asterisk Manager Interface (no leg was queued at all). |
| `503 Service Unavailable` | `{"detail": "Asterisk is disabled in this DEVMODE."}` | The PBX is running in development mode without a real Asterisk connection. |

### 7.5. Other endpoints

The API also provides endpoints for working with number lists. They aren't required for a basic integration (receiving call events and initiating outbound calls), but can be useful if the CRM system takes over management of blocklists/allowlists or the contacts directory.

| Endpoint | Methods | Purpose |
|---|---|---|
| `/api/v1/blacklist/`, `/api/v1/blacklist/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Manage the list of blocked numbers (`callerid` + `destination`). A repeated `POST` with the same `callerid`/`destination` updates the existing record (`200`); a new record is created with status `201`. |
| `/api/v1/whitelist/`, `/api/v1/whitelist/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Same as `blacklist/`, but for allowed numbers. |
| `/api/v1/contacts/`, `/api/v1/contacts/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | A directory mapping `callerid` → contact name. |
| `/api/v1/lists/`, `/api/v1/lists/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Manage arbitrary named lists. |
| `/api/v1/lists/{id}/entries/` | `GET`, `POST` | View and add entries within a particular list. |
| `/api/v1/lists/{id}/entries/{entry_id}/` | `DELETE` | Remove a single entry from a list. |
| `/api/v1/recordings/{uniqueid}/` | `GET` | Fetch a call's audio recording (described in detail in section 6). |

All the list endpoints above support standard pagination (50 records per page by default) and return standard DRF validation errors.

### 7.6. Error format

Request validation errors are returned in the standard Django REST Framework format — an object where the key is the field name and the value is a list of text messages:

```json
{
  "callerid": ["This field is required."]
}
```

Errors not tied to a specific field (e.g. authentication failure or a missing resource) are returned in the `detail` field:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Attempting to create a resource that violates a database-level uniqueness constraint returns `409 Conflict`:

```json
{
  "detail": "Resource already exists or violates a uniqueness constraint."
}
```

It's recommended that the CRM system's response handler primarily key off the HTTP status code, and use the content of the `detail` field / field names for diagnostics and logging.

## 8. Dashboard API and WebSocket: a real-time channel (optional)

Besides webhooks and the REST API (sections 1–7), for some PearlPBX2 installations the administrator can additionally grant access to the internal operator dashboard's API. This is an **optional, alternative** channel — the vast majority of integrations only need the webhooks and REST API described above. This section is for cases where the CRM system needs a current snapshot of the PBX's state (queues, channels, active calls), or a continuous stream of events, rather than just notifications about key moments in a call.

**A fundamental difference from the rest of this document:** this channel's data format is PearlPBX2's internal operator dashboard format, not a stabilized integration contract. The set of fields and event types can change between versions without a separate coordination cycle. If you have a choice, webhooks (section 5) are the priority, recommended data source for a CRM.

### 8.1. Authentication

Both mechanisms below accept the same access token issued by the PBX administrator, following Django REST Framework's token authentication scheme (the same scheme as in section 7.1; check with the administrator whether a shared token is used with the REST API, or a separate one is issued).

### 8.2. Dashboard API (`GET /dashboard/api/...`)

Read-only endpoints, each accepting a token in the `Authorization: Token YOUR_TOKEN` header (a Django session also works, but for CRM integration the token is what's relevant):

| Endpoint | Purpose |
|---|---|
| `GET /dashboard/api/queues/` | The state of all service queues (members, calls, statistics). |
| `GET /dashboard/api/queues/{queue_name}/` | The state of a specific queue. |
| `GET /dashboard/api/channels/` | The state of all active Asterisk channels. |
| `GET /dashboard/api/channels/{channel_name}/` | The state of a specific channel. |
| `GET /dashboard/api/channels/type/{channel_type}/` | Channels filtered by type (`PJSIP`, `Local`, etc.). |
| `GET /dashboard/api/calls/active/` | Active (bridged) calls, with information about both legs. |
| `GET /dashboard/api/endpoints/` | A list of internal SIP users and external SIP trunks configured on the PBX. |
| `GET /dashboard/api/missed-calls/?queue={name}` | Calls missed today in a specific queue. |

Example request:

```bash
curl -H "Authorization: Token YOUR_TOKEN" \
  https://pbx.example.com/dashboard/api/queues/
```

A request without a token, or with an invalid one, returns `401 Unauthorized`.

**Important: two dashboard actions aren't opened up by a token.** `POST /dashboard/api/channels/hangup/` (forcibly ending a call) and `POST /dashboard/api/queues/pause/` (pausing/unpausing an operator) are control actions that directly call the Asterisk Manager Interface. They deliberately remain available only via a Django session with staff status (`is_staff`) and CSRF protection, and don't accept an integration token. A token issued for reading doesn't grant the ability to control live calls or queues.

### 8.3. WebSocket `/ws/asterisk/` — a real-time event stream

`wss://pbx.example.com/ws/asterisk/?token=YOUR_TOKEN` — the same event stream that powers the operator dashboard: every message arrives right after the corresponding Asterisk event, with no polling. The connection is read-only — the server doesn't accept any commands from the client over this socket.

The format of each message:

```json
{
  "type": "channel_new",
  "data": { "channel": "PJSIP/101-0000001a", "uniqueid": "1753000000.42", "..." : "..." },
  "timestamp": "2026-07-24T14:32:10.123456"
}
```

`type` takes values like `channel_new`, `channel_state_change`, `channel_dial_begin`, `channel_dial_end`, `channel_hangup`, `queue_caller_join`, `queue_caller_leave`, `queue_caller_abandon`, `queue_member_status`, `agent_connect`, and others — this is a much more detailed, lower-level stream than the four webhook events in section 5, and is intended more for live display of the PBX's state (e.g. a dispatcher board) than for business logic like creating a CRM task. For a typical integration (a call card, a callback for a missed call, attaching a recording), the webhooks in section 5 remain the correct and sufficient data source.

The browser `WebSocket` API doesn't allow adding custom headers, so the token is passed via the `?token=` query parameter; native (non-browser) clients can equally use the `Authorization: Token YOUR_TOKEN` header. Without a valid token and without an active Django session, the connection is closed immediately by the server.

## 9. Verifying request authenticity

To prevent forged requests impersonating a PearlPBX2 webhook from being accepted, a digital signature mechanism is provided.

Provided the PBX administrator has configured a secret key, every request carries this header:

```
X-PearlPBX-Signature: sha256=abc123...
```

The header value is an HMAC-SHA256 signature of the request body, computed using a secret key known to both sides (the PBX and the CRM server). Verifying the signature confirms that the request really was sent by PearlPBX2 and its content wasn't altered in transit.

Verification example in Python:

```python
import hashlib
import hmac

SECRET = "secret-key-from-the-pbx-settings"

def is_signature_valid(raw_body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(
        SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    # The comparison runs in constant time; a plain string comparison is not acceptable
    return hmac.compare_digest(expected, header_value)
```

The equivalent example in Node.js:

```javascript
const crypto = require("crypto");

const SECRET = "secret-key-from-the-pbx-settings";

function isSignatureValid(rawBody, headerValue) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", SECRET).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}
```

**An important caveat:** the signature is computed over the raw bytes of the request body, before any JSON parsing. If the web framework you're using automatically parses JSON before you get access to the raw body, you need to make sure you get access to the original bytes (in Flask, the `request.get_data()` method; in Express, the `express.raw()` middleware or an equivalent mechanism for preserving the raw buffer).

If no secret key is configured, the signature header will simply be absent — this is normal behavior, meaning signature verification isn't performed. It's nonetheless recommended to configure this mechanism for security reasons.

## 10. Configuring a custom JSON format

If the CRM system expects a request body with a different structure (different field names, or additional nesting), the PBX administrator can configure a custom request body template in the admin panel, where the standard fields are replaced with arbitrary ones, substituting values via `${variable_name}` syntax. Example:

```json
{
  "call_id": "${uniqueid}",
  "customer_phone": "${caller_id_num}",
  "type": "phone_call",
  "recording": "${recording_url}"
}
```

A list of all available substitution variables: `event`, `uniqueid`, `linkedid`, `channel`, `caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`, `duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`, `recording_expected`, `recording_url`, `recording_file`, `missed`, `wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`, `holdtime`, `answered_by_member`, `answered_by_interface`, `direction`, `dest_channel`, `dial_status`, `answered`, `channel_vars`.

`channel_vars` — an object with the Asterisk channel variables allowed by the PBX administrator (e.g. `{"ULINE": "42"}`); an empty object `{}` if none has been set yet. In the template, `${channel_vars}` as the entire content of a string field is substituted as a nested JSON object, not text.

Template configuration is done entirely on the PBX administrator's side and doesn't require any involvement from the CRM developer. If you need to change the default format, simply ask the administrator. When a new webhook is created, the template field in the admin panel already comes pre-filled with an example listing all available variables — editing it usually just means deleting the lines you don't need.

## 11. System behavior on delivery failures

The webhook delivery mechanism is built on a "best-effort" principle:

- There's no guaranteed long-term retry queue.
- If the CRM server doesn't respond in time, or is unreachable, several retry attempts are made at an interval defined by the PBX administrator's settings.
- If all retries fail, the event is considered lost and isn't sent again.

Practical implications for the CRM system's implementation:
- **Response speed.** The endpoint should return `200 OK` as quickly as possible, ideally within a second. If processing the event requires lengthy operations (e.g. calling a third-party system), it's recommended to acknowledge the request immediately and process it asynchronously (a task queue, a background handler, etc.).
- **Handling duplicates.** Receiving the same event twice is theoretically possible (e.g. due to a network failure at the moment the response was being sent). The recommended approach is to use the pair `uniqueid` + `event` as an idempotency key: if an event with that key has already been processed, the repeated request should be ignored.
- **No events.** No incoming requests for a period of time corresponds to no calls happening, and isn't a sign of a malfunction.

## 12. Example receiver server implementation

Below is an example implementation in Python (Flask) that accepts events from both chains (inbound and outbound), verifies the signature, and downloads the recording file if one is available. This example can be used as a starting point for your own implementation.

```python
import hashlib
import hmac
import os

import requests
from flask import Flask, request, abort

app = Flask(__name__)

# Secret key for verifying the webhook signature, agreed with the PBX administrator
WEBHOOK_SECRET = os.environ["PEARLPBX_WEBHOOK_SECRET"]
# Token for downloading call recordings via the API
API_TOKEN = os.environ["PEARLPBX_API_TOKEN"]


def is_signature_valid(raw_body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_value)


@app.post("/pearlpbx/webhook")
def handle_webhook():
    raw_body = request.get_data()  # raw bytes, before JSON parsing

    if not is_signature_valid(raw_body, request.headers.get("X-PearlPBX-Signature")):
        abort(401)

    payload = request.get_json()
    event = payload["event"]
    call_id = payload["uniqueid"]

    if event == "call.incoming":
        open_live_call_card(call_id, payload["caller_id_num"], payload.get("caller_id_name"))

    elif event == "call.answered":
        mark_call_answered(call_id, payload["member_name"])

    elif event == "call.missed":
        create_callback_task(call_id, payload["caller_id_num"], payload["wait_time"])

    elif event == "call.ended":
        close_call_card(call_id, duration=payload["duration"])
        if payload.get("recorded"):
            download_recording(call_id, payload["recording_url"])

    elif event == "call.outgoing":
        open_live_call_card(call_id, payload["exten"], payload.get("caller_id_name"))

    elif event == "call.outgoing_answered":
        mark_call_answered(call_id, payload["caller_id_name"])

    elif event == "call.outgoing_ended":
        close_call_card(call_id, duration=payload["duration"])
        if payload.get("recorded"):
            download_recording(call_id, payload["recording_url"])

    return "", 200


def download_recording(call_id: str, recording_url: str) -> None:
    response = requests.get(
        recording_url,
        headers={"Authorization": f"Token {API_TOKEN}"},
        timeout=10,
    )
    if response.status_code == 404:
        # The file hasn't been written to disk yet; a retry may work later
        return
    response.raise_for_status()

    # The actual file format (wav or mp3) is determined from Content-Type,
    # since recordings are converted from wav to mp3 on the PBX side on a schedule
    extension = "mp3" if response.headers.get("Content-Type") == "audio/mpeg" else "wav"
    with open(f"/data/recordings/{call_id}.{extension}", "wb") as f:
        f.write(response.content)


def open_live_call_card(call_id, phone, name):
    print(f"[incoming] {call_id}: call from {name or phone}")


def mark_call_answered(call_id, member_name):
    print(f"[answered] {call_id}: answered by {member_name}")


def create_callback_task(call_id, phone, wait_time):
    print(f"[missed] {call_id}: {phone}, waited {wait_time}s, needs a callback")


def close_call_card(call_id, duration):
    print(f"[ended] {call_id}: duration {duration}s")
```

An equivalent implementation in Node.js (Express):

```javascript
const express = require("express");
const crypto = require("crypto");

const app = express();
const WEBHOOK_SECRET = process.env.PEARLPBX_WEBHOOK_SECRET;
const API_TOKEN = process.env.PEARLPBX_API_TOKEN;

// Preserve the raw request body bytes for signature verification
app.use(express.json({ verify: (req, res, buf) => { req.rawBody = buf; } }));

function isSignatureValid(rawBody, headerValue) {
  if (!headerValue) return false;
  const expected =
    "sha256=" + crypto.createHmac("sha256", WEBHOOK_SECRET).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}

app.post("/pearlpbx/webhook", async (req, res) => {
  if (!isSignatureValid(req.rawBody, req.headers["x-pearlpbx-signature"])) {
    return res.sendStatus(401);
  }

  const payload = req.body;

  switch (payload.event) {
    case "call.incoming":
      console.log(`[incoming] ${payload.uniqueid}: call from ${payload.caller_id_num}`);
      break;
    case "call.answered":
      console.log(`[answered] ${payload.uniqueid}: answered by ${payload.member_name}`);
      break;
    case "call.missed":
      console.log(`[missed] ${payload.uniqueid}: waited ${payload.wait_time}s`);
      break;
    case "call.ended":
      console.log(`[ended] ${payload.uniqueid}: duration ${payload.duration}s`);
      if (payload.recorded) {
        await downloadRecording(payload.uniqueid, payload.recording_url);
      }
      break;
    case "call.outgoing":
      console.log(`[outgoing] ${payload.uniqueid}: calling ${payload.exten}`);
      break;
    case "call.outgoing_answered":
      console.log(`[outgoing_answered] ${payload.uniqueid}: answered`);
      break;
    case "call.outgoing_ended":
      console.log(`[outgoing_ended] ${payload.uniqueid}: answered=${payload.answered}`);
      if (payload.recorded) {
        await downloadRecording(payload.uniqueid, payload.recording_url);
      }
      break;
  }

  res.sendStatus(200);
});

async function downloadRecording(callId, recordingUrl) {
  const response = await fetch(recordingUrl, {
    headers: { Authorization: `Token ${API_TOKEN}` },
  });
  if (response.status === 404) return; // file not written yet, retry later
  if (!response.ok) throw new Error(`Recording fetch failed: ${response.status}`);

  // The actual file format is determined from Content-Type: recordings are
  // converted from wav to mp3 on a schedule on the PBX side, so the extension
  // isn't fixed in advance
  const extension = response.headers.get("Content-Type") === "audio/mpeg" ? "mp3" : "wav";
  const buffer = Buffer.from(await response.arrayBuffer());
  require("fs").writeFileSync(`/data/recordings/${callId}.${extension}`, buffer);
}

app.listen(3000, () => console.log("Webhook receiver listening on :3000"));
```

## 13. Frequently asked questions

**Is it possible to receive `call.ended` without a prior `call.incoming`?**
No. The system tracks this state internally: the end event is sent exclusively for calls whose start was already reported. The presence of `call.ended` guarantees that a `call.incoming` with the same `uniqueid` was previously sent.

**Are `call.missed` or `call.answered` possible without a prior `call.incoming`?**
Yes. Both events are independent: a missed call and an operator's answer are treated as significant enough to send regardless of any subscription to the call-start event.

**Why is there no `call.answered` event for direct calls without a queue?**
This event corresponds to Asterisk's AMI `AgentConnect` event, which is only generated for calls that went through a service queue. A direct call to a specific employee, without a queue involved, doesn't trigger this event — this is expected behavior.

**What does a `null` value in the `queue` field mean?**
The call was placed without a service queue being involved (e.g. a direct call to a specific employee). This isn't an error.

**Is `uniqueid` stable over time?**
Yes, within a single call `uniqueid` is a stable, unique identifier suitable for use as a primary key when correlating events.

**Is a `recording_expected: null` value in `call.incoming` an error?**
No. It means that at the time the call started, the system hadn't yet determined whether it would be recorded. The final value is in the `recorded` field of the `call.ended` event.

**Do I need separate logic for calls without a recording?**
It's enough to check the `recorded === true` condition before requesting the recording file. For `false` or `null`, requesting the link will return `404`.

**What behavior should I expect if the CRM server is temporarily unavailable while an event is being sent?**
The system will automatically make several delivery retries. If none of them succeed, the event isn't sent again. This should be factored into planning the reliability of your own endpoint (in particular, monitoring its availability).

**Does a successful response from `POST /api/v1/calls/originate/` (`200 OK`) mean the party answered the call?**
No. A successful response only confirms that the `Originate` command was queued for execution in the Asterisk Manager Interface. The actual progress of the call (answer, duration, end) is tracked exclusively through the corresponding webhook events (`call.answered`, `call.ended`), correlated by that call's `uniqueid`.

**Why did the call-initiation request return `502 Bad Gateway`?**
This means an error at the level of the PBX's interaction with the Asterisk Manager Interface — Asterisk itself, not the CRM system, is the source of the problem. The reason is detailed in the response's `detail` field (see section 7.2): no connection to AMI, a timeout being exceeded (`timeout_ms`), or Asterisk refusing to execute the command (e.g. a nonexistent extension or context).

**How does `call.outgoing` differ from `call.incoming`, if both mean "a call started"?**
By the direction of initiation. `call.incoming` — a call arriving at the company (from a customer via a trunk, or an internal call into a context/queue). `call.outgoing` — a call initiated by an employee dialing a number from their phone. These are two fully independent event chains with different names at every step (`call.ended` vs `call.outgoing_ended`), and no call ever generates events from both chains at once.

**Can an outbound-chain event (`call.outgoing*`) arrive for a call that's actually going through a trunk (a connection to a provider)?**
No, never, under any circumstances. The system determines a call's initiator by the specific employee's channel's technical identifier, not by direction or route name — even if the administrator configured a trunk and internal users on the exact same route, trunk calls will never be confused with employee calls.

**Will `call.outgoing_ended` arrive without a prior `call.outgoing_answered` if the line was busy?**
Yes, and this is expected behavior. `call.outgoing_answered` only arrives if the called party picked up. If the line was busy, nobody answered, or the call was cancelled, `call.outgoing_ended` arrives directly, with `answered: false` and a reason code in `dial_status`.

## 14. Integration checklist

- [ ] An HTTP endpoint is implemented that accepts `POST` requests with a JSON body and promptly returns `200 OK`.
- [ ] The endpoint's URL has been given to the PBX administrator, and a secret key for signing requests has been agreed on.
- [ ] An API token has been obtained from the PBX administrator for downloading call recordings and (if needed) for calling the REST API.
- [ ] Handling is implemented for the four inbound-chain events: `call.incoming`, `call.answered`, `call.missed`, `call.ended`.
- [ ] If handling employees' outbound calls is needed — handling is implemented for the three outbound-chain events: `call.outgoing`, `call.outgoing_answered`, `call.outgoing_ended`.
- [ ] If initiating calls from the CRM side is needed — calling `POST /api/v1/calls/originate/` has been implemented and tested, handling `400`, `401`, `502`, `503` codes.
- [ ] If bringing three or more participants into a single conversation is needed — calling `POST /api/v1/calls/conference/` has been implemented, handling partial failures in the `results` array.
- [ ] Verification of the `X-PearlPBX-Signature` signature is implemented, based on the raw bytes of the request body, before JSON parsing.
- [ ] Downloading a call recording via `GET /api/v1/recordings/{uniqueid}/` is implemented using the token, provided `recorded: true`.
- [ ] A `404` response when trying to fetch a recording is handled (the file may appear on disk with a delay).
- [ ] The possibility of `null` values for individual fields is accounted for.
- [ ] Idempotent event handling is implemented in case of repeated delivery (keyed by `uniqueid`).
- [ ] (Optional, only if the administrator has granted access) Use of the Dashboard API / WebSocket (section 8) has been agreed with the PBX administrator, with the understanding that this format is internal and not versioned.

Completing the items above is sufficient for a full implementation of the integration.
