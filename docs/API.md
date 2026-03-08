# PearlPBX2 REST API

All endpoints are available under the `/api/v1/` prefix.

## Access Control

Authentication is IP-based. Only hosts listed in `PEARLPBX_API_ALLOWED_HOSTS` (settings) can access the API. Default: `127.0.0.1` and `::1` (localhost only).

Requests from unlisted IPs receive `HTTP 403 Forbidden`.

There is no token or session-based authentication. CSRF protection is disabled for all API endpoints.

## Common Response Format

**Success**: JSON object or array with resource fields.

**Error**:
```json
{"error": "Description of the error"}
```

**HTTP status codes**:
- `200` — OK (read or update)
- `201` — Created (new resource)
- `400` — Bad Request (missing or invalid fields)
- `403` — Forbidden (IP not allowed)
- `404` — Not Found
- `500` — Internal Server Error

---

## Blacklist

Manages a list of caller IDs to block in Asterisk dialplan.

POST uses upsert logic: if a record with the same `callerid` + `destination` already exists, it is updated; otherwise a new record is created. The response includes `"created": true/false`.

### GET `/api/v1/blacklist/`

Returns all blacklist entries.

**Response:**
```json
[
  {
    "id": "uuid",
    "callerid": "+380501234567",
    "destination": "101",
    "reason": "Spam",
    "expiration_date": "2026-12-31T23:59:59"
  }
]
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

**Response:** the entry object with `"created": true` or `"created": false`.

### DELETE `/api/v1/blacklist/<uuid>/`

Delete a blacklist entry by ID.

**Response:**
```json
{"status": "deleted", "id": "uuid"}
```

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

Returns all contacts.

**Response:**
```json
[
  {
    "id": "uuid",
    "callerid": "+380501234567",
    "name": "Ivan Petrenko"
  }
]
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

**Response:** the contact object with `"created": true` or `"created": false`.

### DELETE `/api/v1/contacts/<uuid>/`

Delete a contact by ID.

---

## Custom Lists

Named lists with entries. Useful for dynamic dialplan lookups (e.g. VIP callers, routing groups).

Each list has a name and contains entries with `callerid`, optional `destination`, `reason`, and `expiration_date`.

### GET `/api/v1/lists/`

Returns all custom lists.

**Response:**
```json
[
  {"id": "uuid", "name": "VIP"}
]
```

### POST `/api/v1/lists/add/`

Create a new list.

**Request body:**
```json
{"name": "VIP"}
```

**Response:** `HTTP 201` with the created list object.

### POST `/api/v1/lists/update/<uuid>/`

Rename a list.

**Request body:**
```json
{"name": "New Name"}
```

### DELETE `/api/v1/lists/revoke/<uuid>/`

Delete a list and all its entries.

---

### GET `/api/v1/lists/<uuid>/`

Returns all entries of a specific list.

**Response:**
```json
[
  {
    "id": "uuid",
    "callerid": "+380501234567",
    "destination": "101",
    "reason": "VIP caller",
    "expiration_date": null
  }
]
```

### POST `/api/v1/lists/<uuid>/add/`

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

### DELETE `/api/v1/lists/<uuid>/revoke/<entry_uuid>/`

Delete a specific entry from a list.

---

## Known Limitations

- No pagination — GET endpoints return all records at once.
- No token-based authentication — IP allowlist only.
- No filtering or search on GET endpoints.
- Error messages from internal exceptions are returned as-is in `"error"` field (may leak implementation details).

---

## Planned Improvements

### OpenAPI / Swagger Documentation

Add interactive API documentation using [drf-spectacular](https://github.com/tfranzel/drf-spectacular) or [drf-yasg](https://github.com/axnsan12/drf-yasg).

**Scope:**
- Auto-generate OpenAPI 3.0 schema from existing views
- Expose Swagger UI at `/api/v1/docs/`
- Expose ReDoc UI at `/api/v1/redoc/`
- Expose raw schema at `/api/v1/schema/`
- Annotate all endpoints with request/response examples, field descriptions, and status codes

**Notes:**
- Current views are class-based Django views (not DRF ViewSets), so manual `@extend_schema` annotations will be needed
- Authentication scheme (IP allowlist) should be documented as a custom security scheme
- Consider migrating views to DRF APIView or ViewSet to reduce annotation effort and enable DRF's built-in schema generation
