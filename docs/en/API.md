*Also available in: [English](API.md) | [Українська](../ua/API.md) | [Español](../es/API.md)*

# PearlPBX2 REST API

All endpoints are available under the `/api/v1/` prefix.

## Access Control

Authentication uses DRF token-based authentication. Send the header `Authorization: Token <key>` with every request.

Requests without a valid token receive `HTTP 401 Unauthorized`.

Create a token:
```bash
python manage.py drf_create_token <username>
```

Or via Django admin / shell (`rest_framework.authtoken.models.Token`).

There is no session-based or IP-based restriction. CSRF protection is not enforced (token auth only).

## Common Response Format

**Success**: JSON object or array with resource fields. GET list endpoints return paginated responses:

```json
{
  "count": 42,
  "next": "http://host/api/v1/blacklist/?page=2",
  "previous": null,
  "results": [...]
}
```

**Validation errors** use DRF's standard format:
```json
{"field_name": ["message"]}
```

**HTTP status codes**:
- `200` — OK (read or update)
- `201` — Created (new resource)
- `204` — No Content (successful delete, empty body)
- `400` — Bad Request (missing or invalid fields)
- `401` — Unauthorized (missing or invalid token)
- `404` — Not Found
- `409` — Conflict (a uniqueness constraint would be violated, e.g. renaming an entry so it collides with an existing one)

---

## Blacklist

Manages a list of caller IDs to block in Asterisk dialplan.

POST uses upsert logic: if a record with the same `callerid` + `destination` already exists, it is updated; otherwise a new record is created.

### GET `/api/v1/blacklist/`

Returns paginated blacklist entries.

**Response:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "destination": "101",
      "reason": "Spam",
      "expiration_date": "2026-12-31T23:59:59"
    }
  ]
}
```

### POST `/api/v1/blacklist/`

Add or update a blacklist entry.

**Request body:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "Spam",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — required
- `destination`, `reason`, `expiration_date` — optional

Uniqueness is enforced on the `callerid` + `destination` pair (a common value is `destination = ""` for system-wide blocking).

**Response:** `201` on create, `200` on update. Updating a record's `callerid`/`destination` (via `PUT`/`PATCH` on `/api/v1/blacklist/<uuid>/`) so that it collides with another existing pair returns `409 Conflict`.

### DELETE `/api/v1/blacklist/<uuid>/`

Delete a blacklist entry by ID.

**Response:** `204 No Content` (empty body).

---

## Whitelist

Manages a list of caller IDs to allow or route in Asterisk dialplan. Identical interface to Blacklist.

### GET `/api/v1/whitelist/`
### POST `/api/v1/whitelist/`
### DELETE `/api/v1/whitelist/<uuid>/`

Same request/response format as Blacklist.

---

## Contacts

A directory of caller IDs with display names. Used for caller ID name resolution.

POST uses upsert logic keyed on `callerid`.

### GET `/api/v1/contacts/`

Returns paginated contacts.

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "name": "Ivan Petrenko"
    }
  ]
}
```

### POST `/api/v1/contacts/`

Add or update a contact.

**Request body:**
```json
{
  "callerid": "+380501234567",
  "name": "Ivan Petrenko"
}
```

Both fields are required.

**Response:** `201` on create, `200` on update.

### DELETE `/api/v1/contacts/<uuid>/`

Delete a contact by ID. Returns `204 No Content`.

---

## Custom Lists

Named lists with entries. Useful for dynamic dialplan lookups (e.g. VIP callers, routing groups).

Each list has a name and contains entries with `callerid`, optional `destination`, `reason`, and `expiration_date`.

### GET `/api/v1/lists/`

Returns all custom lists.

**Response:**
```json
{
  "count": 1,
  "results": [
    {"id": "uuid", "name": "VIP"}
  ]
}
```

### POST `/api/v1/lists/`

Create a new list.

**Request body:**
```json
{"name": "VIP"}
```

**Response:** `HTTP 201` with the created list object.

### PATCH `/api/v1/lists/<uuid>/`

Rename a list.

**Request body:**
```json
{"name": "New Name"}
```

`name` must be a non-empty string. An empty or missing `name` returns `400` with body `{"error": "Missing \"name\""}`.

### DELETE `/api/v1/lists/<uuid>/`

Delete a list and all its entries. Returns `204 No Content`.

---

### GET `/api/v1/lists/<uuid>/entries/`

Returns paginated entries of a specific list.

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "destination": "101",
      "reason": "VIP caller",
      "expiration_date": null
    }
  ]
}
```

### POST `/api/v1/lists/<uuid>/entries/`

Add an entry to a list.

**Request body:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "VIP caller",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — required
- `destination`, `reason`, `expiration_date` — optional

**Response:** `HTTP 201` with the created entry object.

### DELETE `/api/v1/lists/<uuid>/entries/<entry_uuid>/`

Delete a specific entry from a list. Returns `204 No Content`.

---

## Originate a call

**`POST /api/v1/calls/originate/`**

Originate a call via Asterisk AMI. Replaces direct HTTP calls to Asterisk `rawman` — the AMI secret is never sent by the client.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `channel` | string | yes | — | First leg to dial, e.g. `"Local/0441231231@Outgoing"` or `"PJSIP/2101"` |
| `exten` | string | yes | — | External number the first leg connects to, e.g. `"0123123123"` |
| `context` | string | yes | `"Outgoing"` | Routing table that has access to external calls |
| `priority` | integer | yes | `1` | Dialplan priority (leave: 1) |
| `callerid` | string | yes | — | Caller ID in format `name<number>`, e.g. `"PearlPBX2 Auto Call<number_you_are_calling>"` |
| `variable` | object | no | — | Channel variables as key-value pairs, e.g. `{"userId": "0"}` |
| `timeout_ms` | integer | yes | `30000` | Asterisk-side Originate timeout in ms (1000–120000). This is also the server-side wait budget: the API worker will not block waiting for the AMI response longer than `timeout_ms + 5s`. |

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Call originated successfully. Body: `{"status": "originated", "message": "..."}` |
| `400` | Invalid request body (missing required fields, validation errors) |
| `401` | Authentication credentials were not provided |
| `502` | AMI error or Asterisk unreachable |
| `503` | Asterisk is disabled in this DEVMODE |

**Example:**

```bash
curl -k -X 'POST' \
  'https://<your-server>/api/v1/calls/originate/' \
  -H 'accept: */*' \
  -H 'Authorization: Token <your-token>' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRFTOKEN: <your-csrf-token>' \
  -d '{
  "callerid": "0504139380",
  "timeout_ms": 30000,
  "channel": "PJSIP/2101",
  "exten": "0504139380",
  "context": "Outgoing",
  "priority": 1
}'
```

> **Notes:**
> - `timeout_ms` is in **milliseconds** and only bounds the creation of the **first leg** — the `channel` above (`PJSIP/2101`, an internal SIP extension). It has nothing to do with how long the second leg (`exten`) is allowed to ring.
> - If the response is `Originate failed`, Asterisk was unable to establish that first channel at all. Common causes: the extension (`PJSIP/2101`) doesn't exist/isn't registered, the operator's phone didn't answer, or the operator rejected/hung up the call before it connected.

**Mapping from old rawman parameters:**

| rawman param | API field |
|---|---|
| `channel` | `channel` |
| `exten` | `exten` |
| `context` | `context` |
| `priority` | `priority` |
| `Variable` | `variable` (dict) |
| `callerId` | `callerid` |

---

## Queue Members

Pause/unpause a queue member and read live queue member status via Asterisk AMI.
There is no persistent "queue member" resource here — these endpoints talk to
Asterisk directly, so they reflect (and change) live runtime state, not the
`QueueMember` records managed in Django admin.

### POST `/api/v1/queues/members/pause/`

Pause or unpause a queue member.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `interface` | string | yes | — | Queue member interface, e.g. `"PJSIP/101"` |
| `paused` | boolean | yes | — | `true` to pause, `false` to unpause |
| `queue` | string | no | — | Limit the change to one queue. Omitted, it applies to the member in every queue it belongs to |

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | Pause state updated. Body: `{"status": "paused"}` or `{"status": "unpaused"}` |
| `400` | Invalid request body |
| `401` | Authentication credentials were not provided |
| `404` | The interface is not a member of the given queue(s) |
| `502` | AMI error or Asterisk unreachable |
| `503` | Asterisk is disabled in this DEVMODE |

**Example:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/queues/members/pause/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"interface": "PJSIP/101", "paused": true}'
```

### GET `/api/v1/queues/members/`

List queue members and their current status. Optional `?queue=<name>` query
parameter limits results to one queue; omit it to list members of every queue.

**Response:**

```json
{
  "members": [
    {
      "queue": "support",
      "name": "PJSIP/101",
      "location": "PJSIP/101",
      "state_interface": "PJSIP/101",
      "membership": "static",
      "penalty": 0,
      "calls_taken": 3,
      "last_call": 0,
      "in_call": false,
      "status": "1",
      "paused": true
    }
  ]
}
```

`status` is the raw Asterisk device-state code (`AST_DEVICE_*`), passed through
without translation.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | List of members (possibly empty) |
| `401` | Authentication credentials were not provided |
| `502` | AMI error or Asterisk unreachable |
| `503` | Asterisk is disabled in this DEVMODE |

---

## Call Recordings

**`GET /api/v1/recordings/<uniqueid>/`**

Fetch a recorded call's audio by Asterisk uniqueid. This is the endpoint referenced
by `recording_url` in CRM webhook payloads — see the
[CRM integration guide](crm-integration.md) for the full webhook
reference. Supports HTTP `Range` requests for streaming/seeking, and a
`?download=1` query parameter to force a `Content-Disposition: attachment` response.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` / `206` | The audio file (`audio/wav` or `audio/mpeg`), full or partial (Range) |
| `401` | Authentication credentials were not provided |
| `404` | No recording exists for this uniqueid (not recorded, or not yet written to disk) |

**Example:**

```bash
curl -H "Authorization: Token <your-token>" \
  http://127.0.0.1:8000/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

Access is not scoped further — any valid API token can fetch any recording, the
same as the rest of this API.

---

## Known Limitations

- No filtering or search on GET endpoints.

---

## API Documentation

Interactive, auto-generated OpenAPI 3.0 documentation is available (powered by
drf-spectacular). All three endpoints require authentication (a valid token or an
authenticated session), the same as the rest of the API.

- **Raw schema (OpenAPI 3.0, YAML):** `GET /api/v1/schema/`
- **Swagger UI:** `GET /api/v1/docs/`
- **ReDoc UI:** `GET /api/v1/redoc/`

> **Note:** These three endpoints require authentication (`Authorization: Token <key>`),
> just like the rest of the API. Opening them directly in a browser without a token
> returns `401`. This is intentional — the documentation is not publicly exposed.

The schema is generated directly from the DRF ViewSets and serializers, so it always
matches the running code.
