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

## Queue Members (miembros de cola)

Pausar/reanudar un miembro de cola y leer el estado en vivo de los miembros de cola a través de Asterisk AMI.
No existe aquí un recurso persistente "miembro de cola" — estos endpoints hablan
directamente con Asterisk, por lo que reflejan (y modifican) el estado de ejecución en vivo, no los
registros `QueueMember` gestionados en el admin de Django.

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

- No hay filtrado ni búsqueda en los endpoints GET.

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
