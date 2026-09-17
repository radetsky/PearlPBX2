*Also available in: [English](../en/API.md) | [Українська](../ua/API.md) | [Español](API.md)*

# API REST de PearlPBX2

Todos los endpoints están disponibles bajo el prefijo `/api/v1/`.

## Control de acceso

La autenticación usa autenticación por token de DRF. Envía la cabecera `Authorization: Token <clave>` en cada solicitud.

Las solicitudes sin un token válido reciben `HTTP 401 Unauthorized`.

Crear un token:
```bash
python manage.py drf_create_token <username>
```

O a través del admin de Django / shell (`rest_framework.authtoken.models.Token`).

No hay restricción por sesión ni por IP. La protección CSRF no se aplica (solo autenticación por token).

**Excepción:** todos los métodos de `/api/v1/sip-users/`,
`/api/v1/sip-transports/`, `/api/v1/sip-peers/`, `/api/v1/routing-tables/`,
`/api/v1/routing-records/`, `/api/v1/dialplan-contexts/`,
`/api/v1/dialplan-extensions/`, `/api/v1/dialplan-macros/`,
`/api/v1/trunk-groups/`, `/api/v1/phone-devices/`, `/api/v1/queues/` y
`/api/v1/queue-members/`, incluido `GET`, requieren una cuenta de staff o
superusuario — ver [SIP Users](#sip-users),
[SIP Transports](#sip-transports), [SIP Peers](#sip-peers),
[Routing Tables](#routing-tables), [Routing Records](#routing-records),
[Dialplan Contexts](#dialplan-contexts),
[Dialplan Extensions](#dialplan-extensions),
[Dialplan Macros](#dialplan-macros), [Trunk Groups](#trunk-groups),
[Phone Devices](#phone-devices), [Queues](#queues) y
[Queue Members (configuración estática)](#queue-members-configuración-estática)
más abajo. El token válido de un usuario normal recibe `403 Forbidden` en
esos recursos.

**Solo superusuario:** `/api/v1/config/preview/` y `/api/v1/config/apply/`
requieren una cuenta de **superusuario** — un token de solo staff no es
suficiente, ya que `apply` puede reiniciar Asterisk y cortar todas las
llamadas activas. Ver [Config (Apply Changes)](#config-apply-changes).

## Formato de respuesta común

**Éxito**: objeto o array JSON con los campos del recurso. Los endpoints GET de listas devuelven respuestas paginadas:

```json
{
  "count": 42,
  "next": "http://host/api/v1/blacklist/?page=2",
  "previous": null,
  "results": [...]
}
```

**Errores de validación** usan el formato estándar de DRF:
```json
{"field_name": ["message"]}
```

**Códigos de estado HTTP**:
- `200` — OK (lectura o actualización)
- `201` — Created (nuevo recurso)
- `204` — No Content (eliminación exitosa, cuerpo vacío)
- `400` — Bad Request (campos faltantes o inválidos)
- `401` — Unauthorized (token ausente o inválido)
- `404` — Not Found
- `409` — Conflict (se violaría una restricción de unicidad, p. ej. renombrar una entrada de forma que colisione con una existente)

---

## Blacklist (lista negra)

Gestiona una lista de caller IDs a bloquear en el plan de marcado de Asterisk.

POST usa lógica de upsert: si ya existe un registro con el mismo `callerid` + `destination`, se actualiza; en caso contrario se crea uno nuevo.

### GET `/api/v1/blacklist/`

Devuelve las entradas paginadas de la lista negra.

**Respuesta:**
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

Añadir o actualizar una entrada de la lista negra.

**Cuerpo de la solicitud:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "Spam",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — obligatorio
- `destination`, `reason`, `expiration_date` — opcionales

La unicidad se aplica sobre el par `callerid` + `destination` (un valor habitual es `destination = ""` para bloqueo a nivel de todo el sistema).

**Respuesta:** `201` al crear, `200` al actualizar. Actualizar el `callerid`/`destination` de un registro (vía `PUT`/`PATCH` en `/api/v1/blacklist/<uuid>/`) de forma que colisione con otro par ya existente devuelve `409 Conflict`.

### DELETE `/api/v1/blacklist/<uuid>/`

Eliminar una entrada de la lista negra por ID.

**Respuesta:** `204 No Content` (cuerpo vacío).

---

## Whitelist (lista permitida)

Gestiona una lista de caller IDs para permitir o enrutar en el plan de marcado de Asterisk. Interfaz idéntica a Blacklist.

### GET `/api/v1/whitelist/`
### POST `/api/v1/whitelist/`
### DELETE `/api/v1/whitelist/<uuid>/`

Mismo formato de solicitud/respuesta que Blacklist.

---

## Contacts (contactos)

Un directorio de caller IDs con nombres para mostrar. Se usa para resolver el Caller ID Name.

POST usa lógica de upsert con clave `callerid`.

### GET `/api/v1/contacts/`

Devuelve los contactos paginados.

**Respuesta:**
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

Añadir o actualizar un contacto.

**Cuerpo de la solicitud:**
```json
{
  "callerid": "+380501234567",
  "name": "Ivan Petrenko"
}
```

Ambos campos son obligatorios.

**Respuesta:** `201` al crear, `200` al actualizar.

### DELETE `/api/v1/contacts/<uuid>/`

Eliminar un contacto por ID. Devuelve `204 No Content`.

---

## Custom Lists (listas con nombre)

Listas con nombre que contienen entradas. Útiles para búsquedas dinámicas en el plan de marcado (p. ej. llamantes VIP, grupos de enrutamiento).

Cada lista tiene un nombre y contiene entradas con `callerid`, y opcionalmente `destination`, `reason` y `expiration_date`.

### GET `/api/v1/lists/`

Devuelve todas las listas con nombre.

**Respuesta:**
```json
{
  "count": 1,
  "results": [
    {"id": "uuid", "name": "VIP"}
  ]
}
```

### POST `/api/v1/lists/`

Crear una lista nueva.

**Cuerpo de la solicitud:**
```json
{"name": "VIP"}
```

**Respuesta:** `HTTP 201` con el objeto de lista creado.

### PATCH `/api/v1/lists/<uuid>/`

Renombrar una lista.

**Cuerpo de la solicitud:**
```json
{"name": "New Name"}
```

`name` debe ser una cadena no vacía. Un `name` vacío o ausente devuelve `400` con cuerpo `{"error": "Missing \"name\""}`.

### DELETE `/api/v1/lists/<uuid>/`

Eliminar una lista y todas sus entradas. Devuelve `204 No Content`.

---

### GET `/api/v1/lists/<uuid>/entries/`

Devuelve las entradas paginadas de una lista concreta.

**Respuesta:**
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

Añadir una entrada a una lista.

**Cuerpo de la solicitud:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "VIP caller",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — obligatorio
- `destination`, `reason`, `expiration_date` — opcionales

**Respuesta:** `HTTP 201` con el objeto de entrada creado.

### DELETE `/api/v1/lists/<uuid>/entries/<entry_uuid>/`

Eliminar una entrada concreta de una lista. Devuelve `204 No Content`.

---

## SIP Users

Gestiona las extensiones (cuentas) SIP. A diferencia del resto de esta API,
**todos los métodos de este recurso — incluido `GET` — requieren una cuenta
de staff o superusuario**; un token válido de un usuario normal recibe
`403 Forbidden`. Este recurso expone credenciales de marcado saliente, por lo
que un token autenticado normal no es suficiente.

Guardar aquí solo actualiza la base de datos. Los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin — ver la
[guía del administrador](admin-guide.md). Un usuario guardado sin `transport`
o sin `routing_table` se omitiría silenciosamente al generar la
configuración, por eso ambos campos son obligatorios aquí.

Eliminar un usuario SIP elimina en cascada cualquier `PhoneDevice`
aprovisionado para él.

### GET `/api/v1/sip-users/`

Devuelve usuarios SIP paginados. Admite:
- `?username=<exacto>` — filtrar por username exacto
- `?extension=<exacto>` — filtrar por extension exacta
- `?search=<texto>` — coincidencia sin distinción de mayúsculas sobre `name`, `username`, `extension`

**Respuesta:**
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

`realm` y `md5_cred` son la credencial RFC 2617 HA1 derivada de
`username`/`transport`/`secret`. Los endpoints WebRTC (`wss`) siempre se
autentican como MD5 en la configuración generada, sin importar `auth_type`,
por lo que un cliente WebRTC debería usar `md5_cred`/`realm` en lugar del
`secret` en texto plano. `md5_cred` también es `null` para un usuario sin
`transport`. `is_webrtc` es `true` cuando el protocolo del transporte del
usuario es `wss`.

**`secret` y `md5_cred` siempre son `null` en esta respuesta de lista** — las
credenciales no se incluyen en un volcado paginado masivo. Obtén el valor
real con `GET /api/v1/sip-users/<id>/` (o desde el objeto que devuelven
`POST`/`PATCH`).

### POST `/api/v1/sip-users/`

Crear un usuario SIP.

**Cuerpo de la solicitud:**
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

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | mínimo 3 caracteres |
| `username` | sí | 3+ caracteres, solo letras/dígitos, único |
| `secret` | sí | contraseña SIP en texto plano |
| `transport` | sí | ID de un `SIPTransport` existente |
| `routing_table` | sí | ID de un `RoutingTable` existente |
| `extension` | sí | solo letras/dígitos, único |
| `nat` | no | por defecto `false` |
| `auth_type` | no | `userpass` (por defecto) o `md5` |
| `custom_extension`, `custom_settings`, `custom_auth_settings`, `custom_aor_settings` | no | fragmentos crudos de `pjsip.conf`/dialplan, escritos tal cual |

**Respuesta:** `HTTP 201` con el objeto de usuario creado, o `400` si
`username`/`extension` ya está en uso o falla la validación.

### PATCH `/api/v1/sip-users/<id>/`

Actualización parcial de un usuario SIP. Mismas reglas de campos que `POST`.

### DELETE `/api/v1/sip-users/<id>/`

Eliminar un usuario SIP. Devuelve `204 No Content`. Elimina en cascada
cualquier `PhoneDevice` aprovisionado.

---

## SIP Transports

Gestiona los transportes PJSIP. Al igual que [SIP Users](#sip-users),
**todos los métodos de este recurso — incluido `GET` — requieren una cuenta
de staff o superusuario**; `cert_file` y `priv_key_file` contienen material
de certificado TLS/clave privada en texto plano.

Guardar aquí solo actualiza la base de datos. Los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin.
`cert_file`, `priv_key_file` y `ca_list_file` contienen el **contenido** PEM,
no rutas de archivo — se escriben en disco bajo el directorio de
certificados de Asterisk solo cuando se ejecuta "Apply Changes", y solo para
un transporte con `protocol` `"tls"`.

Cambiar `protocol` en un transporte ya en uso reescribe cómo se genera cada
`SIPUser` conectado, e invalida su `md5_cred` (se deriva de
`protocol-username`). Eliminar el último transporte `wss` desactiva las
plantillas de configuración WebRTC para cada usuario WebRTC. Eliminar un
transporte todavía referenciado por un `SIPUser` o `SIPPeer` devuelve
`409 Conflict` en lugar de fallar a nivel de base de datos.

### GET `/api/v1/sip-transports/`

Devuelve transportes paginados. Admite:
- `?name=<exacto>` — filtrar por nombre exacto
- `?protocol=<udp|tcp|tls|wss>` — filtrar por protocolo
- `?search=<texto>` — coincidencia sin distinción de mayúsculas sobre `name`, `description`

**Respuesta:**
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

**`priv_key_file` siempre es `null` en esta respuesta de lista** — la clave
privada no se incluye en un volcado paginado masivo. Obtén el valor real con
`GET /api/v1/sip-transports/<id>/` (o desde el objeto que devuelven
`POST`/`PATCH`). `cert_file`/`ca_list_file` son material de certificado
público y no se ocultan.

`sip_users_count`/`sip_peers_count` son el número de filas `SIPUser`/`SIPPeer`
que actualmente usan este transporte — las mismas filas que bloquean un
`DELETE`. `has_tls_material` es `true` si alguno de los tres campos de
certificado está definido.

### POST `/api/v1/sip-transports/`

Crear un transporte.

**Cuerpo de la solicitud:**
```json
{
  "name": "transport-udp-nat",
  "protocol": "udp",
  "bind": "0.0.0.0:5060",
  "description": "UDP + NAT for remote users"
}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | letras/dígitos/guiones bajos/guiones, único, se usa como nombre de sección en `pjsip.conf` |
| `protocol` | no | `udp` (por defecto), `tcp`, `tls`, `wss` |
| `bind` | no | `<ipv4>` o `<ipv4>:<port>`, por defecto `0.0.0.0`; el puerto debe estar entre 1024-65535 |
| `description` | no | una sola línea, sin `\n`/`\r` — se escribe como comentario en `pjsip.conf` |
| `local_nets` | no | redes CIDR separadas por comas, p. ej. `10.0.0.0/16, 192.168.0.0/24`; en blanco se guarda como `null` |
| `external_media_address`, `external_signaling_address` | no | direcciones IP |
| `method`, `verify_server`, `allow_reload`, `cert_file`, `priv_key_file`, `ca_list_file` | no | solo tienen efecto cuando `protocol` es `tls` |

**Respuesta:** `HTTP 201` con el objeto de transporte creado, o `400` si
`name` ya está en uso o falla la validación.

### PATCH `/api/v1/sip-transports/<id>/`

Actualización parcial de un transporte. Mismas reglas de campos que `POST`.

### DELETE `/api/v1/sip-transports/<id>/`

Eliminar un transporte. Devuelve `204 No Content`, o `409 Conflict` con los
`SIPUser`/`SIPPeer` que todavía lo usan.

---

## SIP Peers

Gestiona los troncales/uplinks SIP. Al igual que [SIP Users](#sip-users),
**todos los métodos de este recurso — incluido `GET` — requieren una cuenta
de staff o superusuario**; este recurso expone credenciales de marcado
saliente (`secret` en texto plano y el `md5_cred` derivado).

Guardar aquí solo actualiza la base de datos. Los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. Un peer
guardado sin `transport` o sin `routing_table` generaría una entrada
incompleta en `pjsip.conf` (una sección `[auth]` sin `[endpoint]`/`[aor]`),
por eso ambos campos son obligatorios aquí. Si `registration_there` está
activado, `registration_uri` y `username` también son obligatorios.

Eliminar un peer que todavía pertenece a un `TrunkGroup` devuelve
`409 Conflict` en lugar de reducir el grupo silenciosamente.

### GET `/api/v1/sip-peers/`

Devuelve peers paginados. Admite:
- `?name=<exacto>` — filtrar por nombre exacto
- `?routing_table=<id>` — filtrar por tabla de enrutamiento
- `?search=<texto>` — coincidencia sin distinción de mayúsculas sobre `name`, `description`, `username`

**Respuesta:**
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

`registration_here`/`registration_there` corresponden a los campos del
modelo `registrationHere`/`registrationThere`. `auth_realm` y `md5_cred` son
la credencial RFC 2617 HA1 derivada de `username`/`auth_realm`/`secret` —
`auth_realm` es la parte del host de `registration_uri`, o `"asterisk"` si no
se ha definido. `trunk_groups` lista los nombres de cualquier `TrunkGroup` al
que pertenezca este peer; eliminar un peer que pertenece a al menos un grupo
se rechaza (ver arriba).

**`secret` y `md5_cred` siempre son `null` en esta respuesta de lista** — las
credenciales no se incluyen en un volcado paginado masivo. Obtén el valor
real con `GET /api/v1/sip-peers/<id>/` (o desde el objeto que devuelven
`POST`/`PATCH`).

### POST `/api/v1/sip-peers/`

Crear un peer.

**Cuerpo de la solicitud:**
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

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | 3+ caracteres, solo letras/dígitos, único, se usa como nombre de sección en `pjsip.conf` |
| `description` | sí | una sola línea, sin `\n`/`\r` |
| `transport` | sí | ID de un `SIPTransport` existente |
| `routing_table` | sí | ID de un `RoutingTable` existente |
| `username`, `contact_user` | no | letras/dígitos/guiones/puntos/guiones bajos |
| `auth_type` | no | `userpass` (por defecto) o `md5` |
| `secret` | no | contraseña SIP en texto plano |
| `registration_uri`, `contact_uri` | no | `host[:port]`; obligatorios si `registration_there` es `true` |
| `match_hosts` | no | hosts/IPs separados por comas, sin puertos |
| `registration_here` | no | por defecto `false` — el peer se registra con nosotros (gateways GSM/E1/T1/FXS/FXO) |
| `registration_there` | no | por defecto `false` — nos registramos con el peer (proveedores); requiere `registration_uri` y `username` |
| `nat` | no | por defecto `false` |
| `custom_auth_settings`, `custom_aor_settings`, `custom_identify_settings` | no | fragmentos crudos de `pjsip.conf`, escritos tal cual |

**Respuesta:** `HTTP 201` con el objeto de peer creado, o `400` si `name` ya
está en uso o falla la validación.

### PATCH `/api/v1/sip-peers/<id>/`

Actualización parcial de un peer. Mismas reglas de campos que `POST`.

### DELETE `/api/v1/sip-peers/<id>/`

Eliminar un peer. Devuelve `204 No Content`, o `409 Conflict` con los
`TrunkGroup` a los que todavía pertenece.

---

## Routing Tables

Gestiona las tablas de enrutamiento. Todos los métodos — incluido `GET` —
requieren una cuenta de staff o superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. `name`
es a la vez el nombre de un contexto AEL (`core.conf.make_routing_tables()`),
así que no puede coincidir con un nombre de `DialplanContext` — una
colisión devuelve `400`, no el `500` que un guardado directo del modelo
lanzaría.

### GET `/api/v1/routing-tables/`

Devuelve tablas de enrutamiento paginadas. Admite `?name=<exacto>` y
`?search=<texto>` (sobre `name`).

**Respuesta:**
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
`routing_records_count` es el número de filas `RoutingRecord` que apuntan a
esta tabla.

### POST `/api/v1/routing-tables/`

**Cuerpo de la solicitud:** `{"name": "Sales"}`

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | letras/dígitos/guiones bajos/guiones, único, no debe existir ya como nombre de `DialplanContext` |

**Respuesta:** `HTTP 201`, o `400` si `name` ya está en uso o colisiona con
un `DialplanContext`.

### PATCH `/api/v1/routing-tables/<id>/`

Mismas reglas de campos que `POST`.

### DELETE `/api/v1/routing-tables/<id>/`

Devuelve `204 No Content`, o `409 Conflict` si la tabla todavía está
referenciada por un `SIPUser`, `SIPPeer`, `RoutingRecord`, un servicio de
callback, o el filtro de tabla de enrutamiento de un `Webhook`.

---

## Routing Records

Gestiona las reglas de enrutamiento basadas en prefijo dentro de una
`RoutingTable`. Todos los métodos — incluido `GET` — requieren una cuenta de
staff o superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin.
`core.conf.make_routing_tables()` genera una línea `goto` por cada registro
dentro del contexto de dialplan de su tabla, ordenadas por especificidad del
patrón de Asterisk. `context` y `routing_table` son obligatorios aunque sean
nulos en la base de datos — un registro sin `context` generaría literalmente
`goto None,${EXTEN},1;`, y un registro sin `routing_table` nunca aparece en
el bloque de ninguna tabla.

### GET `/api/v1/routing-records/`

Devuelve registros de enrutamiento paginados. Admite:
- `?name=<exacto>` — filtrar por nombre exacto
- `?prefix=<exacto>` — filtrar por prefijo exacto
- `?routing_table=<id>` — filtrar por tabla de enrutamiento
- `?context=<id>` — filtrar por contexto de dialplan
- `?search=<texto>` — coincidencia sin distinción de mayúsculas sobre `name`, `prefix`

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"name": "Kyiv landline", "prefix": "044", "context": 1, "routing_table": 1}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | texto libre |
| `prefix` | sí | patrón de dialplan de Asterisk (p. ej. `044`, `_0XX`, `_1XX.`) |
| `context` | sí | ID de un `DialplanContext` existente |
| `routing_table` | sí | ID de una `RoutingTable` existente |

**Respuesta:** `HTTP 201`, o `400` si `prefix` falla la validación de patrón
o falta un campo obligatorio.

### PATCH `/api/v1/routing-records/<id>/`

Mismas reglas de campos que `POST`.

### DELETE `/api/v1/routing-records/<id>/`

Eliminar un registro de enrutamiento. Devuelve `204 No Content` — nada
referencia a un `RoutingRecord`, así que la eliminación nunca se bloquea.

---

## Dialplan Contexts

Gestiona los contextos de dialplan (`core.conf.make_dialplan_contexts()`).
Todos los métodos — incluido `GET` — requieren una cuenta de staff o
superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. `name`
comparte un espacio de nombres con `RoutingTable` — ambos no deben coincidir.

El contexto autogenerado `"PEARLPBX-Users"` se renderiza en vivo a partir de
los datos de `SIPUser` mediante `core.conf.make_local_users_context()` y no
se puede renombrar ni eliminar mediante este endpoint — ver
[Dialplan Extensions](#dialplan-extensions) para saber por qué tampoco se
pueden crear extensiones dentro de él.

### GET `/api/v1/dialplan-contexts/`

Devuelve contextos paginados. Admite `?name=<exacto>` y `?search=<texto>`
(coincide con `name`, `description`).

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"name": "internal", "description": "Internal extensions"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | único; no debe coincidir con un nombre de `RoutingTable` |
| `description` | no | texto libre, sin saltos de línea |

**Respuesta:** `HTTP 201`, o `400` si `name` ya está tomado o coincide con
una `RoutingTable`.

### PATCH `/api/v1/dialplan-contexts/<id>/`

Mismas reglas de campos que `POST`. Renombrar el contexto autogenerado
`"PEARLPBX-Users"` devuelve `400`.

### DELETE `/api/v1/dialplan-contexts/<id>/`

Devuelve `204 No Content`, o `409 Conflict` si el contexto es el
autogenerado `"PEARLPBX-Users"`, todavía lo usa el filtro de contexto de un
webhook, o todavía lo referencia un `DialplanExtension` o `RoutingRecord`.

---

## Dialplan Extensions

Gestiona las extensiones de dialplan dentro de un contexto
(`core.conf.make_dialplan_contexts()`). Todos los métodos — incluido `GET` —
requieren una cuenta de staff o superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin.
`dialplan` debe usar sintaxis válida de Asterisk AEL y referenciar solo
macros que ya existan — `core.validators.validate_dialplan_field` resuelve
el conjunto de macros permitidos desde la base de datos en el momento de la
solicitud, así que **crea primero el macro y luego la extensión** que lo
llama con `&name();` (ver [Dialplan Macros](#dialplan-macros)). No se pueden
crear extensiones dentro del contexto autogenerado `"PEARLPBX-Users"` — se
renderiza en vivo a partir de los datos de `SIPUser`, así que nada de lo
guardado ahí llegaría nunca a `extensions.ael`.

### GET `/api/v1/dialplan-extensions/`

Devuelve extensiones paginadas. Admite:
- `?context=<id>` — filtrar por contexto de dialplan
- `?ext=<exacto>` — filtrar por patrón de extensión exacto
- `?search=<texto>` — coincidencia sin distinción de mayúsculas sobre `ext`,
  `description`, `dialplan`, `context__name`

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"context": 1, "ext": "_1XX", "dialplan": "Dial(PJSIP/${EXTEN},30);\nHangup();"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `context` | sí | ID de un `DialplanContext` existente; no puede ser el contexto autogenerado `"PEARLPBX-Users"` |
| `ext` | sí | patrón de extensión de Asterisk (p. ej. `100`, `_1XX`, `_X.`) |
| `dialplan` | sí | sintaxis de Asterisk AEL; las llamadas a macros (`&name();`) deben referenciar un `DialplanMacro` existente |
| `description` | no | texto libre, sin saltos de línea |

**Respuesta:** `HTTP 201`, o `400` si `dialplan` falla la validación de
sintaxis AEL, referencia un macro desconocido, `ext` falla la validación de
patrón, `context` es el contexto reservado, o el par `(context, ext)` ya
está tomado.

### PATCH `/api/v1/dialplan-extensions/<id>/`

Mismas reglas de campos que `POST`.

### DELETE `/api/v1/dialplan-extensions/<id>/`

Eliminar una extensión. Devuelve `204 No Content` — nada referencia a un
`DialplanExtension`, así que la eliminación nunca se bloquea.

---

## Dialplan Macros

Gestiona los macros de dialplan (`core.conf.make_dialplan_macros()`),
llamados desde el cuerpo de las extensiones como `&name();`. Todos los
métodos — incluido `GET` — requieren una cuenta de staff o superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. `name`
se busca como texto literal de llamada a macro AEL en los cuerpos de
`DialplanExtension.dialplan`, en otros macros y en
`Settings.local_users_dial_template` — **renombrar o eliminar un macro
todavía referenciado así se rechaza** (`400`/`409`) en lugar de romper
silenciosamente el dialplan generado. Es una búsqueda de texto de mejor
esfuerzo (con distinción de mayúsculas, a diferencia de la protección de
nombres de [Queues](#queues)): no puede ver un nombre al que se llega solo
mediante una variable de Asterisk, y no puede ver el fallback de Python
`DEFAULT_LOCAL_USERS_DIAL_TEMPLATE`, usado cuando no existe una fila de
`Settings` o su campo está vacío.

### GET `/api/v1/dialplan-macros/`

Devuelve macros paginados. Admite `?name=<exacto>` y `?search=<texto>`
(coincide con `name`, `description`, `macro`).

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"name": "stdexten", "description": "Standard extension", "macro": "Dial(PJSIP/${ARG1},30);\nVoicemail(${ARG1});"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | único; solo letras, dígitos y guiones bajos, no puede empezar con un dígito |
| `description` | no | texto libre, sin saltos de línea |
| `macro` | sí | sintaxis de Asterisk AEL (no validada contra `AsteriskDialplanValidator`) |

**Respuesta:** `HTTP 201`, o `400` si `name` ya está tomado o tiene un
formato inválido.

### PATCH `/api/v1/dialplan-macros/<id>/`

Mismas reglas de campos que `POST`. Renombrar mientras todavía se
referencia devuelve `400` con la lista de extensiones/macros/campo
`Settings` que lo referencian.

### DELETE `/api/v1/dialplan-macros/<id>/`

Devuelve `204 No Content`, o `409 Conflict` con la lista de
extensiones/macros/campo `Settings` que todavía llaman al macro.

---

## Trunk Groups

Gestiona los grupos de troncales (conjuntos de failover de SIP peers). Todos
los métodos — incluido `GET` — requieren una cuenta de staff o superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. `name`
es buscado por el manejador FastAGI `dial-trunk-group` mediante una llamada
literal `AGI(agi://.../dial-trunk-group,<name>,...)` incrustada en el texto
del dialplan — **renombrar o eliminar un grupo todavía referenciado así se
rechaza** (`400`/`409`) en lugar de romper silenciosamente el enrutamiento
de llamadas. Es un escaneo de texto best-effort: no puede ver un nombre
alcanzado solo a través de una variable de Asterisk (p. ej. `${GROUPNAME}`).

### GET `/api/v1/trunk-groups/`

Devuelve grupos de troncales paginados. Admite `?name=<exacto>` y
`?search=<texto>`.

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"name": "main-trunks", "sip_peers": [5, 6]}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | único |
| `sip_peers` | no | lista de IDs de `SIPPeer`; a diferencia de `SIPPeer.trunk_groups` (solo lectura), este es el lado escribible de la relación |

**Respuesta:** `HTTP 201`, o `400` si `name` ya está en uso.

### PATCH `/api/v1/trunk-groups/<id>/`

Mismas reglas de campos que `POST`. Renombrar mientras el dialplan todavía
referencia el nombre actual devuelve `400` nombrando la(s)
extensión(es)/macro(s) que lo referencian.

### DELETE `/api/v1/trunk-groups/<id>/`

Devuelve `204 No Content`, o `409 Conflict` nombrando la(s)
extensión(es)/macro(s) si el dialplan todavía llama a este grupo por nombre.

---

## Phone Devices

Gestiona los dispositivos telefónicos aprovisionados (teléfonos físicos,
softphones, clientes WebRTC). Todos los métodos — incluido `GET` — requieren
una cuenta de staff o superusuario.

Guardar aquí solo actualiza la base de datos. El archivo de configuración
TFTP de un dispositivo solo se (re)escribe mediante la acción `provision`
descrita abajo, o mediante la acción "Apply configurations" del admin —
ninguna de las dos se ejecuta implícitamente al guardar.

### GET `/api/v1/phone-devices/`

Devuelve dispositivos paginados. Admite:
- `?mac_address=<exacto>` — filtrar por dirección MAC exacta
- `?sip_user=<id>` — filtrar por usuario SIP asignado
- `?telephone_type=<tipo>` — filtrar por tipo de dispositivo (`spa502g`, `spa504g`, `gxp1200`, `softphone`, `webrtc`, `other`)
- `?search=<texto>` — coincidencia sin distinción de mayúsculas contra la MAC, el usuario SIP y el nombre SIP

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"telephone_type": "softphone", "mac_address": "00:1a:2b:3c:4d:5e", "sip_user": 3, "sip_server": "pbx.example.com"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `telephone_type` | no | por defecto `"other"` |
| `mac_address` | sí | única; normalizada a `XX:XX:XX:XX:XX:XX` (acepta separadores, mayúsculas/minúsculas mixtas) |
| `sip_user` | no | ID de un `SIPUser` existente; un dispositivo sin usuario asignado es un estado normal, aún sin configurar |
| `sip_server` | no | por defecto `""` — un valor vacío recurre a la dirección global de aprovisionamiento al generar |

**Respuesta:** `HTTP 201`, o `400` si `mac_address` es inválida o ya está en uso.

### PATCH `/api/v1/phone-devices/<id>/`

Mismas reglas de campos que `POST`.

### DELETE `/api/v1/phone-devices/<id>/`

Elimina un dispositivo. Devuelve `204 No Content` — nada referencia a un
`PhoneDevice`, así que la eliminación nunca se bloquea. Eliminar el
`SIPUser` asignado en cambio elimina en cascada también este dispositivo
(ver [SIP Users](#sip-users)).

### POST `/api/v1/phone-devices/<id>/provision/`

Genera el archivo de configuración TFTP de este dispositivo — la misma
acción que el botón "Apply configurations" del admin, para un solo
dispositivo, vía la API. Solo se admiten `spa502g`, `spa504g` y `gxp1200`;
los dispositivos `softphone`/`webrtc`/`other` no tienen archivo de
configuración que generar.

**Respuestas:**

| Estado | Significado |
|--------|---------|
| `200` | `{"success": true, "device_mac": "...", "filename": "...", "filepath": "...", "size": 512}` |
| `400` | `{"success": false, "device_mac": "...", "error": "..."}` — p. ej. sin usuario SIP asignado, o `telephone_type` no admitido |

---

## Config (Apply Changes)

Envuelve la página "Apply Changes" del admin. **Ambos endpoints requieren
una cuenta de superusuario — un token de solo staff no es suficiente**, ya
que `apply` puede reiniciar Asterisk y cortar todas las llamadas activas.

### GET `/api/v1/config/preview/`

Dry-run: devuelve el mismo contenido de archivos generado que la página de
vista previa del admin. Sin escritura en disco, sin recarga de Asterisk.

**Respuesta:**
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

Escribe las configuraciones generadas (versionadas, con un tarball de
respaldo bajo `ASTERISK_BACKUP_DIR` de antemano) y recarga Asterisk.

**Cuerpo de la solicitud:** `{"mode": "soft"}` o `{"mode": "hard"}`

| Campo | Obligatorio | Notas |
|---|---|---|
| `mode` | **sí** | `soft` — recarga de módulos/AEL, mantiene las llamadas activas; `hard` — `core restart now`, corta todas las llamadas activas |

A diferencia del formulario del admin (donde cualquier valor que no sea la
cadena literal `"soft"` significa silenciosamente un reinicio duro), `mode`
es un campo de elección obligatorio y validado — si falta o es inválido
devuelve `400`.

**Respuesta:**
```json
{
  "mode": "soft",
  "changed_files": ["pjsip.conf", "queues.conf"],
  "reloaded": true,
  "skipped_sip_users": []
}
```
`changed_files` lista solo los archivos cuyo contenido realmente cambió
(obtuvo una nueva versión) en este apply. `reloaded` es `false` cuando
`DEVMODE=without_asterisk_on_localhost` — los archivos se escriben igual,
pero no se hace ninguna llamada AMI (igual que el comportamiento de dev del
admin).

**`409 Conflict`** si ya hay otro apply en curso (un bloqueo Redis de corta
duración); si el propio Redis no está disponible, el apply continúa sin el
bloqueo en lugar de quedar inutilizable.

---

## Iniciar una llamada (Originate)

**`POST /api/v1/calls/originate/`**

Inicia una llamada a través de Asterisk AMI. Sustituye a las llamadas HTTP directas al `rawman` de Asterisk — el secreto de AMI nunca lo envía el cliente.

**Cuerpo de la solicitud:**

| Campo | Tipo | Obligatorio | Valor por defecto | Descripción |
|-------|------|----------|---------|-------------|
| `channel` | cadena | sí | — | La primera pierna a marcar, p. ej. `"Local/0441231231@Outgoing"` o `"PJSIP/2101"` |
| `exten` | cadena | sí | — | El número externo al que se conecta la primera pierna, p. ej. `"0123123123"` |
| `context` | cadena | sí | `"Outgoing"` | Tabla de enrutamiento que tiene acceso a llamadas externas |
| `priority` | entero | sí | `1` | Prioridad del plan de marcado (dejar: 1) |
| `callerid` | cadena | sí | — | Caller ID en formato `nombre<número>`, p. ej. `"PearlPBX2 Auto Call<número_al_que_llama>"` |
| `variable` | objeto | no | — | Variables de canal como pares clave-valor, p. ej. `{"userId": "0"}` |
| `timeout_ms` | entero | sí | `30000` | Timeout de Originate en el lado de Asterisk, en ms (1000–120000). Este es también el presupuesto de espera del lado del servidor: el worker de la API no bloqueará esperando la respuesta de AMI más de `timeout_ms + 5s` |

**Respuestas:**

| Estado | Significado |
|--------|---------|
| `200` | Llamada iniciada correctamente. Cuerpo: `{"status": "originated", "message": "..."}` |
| `400` | Cuerpo de solicitud inválido (faltan campos obligatorios, errores de validación) |
| `401` | No se proporcionaron credenciales de autenticación |
| `502` | Error de AMI o Asterisk inaccesible |
| `503` | Asterisk está deshabilitado en este DEVMODE |

**Ejemplo:**

```bash
curl -k -X 'POST' \
  'https://<tu-servidor>/api/v1/calls/originate/' \
  -H 'accept: */*' \
  -H 'Authorization: Token <tu-token>' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRFTOKEN: <tu-csrf-token>' \
  -d '{
  "callerid": "0504139380",
  "timeout_ms": 30000,
  "channel": "PJSIP/2101",
  "exten": "0504139380",
  "context": "Outgoing",
  "priority": 1
}'
```

> **Notas:**
> - `timeout_ms` se expresa en **milisegundos** y solo limita la creación de la **primera pierna** de la llamada — el `channel` del ejemplo (`PJSIP/2101`, una extensión SIP interna). No afecta cuánto tiempo suena la segunda pierna (`exten`).
> - Si la respuesta es `Originate failed`, significa que Asterisk no pudo crear ese primer canal. Causas habituales: la extensión (`PJSIP/2101`) no existe o no está registrada, el operador no contestó, o el operador rechazó/colgó la llamada antes de conectarse.

**Correspondencia con los parámetros antiguos de rawman:**

| parámetro rawman | campo de la API |
|---|---|
| `channel` | `channel` |
| `exten` | `exten` |
| `context` | `context` |
| `priority` | `priority` |
| `Variable` | `variable` (dict) |
| `callerId` | `callerid` |

---

## Queues

Gestiona la configuración estática de una cola de llamadas (`app_queue`).
Todos los métodos — incluido `GET` — requieren una cuenta de staff o
superusuario.

Guardar aquí solo actualiza la base de datos; los cambios llegan a Asterisk
después de que un superusuario ejecute "Apply Changes" en el admin. `name`
es buscado por `app_queue` de Asterisk mediante una llamada AEL literal
`Queue(<name>,...)` incrustada en el texto del dialplan — **renombrar o
eliminar una cola todavía referenciada así se rechaza** (`400`/`409`) en
lugar de romper silenciosamente el enrutamiento de llamadas. A diferencia de
la protección de [Trunk Groups](#trunk-groups), esta coincidencia no
distingue mayúsculas/minúsculas, ya que `app_queue` busca los nombres de
cola con `strcasecmp()`. Es un escaneo de texto best-effort: no puede ver un
nombre alcanzado solo a través de una variable de Asterisk (p. ej.
`${QUEUENAME}`).

Distinto de [Queue Members (estado AMI en vivo)](#queue-members-estado-ami-en-vivo)
más abajo: este recurso trata sobre lo que se escribe en `queues.conf`, no
sobre el estado de pausa/estado en tiempo de ejecución.

### GET `/api/v1/queues/`

Devuelve colas paginadas. Admite `?name=<exacto>`, `?strategy=<exacto>` y
`?search=<texto>`.

**Respuesta (abreviada — ver POST abajo para la lista completa de campos):**
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

**Cuerpo de la solicitud (mínimo):**
```json
{"name": "Sales", "music_class": 1, "queue_announcement": 1, "strategy": "ringall"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `name` | sí | único |
| `music_class` | sí | ID de una clase `MusicOnHold` existente |
| `queue_announcement` | sí | ID de un registro `QueueAnnouncements` existente |
| `strategy` | sí | uno de `ringall`, `leastrecent`, `fewestcalls`, `random`, `rrmemory`, `rrordered`, `linear`, `wrandom` — obligatorio aunque sea nullable en la BD, ya que la configuración generada no tiene protección contra null para este campo |
| `defaultrule` | no | ID de un `QueueRule` existente |
| `context`, `timeout`, `retry`, `maxlen`, `weight`, `wrapuptime`, `autofill`, `autopause`, `autopausedelay`, `announce`, `queue_announce`, `service_level`, `joinempty`, `leavewhenempty`, `ringinuse`, `timeoutrestart`, `monitor_format`, `periodic_announce`, y los campos `announce_*`/`*_announce_frequency` | no | ver el formulario Queue del admin para el conjunto completo; todos mapean 1:1 con las opciones de `app_queue` |

**Respuesta:** `HTTP 201`, o `400` si `name` ya está en uso, falta `strategy`, o una cola con el mismo nombre (anterior) todavía es referenciada por el dialplan.

### PATCH `/api/v1/queues/<id>/`

Mismas reglas de campos que `POST`. Renombrar mientras el dialplan todavía
referencia el nombre actual devuelve `400` nombrando la(s)
extensión(es)/macro(s) que lo referencian.

### DELETE `/api/v1/queues/<id>/`

Devuelve `204 No Content`, o `409 Conflict` nombrando la(s)
extensión(es)/macro(s) si el dialplan todavía llama a esta cola por nombre.

---

## Queue Members (configuración estática)

Gestiona la lista estática de miembros de una cola (`core.conf` genera una
línea `member => ...` por fila en `queues.conf`). Todos los métodos —
incluido `GET` — requieren una cuenta de staff o superusuario, ya que esto
escribe configuración en la BD en lugar de leer el estado de ejecución en
vivo (a diferencia de los endpoints AMI de abajo, que solo requieren
autenticación).

Distinto de [Queue Members (estado AMI en vivo)](#queue-members-estado-ami-en-vivo)
más abajo: `GET /api/v1/queue-members/?queue=<id>` responde "quién está
configurado estáticamente en esta cola" desde la base de datos; `GET
/api/v1/queues/members/?queue=<name>` (abajo) responde "quién está
actualmente en pausa/sonando/en llamada" desde el estado AMI en vivo de
Asterisk. Ambos endpoints permanecen — responden preguntas diferentes.

### GET `/api/v1/queue-members/`

Devuelve miembros de cola paginados. Admite:
- `?queue=<id>` — filtrar por cola
- `?interface=<exacto>` — filtrar por interfaz exacta
- `?search=<texto>` — coincidencia sin distinción de mayúsculas contra el nombre del miembro, la interfaz, la state interface y el nombre de la cola

**Respuesta:**
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

**Cuerpo de la solicitud:**
```json
{"queue": 1, "interface": "PJSIP/101"}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `queue` | sí | ID de una `Queue` existente |
| `interface` | sí | p. ej. `"PJSIP/101"`; solo letras, dígitos y `_.-/@` |
| `penalty` | no | por defecto `0` |
| `member_name` | no | por defecto `""` — un valor null se renderizaría en `queues.conf` como la palabra literal `None` |
| `state_interface`, `ringinuse`, `wrapuptime` | no | ver el formulario inline del admin |

Un par `(queue, interface)` dado debe ser único.

**Respuesta:** `HTTP 201`, o `400` si `interface` es inválida, faltan campos obligatorios, o el par `(queue, interface)` ya existe.

### PATCH `/api/v1/queue-members/<id>/`

Mismas reglas de campos que `POST`.

### DELETE `/api/v1/queue-members/<id>/`

Elimina un miembro de cola. Devuelve `204 No Content` — nada referencia a un
`QueueMember`, así que la eliminación nunca se bloquea.

---

## Queue Members (estado AMI en vivo)

Pausar/reanudar un miembro de cola y leer el estado en vivo de los miembros de cola a través de Asterisk AMI.
No existe aquí un recurso persistente "miembro de cola" — estos endpoints hablan
directamente con Asterisk, por lo que reflejan (y modifican) el estado de ejecución en vivo, no los
registros `QueueMember` gestionados en [Queue Members (configuración
estática)](#queue-members-configuración-estática) arriba.

### POST `/api/v1/queues/members/pause/`

Pausar o reanudar un miembro de cola.

**Cuerpo de la solicitud:**

| Campo | Tipo | Obligatorio | Valor por defecto | Descripción |
|-------|------|----------|---------|-------------|
| `interface` | cadena | sí | — | Interfaz del miembro de cola, p. ej. `"PJSIP/101"` |
| `paused` | booleano | sí | — | `true` para pausar, `false` para reanudar |
| `queue` | cadena | no | — | Limitar el cambio a una sola cola. Si se omite, se aplica al miembro en todas las colas a las que pertenece |

**Respuestas:**

| Estado | Significado |
|--------|---------|
| `200` | Estado de pausa actualizado. Cuerpo: `{"status": "paused"}` o `{"status": "unpaused"}` |
| `400` | Cuerpo de solicitud inválido |
| `401` | No se proporcionaron credenciales de autenticación |
| `404` | La interfaz no es miembro de la(s) cola(s) indicada(s) |
| `502` | Error de AMI o Asterisk inaccesible |
| `503` | Asterisk está deshabilitado en este DEVMODE |

**Ejemplo:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/queues/members/pause/ \
  -H "Authorization: Token <tu-token>" \
  -H "Content-Type: application/json" \
  -d '{"interface": "PJSIP/101", "paused": true}'
```

### GET `/api/v1/queues/members/`

Lista los miembros de cola y su estado actual. El parámetro de consulta opcional
`?queue=<name>` limita los resultados a una cola; si se omite, se listan los miembros de todas las colas.

**Respuesta:**

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

`status` es el código crudo de estado de dispositivo de Asterisk (`AST_DEVICE_*`), transmitido
sin traducción.

**Respuestas:**

| Estado | Significado |
|--------|---------|
| `200` | Lista de miembros (posiblemente vacía) |
| `401` | No se proporcionaron credenciales de autenticación |
| `502` | Error de AMI o Asterisk inaccesible |
| `503` | Asterisk está deshabilitado en este DEVMODE |

---

## Call Recordings (grabaciones de llamadas)

**`GET /api/v1/recordings/<uniqueid>/`**

Obtén el audio de una llamada grabada por su uniqueid de Asterisk. Este es el endpoint al que hace referencia
`recording_url` en los payloads de webhook del CRM — ver la
[guía de integración con CRM](crm-integration.md) para la referencia completa de webhooks. Admite solicitudes HTTP
`Range` para streaming/avance, y un parámetro de consulta
`?download=1` que fuerza una respuesta `Content-Disposition: attachment`.

**Respuestas:**

| Estado | Significado |
|--------|---------|
| `200` / `206` | El archivo de audio (`audio/wav` o `audio/mpeg`), completo o parcial (Range) |
| `401` | No se proporcionaron credenciales de autenticación |
| `404` | No existe grabación para este uniqueid (no se grabó, o aún no se ha escrito en disco) |

**Ejemplo:**

```bash
curl -H "Authorization: Token <tu-token>" \
  http://127.0.0.1:8000/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

El acceso no está delimitado más allá de esto — cualquier token de API válido puede obtener cualquier
grabación, igual que en el resto de esta API.

---

## Limitaciones conocidas

- No hay filtrado ni búsqueda en los endpoints GET, excepto en
  `/api/v1/sip-users/` (`?username=`, `?extension=`, `?search=`),
  `/api/v1/sip-transports/` (`?name=`, `?protocol=`, `?search=`),
  `/api/v1/sip-peers/` (`?name=`, `?routing_table=`, `?search=`),
  `/api/v1/routing-tables/` (`?name=`, `?search=`),
  `/api/v1/routing-records/` (`?name=`, `?prefix=`, `?routing_table=`,
  `?context=`, `?search=`), `/api/v1/dialplan-contexts/` (`?name=`,
  `?search=`), `/api/v1/dialplan-extensions/` (`?context=`, `?ext=`,
  `?search=`), `/api/v1/dialplan-macros/` (`?name=`, `?search=`),
  `/api/v1/trunk-groups/` (`?name=`, `?search=`),
  `/api/v1/phone-devices/` (`?mac_address=`, `?sip_user=`,
  `?telephone_type=`, `?search=`), `/api/v1/queues/` (`?name=`,
  `?strategy=`, `?search=`) y `/api/v1/queue-members/` (`?queue=`,
  `?interface=`, `?search=`).
- La protección de renombrado/eliminación de grupos de troncales es un
  escaneo de texto best-effort de los cuerpos del dialplan buscando una
  llamada literal `dial-trunk-group,<name>,` — no puede ver un nombre de
  grupo alcanzado solo a través de una variable de Asterisk. La protección
  de colas es el mismo tipo de escaneo para una llamada literal
  `Queue(<name>,...)`, pero sin distinción de mayúsculas/minúsculas (a
  diferencia de la de grupos de troncales), ya que `app_queue` busca los
  nombres de cola con `strcasecmp()`. La protección de macros de dialplan
  es el mismo tipo de escaneo para una llamada literal `&<name>();`, con
  distinción de mayúsculas/minúsculas (AEL resuelve las llamadas a macros
  por nombre exacto); además escanea
  `Settings.local_users_dial_template`, pero no puede ver el fallback de
  Python `DEFAULT_LOCAL_USERS_DIAL_TEMPLATE`, usado cuando no existe una
  fila de `Settings` o su campo está vacío.
- El contexto de dialplan autogenerado `"PEARLPBX-Users"` no se puede
  renombrar ni eliminar, y no se puede crear ningún `DialplanExtension`
  dentro de él — se renderiza en vivo a partir de los datos de `SIPUser`
  mediante `core.conf.make_local_users_context()`, así que nada de lo
  guardado en la fila de la base de datos llegaría nunca a
  `extensions.ael`.

---

## Documentación de la API

Hay disponible documentación interactiva de OpenAPI 3.0 generada automáticamente (basada en
drf-spectacular). Los tres endpoints requieren autenticación (un token válido o una
sesión autenticada), igual que el resto de la API.

- **Esquema crudo (OpenAPI 3.0, YAML):** `GET /api/v1/schema/`
- **Swagger UI:** `GET /api/v1/docs/`
- **ReDoc UI:** `GET /api/v1/redoc/`

> **Nota:** Estos tres endpoints requieren autenticación (`Authorization: Token <clave>`),
> igual que el resto de la API. Abrirlos directamente en un navegador sin token
> devuelve `401`. Esto es intencional — la documentación no está expuesta públicamente.

El esquema se genera directamente a partir de los ViewSets y serializers de DRF, por lo que siempre
coincide con el código que se está ejecutando.
