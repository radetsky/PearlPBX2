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

**Exception:** every method on `/api/v1/sip-users/`, `/api/v1/sip-transports/`,
`/api/v1/sip-peers/`, `/api/v1/routing-tables/`, `/api/v1/routing-records/`,
`/api/v1/dialplan-contexts/`, `/api/v1/dialplan-extensions/`,
`/api/v1/dialplan-macros/`, `/api/v1/trunk-groups/`, `/api/v1/phone-devices/`,
`/api/v1/queues/` and `/api/v1/queue-members/`, including `GET`, requires a
staff or superuser account — see [SIP Users](#sip-users),
[SIP Transports](#sip-transports), [SIP Peers](#sip-peers),
[Routing Tables](#routing-tables), [Routing Records](#routing-records),
[Dialplan Contexts](#dialplan-contexts),
[Dialplan Extensions](#dialplan-extensions),
[Dialplan Macros](#dialplan-macros), [Trunk Groups](#trunk-groups),
[Phone Devices](#phone-devices), [Queues](#queues) and
[Queue Members (Static Configuration)](#queue-members-static-configuration)
below. A regular user's valid token receives `403 Forbidden` on those
resources.

**Superuser only:** `/api/v1/config/preview/` and `/api/v1/config/apply/`
require a **superuser** account — a staff-only token is not enough, since
`apply` can restart Asterisk and drop every active call. See
[Config (Apply Changes)](#config-apply-changes).

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

## SIP Users

Manages SIP extensions (accounts). Unlike the rest of this API, **every method
on this resource — including `GET` — requires a staff or superuser account**;
a valid token belonging to a regular user receives `403 Forbidden`. This
resource exposes dial-out credentials, so a plain authenticated token is not
enough.

Saving here only updates the database. Changes reach Asterisk after a
superuser runs "Apply Changes" in the admin — see the
[admin guide](admin-guide.md). A user saved with no `transport` or no
`routing_table` would silently be skipped when the configuration is
generated, which is why both fields are required here.

Deleting a SIP user cascades to any `PhoneDevice` provisioned for it.

### GET `/api/v1/sip-users/`

Returns paginated SIP users. Supports:
- `?username=<exact>` — filter by exact username
- `?extension=<exact>` — filter by exact extension
- `?search=<text>` — case-insensitive match against `name`, `username`, `extension`

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 12,
      "name": "John Doe",
      "username": "101",
      "secret": null,
      "transport": 1,
      "transport_name": "transport-udp",
      "nat": false,
      "extension": "101",
      "routing_table": 1,
      "routing_table_name": "PEARLPBX",
      "auth_type": "userpass",
      "custom_extension": "",
      "custom_settings": "",
      "custom_auth_settings": "",
      "custom_aor_settings": "",
      "pjsip_endpoint": "PJSIP/101",
      "is_webrtc": false,
      "realm": "udp-101",
      "md5_cred": null,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

`realm` and `md5_cred` are the RFC 2617 HA1 credential derived from
`username`/`transport`/`secret`. WebRTC (`wss`) endpoints are always
authenticated as MD5 in the generated config regardless of `auth_type`, so a
WebRTC client should use `md5_cred`/`realm` rather than the plaintext
`secret`. `md5_cred` is also `null` for a user with no `transport` set.
`is_webrtc` is `true` when the user's transport protocol is `wss`.

**`secret` and `md5_cred` are always `null` in this list response** —
credentials aren't included in a paginated bulk dump. Fetch
`GET /api/v1/sip-users/<id>/` (or use the object returned by `POST`/`PATCH`)
to read the real value.

### POST `/api/v1/sip-users/`

Create a SIP user.

**Request body:**
```json
{
  "name": "John Doe",
  "username": "101",
  "secret": "s3cret123",
  "extension": "101",
  "transport": 1,
  "routing_table": 1,
  "auth_type": "userpass"
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | at least 3 characters |
| `username` | yes | 3+ characters, letters/digits only, unique |
| `secret` | yes | plaintext SIP password |
| `transport` | yes | ID of an existing `SIPTransport` |
| `routing_table` | yes | ID of an existing `RoutingTable` |
| `extension` | yes | letters/digits only, unique |
| `nat` | no | default `false` |
| `auth_type` | no | `userpass` (default) or `md5` |
| `custom_extension`, `custom_settings`, `custom_auth_settings`, `custom_aor_settings` | no | raw `pjsip.conf`/dialplan snippets, written verbatim |

**Response:** `HTTP 201` with the created user object, or `400` if `username`/`extension`
is already taken or fails validation.

### PATCH `/api/v1/sip-users/<id>/`

Partially update a SIP user. Same field rules as `POST`.

### DELETE `/api/v1/sip-users/<id>/`

Delete a SIP user. Returns `204 No Content`. Cascades to any provisioned
`PhoneDevice`.

---

## SIP Transports

Manages PJSIP transports. Like [SIP Users](#sip-users), **every method on this
resource — including `GET` — requires a staff or superuser account**;
`cert_file` and `priv_key_file` carry TLS certificate/private key material in
plaintext.

Saving here only updates the database. Changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `cert_file`, `priv_key_file` and
`ca_list_file` hold PEM **contents**, not file paths — they are written to
disk under the Asterisk certificate directory only when "Apply Changes" runs,
and only for a transport with `protocol` `"tls"`.

Changing `protocol` on a transport already in use rewrites how every attached
`SIPUser` is generated, and invalidates their `md5_cred` (it is derived from
`protocol-username`). Deleting the last `wss` transport disables the WebRTC
config templates for every WebRTC user. Deleting a transport still referenced
by a `SIPUser` or `SIPPeer` returns `409 Conflict` instead of failing at the
database level.

### GET `/api/v1/sip-transports/`

Returns paginated transports. Supports:
- `?name=<exact>` — filter by exact name
- `?protocol=<udp|tcp|tls|wss>` — filter by protocol
- `?search=<text>` — case-insensitive match against `name`, `description`

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "transport-udp",
      "description": "UDP transport",
      "protocol": "udp",
      "bind": "0.0.0.0:5060",
      "local_nets": "10.0.0.0/16, 192.168.0.0/24",
      "external_media_address": null,
      "external_signaling_address": null,
      "method": "default",
      "verify_server": false,
      "allow_reload": true,
      "cert_file": "",
      "priv_key_file": null,
      "ca_list_file": "",
      "has_tls_material": false,
      "sip_users_count": 3,
      "sip_peers_count": 0,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

**`priv_key_file` is always `null` in this list response** — the private key
isn't included in a paginated bulk dump. Fetch
`GET /api/v1/sip-transports/<id>/` (or use the object returned by
`POST`/`PATCH`) to read the real value. `cert_file`/`ca_list_file` are public
certificate material and are not hidden.

`sip_users_count`/`sip_peers_count` are read-only counts of the `SIPUser`/
`SIPPeer` rows currently on this transport — the same rows that block a
`DELETE`. `has_tls_material` is `true` if any of the three cert fields is set.

### POST `/api/v1/sip-transports/`

Create a transport.

**Request body:**
```json
{
  "name": "transport-udp-nat",
  "protocol": "udp",
  "bind": "0.0.0.0:5060",
  "description": "UDP + NAT for remote users"
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | letters/digits/underscores/hyphens, unique, used as the `pjsip.conf` section name |
| `protocol` | no | `udp` (default), `tcp`, `tls`, `wss` |
| `bind` | no | `<ipv4>` or `<ipv4>:<port>`, default `0.0.0.0`; port must be 1024-65535 |
| `description` | no | single line, no `\n`/`\r` — written as a `pjsip.conf` comment |
| `local_nets` | no | comma-separated CIDR networks, e.g. `10.0.0.0/16, 192.168.0.0/24`; blank is stored as `null` |
| `external_media_address`, `external_signaling_address` | no | IP addresses |
| `method`, `verify_server`, `allow_reload`, `cert_file`, `priv_key_file`, `ca_list_file` | no | only take effect when `protocol` is `tls` |

**Response:** `HTTP 201` with the created transport object, or `400` if `name`
is already taken or fails validation.

### PATCH `/api/v1/sip-transports/<id>/`

Partially update a transport. Same field rules as `POST`.

### DELETE `/api/v1/sip-transports/<id>/`

Delete a transport. Returns `204 No Content`, or `409 Conflict` naming the
`SIPUser`/`SIPPeer` rows still on this transport.

---

## SIP Peers

Manages SIP trunks/uplinks. Like [SIP Users](#sip-users), **every method on
this resource — including `GET` — requires a staff or superuser account**;
this resource exposes dial-out credentials (plaintext `secret` and the
derived `md5_cred`).

Saving here only updates the database. Changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. A peer saved with no `transport`
or no `routing_table` would generate a half-complete `pjsip.conf` entry (an
`[auth]` section with no `[endpoint]`/`[aor]`), which is why both fields are
required here. If `registration_there` is set, `registration_uri` and
`username` are also required.

Deleting a peer that still belongs to a `TrunkGroup` returns `409 Conflict`
rather than silently shrinking the group.

### GET `/api/v1/sip-peers/`

Returns paginated peers. Supports:
- `?name=<exact>` — filter by exact name
- `?routing_table=<id>` — filter by routing table
- `?search=<text>` — case-insensitive match against `name`, `description`, `username`

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 5,
      "name": "myprovider",
      "description": "SIP trunk provider",
      "username": "trunkuser",
      "contact_user": "",
      "auth_type": "userpass",
      "secret": null,
      "transport": 1,
      "transport_name": "transport-udp",
      "routing_table": 1,
      "routing_table_name": "PEARLPBX",
      "registration_uri": "reg.provider.com:5060",
      "contact_uri": "",
      "match_hosts": "",
      "registration_here": false,
      "registration_there": true,
      "nat": false,
      "custom_auth_settings": "",
      "custom_aor_settings": "",
      "custom_identify_settings": "",
      "auth_realm": "reg.provider.com",
      "md5_cred": null,
      "trunk_groups": ["main-trunks"],
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

`registration_here`/`registration_there` map to the model's
`registrationHere`/`registrationThere` fields. `auth_realm` and `md5_cred` are
the RFC 2617 HA1 credential derived from `username`/`auth_realm`/`secret` —
`auth_realm` is the host part of `registration_uri`, or `"asterisk"` if none
is set. `trunk_groups` lists the names of any `TrunkGroup` this peer belongs
to; deleting a peer in at least one group is refused (see above).

**`secret` and `md5_cred` are always `null` in this list response** —
credentials aren't included in a paginated bulk dump. Fetch
`GET /api/v1/sip-peers/<id>/` (or use the object returned by `POST`/`PATCH`)
to read the real value.

### POST `/api/v1/sip-peers/`

Create a peer.

**Request body:**
```json
{
  "name": "myprovider",
  "description": "SIP trunk provider",
  "username": "trunkuser",
  "secret": "s3cret123",
  "auth_type": "userpass",
  "transport": 1,
  "routing_table": 1,
  "registration_there": true,
  "registration_uri": "reg.provider.com:5060"
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | 3+ characters, letters/digits only, unique, used as the `pjsip.conf` section name |
| `description` | yes | single line, no `\n`/`\r` |
| `transport` | yes | ID of an existing `SIPTransport` |
| `routing_table` | yes | ID of an existing `RoutingTable` |
| `username`, `contact_user` | no | letters/digits/hyphens/dots/underscores |
| `auth_type` | no | `userpass` (default) or `md5` |
| `secret` | no | plaintext SIP password |
| `registration_uri`, `contact_uri` | no | `host[:port]`; required when `registration_there` is `true` |
| `match_hosts` | no | comma-separated hosts/IPs, no ports |
| `registration_here` | no | default `false` — peer registers to us (GSM/E1/T1/FXS/FXO gateways) |
| `registration_there` | no | default `false` — we register to the peer (providers); requires `registration_uri` and `username` |
| `nat` | no | default `false` |
| `custom_auth_settings`, `custom_aor_settings`, `custom_identify_settings` | no | raw `pjsip.conf` snippets, written verbatim |

**Response:** `HTTP 201` with the created peer object, or `400` if `name` is
already taken or fails validation.

### PATCH `/api/v1/sip-peers/<id>/`

Partially update a peer. Same field rules as `POST`.

### DELETE `/api/v1/sip-peers/<id>/`

Delete a peer. Returns `204 No Content`, or `409 Conflict` naming the
`TrunkGroup`(s) it still belongs to.

---

## Routing Tables

Manages routing tables. Every method — including `GET` — requires a staff or
superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `name` doubles as an AEL
dialplan context name (`core.conf.make_routing_tables()`), so it must not
collide with a `DialplanContext` name — a collision returns `400`, not the
`500` a direct model save would raise.

### GET `/api/v1/routing-tables/`

Returns paginated routing tables. Supports `?name=<exact>` and
`?search=<text>` (matches `name`).

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "PEARLPBX",
      "routing_records_count": 3,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```
`routing_records_count` is the number of `RoutingRecord` rows pointing at
this table.

### POST `/api/v1/routing-tables/`

**Request body:** `{"name": "Sales"}`

| Field | Required | Notes |
|---|---|---|
| `name` | yes | letters/digits/underscores/hyphens, unique, must not already exist as a `DialplanContext` name |

**Response:** `HTTP 201`, or `400` if `name` is taken or collides with a
`DialplanContext`.

### PATCH `/api/v1/routing-tables/<id>/`

Same field rules as `POST`.

### DELETE `/api/v1/routing-tables/<id>/`

Returns `204 No Content`, or `409 Conflict` if the table is still referenced
by a `SIPUser`, `SIPPeer`, `RoutingRecord`, a callback service, or a
`Webhook`'s routing-table filter.

---

## Routing Records

Manages prefix-based routing rules within a `RoutingTable`. Every method —
including `GET` — requires a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin.
`core.conf.make_routing_tables()` emits one `goto` line per record inside its
table's dialplan context, sorted by Asterisk pattern specificity. `context`
and `routing_table` are required even though nullable in the DB — a record
with no `context` would literally emit `goto None,${EXTEN},1;`, and a record
with no `routing_table` never appears in any table's generated block.

### GET `/api/v1/routing-records/`

Returns paginated routing records. Supports:
- `?name=<exact>` — filter by exact name
- `?prefix=<exact>` — filter by exact prefix
- `?routing_table=<id>` — filter by routing table
- `?context=<id>` — filter by dialplan context
- `?search=<text>` — case-insensitive match against `name`, `prefix`

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "Kyiv landline",
      "prefix": "044",
      "context": 1,
      "context_name": "internal",
      "routing_table": 1,
      "routing_table_name": "PEARLPBX",
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/routing-records/`

**Request body:**
```json
{"name": "Kyiv landline", "prefix": "044", "context": 1, "routing_table": 1}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | free text |
| `prefix` | yes | Asterisk dialplan pattern (e.g. `044`, `_0XX`, `_1XX.`) |
| `context` | yes | ID of an existing `DialplanContext` |
| `routing_table` | yes | ID of an existing `RoutingTable` |

**Response:** `HTTP 201`, or `400` if `prefix` fails pattern validation or a
required field is missing.

### PATCH `/api/v1/routing-records/<id>/`

Same field rules as `POST`.

### DELETE `/api/v1/routing-records/<id>/`

Delete a routing record. Returns `204 No Content` — nothing references a
`RoutingRecord`, so deletion is never blocked.

---

## Dialplan Contexts

Manages dialplan contexts (`core.conf.make_dialplan_contexts()`). Every
method — including `GET` — requires a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `name` shares a naming
namespace with `RoutingTable` — the two must not collide.

The auto-generated `"PEARLPBX-Users"` context is rendered live from
`SIPUser` data by `core.conf.make_local_users_context()` and cannot be
renamed or deleted through this endpoint — see
[Dialplan Extensions](#dialplan-extensions) for why extensions cannot be
created inside it either.

### GET `/api/v1/dialplan-contexts/`

Returns paginated contexts. Supports `?name=<exact>` and
`?search=<text>` (matches `name`, `description`).

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "internal",
      "description": "Internal extensions",
      "extensions_count": 3,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/dialplan-contexts/`

**Request body:**
```json
{"name": "internal", "description": "Internal extensions"}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique; must not collide with a `RoutingTable` name |
| `description` | no | free text, no line breaks |

**Response:** `HTTP 201`, or `400` if `name` is taken or collides with a
`RoutingTable`.

### PATCH `/api/v1/dialplan-contexts/<id>/`

Same field rules as `POST`. Renaming the auto-generated `"PEARLPBX-Users"`
context returns `400`.

### DELETE `/api/v1/dialplan-contexts/<id>/`

Returns `204 No Content`, or `409 Conflict` if the context is the
auto-generated `"PEARLPBX-Users"` context, is still used by a webhook's
context filter, or is still referenced by a `DialplanExtension` or
`RoutingRecord`.

---

## Dialplan Extensions

Manages dialplan extensions within a context
(`core.conf.make_dialplan_contexts()`). Every method — including `GET` —
requires a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `dialplan` must use valid
Asterisk AEL syntax and reference only macros that already exist —
`core.validators.validate_dialplan_field` resolves the allowed macro set
from the database at request time, so **create a macro before an extension
that calls it** with `&name();` (see
[Dialplan Macros](#dialplan-macros)). Extensions cannot be created inside
the auto-generated `"PEARLPBX-Users"` context — it is rendered live from
`SIPUser` data, so anything stored there would never reach
`extensions.ael`.

### GET `/api/v1/dialplan-extensions/`

Returns paginated extensions. Supports:
- `?context=<id>` — filter by dialplan context
- `?ext=<exact>` — filter by exact extension pattern
- `?search=<text>` — case-insensitive match against `ext`, `description`,
  `dialplan`, `context__name`

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "context": 1,
      "context_name": "internal",
      "ext": "_1XX",
      "dialplan": "Dial(PJSIP/${EXTEN},30);\nHangup();",
      "description": "Internal 1xx range",
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/dialplan-extensions/`

**Request body:**
```json
{"context": 1, "ext": "_1XX", "dialplan": "Dial(PJSIP/${EXTEN},30);\nHangup();"}
```

| Field | Required | Notes |
|---|---|---|
| `context` | yes | ID of an existing `DialplanContext`; must not be the auto-generated `"PEARLPBX-Users"` context |
| `ext` | yes | Asterisk extension pattern (e.g. `100`, `_1XX`, `_X.`) |
| `dialplan` | yes | Asterisk AEL syntax; macro calls (`&name();`) must reference an existing `DialplanMacro` |
| `description` | no | free text, no line breaks |

**Response:** `HTTP 201`, or `400` if `dialplan` fails AEL syntax
validation, references an unknown macro, `ext` fails pattern validation,
`context` is the reserved context, or `(context, ext)` is already taken.

### PATCH `/api/v1/dialplan-extensions/<id>/`

Same field rules as `POST`.

### DELETE `/api/v1/dialplan-extensions/<id>/`

Delete an extension. Returns `204 No Content` — nothing references a
`DialplanExtension`, so deletion is never blocked.

---

## Dialplan Macros

Manages dialplan macros (`core.conf.make_dialplan_macros()`), called from
extension bodies as `&name();`. Every method — including `GET` — requires
a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `name` is looked up as literal
AEL macro-call text in `DialplanExtension.dialplan` bodies, other macros,
and `Settings.local_users_dial_template` — **renaming or deleting a macro
still called that way is rejected** (`400`/`409`) instead of silently
breaking the generated dialplan. This is a best-effort text scan (matched
case-sensitively, unlike the [Queues](#queues) name guard): it cannot see a
name reached only through an Asterisk variable, and it cannot see the
Python-level `DEFAULT_LOCAL_USERS_DIAL_TEMPLATE` fallback used when no
`Settings` row exists or its field is blank.

### GET `/api/v1/dialplan-macros/`

Returns paginated macros. Supports `?name=<exact>` and `?search=<text>`
(matches `name`, `description`, `macro`).

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "stdexten",
      "description": "Standard extension",
      "macro": "Dial(PJSIP/${ARG1},30);\nVoicemail(${ARG1});",
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/dialplan-macros/`

**Request body:**
```json
{"name": "stdexten", "description": "Standard extension", "macro": "Dial(PJSIP/${ARG1},30);\nVoicemail(${ARG1});"}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique; letters, digits and underscores only, must not start with a digit |
| `description` | no | free text, no line breaks |
| `macro` | yes | Asterisk AEL syntax (not validated against `AsteriskDialplanValidator`) |

**Response:** `HTTP 201`, or `400` if `name` is taken or has an invalid
format.

### PATCH `/api/v1/dialplan-macros/<id>/`

Same field rules as `POST`. Renaming while still referenced returns `400`
naming the referencing extension(s)/macro(s)/`Settings` field.

### DELETE `/api/v1/dialplan-macros/<id>/`

Returns `204 No Content`, or `409 Conflict` naming the referencing
extension(s)/macro(s)/`Settings` field if the macro is still called.

---

## Trunk Groups

Manages trunk groups (failover sets of SIP peers). Every method — including
`GET` — requires a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `name` is looked up by the
FastAGI `dial-trunk-group` handler via a literal
`AGI(agi://.../dial-trunk-group,<name>,...)` call embedded in dialplan text —
**renaming or deleting a group still referenced that way is rejected**
(`400`/`409`) instead of silently breaking call routing. This is a
best-effort text scan: it cannot see a name reached only through an Asterisk
variable (e.g. `${GROUPNAME}`).

### GET `/api/v1/trunk-groups/`

Returns paginated trunk groups. Supports `?name=<exact>` and
`?search=<text>`.

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "main-trunks",
      "sip_peers": [5, 6],
      "sip_peer_names": ["provider-a", "provider-b"],
      "sip_peers_count": 2,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/trunk-groups/`

**Request body:**
```json
{"name": "main-trunks", "sip_peers": [5, 6]}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique |
| `sip_peers` | no | list of `SIPPeer` IDs; unlike `SIPPeer.trunk_groups` (read-only), this is the writable side of the relationship |

**Response:** `HTTP 201`, or `400` if `name` is taken.

### PATCH `/api/v1/trunk-groups/<id>/`

Same field rules as `POST`. Renaming while dialplan still references the
current name returns `400` naming the referencing extension(s)/macro(s).

### DELETE `/api/v1/trunk-groups/<id>/`

Returns `204 No Content`, or `409 Conflict` naming the referencing
extension(s)/macro(s) if dialplan still calls this group by name.

---

## Phone Devices

Manages provisioned phone devices (physical handsets, softphones, WebRTC
clients). Every method — including `GET` — requires a staff or superuser
account.

Saving here only updates the database. A device's TFTP config file is only
(re)written by the `provision` action below, or by the admin's "Apply
configurations" action — neither runs implicitly on save.

### GET `/api/v1/phone-devices/`

Returns paginated phone devices. Supports:
- `?mac_address=<exact>` — filter by exact MAC address
- `?sip_user=<id>` — filter by assigned SIP user
- `?telephone_type=<type>` — filter by device type (`spa502g`, `spa504g`, `gxp1200`, `softphone`, `webrtc`, `other`)
- `?search=<text>` — case-insensitive match against MAC address, SIP username, SIP name

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "telephone_type": "softphone",
      "mac_address": "00:1A:2B:3C:4D:5E",
      "sip_user": 3,
      "sip_user_username": "101",
      "sip_server": "pbx.example.com",
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/phone-devices/`

**Request body:**
```json
{"telephone_type": "softphone", "mac_address": "00:1a:2b:3c:4d:5e", "sip_user": 3, "sip_server": "pbx.example.com"}
```

| Field | Required | Notes |
|---|---|---|
| `telephone_type` | no | default `"other"` |
| `mac_address` | yes | unique; normalized to `XX:XX:XX:XX:XX:XX` (accepts separators, mixed case) |
| `sip_user` | no | ID of an existing `SIPUser`; a device with none assigned is a normal, not-yet-configured state |
| `sip_server` | no | default `""` — an empty value falls back to the global provisioning address at generation time |

**Response:** `HTTP 201`, or `400` if `mac_address` is invalid or already in use.

### PATCH `/api/v1/phone-devices/<id>/`

Same field rules as `POST`.

### DELETE `/api/v1/phone-devices/<id>/`

Delete a phone device. Returns `204 No Content` — nothing references a
`PhoneDevice`, so deletion is never blocked. Deleting the assigned `SIPUser`
instead cascades and deletes this device too (see [SIP Users](#sip-users)).

### POST `/api/v1/phone-devices/<id>/provision/`

Generate this device's TFTP config file — the same action as the admin's
"Apply configurations" button, for a single device, over the API. Only
`spa502g`, `spa504g` and `gxp1200` are supported; `softphone`/`webrtc`/`other`
devices have no config file to generate.

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | `{"success": true, "device_mac": "...", "filename": "...", "filepath": "...", "size": 512}` |
| `400` | `{"success": false, "device_mac": "...", "error": "..."}` — e.g. no SIP user assigned, or an unsupported `telephone_type` |

---

## Config (Apply Changes)

Wraps the admin's "Apply Changes" page. **Both endpoints require a
superuser account — a staff-only token is not enough**, since `apply` can
restart Asterisk and drop every active call.

### GET `/api/v1/config/preview/`

Dry-run: returns the same generated file contents as the admin's preview
page. No filesystem writes, no Asterisk reload.

**Response:**
```json
{
  "files": {
    "pjsip.conf": "...",
    "extensions.ael": "...",
    "queues.conf": "...",
    "queuerules.conf": "...",
    "manager.conf": "...",
    "musiconhold.conf": "...",
    "confbridge.conf": "..."
  },
  "skipped_sip_users": ["userA"]
}
```

### POST `/api/v1/config/apply/`

Writes the generated configs (versioned, with a backup tarball under
`ASTERISK_BACKUP_DIR` beforehand) and reloads Asterisk.

**Request body:** `{"mode": "soft"}` or `{"mode": "hard"}`

| Field | Required | Notes |
|---|---|---|
| `mode` | **yes** | `soft` — per-module/AEL reload, keeps active calls; `hard` — `core restart now`, drops every active call |

Unlike the admin form (where anything other than the literal string `"soft"`
silently means a hard restart), `mode` is a required, validated choice —
missing or invalid returns `400`.

**Response:**
```json
{
  "mode": "soft",
  "changed_files": ["pjsip.conf", "queues.conf"],
  "reloaded": true,
  "skipped_sip_users": []
}
```
`changed_files` lists only the files whose content actually changed (got a
new version) on this apply. `reloaded` is `false` when
`DEVMODE=without_asterisk_on_localhost` — files are still written, but no
AMI call is made (matching the admin's dev-mode behavior).

**`409 Conflict`** if another apply is already in progress (a short-lived
Redis lock); if Redis itself is unreachable, the apply proceeds without the
lock rather than becoming unavailable.

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

## Queues

Manages a call queue's static configuration (`app_queue`). Every method —
including `GET` — requires a staff or superuser account.

Saving here only updates the database; changes reach Asterisk after a
superuser runs "Apply Changes" in the admin. `name` is looked up by
Asterisk's `app_queue` from a literal `Queue(<name>,...)` AEL app-call
embedded in dialplan text — **renaming or deleting a queue still referenced
that way is rejected** (`400`/`409`) instead of silently breaking call
routing. Unlike the [Trunk Groups](#trunk-groups) guard, this match is
case-insensitive, since `app_queue` looks up queue names with `strcasecmp()`.
This is a best-effort text scan: it cannot see a name reached only through an
Asterisk variable (e.g. `${QUEUENAME}`).

Distinct from [Queue Members (Live AMI State)](#queue-members-live-ami-state)
below: this resource is about what gets written into `queues.conf`, not
runtime pause/status.

### GET `/api/v1/queues/`

Returns paginated queues. Supports `?name=<exact>`, `?strategy=<exact>` and
`?search=<text>`.

**Response (abbreviated — see POST below for the full field list):**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "Sales",
      "music_class": 1,
      "music_class_name": "default",
      "strategy": "ringall",
      "queue_announcement": 1,
      "queue_announcement_name": "default",
      "defaultrule": null,
      "defaultrule_name": null,
      "members_count": 2,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/queues/`

**Request body (minimal):**
```json
{"name": "Sales", "music_class": 1, "queue_announcement": 1, "strategy": "ringall"}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique |
| `music_class` | yes | ID of an existing `MusicOnHold` class |
| `queue_announcement` | yes | ID of an existing `QueueAnnouncements` row |
| `strategy` | yes | one of `ringall`, `leastrecent`, `fewestcalls`, `random`, `rrmemory`, `rrordered`, `linear`, `wrandom` — required even though nullable in the DB, since the generated config has no null guard for it |
| `defaultrule` | no | ID of an existing `QueueRule` |
| `context`, `timeout`, `retry`, `maxlen`, `weight`, `wrapuptime`, `autofill`, `autopause`, `autopausedelay`, `announce`, `queue_announce`, `service_level`, `joinempty`, `leavewhenempty`, `ringinuse`, `timeoutrestart`, `monitor_format`, `periodic_announce`, and the `announce_*`/`*_announce_frequency` fields | no | see the admin's Queue form for the full set; all map 1:1 onto `app_queue` options |

**Response:** `HTTP 201`, or `400` if `name` is taken, `strategy` is missing, or a queue with the same (old) name is still referenced by dialplan.

### PATCH `/api/v1/queues/<id>/`

Same field rules as `POST`. Renaming while dialplan still references the
current name returns `400` naming the referencing extension(s)/macro(s).

### DELETE `/api/v1/queues/<id>/`

Returns `204 No Content`, or `409 Conflict` naming the referencing
extension(s)/macro(s) if dialplan still calls this queue by name.

---

## Queue Members (Static Configuration)

Manages a queue's static member list (`core.conf` emits one `member => ...`
line per row into `queues.conf`). Every method — including `GET` — requires
a staff or superuser account, since this writes DB configuration rather than
reading live runtime state (contrast with the AMI-backed endpoints below,
which only require authentication).

Distinct from [Queue Members (Live AMI State)](#queue-members-live-ami-state)
below: `GET /api/v1/queue-members/?queue=<id>` answers "who is statically
configured in this queue" from the database; `GET /api/v1/queues/members/?queue=<name>`
(below) answers "who is currently paused/ringing/on a call" from Asterisk's
live AMI state. Both endpoints stay — they answer different questions.

### GET `/api/v1/queue-members/`

Returns paginated queue members. Supports:
- `?queue=<id>` — filter by queue
- `?interface=<exact>` — filter by exact interface
- `?search=<text>` — case-insensitive match against member name, interface, state interface, queue name

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "queue": 1,
      "queue_name": "Sales",
      "interface": "PJSIP/101",
      "penalty": 0,
      "member_name": "101",
      "state_interface": "PJSIP/101",
      "ringinuse": false,
      "wrapuptime": 0,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

### POST `/api/v1/queue-members/`

**Request body:**
```json
{"queue": 1, "interface": "PJSIP/101"}
```

| Field | Required | Notes |
|---|---|---|
| `queue` | yes | ID of an existing `Queue` |
| `interface` | yes | e.g. `"PJSIP/101"`; letters, digits and `_.-/@` only |
| `penalty` | no | default `0` |
| `member_name` | no | default `""` — a null value would otherwise render as the literal word `None` in `queues.conf` |
| `state_interface`, `ringinuse`, `wrapuptime` | no | see the admin's inline form |

A given `(queue, interface)` pair must be unique.

**Response:** `HTTP 201`, or `400` if `interface` is invalid, required fields are missing, or the `(queue, interface)` pair already exists.

### PATCH `/api/v1/queue-members/<id>/`

Same field rules as `POST`.

### DELETE `/api/v1/queue-members/<id>/`

Delete a queue member. Returns `204 No Content` — nothing references a
`QueueMember`, so deletion is never blocked.

---

## Queue Members (Live AMI State)

Pause/unpause a queue member and read live queue member status via Asterisk AMI.
There is no persistent "queue member" resource here — these endpoints talk to
Asterisk directly, so they reflect (and change) live runtime state, not the
`QueueMember` records managed in
[Queue Members (Static Configuration)](#queue-members-static-configuration)
above.

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

- No filtering or search on GET endpoints, except `/api/v1/sip-users/`
  (`?username=`, `?extension=`, `?search=`), `/api/v1/sip-transports/`
  (`?name=`, `?protocol=`, `?search=`), `/api/v1/sip-peers/`
  (`?name=`, `?routing_table=`, `?search=`), `/api/v1/routing-tables/`
  (`?name=`, `?search=`), `/api/v1/routing-records/` (`?name=`, `?prefix=`,
  `?routing_table=`, `?context=`, `?search=`), `/api/v1/dialplan-contexts/`
  (`?name=`, `?search=`), `/api/v1/dialplan-extensions/` (`?context=`,
  `?ext=`, `?search=`), `/api/v1/dialplan-macros/` (`?name=`, `?search=`),
  `/api/v1/trunk-groups/` (`?name=`, `?search=`), `/api/v1/phone-devices/`
  (`?mac_address=`, `?sip_user=`, `?telephone_type=`, `?search=`),
  `/api/v1/queues/` (`?name=`, `?strategy=`, `?search=`) and
  `/api/v1/queue-members/` (`?queue=`, `?interface=`, `?search=`).
- The trunk-group rename/delete guard is a best-effort text scan of dialplan
  bodies for a literal `dial-trunk-group,<name>,` call — it cannot see a
  group name reached only through an Asterisk variable. The queue rename/
  delete guard is the same kind of scan for a literal `Queue(<name>,...)`
  call, but case-insensitive (unlike the trunk-group one) since `app_queue`
  looks up queue names with `strcasecmp()`. The dialplan-macro rename/delete
  guard is the same kind of scan for a literal `&<name>();` call,
  case-sensitive (AEL resolves macro calls by exact name); it additionally
  scans `Settings.local_users_dial_template`, but cannot see the Python-level
  `DEFAULT_LOCAL_USERS_DIAL_TEMPLATE` fallback used when no `Settings` row
  exists or its field is blank.
- The auto-generated `"PEARLPBX-Users"` dialplan context cannot be renamed
  or deleted, and no `DialplanExtension` can be created inside it — it is
  rendered live from `SIPUser` data by
  `core.conf.make_local_users_context()`, so anything stored in the
  database row would never reach `extensions.ael`.

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
