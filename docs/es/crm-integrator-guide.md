*Also available in: [English](../en/crm-integrator-guide.md) | [Українська](../ua/crm-integrator-guide.md) | [Español](crm-integrator-guide.md)*

# Integración de un sistema CRM con PearlPBX2: guía técnica

**Versión:** 2.7.2

---

Este documento describe el procedimiento para integrar un sistema CRM externo con la plataforma PearlPBX2. Está pensado para desarrolladores sin experiencia previa con sistemas de telefonía, y contiene todo lo necesario para implementar la integración: el modelo de eventos, el formato de los datos transmitidos, una descripción completa de la API REST (incluida la iniciación de llamadas salientes), el mecanismo para obtener grabaciones de llamadas y los requisitos para verificar la autenticidad de las solicitudes.

Trabajar con este documento solo requiere conocimientos básicos de implementación de manejadores HTTP (endpoints de webhook) y de realizar solicitudes autenticadas a una API REST. No se requiere conocimiento adicional del dominio de la telefonía.

Este documento es una fuente de información autosuficiente: todo lo necesario para implementar la integración se detalla a continuación, sin necesidad de consultar fuentes adicionales.

---

## Contenido

1. [Esquema general de interacción](#1-esquema-general-de-interacción)
2. [Terminología](#2-terminología)
3. [Reparto de responsabilidades](#3-reparto-de-responsabilidades)
4. [Ciclo de vida de una llamada](#4-ciclo-de-vida-de-una-llamada)
5. [Descripción de los eventos y sus campos](#5-descripción-de-los-eventos-y-sus-campos)
6. [Obtención de la grabación de una llamada](#6-obtención-de-la-grabación-de-una-llamada)
7. [API REST de PearlPBX2](#7-api-rest-de-pearlpbx2)
8. [Dashboard API y WebSocket: canal en tiempo real (opcional)](#8-dashboard-api-y-websocket-canal-en-tiempo-real-opcional)
9. [Verificación de la autenticidad de las solicitudes](#9-verificación-de-la-autenticidad-de-las-solicitudes)
10. [Configuración de un formato JSON personalizado](#10-configuración-de-un-formato-json-personalizado)
11. [Comportamiento del sistema ante fallos de entrega](#11-comportamiento-del-sistema-ante-fallos-de-entrega)
12. [Ejemplo de implementación de un servidor receptor](#12-ejemplo-de-implementación-de-un-servidor-receptor)
13. [Preguntas frecuentes](#13-preguntas-frecuentes)
14. [Lista de verificación de la integración](#14-lista-de-verificación-de-la-integración)

---

## 1. Esquema general de interacción

PearlPBX2 es un sistema de gestión de telefonía empresarial: recibe llamadas entrantes, las distribuye entre operadores mediante colas de servicio y graba las conversaciones. A efectos de integración, un sistema CRM necesita tres datos: el momento en que empieza una llamada, el momento en que termina, y la ubicación de su grabación (si la llamada se grabó).

La integración se basa en dos mecanismos:

- **Webhooks** — el propio PearlPBX2 envía un mensaje a la URL indicada por el sistema CRM en el momento en que ocurre un evento (inicio de llamada, fin de llamada, llamada perdida en una cola). La solicitud es un `POST` con cuerpo JSON. No es necesario que el CRM inicie ninguna solicitud — basta con aceptar solicitudes entrantes en un endpoint definido.
- **API REST** — el archivo de audio de la grabación no se envía directamente por el webhook, dado su tamaño. En su lugar, el webhook contiene un enlace a él. El archivo se obtiene con una solicitud independiente a la API usando un token de acceso.

Las secciones siguientes describen cada mecanismo en detalle.

## 2. Terminología

- **Llamada (call)** — una llamada telefónica desde que llega hasta que finaliza.
- **uniqueid** — un identificador único de **un solo** canal de Asterisk, p. ej.: `1753000000.42`. No es un número de teléfono ni un identificador de cliente. Se asigna en el momento en que se crea el canal. Es la clave para correlacionar eventos de la misma cadena (`call.incoming` → `call.answered`/`call.missed` → `call.ended`, o `call.outgoing` → `call.outgoing_answered` → `call.outgoing_ended`) — todos ellos se refieren al mismo canal y llevan el mismo `uniqueid`.
- **linkedid** — un identificador compartido por **todos los canales de una misma llamada lógica** (p. ej. las dos piernas de una llamada interna entre dos empleados — cada pierna tiene su propio `uniqueid`, pero el mismo `linkedid`, igual al `uniqueid` del canal que inició la llamada). Si el CRM necesita combinar varios eventos de webhook independientes (p. ej. dos `call.outgoing` de dos usuarios SIP distintos) en un único registro de llamada, debe comparar `linkedid`, no confiar en la proximidad de `uniqueid`/`timestamp`.
- **Caller ID** — el número (y, si está disponible, el nombre) de quien realiza la llamada. Se transmite en los campos `caller_id_num` / `caller_id_name`.
- **Contexto (context) y extensión (exten)** — parámetros de enrutamiento interno de la PBX que determinan la dirección y el punto final de la llamada. Para efectos de integración con el CRM, generalmente basta con saber que estos campos existen, sin entrar en la lógica del plan de marcado.
- **Cola (queue)** — si la empresa distribuye las llamadas entre varios operadores, la llamada entra primero en una cola de servicio, desde la cual se asigna a un operador libre. Si la llamada se realiza directamente, sin pasar por una cola, el campo `queue` tendrá el valor `null`.
- **Grabación de la llamada (recording)** — el archivo de audio de la llamada, siempre que la función de grabación esté habilitada en la configuración de esa PBX en particular (no siempre se aplica, ni a todas las llamadas).
- **Causa de finalización (hangup cause)** — un código y una descripción textual del motivo por el que finalizó la llamada (finalización normal, línea ocupada, sin respuesta, etc.). Se usa principalmente con fines analíticos.
- **Usuario SIP** — la extensión interna de un empleado (un teléfono, un softphone) registrada en la PBX. Cuando ese empleado inicia una llamada por sí mismo, esto genera eventos de la cadena saliente (`call.outgoing`, sección 5.5).
- **Troncal (trunk)** — la conexión de la PBX con un proveedor de telefonía externo, a través de la cual llegan las llamadas de los clientes y salen las llamadas hacia números normales. Las llamadas que llegan a través de un troncal siempre pertenecen a la cadena entrante (`call.incoming`), aunque técnicamente sea una llamada saliente desde el punto de vista del proveedor — lo que importa para la integración con el CRM es quién inicia la llamada dentro de la PBX (un empleado o un llamante externo), no la dirección física de la señal en la línea.

## 3. Reparto de responsabilidades

- **El administrador de PearlPBX2** crea la configuración del webhook en el panel de administración de la PBX: especifica la URL del servidor CRM, la lista de eventos a enviar y, si es necesario, una clave secreta para firmar las solicitudes. Esta acción se realiza enteramente en el lado de la PBX; el desarrollador del CRM solo necesita proporcionar la URL y, si es necesario, acordar la clave secreta.
- **El desarrollador del CRM** implementa un endpoint HTTP para recibir solicitudes `POST` con cuerpo JSON y, si es necesario, realiza solicitudes a la API de PearlPBX2 para obtener los archivos de grabación — para esto se emite un token de acceso separado.

Así, la interacción ocurre en dos direcciones: entrante (webhooks que llegan desde la PBX) y saliente (solicitudes del CRM a la API para obtener grabaciones).

## 4. Ciclo de vida de una llamada

Repasemos la secuencia de eventos con el ejemplo de una llamada. Un cliente llama a la línea de soporte de la empresa.

**Paso 1.** La llamada llega al sistema. Si cumple los criterios definidos por el administrador (una dirección entrante o cola determinada), se envía un evento `call.incoming` al servidor CRM. El mensaje contiene el `uniqueid`, el número del llamante y una predicción preliminar de si la llamada será grabada (detalles en la sección 6).

En este momento, el sistema CRM normalmente muestra una tarjeta de la llamada en curso — por ejemplo, una notificación emergente para el operador, o un borrador de registro en el historial de interacción con el cliente.

**Paso 2.** La llamada entra en una cola de servicio, y el llamante espera a ser conectado con un operador. Son posibles dos desenlaces.

Opción A: **un operador contesta la llamada.** Se envía un evento `call.answered`, que contiene el nombre del operador, su extensión, cuánto tiempo sonó antes de contestar y cuánto tiempo esperó el llamante en la cola. Este evento está pensado para mostrar la tarjeta del cliente al operador en el momento de la conexión.

Opción B: **el llamante cuelga sin que nadie conteste.** Se envía un evento `call.missed` (llamada perdida). Este evento llega independientemente de si el sistema CRM está suscrito a `call.incoming` — una llamada perdida se considera un evento significativo por sí mismo.

**Paso 3.** Al finalizar la conversación (independientemente de si ocurrió de inmediato o tras el paso 2A), se envía un evento `call.ended`. Contiene la duración de la conversación, el motivo de la finalización, datos del operador que atendió la llamada (si ocurrió un evento `call.answered`) y un enlace a la grabación de audio, si la llamada se grabó.

**Una regla clave:** el evento `call.ended` se envía exclusivamente para llamadas sobre las que se envió previamente un `call.incoming`. El sistema rastrea este estado internamente, por lo que es imposible recibir un evento de finalización sin un evento de inicio previo, así como enviar dos veces el evento de finalización para la misma llamada. Los eventos `call.missed` y `call.answered`, en cambio, son independientes y llegan sin importar la suscripción a `call.incoming`.

La cadena descrita arriba (`call.incoming` → `call.answered`/`call.missed` → `call.ended`) se aplica a las llamadas que **llegan** a la empresa. Para las llamadas que **inicia** un empleado (p. ej. un operador devolviendo la llamada a un cliente), existe una cadena de eventos separada y totalmente independiente.

**Paso 1' (llamada saliente).** Un empleado descuelga y marca un número. Se envía un evento `call.outgoing` al servidor CRM — el equivalente de `call.incoming`, pero para una llamada iniciada desde dentro de la PBX.

**Paso 2' (llamada saliente).** Si la parte llamada descuelga, se envía un evento `call.outgoing_answered` con la hora de la respuesta. Si la línea está ocupada, nadie contesta, o la llamada se cancela — este evento nunca se envía.

**Paso 3' (llamada saliente).** Al finalizar la llamada (haya sido contestada o no), se envía un evento `call.outgoing_ended`. Contiene un campo `answered` que indica directamente si la llamada se conectó, para que el CRM no tenga que adivinar el resultado a partir del código de causa de finalización.

Estas dos secuencias de eventos — entrante y saliente — siempre llegan por separado una de otra, con nombres de evento distintos (`call.ended` frente a `call.outgoing_ended`), incluso si en el panel de administración solo hay configurado un único webhook suscrito a ambas cadenas a la vez. El identificador `uniqueid` permite rastrear todos los eventos de una misma llamada, sin importar a qué cadena pertenezca.

La sección 5 contiene una descripción detallada de cada uno de los siete eventos.

## 5. Descripción de los eventos y sus campos

Todas las solicitudes son `POST` con cuerpo en formato `application/json`. El tipo de evento lo determina el valor del campo `event`.

### 5.1. `call.incoming` — inicio de llamada

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Juan Pérez",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "channel_vars": {}
}
```

Detalles de los campos:
- `queue` tendrá el valor `null` si la llamada se clasificó por dirección (context) y no por cola. Si la llamada llegó a través de una cola, aquí aparecerá su nombre, p. ej. `"support"`.
- El campo `recording_url` ya está presente en esta etapa, antes de que el archivo de grabación exista realmente. Esto no es un error: el enlace se construye de forma determinista a partir del `uniqueid` de antemano (detalles en la sección 6). El archivo en ese enlace estará disponible más adelante, siempre que la llamada termine grabándose.
- `recording_expected` — una estimación preliminar de la probabilidad de grabación. En algunos casos el sistema ya tiene una respuesta definida (`true`/`false`); en otros, el valor es `null`, lo cual refleja un estado intermedio de incertidumbre, no un error.

### 5.2. `call.answered` — un operador contestó la llamada

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Juan Pérez",
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

Descripción de los campos:
- `member_name` — el nombre del operador, configurado en PearlPBX2 para ese miembro de la cola.
- `member_interface` — el identificador técnico del operador en Asterisk, p. ej. `PJSIP/101`.
- `member_number` — el mismo valor de forma simplificada (`101`); normalmente más práctico para buscar al operador en el sistema CRM.
- `ringtime` — cuánto tiempo sonó el dispositivo del operador antes de contestar, en milisegundos.
- `holdtime` — cuánto tiempo esperó el cliente en la cola antes de ser atendido, en segundos (conceptualmente equivalente al campo `wait_time` de una llamada perdida, pero para una conexión exitosa).

Este evento se genera exclusivamente para llamadas que pasaron por una cola de servicio; una conexión directa fuera de una cola nunca lo dispara.

### 5.3. `call.missed` — llamada perdida en una cola

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

El cliente esperó en la cola `support` durante `wait_time` segundos (21 segundos en este ejemplo) y colgó antes de que un operador contestara. Este evento está pensado, entre otras cosas, para crear automáticamente una tarea de devolución de llamada en el sistema CRM.

### 5.4. `call.ended` — fin de la llamada

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
  "linkedid": "1753000000.42",
  "channel": "PJSIP/trunk1-0000001a",
  "caller_id_num": "380501234567",
  "caller_id_name": "Juan Pérez",
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

Este evento lleva la mayor cantidad de datos. Campos principales:
- `duration` — la duración total de la llamada en segundos, desde el inicio hasta el final.
- `cause_txt` — una descripción textual del motivo de finalización. El valor `"Normal Clearing"` corresponde a una finalización normal de la conversación. Valores como `"Busy"` o `"No Answer"` también son resultados válidos, no una señal de error del sistema.
- `missed` — `true` si esta llamada ya había sido registrada como perdida (ocurrió un evento `call.missed`).
- `answered_by_member` / `answered_by_interface` — el nombre y la interfaz del operador que atendió la llamada, siempre que haya ocurrido un evento `call.answered` antes. El sistema correlaciona los datos entre eventos automáticamente. Si la llamada quedó sin respuesta (p. ej. perdida), ambos campos son `null`.
- `recorded` — el hecho ya confirmado de que la llamada se grabó (a diferencia de la estimación previa `recording_expected`). Valores posibles: `true`, `false`, ocasionalmente `null` (si no fue posible determinar el hecho de la grabación por razones técnicas).
- `recording_url` — un enlace al archivo de grabación, siempre que `recorded: true`. Si no hay grabación, este valor es `null`, y no tiene sentido solicitar este enlace.
- `recording_file` — la ruta al archivo de grabación en el sistema de archivos de la PBX, mostrado en el ejemplo anterior con un valor `.wav`, ya que es el formato en el que Asterisk crea la grabación justo después de que la llamada finaliza. Este campo refleja la ruta interna en el momento en que se generó el evento y no está pensado para que lo use el sistema CRM: el archivo puede convertirse automáticamente a `.mp3` más adelante, según un programa en el lado de la PBX (detalles en la sección 6). Para obtener la grabación de audio solo debe usarse `recording_url`.

Nota: no todos los campos están necesariamente rellenados para cada llamada — por ejemplo, `queue` a menudo tendrá el valor `null` para llamadas directas. Se recomienda diseñar el manejo de eventos teniendo en cuenta posibles valores `null`.

### 5.5. `call.outgoing` — inicio de una llamada saliente

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

Detalles de los campos:
- `caller_id_num` / `caller_id_name` aquí son el número y el nombre del **empleado** que inicia la llamada, no del cliente (a diferencia de `call.incoming`, donde estos campos pertenecen al llamante).
- `exten` — el número que marcó el empleado (el número del cliente).
- `direction` — siempre `"outbound"` para este evento; el campo está presente en todos los eventos de ambas cadenas y permite determinar con una sola comprobación a cuál pertenece un evento, sin analizar el propio nombre de `event`.
- Este evento solo se envía cuando la llamada la inicia un usuario SIP interno (un empleado), no un troncal (una conexión con un proveedor de telefonía). Las llamadas que llegan desde fuera a través de un troncal siempre pasan por `call.incoming`, nunca por `call.outgoing`.
- Por defecto, la PBX tampoco envía `call.outgoing` para un canal interno que Asterisk acaba de crear (vía `Dial()`/`Originate()`) pero que aún no se ha conectado a un número concreto — en ese momento `exten` es igual al placeholder de sistema `"s"`, no un número real, y no tiene sentido mostrar ese evento al CRM. Si este comportamiento necesita cambiarse, consúltalo con el administrador de la PBX (la configuración `WEBHOOK_SEND_SYSTEM_CHANNELS`).

### 5.6. `call.outgoing_answered` — la parte llamada descolgó

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

Descripción de los campos:
- `dest_channel` — el identificador técnico de la ruta por la que salió la llamada (p. ej. un troncal concreto). Este campo es informativo; para la mayoría de las integraciones con CRM, basta con `exten` para saber a quién se llamó.
- `dial_status` — el valor del campo AMI `DialStatus` de Asterisk en el momento de la respuesta, aquí siempre `"ANSWER"` (los valores para otros resultados se describen en la sección 5.7).

Este evento solo llega si la llamada fue contestada. Si la línea estaba ocupada, nadie contestó, o la llamada se canceló antes de ser contestada — este evento nunca se envía, y la secuencia pasa directamente a `call.outgoing_ended`.

### 5.7. `call.outgoing_ended` — fin de una llamada saliente

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

Este evento repite estructuralmente a `call.ended` (sección 5.4) — los mismos campos `duration`, `cause`, `cause_txt`, `recorded`/`recording_url`/`recording_file` para la grabación, si está habilitada también para llamadas salientes. Además tiene dos campos específicos de la cadena saliente:
- `answered` — un valor booleano: `true` si antes de este evento llegó un `call.outgoing_answered`, `false` en caso contrario. Esta es la forma más simple de determinar el resultado de la llamada sin analizar el código de causa de finalización.
- `dial_status` — el último valor conocido de `DialStatus`: `"ANSWER"` en caso de conexión exitosa, o `"BUSY"` / `"NOANSWER"` / `"CANCEL"`, etc. en caso de intento fallido.

Los campos `answered_by_member` / `answered_by_interface` aquí siempre son `null` — corresponden exclusivamente al operador de una cola en la cadena entrante (sección 5.4) y no tienen significado para una llamada iniciada directamente por un empleado.

## 6. Obtención de la grabación de una llamada

**El archivo de grabación no se envía junto con el webhook.** Dado el volumen de los datos de audio, el webhook solo contiene un enlace al archivo, al cual el sistema CRM puede acceder con una solicitud independiente en el momento en que realmente lo necesite (p. ej. al abrir la tarjeta de una llamada para escucharla).

El enlace se construye de forma determinista a partir del `uniqueid`, por lo que ya está presente en el primer evento `call.incoming`, mucho antes de que la llamada finalice y el archivo aparezca realmente en el disco.

**Nota importante sobre el formato del archivo.** En el lado de la PBX, las grabaciones se crean primero en formato WAV, y luego, según un programa (una tarea periódica en segundo plano), se convierten a MP3, tras lo cual se elimina el archivo WAV original. Por lo tanto, en el momento en que el sistema CRM solicita la grabación, el formato real del archivo no se conoce de antemano y depende de si la tarea de conversión ya se ha ejecutado. El endpoint tiene esto en cuenta automáticamente: el servidor determina por sí mismo qué archivo existe en el disco (`.mp3` o `.wav`) y devuelve las cabeceras `Content-Type` (`audio/mpeg` o `audio/wav`) y `Content-Disposition` correspondientes, con un nombre de archivo que lleva la extensión real. El sistema CRM no debe (y se recomienda que no lo haga) asumir una extensión fija — una implementación correcta debe determinar el formato del archivo recibido a partir de la cabecera `Content-Type` de la respuesta, no de la URL ni de un nombre de archivo predefinido.

Para obtener el archivo, realiza una solicitud `GET` con una cabecera de autorización:

```bash
curl -H "Authorization: Token TU_TOKEN" \
  https://pbx.example.com/api/v1/recordings/1753000000.42/ \
  -o call_recording
```

El token lo emite el administrador de la PBX una sola vez, de forma análoga a las claves de API de otros servicios, y debe guardarse con el mismo nivel de protección que una contraseña.

Posibles respuestas del servidor:

| Código de respuesta | Significado |
|---|---|
| `200` o `206` con el archivo de audio | la solicitud se completó correctamente; `206` se devuelve al solicitar una parte del archivo (avance/streaming) |
| `401` | falta el token o no es válido — comprueba la cabecera de la solicitud |
| `404` | no hay grabación disponible (la llamada no se grabó, o el archivo aún no ha terminado de aparecer en el disco) |

Si la solicitud se hace justo después de `call.ended` y devuelve `404`, esto no significa necesariamente un error: la escritura del archivo en disco puede tener un pequeño retraso respecto al envío del mensaje JSON. En ese caso, se recomienda reintentar la solicitud a los pocos segundos.

Para forzar la descarga del archivo en el navegador (en lugar de reproducirlo), añade el parámetro `?download=1` a la URL.

## 7. API REST de PearlPBX2

Además de recibir webhooks, el sistema CRM puede llamar directamente a la API REST de PearlPBX2 — en particular para iniciar llamadas salientes, unir a varios participantes en una sola conferencia y (si es necesario) trabajar con listas de números. Todos los endpoints están bajo el prefijo `/api/v1/` y requieren autenticación.

### 7.1. Autenticación

La API usa autenticación por token. El token se envía en la cabecera `Authorization` de cada solicitud:

```
Authorization: Token TU_TOKEN
```

El token lo emite el administrador de la PBX de forma independiente del token usado para obtener grabaciones de llamadas (sección 6) — conviene consultar con el administrador si se usa un token compartido o si se emite uno distinto para cada propósito. Una solicitud sin token, o con un token inválido, devuelve `401 Unauthorized`.

### 7.2. Documentación interactiva (Swagger / ReDoc)

Además de este documento, PearlPBX2 genera automáticamente una especificación de API legible por máquina (basada en `drf-spectacular`) y ofrece dos interfaces web ya preparadas para ella. Esto es útil tanto como referencia con una lista de campos actualizada, como herramienta para probar solicitudes manualmente sin escribir código:

- `GET /api/v1/schema/` — la propia especificación OpenAPI, en formato JSON/YAML. Adecuada para importar en Postman, Insomnia, o para generar automáticamente código de cliente (un SDK) en tu lenguaje de programación.
- `GET /api/v1/docs/` — la interfaz interactiva **Swagger UI**. Permite ver todos los endpoints, sus parámetros y ejemplos de respuesta, y ejecutar solicitudes de prueba directamente desde el navegador mediante el botón "Try it out".
- `GET /api/v1/redoc/` — los mismos datos, presentados como una página de referencia estática y fácil de leer (**ReDoc**), sin posibilidad de ejecutar solicitudes.

**Una nota importante sobre el acceso.** Estas páginas no están exentas del requisito general de autenticación — al igual que el resto de la API, están protegidas por autenticación por token (ver la sección 7.1), no por autenticación de sesión de Django. Esto significa que simplemente abrir `/api/v1/docs/` en un navegador sin más acciones devolverá `401 Unauthorized`, ya que el navegador no añade la cabecera `Authorization` automáticamente. Para usar el Swagger UI, necesitas un plugin o extensión del navegador que permita añadir una cabecera `Authorization: Token TU_TOKEN` a las solicitudes de la página, o puedes ver la especificación mediante una herramienta como Postman/Insomnia, donde el token se puede indicar en la configuración de la solicitud. Para una comprobación puntual de la especificación sin navegador, basta con una solicitud normal con token:

```bash
curl -H "Authorization: Token TU_TOKEN" https://pbx.example.com/api/v1/schema/
```

Se recomienda consultar estas fuentes ante cualquier duda sobre la versión actual de la API — se generan directamente a partir del código del servidor y siempre reflejan su estado actual.

### 7.3. Iniciación de una llamada saliente

**`POST /api/v1/calls/originate/`**

Este endpoint pone en cola una llamada saliente para su ejecución a través del Asterisk Manager Interface (AMI). Un caso de uso típico desde el lado del CRM es una llamada "en dos pasos" (click-to-call): primero se llama a la extensión interna del operador (`channel`), y solo después de que el operador descuelga, la PBX lo conecta con el número del cliente (`exten`).

**Campos del cuerpo de la solicitud:**

| Campo | Tipo | Obligatorio | Valor por defecto | Descripción |
|---|---|---|---|---|
| `channel` | cadena (hasta 256 caracteres) | Sí | — | El canal al que llama primero la PBX, p. ej. `Local/0503856087@default` o `PJSIP/0504139380@mega-provider`. |
| `exten` | cadena (hasta 128 caracteres) | Sí | — | La extensión o número al que se conecta el canal `channel` tras contestar, p. ej. `0675653380`. |
| `context` | cadena (hasta 128 caracteres) | No | `"default"` | El contexto del plan de marcado en el que se realiza la conexión a `exten` (explicación detallada más abajo). |
| `priority` | entero | No | `1` | La prioridad del plan de marcado (valor mínimo `1`). |
| `callerid` | cadena (hasta 128 caracteres) | No | — | El Caller ID que verá la parte llamada, en formato `nombre<número>`, p. ej. `380443333333<0675653380>`. |
| `variable` | objeto (pares cadena → cadena) | No | — | Variables de canal de Asterisk arbitrarias, p. ej. `{"userId": "0"}`. |
| `timeout_ms` | entero | No | `30000` | El tiempo máximo de espera de respuesta a la llamada, en milisegundos (de `1000` a `120000`). |

**Qué significa `context` en esta solicitud.** El valor `"default"` de la tabla anterior es solo un ejemplo de relleno, no una constante del sistema. En realidad, `context` es el nombre de una tabla de enrutamiento (`RoutingTable`) o de un contexto del plan de marcado (`DialplanContext`) configurado por el administrador de PearlPBX2 específicamente para esa instalación, en el panel de administración. Estos nombres de contexto son arbitrarios (p. ej. `Incoming`, `Outgoing`, `internal-users`) y no siguen ninguna convención universal — cada instalación de la PBX puede tener su propio conjunto de nombres según cuántos proveedores, troncales y escenarios de enrutamiento estén configurados. **Antes de implementar la integración, asegúrate de consultar con el administrador de la PBX los nombres exactos de los contextos que debes usar para tus escenarios, y pídele ejemplos de solicitud `channel`/`exten`/`context` ya preparados específicamente para tu instalación** — no es posible adivinar estos valores por tu cuenta.

**Ejemplo 1: una llamada "en dos pasos" (click-to-call) a través de un operador interno.**

Primero la PBX llama a la extensión interna del operador (`channel`), y solo después de que el operador descuelga lo conecta con el número del cliente (`exten`):

```bash
curl -X POST https://pbx.example.com/api/v1/calls/originate/ \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "Local/0503856087@default",
    "exten": "0675653380",
    "context": "default",
    "callerid": "380443333333<0675653380>",
    "variable": {"userId": "0"}
  }'
```

**Ejemplo 2: una llamada directa a través de un troncal de proveedor concreto, sin canal Local.**

En algunos escenarios no hace falta ningún canal Local: `channel` puede apuntar directamente a un canal real del proveedor, y `exten`/`context`/`priority` es el punto del plan de marcado donde Asterisk hará aterrizar ese canal justo después de que el proveedor conteste la llamada. Este es el comportamiento estándar del comando AMI `Originate` — un canal Local solo se necesita cuando el primer "paso" es en sí mismo una extensión interna (como en el ejemplo 1), no cuando `channel` ya es el canal final de la llamada.

Por ejemplo: necesitas llamar directamente al número `0504139380` a través del troncal del proveedor `mega-provider`, y dirigir el resultado (una vez contestado) a la extensión interna `222` en la tabla de enrutamiento `Incoming`, con CallerID `0442222222`:

```bash
curl -X POST https://pbx.example.com/api/v1/calls/originate/ \
  -H "Authorization: Token TU_TOKEN" \
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

Aquí `PJSIP/0504139380@mega-provider` significa "marcar el número `0504139380` a través del troncal SIP (peer) llamado `mega-provider`"; `mega-provider` e `Incoming` son nombres que deben existir realmente en esa instalación concreta de la PBX (acordados con el administrador, como se describió arriba).

**Nota importante sobre `callerid` en el escenario de llamada directa a un troncal.** A diferencia del click-to-call a través de una extensión interna (ejemplo 1), donde el CallerID suele ser solo informativo y puede ser sobrescrito por la lógica predeterminada del plan de marcado, en el escenario de llamada directa a un troncal (ejemplo 2) el valor de `callerid` **se transmite realmente al proveedor/la red** como el número desde el que supuestamente se origina la llamada. Este no es un campo cosmético: si el número indicado no pertenece a tu pool de números, o el proveedor no permite sustituirlo, la llamada puede ser rechazada por el operador de telecomunicaciones, marcada como spam/sospechosa, o, según la legislación y la política del proveedor, esto podría considerarse suplantación de identidad de llamante (CLI spoofing). Antes de usar este escenario, asegúrate de consultar con el administrador de la PBX y con el proveedor qué números están permitidos como CallerID para un troncal concreto.

**Respuesta exitosa (`200 OK`):**

```json
{
  "status": "originated",
  "message": "Originate successfully queued"
}
```

Importante: un estado `200` y `"status": "originated"` solo significan que el comando para establecer la conexión fue aceptado y pasado a AMI. Esto no es confirmación de que la llamada realmente ocurriera o de que el llamado contestara — el sistema CRM obtiene esa información por separado mediante webhooks (`call.answered`, `call.ended`), correlacionados por el `uniqueid` de la llamada resultante del `originate`.

**Posibles errores:**

| Código | Cuerpo de la respuesta | Motivo |
|---|---|---|
| `400 Bad Request` | `{"channel": ["This field is required."]}` (ejemplo para el campo `channel`; análogo para cualquier otro campo obligatorio) | No se rellenó un campo obligatorio, o se incumplió una restricción (p. ej. `timeout_ms` fuera del rango `1000`–`120000`). |
| `401 Unauthorized` | `{"detail": "Authentication credentials were not provided."}` | Falta el token de autenticación, o no es válido. |
| `502 Bad Gateway` | `{"detail": "AMI unavailable."}` | La PBX no pudo establecer o mantener la conexión con el Asterisk Manager Interface. |
| `502 Bad Gateway` | `{"detail": "AMI originate timed out."}` | No llegó respuesta de AMI dentro de `timeout_ms` (más un margen de servicio). |
| `502 Bad Gateway` | `{"detail": "Extension does not exist"}` (ejemplo; el texto corresponde al mensaje de AMI) | AMI devolvió un error al ejecutar el comando `Originate` — el texto del mensaje proviene directamente de la respuesta de Asterisk y puede variar según el motivo del fallo. |
| `503 Service Unavailable` | `{"detail": "Asterisk is disabled in this DEVMODE."}` | La PBX funciona en modo de desarrollo sin conexión a un Asterisk real (solo en bancos de pruebas, no ocurre en producción). |

Este endpoint no tiene límites de frecuencia de solicitudes propios (rate limiting) — el límite práctico lo determina la capacidad de la propia línea/troncales de la PBX, por lo que se recomienda que el sistema CRM controle por su cuenta la intensidad de iniciación de llamadas, según lo acordado con el administrador de la PBX.

### 7.4. Iniciación de una conferencia (tres o más participantes)

**`POST /api/v1/calls/conference/`**

El endpoint `calls/originate/` (sección 7.3) siempre conecta exactamente a dos participantes. Si necesitas reunir a tres o más personas en una misma conversación a la vez (p. ej. Operador, Cliente y Conductor), usa `calls/conference/`: el endpoint acepta una lista de canales y hace que cada uno entre en una sala de conferencia compartida basada en `ConfBridge`.

**El modelo de conferencia.** Las salas no necesitan crearse de antemano: una sala surge en el momento en que entra el primer canal, y desaparece cuando sale el último. El número de sala es una cadena numérica arbitraria; todos los participantes que aterrizan en el mismo número se escuchan entre sí.

**Campos del cuerpo de la solicitud:**

| Campo | Tipo | Obligatorio | Valor por defecto | Descripción |
|---|---|---|---|---|
| `parties` | lista de cadenas (mínimo 2) | Sí | — | Los canales de los participantes, p. ej. `["PJSIP/101", "PJSIP/0504139380@mega-provider", "Local/2222@internal"]`. |
| `room` | cadena (hasta 64 caracteres) | No | se genera automáticamente | El número de la sala de conferencia. Si no se indica, el servidor genera uno y lo devuelve en la respuesta. |
| `context` | cadena (hasta 128 caracteres) | No | el contexto de conferencia configurado en la PBX | El contexto del plan de marcado que hace aterrizar cada pierna en `ConfBridge`. La mayoría de las integraciones no necesitan cambiarlo. |
| `callerid` | cadena (hasta 128 caracteres) | No | — | El Caller ID aplicado a cada una de las piernas de originate. |
| `timeout_ms` | entero | No | `30000` | El tiempo máximo de espera de respuesta para cada pierna, en milisegundos (de `1000` a `120000`). |

Como en el ejemplo del conductor de la sección 7.3, un canal que deba aterrizar en una extensión interna con soporte multi-dispositivo/fallback conviene indicarlo mediante un canal `Local` (p. ej. `Local/2222@internal`), no directamente — esto permite que la lógica del plan de marcado (varios dispositivos, follow-me) decida por sí misma dónde termina la llamada.

**Ejemplo de solicitud** (Operador, Cliente a través de un troncal de proveedor, Conductor a través de una extensión interna con fallback):

```bash
curl -X POST https://pbx.example.com/api/v1/calls/conference/ \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parties": [
      "PJSIP/101",
      "PJSIP/0504139380@mega-provider",
      "Local/2222@internal"
    ]
  }'
```

**Respuesta (`202 Accepted`):**

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

Un código `202` y `"queued": true` solo significan que el correspondiente comando `Originate` fue puesto en cola en AMI — todas las piernas se marcan **en paralelo**, no una tras otra.

Esto no es confirmación de respuesta ni de que la conversación se haya establecido: el CRM obtiene esa información por separado mediante webhooks (`call.answered`, `call.ended`) para cada pierna, usando su propio `uniqueid`.

Es posible un fallo parcial: si una pierna no logró conectarse mientras las demás se unieron con éxito, el elemento correspondiente de `results` tendrá `"queued": false` con una explicación en `detail`, y el resto tendrá `"queued": true`.

**Posibles errores:**

| Código | Cuerpo de la respuesta | Motivo |
|---|---|---|
| `400 Bad Request` | `{"parties": ["Ensure this field has at least 2 elements."]}` | Se enviaron menos de dos participantes, o se incumplió otra restricción de campo. |
| `401 Unauthorized` | `{"detail": "Authentication credentials were not provided."}` | Falta el token de autenticación, o no es válido. |
| `502 Bad Gateway` | `{"detail": "AMI unavailable."}` | La PBX no pudo establecer conexión con el Asterisk Manager Interface (ninguna pierna se puso en cola). |
| `503 Service Unavailable` | `{"detail": "Asterisk is disabled in this DEVMODE."}` | La PBX funciona en modo de desarrollo sin conexión a un Asterisk real. |

### 7.5. Otros endpoints

La API también ofrece endpoints para trabajar con listas de números. No son obligatorios para una integración básica (recepción de eventos de llamada e iniciación de llamadas salientes), pero pueden ser útiles si el sistema CRM se encarga de gestionar listas negras/permitidas o el directorio de contactos.

| Endpoint | Métodos | Función |
|---|---|---|
| `/api/v1/blacklist/`, `/api/v1/blacklist/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Gestión de la lista de números bloqueados (`callerid` + `destination`). Un `POST` repetido con el mismo `callerid`/`destination` actualiza el registro existente (`200`); se crea un nuevo registro con estado `201`. |
| `/api/v1/whitelist/`, `/api/v1/whitelist/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Igual que `blacklist/`, pero para números permitidos. |
| `/api/v1/contacts/`, `/api/v1/contacts/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Un directorio que asocia `callerid` → nombre de contacto. |
| `/api/v1/lists/`, `/api/v1/lists/{id}/` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` | Gestión de listas con nombre arbitrarias. |
| `/api/v1/lists/{id}/entries/` | `GET`, `POST` | Ver y añadir entradas dentro de una lista concreta. |
| `/api/v1/lists/{id}/entries/{entry_id}/` | `DELETE` | Eliminar una entrada de una lista. |
| `/api/v1/recordings/{uniqueid}/` | `GET` | Obtener la grabación de audio de una llamada (descrito en detalle en la sección 6). |

Todos los endpoints de listas anteriores admiten paginación estándar (50 registros por página por defecto) y devuelven los errores de validación estándar de DRF.

### 7.6. Formato de errores

Los errores de validación de la solicitud se devuelven en el formato estándar de Django REST Framework — un objeto donde la clave corresponde al nombre del campo y el valor es una lista de mensajes de texto:

```json
{
  "callerid": ["This field is required."]
}
```

Los errores no asociados a un campo concreto (p. ej. un fallo de autenticación o un recurso inexistente) se devuelven en el campo `detail`:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

Un intento de crear un recurso que infringe una restricción de unicidad a nivel de base de datos devuelve `409 Conflict`:

```json
{
  "detail": "Resource already exists or violates a uniqueness constraint."
}
```

Se recomienda que el manejador de respuestas del sistema CRM se guíe principalmente por el código de estado HTTP, y use el contenido del campo `detail`/los nombres de los campos para diagnóstico y registro.

## 8. Dashboard API y WebSocket: canal en tiempo real (opcional)

Además de los webhooks y la API REST (secciones 1–7), para algunas instalaciones de PearlPBX2 el administrador puede conceder adicionalmente acceso a la API interna del panel de operador. Este es un canal **opcional y alternativo** — la gran mayoría de las integraciones solo necesitan los webhooks y la API REST descritos arriba. Esta sección está pensada para los casos en los que el sistema CRM necesita una instantánea actual del estado de la PBX (colas, canales, llamadas activas), o un flujo continuo de eventos, en lugar de solo notificaciones sobre los momentos clave de una llamada.

**Una diferencia fundamental respecto al resto del documento:** el formato de datos de este canal es el formato interno del panel de operador de PearlPBX2, no un contrato de integración estabilizado. El conjunto de campos y tipos de eventos puede cambiar entre versiones sin un ciclo de coordinación aparte. Si tienes elección, los webhooks (sección 5) son la fuente de datos prioritaria y recomendada para un CRM.

### 8.1. Autenticación

Ambos mecanismos siguientes aceptan el mismo token de acceso emitido por el administrador de la PBX, siguiendo el esquema de autenticación por token de Django REST Framework (el mismo esquema que en la sección 7.1; consulta con el administrador si se usa un token compartido con la API REST, o si se emite uno distinto).

### 8.2. Dashboard API (`GET /dashboard/api/...`)

Endpoints de solo lectura, cada uno acepta un token en la cabecera `Authorization: Token TU_TOKEN` (una sesión de Django también funciona, pero para la integración con un CRM lo relevante es el token):

| Endpoint | Función |
|---|---|
| `GET /dashboard/api/queues/` | El estado de todas las colas de servicio (miembros, llamadas, estadísticas). |
| `GET /dashboard/api/queues/{queue_name}/` | El estado de una cola concreta. |
| `GET /dashboard/api/channels/` | El estado de todos los canales activos de Asterisk. |
| `GET /dashboard/api/channels/{channel_name}/` | El estado de un canal concreto. |
| `GET /dashboard/api/channels/type/{channel_type}/` | Canales filtrados por tipo (`PJSIP`, `Local`, etc.). |
| `GET /dashboard/api/calls/active/` | Llamadas activas (puenteadas), con información de ambas piernas. |
| `GET /dashboard/api/endpoints/` | Una lista de los usuarios SIP internos y troncales SIP externos configurados en la PBX. |
| `GET /dashboard/api/missed-calls/?queue={nombre}` | Llamadas perdidas hoy en una cola concreta. |

Ejemplo de solicitud:

```bash
curl -H "Authorization: Token TU_TOKEN" \
  https://pbx.example.com/dashboard/api/queues/
```

Una solicitud sin token, o con un token inválido, devuelve `401 Unauthorized`.

**Importante: dos acciones del panel no se habilitan con un token.** `POST /dashboard/api/channels/hangup/` (finalizar una llamada por la fuerza) y `POST /dashboard/api/queues/pause/` (pausar/reanudar a un operador) son acciones de control que llaman directamente al Asterisk Manager Interface. Deliberadamente solo están disponibles a través de una sesión de Django con estado de staff (`is_staff`) y protección CSRF, y no aceptan un token de integración. Un token emitido para lectura no otorga la capacidad de controlar llamadas o colas en vivo.

### 8.3. WebSocket `/ws/asterisk/` — flujo de eventos en tiempo real

`wss://pbx.example.com/ws/asterisk/?token=TU_TOKEN` — el mismo flujo de eventos que alimenta el panel de operador: cada mensaje llega justo después del evento correspondiente de Asterisk, sin sondeo (polling). La conexión es solo de lectura — el servidor no acepta ningún comando del cliente en este socket.

El formato de cada mensaje:

```json
{
  "type": "channel_new",
  "data": { "channel": "PJSIP/101-0000001a", "uniqueid": "1753000000.42", "..." : "..." },
  "timestamp": "2026-07-24T14:32:10.123456"
}
```

`type` toma valores como `channel_new`, `channel_state_change`, `channel_dial_begin`, `channel_dial_end`, `channel_hangup`, `queue_caller_join`, `queue_caller_leave`, `queue_caller_abandon`, `queue_member_status`, `agent_connect`, entre otros — este es un flujo mucho más detallado y de bajo nivel que los cuatro eventos de webhook de la sección 5, y está pensado más para mostrar en vivo el estado de la PBX (p. ej. un panel de despacho) que para lógica de negocio como crear una tarea en el CRM. Para una integración típica (una tarjeta de llamada, una devolución de llamada por una perdida, adjuntar una grabación), los webhooks de la sección 5 siguen siendo la fuente de datos correcta y suficiente.

La API `WebSocket` del navegador no permite añadir cabeceras personalizadas, por lo que el token se pasa mediante el parámetro de consulta `?token=`; para clientes nativos (no de navegador) se acepta igualmente la cabecera `Authorization: Token TU_TOKEN`. Sin un token válido y sin una sesión de Django activa, el servidor cierra la conexión de inmediato.

## 9. Verificación de la autenticidad de las solicitudes

Para evitar aceptar solicitudes falsificadas que imiten un webhook de PearlPBX2, se ofrece un mecanismo de firma digital.

Siempre que el administrador de la PBX haya configurado una clave secreta, cada solicitud lleva esta cabecera:

```
X-PearlPBX-Signature: sha256=abc123...
```

El valor de la cabecera es una firma HMAC-SHA256 del cuerpo de la solicitud, calculada usando una clave secreta conocida por ambas partes (la PBX y el servidor CRM). Verificar la firma confirma que la solicitud realmente la envió PearlPBX2 y que su contenido no se modificó durante la transmisión.

Ejemplo de verificación en Python:

```python
import hashlib
import hmac

SECRET = "clave-secreta-de-la-configuracion-de-la-pbx"

def is_signature_valid(raw_body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(
        SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    # La comparación se realiza en tiempo constante; una comparación directa de cadenas no es aceptable
    return hmac.compare_digest(expected, header_value)
```

Ejemplo equivalente en Node.js:

```javascript
const crypto = require("crypto");

const SECRET = "clave-secreta-de-la-configuracion-de-la-pbx";

function isSignatureValid(rawBody, headerValue) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", SECRET).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}
```

**Una advertencia importante:** la firma se calcula sobre los bytes crudos del cuerpo de la solicitud, antes de cualquier parseo de JSON. Si el framework web que usas parsea el JSON automáticamente antes de que puedas acceder al cuerpo crudo, es necesario asegurarse de tener acceso a los bytes originales (en Flask, el método `request.get_data()`; en Express, el middleware `express.raw()` o un mecanismo equivalente para conservar el buffer crudo).

Si no se configura ninguna clave secreta, la cabecera de firma simplemente estará ausente — este es el comportamiento normal, y significa que no se realiza verificación de firma. Aun así, se recomienda configurar este mecanismo por razones de seguridad.

## 10. Configuración de un formato JSON personalizado

En caso de que el sistema CRM espere un cuerpo de solicitud con una estructura distinta (nombres de campo diferentes, o anidamiento adicional), el administrador de la PBX puede configurar una plantilla de cuerpo de solicitud personalizada en el panel de administración, donde los campos estándar se sustituyen por otros arbitrarios, con sustitución de valores mediante la sintaxis `${nombre_variable}`. Ejemplo:

```json
{
  "call_id": "${uniqueid}",
  "customer_phone": "${caller_id_num}",
  "type": "phone_call",
  "recording": "${recording_url}"
}
```

Lista de todas las variables de sustitución disponibles: `event`, `uniqueid`, `linkedid`, `channel`, `caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`, `duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`, `recording_expected`, `recording_url`, `recording_file`, `missed`, `wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`, `holdtime`, `answered_by_member`, `answered_by_interface`, `direction`, `dest_channel`, `dial_status`, `answered`, `channel_vars`.

`channel_vars` — un objeto con las variables de canal de Asterisk permitidas por el administrador de la PBX (p. ej. `{"ULINE": "42"}`); un objeto vacío `{}` si aún no se ha establecido ninguna. En la plantilla, `${channel_vars}` como único contenido de un campo de cadena se sustituye como un objeto JSON anidado, no como texto.

La configuración de la plantilla se realiza enteramente en el lado del administrador de la PBX y no requiere ninguna participación del desarrollador del CRM. Si necesitas cambiar el formato predeterminado, simplemente pídeselo al administrador. Al crear un webhook nuevo, el campo de plantilla en el panel de administración ya viene rellenado con un ejemplo que lista todas las variables disponibles — editarlo normalmente solo consiste en eliminar las líneas que no necesites.

## 11. Comportamiento del sistema ante fallos de entrega

El mecanismo de entrega de webhooks se basa en el principio de "mejor esfuerzo" (best-effort):

- No existe una cola de reintentos garantizada durante un período prolongado.
- Si el servidor CRM no responde a tiempo, o no está disponible, se realizan varios reintentos con un intervalo definido por la configuración del administrador de la PBX.
- Si todos los reintentos fallan, el evento se considera perdido y no se vuelve a enviar.

Implicaciones prácticas para la implementación del sistema CRM:
- **Velocidad de respuesta.** El endpoint debe devolver `200 OK` lo más rápido posible, idealmente en menos de un segundo. Si procesar el evento requiere operaciones largas (p. ej. llamar a un sistema de terceros), se recomienda confirmar la recepción de inmediato y procesar el evento de forma asíncrona (una cola de tareas, un manejador en segundo plano, etc.).
- **Manejo de duplicados.** Recibir el mismo evento dos veces es teóricamente posible (p. ej. debido a un fallo de red en el momento de enviar la respuesta). El enfoque recomendado es usar el par `uniqueid` + `event` como clave de idempotencia: si un evento con esa clave ya se procesó, la solicitud repetida debe ignorarse.
- **Ausencia de eventos.** La ausencia de solicitudes entrantes durante un período corresponde a la ausencia de llamadas, y no es señal de un fallo.

## 12. Ejemplo de implementación de un servidor receptor

A continuación se muestra un ejemplo de implementación en Python (Flask) que acepta eventos de ambas cadenas (entrante y saliente), verifica la firma y descarga el archivo de grabación cuando está disponible. Este ejemplo puede usarse como base para tu propia implementación.

```python
import hashlib
import hmac
import os

import requests
from flask import Flask, request, abort

app = Flask(__name__)

# Clave secreta para verificar la firma del webhook, acordada con el administrador de la PBX
WEBHOOK_SECRET = os.environ["PEARLPBX_WEBHOOK_SECRET"]
# Token para descargar grabaciones de llamadas a través de la API
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
    raw_body = request.get_data()  # bytes crudos, antes de parsear el JSON

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
        # El archivo aún no se ha escrito en disco; se puede reintentar más tarde
        return
    response.raise_for_status()

    # El formato real del archivo (wav o mp3) se determina por Content-Type,
    # ya que en el lado de la PBX las grabaciones se convierten de wav a mp3 según un programa
    extension = "mp3" if response.headers.get("Content-Type") == "audio/mpeg" else "wav"
    with open(f"/data/recordings/{call_id}.{extension}", "wb") as f:
        f.write(response.content)


def open_live_call_card(call_id, phone, name):
    print(f"[incoming] {call_id}: llamada de {name or phone}")


def mark_call_answered(call_id, member_name):
    print(f"[answered] {call_id}: contestó {member_name}")


def create_callback_task(call_id, phone, wait_time):
    print(f"[missed] {call_id}: {phone}, esperó {wait_time}s, necesita devolución de llamada")


def close_call_card(call_id, duration):
    print(f"[ended] {call_id}: duración {duration}s")
```

Implementación equivalente en Node.js (Express):

```javascript
const express = require("express");
const crypto = require("crypto");

const app = express();
const WEBHOOK_SECRET = process.env.PEARLPBX_WEBHOOK_SECRET;
const API_TOKEN = process.env.PEARLPBX_API_TOKEN;

// Conservar los bytes crudos del cuerpo de la solicitud para verificar la firma
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
      console.log(`[incoming] ${payload.uniqueid}: llamada de ${payload.caller_id_num}`);
      break;
    case "call.answered":
      console.log(`[answered] ${payload.uniqueid}: contestó ${payload.member_name}`);
      break;
    case "call.missed":
      console.log(`[missed] ${payload.uniqueid}: esperó ${payload.wait_time}s`);
      break;
    case "call.ended":
      console.log(`[ended] ${payload.uniqueid}: duración ${payload.duration}s`);
      if (payload.recorded) {
        await downloadRecording(payload.uniqueid, payload.recording_url);
      }
      break;
    case "call.outgoing":
      console.log(`[outgoing] ${payload.uniqueid}: llamando a ${payload.exten}`);
      break;
    case "call.outgoing_answered":
      console.log(`[outgoing_answered] ${payload.uniqueid}: contestaron`);
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
  if (response.status === 404) return; // archivo aún no escrito, reintentar más tarde
  if (!response.ok) throw new Error(`Recording fetch failed: ${response.status}`);

  // El formato real del archivo se determina por Content-Type: las grabaciones
  // se convierten de wav a mp3 según un programa en el lado de la PBX, por lo
  // que la extensión no está fija de antemano
  const extension = response.headers.get("Content-Type") === "audio/mpeg" ? "mp3" : "wav";
  const buffer = Buffer.from(await response.arrayBuffer());
  require("fs").writeFileSync(`/data/recordings/${callId}.${extension}`, buffer);
}

app.listen(3000, () => console.log("Webhook receiver listening on :3000"));
```

## 13. Preguntas frecuentes

**¿Es posible recibir `call.ended` sin un `call.incoming` previo?**
No. El sistema rastrea este estado internamente: el evento de finalización se envía exclusivamente para llamadas cuyo inicio ya se había notificado. La presencia de `call.ended` garantiza que previamente se envió un `call.incoming` con el mismo `uniqueid`.

**¿Son posibles `call.missed` o `call.answered` sin un `call.incoming` previo?**
Sí. Ambos eventos son independientes: una llamada perdida y el hecho de que un operador conteste se consideran lo bastante significativos como para enviarse independientemente de la suscripción al evento de inicio de llamada.

**¿Por qué no hay evento `call.answered` para llamadas directas sin cola?**
Este evento corresponde al evento AMI de Asterisk `AgentConnect`, que solo se genera para llamadas que pasaron por una cola de servicio. Una llamada directa a un empleado concreto, sin que intervenga una cola, no dispara este evento — este es el comportamiento esperado.

**¿Qué significa un valor `null` en el campo `queue`?**
La llamada se realizó sin que interviniera una cola de servicio (p. ej. una llamada directa a un empleado concreto). Esto no es un error.

**¿Es `uniqueid` un identificador estable en el tiempo?**
Sí, dentro de una misma llamada, `uniqueid` es un identificador estable y único, apto para usarse como clave primaria al correlacionar eventos.

**¿Es un error el valor `recording_expected: null` en `call.incoming`?**
No. Significa que en el momento en que empezó la llamada, el sistema aún no había determinado si se grabaría. El valor definitivo está en el campo `recorded` del evento `call.ended`.

**¿Necesito lógica separada para llamadas sin grabación?**
Basta con comprobar la condición `recorded === true` antes de solicitar el archivo de grabación. Para `false` o `null`, solicitar el enlace devolverá `404`.

**¿Qué comportamiento debo esperar si el servidor CRM no está disponible temporalmente mientras se envía un evento?**
El sistema realizará automáticamente varios reintentos de entrega. Si ninguno tiene éxito, el evento no se vuelve a enviar. Esto debe tenerse en cuenta al planificar la fiabilidad de tu propio endpoint (en particular, monitorear su disponibilidad).

**¿Una respuesta exitosa de `POST /api/v1/calls/originate/` (`200 OK`) significa que la parte contestó la llamada?**
No. Una respuesta exitosa solo confirma que el comando `Originate` fue puesto en cola para su ejecución en el Asterisk Manager Interface. El progreso real de la llamada (respuesta, duración, finalización) se rastrea exclusivamente mediante los eventos de webhook correspondientes (`call.answered`, `call.ended`), correlacionados por el `uniqueid` de esa llamada.

**¿Por qué la solicitud de iniciación de llamada devolvió `502 Bad Gateway`?**
Esto significa un error a nivel de la interacción de la PBX con el Asterisk Manager Interface — es Asterisk, no el sistema CRM, la fuente del problema. El motivo se detalla en el campo `detail` de la respuesta (ver la sección 7.2): falta de conexión con AMI, se superó el tiempo de espera (`timeout_ms`), o Asterisk se negó a ejecutar el comando (p. ej. una extensión o contexto inexistente).

**¿En qué se diferencia `call.outgoing` de `call.incoming`, si ambos significan "una llamada comenzó"?**
En la dirección de la iniciación. `call.incoming` — una llamada que llega a la empresa (de un cliente a través de un troncal, o una llamada interna hacia un contexto/cola). `call.outgoing` — una llamada iniciada por un empleado que marca un número desde su teléfono. Son dos cadenas de eventos totalmente independientes con nombres distintos en cada paso (`call.ended` frente a `call.outgoing_ended`), y ninguna llamada genera eventos de ambas cadenas a la vez.

**¿Puede llegar un evento de la cadena saliente (`call.outgoing*`) para una llamada que en realidad pasa por un troncal (una conexión con un proveedor)?**
No, nunca, bajo ninguna circunstancia. El sistema determina el iniciador de una llamada por el identificador técnico del canal de un empleado concreto, no por la dirección o el nombre de la ruta — incluso si el administrador configuró un troncal y usuarios internos en la misma ruta, las llamadas del troncal nunca se confundirán con las de los empleados.

**¿Llegará `call.outgoing_ended` sin un `call.outgoing_answered` previo si la línea estaba ocupada?**
Sí, y este es el comportamiento esperado. `call.outgoing_answered` solo llega si la parte llamada descolgó. Si la línea estaba ocupada, nadie contestó, o la llamada se canceló, `call.outgoing_ended` llega directamente, con `answered: false` y un código de motivo en `dial_status`.

## 14. Lista de verificación de la integración

- [ ] Se implementó un endpoint HTTP que acepta solicitudes `POST` con cuerpo JSON y devuelve `200 OK` con prontitud.
- [ ] Se entregó la URL del endpoint al administrador de la PBX, y se acordó una clave secreta para firmar las solicitudes.
- [ ] Se obtuvo del administrador de la PBX un token de API para descargar grabaciones de llamadas y (si es necesario) para llamar a la API REST.
- [ ] Se implementó el manejo de los cuatro eventos de la cadena entrante: `call.incoming`, `call.answered`, `call.missed`, `call.ended`.
- [ ] Si es necesario manejar las llamadas salientes de los empleados — se implementó el manejo de los tres eventos de la cadena saliente: `call.outgoing`, `call.outgoing_answered`, `call.outgoing_ended`.
- [ ] Si es necesario iniciar llamadas desde el lado del CRM — se implementó y probó la llamada a `POST /api/v1/calls/originate/`, manejando los códigos `400`, `401`, `502`, `503`.
- [ ] Si es necesario reunir a tres o más participantes en una misma conversación — se implementó la llamada a `POST /api/v1/calls/conference/`, manejando fallos parciales en el array `results`.
- [ ] Se implementó la verificación de la firma `X-PearlPBX-Signature`, basada en los bytes crudos del cuerpo de la solicitud, antes de parsear el JSON.
- [ ] Se implementó la descarga de la grabación de una llamada mediante `GET /api/v1/recordings/{uniqueid}/` usando el token, siempre que `recorded: true`.
- [ ] Se maneja una respuesta `404` al intentar obtener una grabación (el archivo puede aparecer en disco con retraso).
- [ ] Se tiene en cuenta la posibilidad de valores `null` en campos individuales.
- [ ] Se implementó un manejo idempotente de eventos en caso de entrega repetida (usando `uniqueid` como clave).
- [ ] (Opcional, solo si el administrador ha concedido acceso) El uso del Dashboard API / WebSocket (sección 8) se acordó con el administrador de la PBX, con el entendimiento de que este formato es interno y no está versionado.

Completar los puntos anteriores es suficiente para una implementación completa de la integración.
