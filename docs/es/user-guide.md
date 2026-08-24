*Also available in: [English](../en/user-guide.md) | [Українська](../ua/user-guide.md) | [Español](user-guide.md)*

# Guía del usuario de PearlPBX2

**Versión:** 2.7.2

---

## Contenido

1. [Introducción](#1-introducción)
2. [Primeros pasos](#2-primeros-pasos)
3. [Página de inicio](#3-página-de-inicio)
4. [Panel de operador](#4-panel-de-operador)
5. [Monitoreo ULINE](#5-monitoreo-uline)
6. [Reportes](#6-reportes)
7. [Analítica](#7-analítica)
8. [Listas](#8-listas)
9. [Preguntas frecuentes](#9-preguntas-frecuentes)

---

## 1. Introducción

PearlPBX2 es una interfaz web para gestionar una central telefónica Asterisk PBX. El sistema permite:

- ver el estado del sistema en tiempo real;
- seguir las llamadas activas y las colas;
- ver reportes y analítica de llamadas;
- gestionar listas de números (lista negra, permitidos, contactos).

Basta con un navegador web para usar el sistema. No se necesita software adicional.

### A quién va dirigida esta guía

Esta guía está destinada a **operadores de call center**, **gerentes** y **personal** con acceso mediante el grupo "Report Viewer". Estos usuarios tienen acceso a:

- la página de inicio con el estado del sistema;
- el panel de operador (modo en tiempo real);
- reportes y analítica;
- gestión de listas de números.

---

## 2. Primeros pasos

### Inicio de sesión

1. Abre un navegador web y ve a la dirección de tu sistema PearlPBX2.
2. Verás una página de inicio de sesión:
   - **Username** — tu nombre de usuario.
   - **Password** — tu contraseña.
3. Haz clic en **Log in**.

![Página de inicio de sesión](images/login.png)

### Cerrar sesión

Haz clic en el botón **Logout** en el menú superior.

### Elegir el idioma

El sistema admite tres idiomas:

- Українська (idioma por defecto)
- English
- Español

Usa el selector de idioma en el menú superior, o ve a `/i18n/set-language/`, para cambiar de idioma.

### Navegación

Una vez iniciada la sesión, el menú superior ofrece:

| Elemento del menú | Descripción |
|------------|------|
| **Dashboard** (`/dashboard/`) | Panel de operador (modo en tiempo real) |
| **Parking** (`/dashboard/ulines/`) | Monitoreo de slots de parking (ULINE) |
| **Reports** (`/reports/`) | Reportes y analítica |
| **Lists** (`/lists/`) | Gestión de listas de números |

Si tienes el rol de **superuser**, también estará disponible el elemento **Admin panel** (`/admin`) — a diferencia de los demás elementos del menú, solo es visible para superusuarios, no para cualquier usuario con permisos de administración.

---

## 3. Página de inicio

La página de inicio (`/`) muestra el estado general del sistema.

### Estadísticas del sistema

La parte superior de la página muestra el recuento de objetos en el sistema:

- **SIP Users** — número de abonados internos.
- **SIP Peers** — número de conexiones externas (troncales).
- **Queues** — número de colas.
- **Routing Records** — número de reglas de enrutamiento.
- **Contacts** — número de entradas en el directorio de contactos.
- **Blocklist** — número de números bloqueados.

### Estado de Asterisk

Se muestra información sobre el estado de Asterisk:

- **Version** — versión de Asterisk (p. ej. "Asterisk 22.0.0").
- **Current calls** — número de llamadas activas.
- **Processed calls** — número total de llamadas procesadas desde el arranque.
- **Uptime** — tiempo que lleva funcionando Asterisk desde su último arranque.

### Llamadas activas y colas

- **Active calls** — número de llamadas actualmente en curso (unidas en puentes).
- **Queues** — lista de colas con el número de llamadas en espera y agentes disponibles.

### Gráfico de CDR

El gráfico muestra el número de llamadas de los últimos 14 días, desglosado por estado (ANSWERED, NO ANSWER, BUSY, FAILED).

---

## 4. Panel de operador

El panel de operador (disponible en `/dashboard/` desde el menú superior, o directamente en `/dashboard/live/` — ambos enlaces abren la misma página) es una herramienta para monitorear el sistema telefónico en tiempo real. Se actualiza automáticamente mediante una conexión WebSocket.

### Indicador de conexión

En la esquina superior derecha del panel hay un indicador:

- **Connected** (verde) — la conexión WebSocket está activa; los datos se actualizan en tiempo real.
- **Disconnected** (rojo) — se perdió la conexión. Intenta recargar la página.

### Pestañas del panel

#### Overview

Un resumen general del sistema:

- número total de llamadas activas;
- número de llamadas en colas;
- número de agentes disponibles;
- número de canales PJSIP activos.

#### Queues

Una lista de colas con información detallada:

- nombre de la cola;
- número de llamadas en espera;
- número de agentes (disponibles / total);
- estado de los agentes (disponible / en pausa / ocupado).

Al hacer clic en una cola se abre una ventana modal con información detallada sobre sus llamadas y agentes.

**Pausar a un agente:** cada agente de la cola tiene un botón **Pause / Unpause**, que lo pausa (o lo reanuda) en la cola vía AMI. Este botón solo está disponible para usuarios con permisos de **staff**.

#### PJSIP

Una lista de todos los usuarios SIP y troncales con su estado actual:

- **Online** — registrado y disponible.
- **Offline** — no registrado.

#### Bridged

Una lista de llamadas puenteadas (conversaciones en curso):

- canales participantes;
- identificador del puente.

#### Channels

Una lista completa de todos los canales activos con información detallada:

- tipo de canal (PJSIP, Local, DAHDI, etc.);
- Caller ID;
- estado;
- nombre de la cola (si el canal está en una cola).

### Finalizar una llamada

Para finalizar una llamada activa, haz clic en el botón **Hangup** junto al canal o llamada correspondiente. Este botón solo está disponible para usuarios con permisos de **staff**.

---

## 5. Monitoreo ULINE (Parking)

La página **Parking** (`/dashboard/ulines/`, el elemento **Parking** en el menú de navegación) muestra el estado de los slots de parking.

### Qué es ULINE

ULINE (Unique Line Number) es un sistema de asignación de slots de parking (números 1–199). Cada slot puede estar:

- **libre** — disponible para usar;
- **ocupado** — hay una llamada aparcada en ese slot.

### Cómo usarlo

- La página se actualiza automáticamente en tiempo real.
- Los slots ocupados se resaltan.
- El botón **Flush all** permite liberar todos los slots. Disponible solo para usuarios con permisos de **superuser**.

---

## 6. Reportes

La sección Reports (`/reports/`) da acceso al historial de llamadas y otros datos.

### CDR (Call Detail Records)

La página `/reports/cdr/` — un reporte detallado de todas las llamadas.

**Filtros:**

- **Date range** — período (desde/hasta).
- **Source / Destination number** — número de la parte A o B.
- **Source / Destination channel** — canal de la parte A o B (campos separados).
- **Disposition** — estado: Answered, Busy, No answer, Failed.
- **Min / Max duration** — duración de la llamada (seg).
- **Call direction** — dirección: Incoming, Outgoing, Internal, Transit, Unbridged Peers, Unbridged Users.

**Columnas del reporte:**

| Columna | Descripción |
|---------|------|
| Start | Fecha y hora de inicio de la llamada |
| Answer | Fecha y hora de la respuesta |
| End | Fecha y hora de finalización |
| Duration | Duración de la llamada |
| Billsec | Duración de la conversación (seg) |
| Disposition | Estado (ANSWERED, NO ANSWER, BUSY, FAILED) |
| Source | Número de la parte A |
| Destination | Número de la parte B |
| Context | Contexto del plan de marcado |

**Exportar:** el botón **Export CSV** permite exportar la selección actual del reporte como CSV.

### Grabaciones de llamadas (Monitor)

La página `/reports/monitor/` — buscar y reproducir grabaciones de llamadas.

- Filtrar por fecha (desde/hasta) y número de la parte A/B.
- Haz clic en el botón **Play** para reproducir una grabación.

### Registro de colas (Queue Log)

La página `/reports/queuelog/` — un registro de eventos de las colas.

- filtrar por cola, fecha (desde/hasta), agente, tipo de evento (Abandoned, Completed by Agent, Completed by Caller, Connected, Enter Queue, Exit with Key, Exit with Timeout, Ring No Answer);
- el selector **Report Type** permite elegir la vista del reporte: Summary, Detailed, Agent Performance, Queue Performance, Lost and Found;
- la casilla **Exclude known Contacts** permite excluir llamadas de contactos conocidos;
- ver detalles de cada llamada;
- un botón **Export CSV** para exportar el reporte.

### Reporte de callbacks

La página `/reports/callback/` — un reporte sobre las llamadas de devolución automática.

**Columnas:**

- ID del registro;
- Created — fecha y hora de la solicitud;
- Source — el número desde el que llegó la solicitud de callback;
- Destination — el número al que se hace la devolución de llamada;
- estado (NEW, PENDING, ANSWERED, BUSY);
- Updated — fecha y hora de la última actualización de estado;
- Schedule — hora programada de la llamada;
- Service — servicio/origen de la solicitud;
- duración de la conversación;
- enlace a la grabación de la llamada (si existe).

**Exportar:** el botón **Export CSV** para exportar el reporte.

### Reporte de enrutamiento

La página `/reports/routing/` — registros de enrutamiento de llamadas, agrupados por tabla de enrutamiento (el nombre de la tabla es el encabezado del grupo, no una columna aparte). Para cada registro se muestra:

- Prefix — el prefijo del número;
- Name — el nombre del registro de enrutamiento;
- Target Context — el contexto de destino.

---

## 7. Analítica

La sección Analytics (`/reports/analytics/`) contiene 8 tipos de reportes con gráficos Chart.js.

### Llamadas en colas (Queue Calls)

`/reports/analytics/queue-calls/` — número de llamadas por cola en el período seleccionado.

### Llamadas por número de destino (Destination Calls)

`/reports/analytics/destination-calls/` — número de llamadas externas entrantes, agrupadas
por número marcado (número B). Muestra el total, las respuestas, la tasa de respuesta,
los llamantes únicos y la duración promedio de la llamada. Hay filtros disponibles por número
de destino, exclusión de contactos y límite de top-N, además de exportación a CSV.

### Llamadas de agentes (Agent Calls)

`/reports/analytics/agent-calls/` — un resumen de las llamadas de cada agente.

### Llamadas salientes (Outbound Calls)

`/reports/analytics/outbound-calls/` — estadísticas de llamadas salientes.

### Llamadas perdidas (Missed Calls)

`/reports/analytics/missed-calls/` — número de llamadas perdidas en el período.

### Perdidas por hora (Missed by Hour)

`/reports/analytics/missed-by-hour/` — distribución de llamadas perdidas por hora del día.

### Duración de llamadas (Call Duration)

`/reports/analytics/call-duration/` — distribución de llamadas por duración.

### Actividad de colas (Queue Activity)

`/reports/analytics/queue-activity/` — actividad de las colas por hora o día. Hay un filtro de exclusión de contactos disponible.

### Elementos comunes de analítica

- Selección de período (fecha desde/hasta).
- Filtrado por cola o agente.
- Gráficos basados en Chart.js (de línea, de barras, circulares).

**Nota:** a diferencia de los reportes CDR, Queue Log y Callback (sección 6), las páginas de analítica no tienen botón de exportación de datos.

---

## 8. Listas

La sección Lists (`/lists/`) permite gestionar listas de números sin necesidad de acceder al panel de administración.

### Lista negra (Blocklist)

`/lists/blocklist/` — una lista de números cuyas llamadas se bloquean.

**Añadir una entrada:**

1. Haz clic en **Add**.
2. Introduce el **Caller ID** — el número de teléfono del abonado.
3. (Opcional) **Destination** — un destino específico a bloquear.
4. (Opcional) **Reason** — el motivo del bloqueo.
5. (Opcional) **Expiration** — la fecha de expiración del bloqueo.
6. Haz clic en **Save**.

**Editar:** haz clic en una fila de la tabla — se abrirá una ventana modal de edición.

**Eliminar:** haz clic en el botón **Delete** junto a la entrada.

### Lista permitida (Allowlist)

`/lists/allowlist/` — una lista de números con rutas de tratamiento especial.

La interfaz es igual a la de la lista negra.

### Contactos (Contacts)

`/lists/contacts/` — un directorio que asocia números de teléfono con nombres de abonados. Se usa para determinar el Caller ID Name.

**Campos:**

- **Caller ID** — el número de teléfono.
- **Name** — el nombre del abonado.

La interfaz es igual a la de la lista negra.

---

## 9. Preguntas frecuentes

### ¿Cómo actualizo el panel en tiempo real?

El panel se actualiza automáticamente vía WebSocket. Si se pierde la conexión (el indicador muestra "Disconnected"), recarga la página. Si el problema persiste, contacta a tu administrador.

### ¿Por qué no veo algunos elementos del menú?

La visibilidad de los elementos del menú depende de tu rol en el sistema. Si crees que necesitas acceso a secciones adicionales, contacta a tu administrador.

### ¿Cómo escucho una grabación de llamada?

Ve a **Reports → Monitor**, busca la grabación por fecha o número, y haz clic en **Play**. Si el botón Play está inactivo, no hay ninguna grabación disponible.

### ¿Cómo añado un número a la lista negra?

Ve a **Lists → Blocklist**, haz clic en **Add**, introduce el número y haz clic en **Save**. Los cambios surten efecto cuando el administrador aplica la configuración (en el siguiente Apply Changes).

### ¿Puedo exportar los datos de un reporte?

Sí — para los reportes **CDR**, **Queue Log** y **Callback** (sección 6), hay disponible un botón **Export CSV** que exporta la selección actual como CSV. Las páginas **Monitor**, **Routing** y **Analytics** (sección 7) no tienen botón de exportación — puedes copiar los datos de sus tablas manualmente.

### ¿Qué hago si el panel no carga?

1. Comprueba tu conexión de red.
2. Intenta recargar la página (F5 o Cmd+R).
3. Si el problema persiste, contacta a tu administrador — es posible que Redis o el Dashboard Listener no estén funcionando.

---

*Documento creado para PearlPBX2 v2.7.2. La interfaz del sistema puede variar según la versión.*
