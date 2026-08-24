*Also available in: [English](../en/crm-integration.md) | [Українська](../ua/crm-integration.md) | [Español](crm-integration.md)*

# Integración con CRM

**Versión:** 2.7.2

---

PearlPBX2 notifica a sistemas CRM externos sobre las llamadas de dos formas:

- **webhooks** — el propio servicio dashboard envía una solicitud `POST` a la URL configurada en el CRM cuando llega una llamada entrante, un operador responde una llamada, una llamada finaliza, o se pierde una llamada en una cola;
- **API REST** — con un token, el CRM obtiene el archivo de grabación de la llamada en un enlace determinista que llega en el cuerpo del webhook.

Esta funcionalidad es completamente opcional: mientras no exista ningún registro `Webhook` activo en el panel de administración, no se envía nada y no hay carga adicional sobre el sistema.

## Contenido

1. [Cómo funciona](#1-cómo-funciona)
2. [Configurar un webhook en el panel de administración](#2-configurar-un-webhook-en-el-panel-de-administración)
3. [Formatos de los mensajes (payload)](#3-formatos-de-los-mensajes-payload)
4. [Grabaciones de llamadas: enlaces y descarga vía la API](#4-grabaciones-de-llamadas-enlaces-y-descarga-vía-la-api)
5. [Verificación de la firma de la solicitud](#5-verificación-de-la-firma-de-la-solicitud)
6. [Plantilla personalizada del cuerpo de la solicitud](#6-plantilla-personalizada-del-cuerpo-de-la-solicitud)
7. [Comportamiento ante fallos de entrega](#7-comportamiento-ante-fallos-de-entrega)
8. [Ejemplo: un manejador mínimo de webhooks](#8-ejemplo-un-manejador-mínimo-de-webhooks)

---

## 1. Cómo funciona

La fuente de verdad sobre el estado de las llamadas es el servicio `services/dashboard/dashboard_listener.py` — escucha los eventos AMI de Asterisk en tiempo real. Envía webhooks en dos cadenas de eventos independientes.

**Cadena entrante** — llamadas que llegan a la PBX (desde un troncal, o una llamada interna que entra en un contexto/cola):

| Evento          | Cuándo se dispara | Condición |
|----------------|------------------|-------|
| `call.incoming` | una llamada nueva entra en un contexto configurado, o se une a una cola configurada | el contexto/cola de la llamada coincide con el filtro del webhook |
| `call.answered` | un operador contesta una llamada de una cola (evento AMI `AgentConnect`) | la cola de la llamada coincide con el filtro del webhook, y "Send answered" está habilitado en él |
| `call.missed`   | el llamante cuelga antes de que un operador conteste en la cola | la cola de la llamada coincide con el filtro del webhook, y "Send missed" está habilitado en él |
| `call.ended`    | el canal finaliza (hangup) | **solo para llamadas para las que se envió previamente un `call.incoming`** |

**Cadena saliente** — llamadas iniciadas por un usuario SIP (un abonado interno que descuelga y marca un número), **nunca** un troncal:

| Evento | Cuándo se dispara | Condición |
|-------|------------------|-------|
| `call.outgoing` | un canal nuevo perteneciente a un usuario SIP cuyo endpoint está en una de las tablas de enrutamiento del webhook | el endpoint del canal coincide con el filtro "Routing tables" del webhook |
| `call.outgoing_answered` | la parte llamada descuelga (evento AMI `DialEnd` con `DialStatus=ANSWER`) | **solo para llamadas para las que se envió previamente un `call.outgoing`** |
| `call.outgoing_ended` | el canal finaliza (hangup) | **solo para llamadas para las que se envió previamente un `call.outgoing`** |

Un matiz importante: `call.ended` y `call.outgoing_ended` se envían deliberadamente **solo** para llamadas sobre las que el CRM ya fue informado mediante `call.incoming` o `call.outgoing`, respectivamente. El sistema recuerda en Redis (`webhook:notified:{uniqueid}`, TTL de 2 horas) a qué webhooks se les notificó el inicio de una llamada (y en qué cadena — entrante o saliente), y comprueba este registro cuando la llamada finaliza. Esto garantiza que:
- el CRM nunca reciba un evento de "llamada finalizada" para una llamada de la que nunca se le informó;
- el CRM nunca reciba este evento dos veces;
- una llamada de la cadena saliente siempre finaliza con `call.outgoing_ended`, nunca con `call.ended`, incluso si el mismo webhook está suscrito a ambas cadenas.

Los eventos `call.missed` y `call.answered`, en cambio, **no** requieren un `call.incoming` previo — tanto una llamada perdida como una respondida merecen su propio registro en el CRM, aunque este webhook no esté suscrito a llamadas entrantes. Si la llamada fue anunciada de todos modos (se envió `call.incoming` para ella), ambos eventos marcan además un indicador interno: una llamada perdida establece `missed: true`, y la respuesta de un operador registra quién respondió exactamente (`answered_by_member`, `answered_by_interface`). El posterior `call.ended` incluirá todos estos campos — así el CRM puede correlacionar todos los eventos de una misma llamada sin solicitudes adicionales. `call.outgoing_answered` funciona de forma análoga: el indicador recibe un `DialStatus` y una marca de tiempo de la respuesta, y `call.outgoing_ended` lleva los campos `answered`/`dial_status`, para que el CRM distinga una conexión exitosa de BUSY/NOANSWER/CANCEL sin solicitudes adicionales.

El evento `call.answered` solo existe para llamadas que pasan por una cola — corresponde al evento AMI de Asterisk `AgentConnect`, que no ocurre fuera de las colas. Por eso "Send answered" solo se puede habilitar si hay al menos una cola seleccionada (igual que `send_missed`).

**Cómo se distingue una llamada saliente de un troncal con la misma tabla de enrutamiento.** Tanto un usuario SIP como un troncal pueden tener un `context` de PJSIP igual al nombre de la tabla de enrutamiento (así es como funciona la generación de `pjsip.conf`), por lo que el contexto del canal por sí solo no permite diferenciarlos. En su lugar, Django serializa en Redis un mapa `{nombre_endpoint: nombre_tabla_enrutamiento}` — **solo para usuarios SIP**, los troncales nunca entran en él. Cuando llega un canal nuevo, `dashboard_listener` extrae de su nombre (`PJSIP/1001-0000000a` → `1001`) el nombre del endpoint y lo busca en este mapa. Si el endpoint no se encuentra (es un troncal, o cualquier otra cosa que no sea un usuario SIP configurado), la cadena de eventos salientes nunca se dispara, sin importar qué contexto o tabla de enrutamiento estén configurados.

## 2. Configurar un webhook en el panel de administración

Los webhooks se configuran en el admin de Django, en el modelo **Webhooks** (solo superuser). Cada fila es una integración independiente, así que puedes conectar varios CRM distintos a la vez — por ejemplo, una fila para la cadena entrante y otra fila separada (con su propia URL) para la cadena saliente.

Campos del formulario:

| Campo | Descripción |
|------|------|
| `is_active` | activar/desactivar este webhook sin eliminar su configuración |
| `url` | la dirección en la que el CRM recibe las solicitudes `POST` |
| `send_incoming` / `send_ended` / `send_missed` / `send_answered` | a qué eventos de la cadena **entrante** está suscrito este webhook. `send_ended` requiere que `send_incoming` esté habilitado. `send_missed` y `send_answered` requieren cada uno al menos una cola seleccionada. Estos eventos se comparan solo por `contexts`/`queues`, nunca por `routing_tables` |
| `send_outgoing` / `send_outgoing_answered` / `send_outgoing_ended` | a qué eventos de la cadena **saliente** está suscrito este webhook. `send_outgoing_answered` y `send_outgoing_ended` requieren cada uno que `send_outgoing` esté habilitado. Estos eventos se comparan solo por `routing_tables` |
| `contexts` | una lista de contextos del plan de marcado — las llamadas entrantes a estos contextos disparan `call.incoming` |
| `routing_tables` | los usuarios SIP asignados a estas tablas de enrutamiento disparan la cadena saliente cuando ellos mismos inician una llamada. Un troncal — nunca |
| `queues` | una lista de colas — las llamadas que se unen a estas colas disparan eventos de la cadena entrante relacionados con colas |
| `headers` | cabeceras HTTP adicionales en formato JSON, p. ej. `{"X-Api-Key": "..."}` |
| `secret` | un secreto compartido opcional para firmar el cuerpo de la solicitud (HMAC-SHA256), ver la sección 5 |
| `timeout` | tiempo de espera de un intento de entrega, en segundos (por defecto 5) |
| `retries` | cuántos intentos adicionales hacer tras un fallo (por defecto 1) |
| `payload_template` | una plantilla JSON personalizada para el cuerpo de la solicitud, ver la sección 6. Al crear un webhook nuevo, el formulario de administración rellena automáticamente este campo con un ejemplo completo que contiene todos los placeholders disponibles — puedes eliminar los que no necesites, o vaciar el campo por completo para volver al payload predeterminado integrado |

**Es obligatorio** seleccionar al menos un contexto, tabla de enrutamiento o cola — de lo contrario el formulario no se guardará: esto es lo que determina para qué "escenarios" de llamada se dispara el webhook.

Dos configuraciones se aplican a todos los webhooks a la vez y se definen mediante variables de entorno del servicio (`services/dashboard/env`), no en el panel de administración:

| Variable | Valor por defecto | Descripción |
|--------|-------------------|------|
| `WEBHOOK_SEND_SYSTEM_CHANNELS` | `false` | Un canal que Asterisk crea vía `Dial()`/`Originate()` aún no tiene un `Goto()` a un número real en el momento del `Newchannel` — `exten` es entonces el placeholder de sistema `"s"`. Por defecto, `call.outgoing` (y toda la cadena `outgoing_answered`/`outgoing_ended`) no se envía para ese canal — el CRM no tiene nada significativo que mostrar sin un número. Ponlo en `true` para enviarlos de todos modos. |
| `WEBHOOK_CHANNEL_VARS` | `ULINE` | Una lista separada por comas de nombres de variables de canal de Asterisk que se incluyen en el payload como `channel_vars`. Todo lo que no esté en esta lista se ignora. |

Los cambios en el panel de administración surten efecto **sin reiniciar el servicio**: en cada guardado, Django serializa los webhooks activos en la clave de Redis `webhooks:config`, y `dashboard_listener` vuelve a leer esta clave al iniciar y en cada ciclo de comprobación de salud (cada 30 segundos). Para forzar una sincronización manual de la configuración (p. ej. tras una pérdida de datos de Redis):

```bash
python manage.py sync_webhooks
```

## 3. Formatos de los mensajes (payload)

Todas las solicitudes son `POST` con un cuerpo `application/json`.

### `call.incoming` — inicio de llamada

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "channel_vars": {}
}
```

### `call.answered` — un operador respondió una llamada en cola

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "queue": "support",
  "member_name": "Operador Petrenko",
  "member_interface": "PJSIP/101",
  "member_number": "101",
  "ringtime": "3500",
  "holdtime": "18",
  "timestamp": "2026-07-21T18:58:51.812900",
  "channel_vars": {"ULINE": "42"}
}
```

`ringtime` (milisegundos) y `holdtime` (segundos) provienen directamente del evento AMI de Asterisk `AgentConnect`: cuánto tiempo sonó el teléfono del operador y cuánto tiempo esperó el llamante en la cola antes de ser conectado.

### `call.ended` — fin de la llamada

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
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
  "answered_by_member": "Operador Petrenko",
  "answered_by_interface": "PJSIP/101",
  "recorded": true,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "recording_file": "/var/spool/asterisk/monitor/2026/07/21/x.wav",
  "channel_vars": {"ULINE": "42"}
}
```

`answered_by_member` / `answered_by_interface` se rellenan si llegó un evento `call.answered` para esta llamada antes de que finalizara — de lo contrario ambos campos son `null` (p. ej. la llamada se perdió, o nunca pasó por una cola).

### `call.missed` — llamada perdida en una cola

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

Los campos que no aplican a un evento concreto llegan como `null` (p. ej. `queue` para una llamada clasificada por contexto en lugar de por cola).

### `call.outgoing` — inicio de una llamada saliente

```json
{
  "event": "call.outgoing",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operador Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:51.811673",
  "channel_vars": {}
}
```

### `call.outgoing_answered` — la parte llamada descolgó

```json
{
  "event": "call.outgoing_answered",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operador Petrenko",
  "exten": "380671112233",
  "context": "outbound-users",
  "dest_channel": "PJSIP/trunk1-0000002a",
  "dial_status": "ANSWER",
  "direction": "outbound",
  "timestamp": "2026-08-11T18:58:56.203112",
  "channel_vars": {}
}
```

`dial_status` es el valor del campo AMI `DialStatus` (`ANSWER`, `BUSY`, `NOANSWER`, `CANCEL`, ...). El evento se dispara solo cuando su valor es `ANSWER`, y solo una vez por llamada, incluso si Asterisk prueba varios destinos (p. ej. un troncal de respaldo) antes de que alguien responda.

### `call.outgoing_ended` — fin de una llamada saliente

```json
{
  "event": "call.outgoing_ended",
  "uniqueid": "1753000000.55",
  "linkedid": "1753000000.55",
  "channel": "PJSIP/1001-0000002a",
  "caller_id_num": "1001",
  "caller_id_name": "Operador Petrenko",
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

`answered` es `true` solo si llegó un evento `call.outgoing_answered` antes de que la llamada finalizara; de lo contrario es `false`, y `dial_status` muestra la razón (`BUSY`, `NOANSWER`, `CANCEL`...). Esto permite que el CRM distinga una conexión exitosa de una fallida sin solicitudes adicionales.

## 4. Grabaciones de llamadas: enlaces y descarga vía la API

`recording_url` en cada payload es un enlace **determinista**, construido a partir del `uniqueid` de la llamada. Se puede calcular incluso antes de que la llamada finalice, por lo que ya está presente en `call.incoming` — como una predicción:

- `recording_expected` — una predicción de si la llamada será grabada, tomada del valor de la variable `MIXMONITOR` de Asterisk en el momento del evento. Para llamadas clasificadas por cola, este valor suele conocerse ya (el AGI que decide sobre la grabación se ejecuta antes de `Queue()`). Para llamadas clasificadas solo por contexto, el evento `call.incoming` se dispara antes que ese AGI, por lo que el valor es `null` (desconocido).
- En `call.ended`, el campo `recorded` es el hecho ya confirmado (`true`/`false`, o `null` si la información se perdió, p. ej. por una reconexión de AMI a mitad de la llamada). `recording_url` se rellena solo cuando `recorded: true`.

El propio CRM obtiene el archivo mediante una solicitud independiente a la API REST (no desde el webhook):

```bash
curl -H "Authorization: Token <tu-token>" \
  https://pbx.example.com/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

Detalles del endpoint:

| | |
|---|---|
| Método | `GET /api/v1/recordings/<uniqueid>/` |
| Autenticación | token DRF (`Authorization: Token <clave>`), igual que el resto de la API REST de PearlPBX2 |
| Control de acceso | ninguno adicional — cualquier token de API válido tiene acceso a cualquier grabación (igual que en los demás endpoints de la API) |
| `200` / `206` | el archivo de audio (`audio/wav` o `audio/mpeg`); se admiten solicitudes `Range` para reproducción en streaming |
| `?download=1` | fuerza la descarga del archivo (`Content-Disposition: attachment`) en lugar de una respuesta inline |
| `401` | no se envió ningún token, o no es válido |
| `404` | aún no hay grabación (la llamada no se grabó, o el archivo todavía no ha aparecido en el disco) |

El token se emite igual que para el resto de la API — a través del admin de Django (`Auth Token`) o con:

```bash
python manage.py drf_create_token <username>
```

> Para personas (no CRMs) que escuchan desde el navegador, la interfaz web de PearlPBX2 ofrece un enlace separado, autenticado por sesión, en `/reports/audio/uid/{uniqueid}/` — es el mismo archivo, solo cambia el método de autenticación.

## 5. Verificación de la firma de la solicitud

Si un webhook tiene el campo `secret` rellenado, cada solicitud lleva además esta cabecera:

```
X-PearlPBX-Signature: sha256=<firma HMAC-SHA256 en hex del cuerpo crudo de la solicitud>
```

Ejemplo de verificación de la firma (Python):

```python
import hashlib
import hmac

def verify(secret: str, body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)
```

Ejemplo en Node.js:

```javascript
const crypto = require("crypto");

function verify(secret, rawBody, headerValue) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}
```

**Importante:** la firma se calcula sobre los bytes crudos del cuerpo de la solicitud — verifícala antes de hacer cualquier parseo de JSON.

## 6. Plantilla personalizada del cuerpo de la solicitud

Por defecto se envía el payload estándar (ver la sección 3). Si tu CRM espera un formato de campos distinto, puedes definir tu propio objeto JSON en el campo `payload_template`. Los valores de cadena pueden contener placeholders `${nombre_variable}`:

Al crear un webhook nuevo en el panel de administración, el campo **Payload template** viene ya rellenado — con un ejemplo completo que contiene todos los placeholders disponibles (uno por cada campo). Esto es deliberado, para que puedas ver de un vistazo todo el conjunto de opciones en lugar de tener que consultar la documentación. Simplemente elimina las líneas que no necesites, o deja todo tal cual — para los campos que no aplican a un evento concreto (p. ej. `${ringtime}` en `call.incoming`), el sistema sustituye una cadena vacía, en lugar de mostrar el texto literal del placeholder. Si no necesitas un formato personalizado en absoluto, vacía el campo por completo (vacío/`null`), y se enviará el payload estándar descrito en la sección 3.

```json
{
  "call_id": "${uniqueid}",
  "from": "${caller_id_num}",
  "direction": "${direction}",
  "recording": "${recording_url}"
}
```

Placeholders disponibles: `event`, `uniqueid`, `linkedid`, `channel`, `caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`, `duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`, `recording_expected`, `recording_url`, `recording_file`, `missed`, `wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`, `holdtime`, `answered_by_member`, `answered_by_interface`, `direction`, `dest_channel`, `dial_status`, `answered`, `channel_vars`.

Usar un placeholder desconocido provoca un error de validación del formulario — el panel de administración no te dejará guardar esa plantilla. Si el campo se deja vacío, se envía el payload estándar para cada evento.

**`linkedid`** — el propio mecanismo de correlación de Asterisk: todos los canales de una misma llamada lógica (p. ej. las dos piernas de una llamada interna) comparten el mismo `linkedid`, igual al `uniqueid` del canal que inició la llamada. Es este campo — y no la proximidad de `uniqueid`/`timestamp` entre dos eventos distintos — el que debe usarse para correlacionar varias entregas de webhook en una sola llamada dentro del CRM.

**`channel_vars`** — un objeto con las variables de canal de Asterisk permitidas por `WEBHOOK_CHANNEL_VARS` (ver la sección 2), p. ej. `{"ULINE": "42"}`. En la plantilla, `${channel_vars}` como único contenido de un campo de cadena se sustituye como un objeto JSON anidado; dentro de una cadena más larga (`"vars: ${channel_vars}"`) se sustituye como una representación de texto. El campo siempre está presente (un objeto vacío `{}` si todavía no hay variables).

## 7. Comportamiento ante fallos de entrega

La entrega de webhooks es "best-effort" (mejor esfuerzo), sin garantía de "exactamente una vez" y sin cola de reintentos:

- la solicitud se ejecuta de forma asíncrona y nunca bloquea el procesamiento de la llamada — incluso si el servidor del CRM no está disponible o responde lentamente, esto no afectará al funcionamiento de Asterisk ni del dashboard;
- cada intento está limitado por el `timeout` configurado en el webhook;
- en caso de fallo, se realizan hasta `retries` intentos adicionales con una pequeña pausa entre ellos;
- si todos los intentos fallan, el evento simplemente se registra en el servidor y no se vuelve a intentar.

Por ello se recomienda que el endpoint receptor del CRM:
- responda rápido (en un par de segundos) — un procesamiento lento en el lado del CRM aumenta el riesgo de timeout;
- sea idempotente por `uniqueid` — por si el propio sistema CRM reintenta el procesamiento de solicitudes entrantes.

## 8. Ejemplo: un manejador mínimo de webhooks

Un ejemplo simplificado en Python (Flask) — acepta eventos de ambas cadenas, verifica la firma y, si es necesario, obtiene la grabación de la llamada:

```python
import hashlib
import hmac
import os

import requests
from flask import Flask, request, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ["PEARLPBX_WEBHOOK_SECRET"]
API_TOKEN = os.environ["PEARLPBX_API_TOKEN"]


def verify_signature(body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_value)


@app.post("/pearlpbx/webhook")
def handle_webhook():
    raw_body = request.get_data()
    if not verify_signature(raw_body, request.headers.get("X-PearlPBX-Signature")):
        abort(401)

    payload = request.get_json()
    event = payload["event"]

    if event == "call.incoming":
        create_or_update_call_card(payload)
    elif event == "call.answered":
        mark_call_card_answered(payload["uniqueid"], payload["member_name"])
    elif event == "call.missed":
        create_missed_call_task(payload)
    elif event in ("call.ended", "call.outgoing_ended"):
        close_call_card(payload)
        if payload.get("recorded"):
            fetch_recording(payload["uniqueid"], payload["recording_url"])
    elif event == "call.outgoing":
        create_or_update_call_card(payload)
    elif event == "call.outgoing_answered":
        mark_call_card_answered(payload["uniqueid"], payload["caller_id_name"])

    return "", 200


def fetch_recording(uniqueid: str, recording_url: str) -> None:
    response = requests.get(
        recording_url,
        headers={"Authorization": f"Token {API_TOKEN}"},
        timeout=10,
    )
    response.raise_for_status()
    with open(f"/data/recordings/{uniqueid}.wav", "wb") as f:
        f.write(response.content)
```

---

Documentación relacionada:
- [API.md](API.md) — referencia completa de la API REST de PearlPBX2
- [services/dashboard/README.md](../../services/dashboard/README.md) — detalles técnicos del funcionamiento del servicio dashboard y el formato de eventos de Redis
