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

**Response:** `201` on create, `200` on update.

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

## Known Limitations

- No filtering or search on GET endpoints.
- No Swagger/OpenAPI documentation yet.

---

## Planned Improvements

### OpenAPI / Swagger Documentation

Add interactive API documentation using [drf-spectacular](https://github.com/tfranzel/drf-spectacular) or [drf-yasg](https://github.com/axnsan12/drf-yasg).

**Scope:**
- Auto-generate OpenAPI 3.0 schema from existing ViewSets
- Expose Swagger UI at `/api/v1/docs/`
- Expose ReDoc UI at `/api/v1/redoc/`
- Expose raw schema at `/api/v1/schema/`
- Annotate all endpoints with request/response examples, field descriptions, and status codes
