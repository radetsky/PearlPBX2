*Also available in: [English](../en/admin-guide.md) | [Українська](../ua/admin-guide.md) | [Español](admin-guide.md)*

# Guía del administrador de PearlPBX2

**Versión:** 2.7.2

---

## Contenido

1. [Introducción](#1-introducción)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Instalación (resumen)](#3-instalación-resumen)
4. [Configuración mediante variables de entorno](#4-configuración-mediante-variables-de-entorno)
5. [Usuarios y roles](#5-usuarios-y-roles)
6. [Transportes SIP](#6-transportes-sip)
7. [Usuarios SIP](#7-usuarios-sip)
8. [Peers SIP (troncales)](#8-peers-sip-troncales)
9. [Grupos de troncales](#9-grupos-de-troncales)
10. [Plan de marcado (Dialplan)](#10-plan-de-marcado-dialplan)
11. [Enrutamiento de llamadas](#11-enrutamiento-de-llamadas)
12. [Colas](#12-colas)
13. [Música en espera (MOH)](#13-música-en-espera-moh)
14. [Archivos de sonido](#14-archivos-de-sonido)
15. [Apply Changes](#15-apply-changes)
16. [Servicios](#16-servicios)
17. [Webhooks (CRM)](#17-webhooks-crm)
18. [API REST](#18-api-rest)
19. [Aprovisionamiento de teléfonos](#19-aprovisionamiento-de-teléfonos)
20. [Mantenimiento](#20-mantenimiento)

---

## 1. Introducción

PearlPBX2 es una interfaz web de administración para Asterisk PBX, construida sobre Django. El sistema permite gestionar endpoints SIP, troncales, plan de marcado, enrutamiento, colas y otros objetos de Asterisk a través de una interfaz web, generando automáticamente los archivos de configuración de Asterisk a partir de la base de datos.

### Características principales

- Gestión de transportes, endpoints y troncales PJSIP
- Editor de plan de marcado con soporte de sintaxis AEL y validación
- Enrutamiento de llamadas basado en prefijos
- Colas con soporte de escalado, anuncios y configuración global
- Panel de operador en tiempo real (WebSocket)
- CDR, grabaciones de llamadas, registros de colas
- Analítica con gráficos (Chart.js)
- Devoluciones de llamada (callback) automatizadas
- Aprovisionamiento de teléfonos (TFTP)
- API REST para integración externa
- Apply Changes — generación de configuración y recarga de Asterisk con un clic

### Quién es administrador

Un administrador es un usuario con permisos de **superuser** (is_superuser=True). Solo un superuser puede:

- aplicar cambios de configuración a Asterisk (`/admin/apply`);
- gestionar todos los objetos de la PBX a través del panel de administración;
- crear y editar otros usuarios.

Los usuarios con permisos de **staff** (is_staff=True) pueden ver el panel de administración, pero sin acceso a Apply Changes.

---

## 2. Arquitectura del sistema

### Esquema general

```
Browser ──WebSocket──► Django Channels ◄── Redis ◄── Dashboard Listener ◄── Asterisk AMI
Browser ──HTTP──────► Django (ASGI) ◄──── PostgreSQL
                            │
                            └──► /etc/asterisk/*.conf  (generación de configuración)

Asterisk FastAGI ◄──────────► FastAGI Service (puerto 4573)
Callback daemon ─────────────► Asterisk AMI (llamadas salientes)
```

### Componentes

| Componente | Función |
|-----------|-------------|
| **Django (ASGI)** | Aplicación web, HTTP + WebSocket, puerto 8000 |
| **PostgreSQL** | Base de datos para todos los objetos de la PBX |
| **Redis** | Canal de mensajes para WebSocket, almacenamiento del estado de colas/canales |
| **Dashboard Listener** | Servicio que escucha los eventos AMI de Asterisk y los publica en Redis |
| **Callback Daemon** | Servicio que monitorea la cola de callbacks en la BD e inicia llamadas vía AMI |
| **FastAGI Server** | Servicio FastAGI para el procesamiento del plan de marcado (comprobación de listas, grabación de llamadas, enrutamiento, parking) |

### Flujo de datos

1. **Configuración:** Admin UI → Modelos de Django → `core/conf.py` → archivos `/etc/asterisk/*.conf` → recarga de Asterisk
2. **Dashboard:** Eventos AMI de Asterisk → Dashboard Listener → Redis Pub/Sub → Django Channels → WebSocket → Navegador
3. **Callback:** Solicitud en la BD → Callback Daemon (SELECT FOR UPDATE) → AMI Originate → llamada saliente
4. **FastAGI:** Plan de marcado de Asterisk → AGI(agi://localhost:4573/handler) → servidor FastAGI → variables de canal

### Componentes de Django

| Módulo | Función |
|--------|-------------|
| `core/` | Modelos centrales, generador de configuración, validadores, interfaz de administración |
| `apps/dashboard/` | Panel de operador WebSocket |
| `apps/reports/` | CDR, grabaciones, registros, analítica |
| `apps/lists/` | CRUD para listas de números |
| `apps/callback/` | Modelos y vistas para callbacks |
| `apps/provision/` | Aprovisionamiento de teléfonos |
| `apps/api/` | API REST |
| `apps/webhooks/` | Webhooks para integración con CRM (eventos de llamada) |

---

## 3. Instalación (resumen)

### Requisitos del sistema

- **Python** 3.10+
- **Django** 5.2
- **PostgreSQL** 14+
- **Redis** 7+
- **Asterisk** 22+ (con los módulos `res_pjsip`, `res_agi`, `cdr_pgsql`)

### Inicio rápido (desarrollo)

```bash
# Crear un entorno virtual
python3 -m venv .python-venv
source .python-venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp env.sample .env
# Edita .env — BD, AMI, DEVMODE, etc.

# Inicializar la base de datos
python manage.py migrate
python manage.py createsuperuser

# Ejecutar el servidor de desarrollo
python manage.py runserver
```

### Entorno de producción

```bash
# Vía uvicorn (ASGI + WebSocket)
uvicorn pbx.asgi:application --host 0.0.0.0 --port 8000 --workers 3
```

**Importante:** Django debe ejecutarse como el usuario `asterisk` para poder acceder a `/etc/asterisk`.

### Instrucciones detalladas

- Despliegue con Docker: `docker-compose.yml` (django, asterisk, postgres, redis, fastagi, dashboard-listener, callback)
- Despliegue con Ansible (recomendado para producción bare-metal): `ansible/install.yml` (9 roles: system, postgres, redis, asterisk, pearlpbx2, services, nginx, tftp, firewall)

### Modos de funcionamiento (DEVMODE)

| Modo | Valor | Descripción |
|-------|----------|------|
| Production | `Production` | Cookies seguras, sin debug |
| Staging | `Staging` | Servidor de pruebas |
| Development | `Development` | Modo debug, desarrollo en un VPS |
| without_asterisk_on_localhost | `without_asterisk_on_localhost` | Desarrollo local sin Asterisk |

---

## 4. Configuración mediante variables de entorno

Toda la configuración se suministra mediante variables de entorno. Ejemplo: [env.sample](../../env.sample).

### Variables obligatorias

| Variable | Descripción | Valor por defecto |
|--------|------|-----------------|
| `DEVMODE` | Modo de funcionamiento | `Development` |
| `DJANGO_SECRET_KEY` | Clave secreta de Django (obligatoria en Production) | — |
| `DB_HOST` | Host de PostgreSQL | `localhost` |
| `DB_NAME` | Nombre de la base de datos | `pearlpbx2` |
| `DB_USER` | Usuario de la BD | `pearlpbx2` |
| `DB_PASS` | Contraseña de la BD | — |
| `ASTERISK_MANAGER_HOST` | Host AMI de Asterisk | `127.0.0.1` |
| `ASTERISK_MANAGER_USERNAME` | Usuario AMI | `django` |
| `ASTERISK_MANAGER_SECRET` | Contraseña AMI | — |

### Variables opcionales

| Variable | Descripción | Valor por defecto |
|--------|------|-----------------|
| `ALLOWED_HOSTS` | Hosts permitidos (separados por comas) | `127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes CSRF de confianza | — |
| `ASTERISK_ROOT_DIR` | Directorio raíz de Asterisk | `/tmp` |
| `ASTERISK_CONFIG_DIR` | Directorio de configuración de Asterisk | `/etc/asterisk` |
| `ASTERISK_BACKUP_DIR` | Directorio de copias de seguridad | `/tmp/backup/asterisk` |
| `ASTERISK_MONITOR_DIR` | Directorio de grabaciones de llamadas | `/var/spool/asterisk/monitor` |
| `ASTERISK_BACKUP_MONITOR_DIR` | Directorio de respaldo de grabaciones (iSCSI) | — |
| `REDIS_URL` | URL de conexión a Redis | `redis://localhost:6379` |
| `TFTP_DIR` | Directorio TFTP de aprovisionamiento | `/var/lib/tftpboot` |
| `DASHBOARD_MISSED_CALL_WINDOW_MINUTES` | Ventana de llamadas perdidas | `0` (día actual) |
| `PHONE_COUNTRY_CODE` | Código de país para normalización | `380` |
| `PHONE_LOCAL_CODE` | Código de ciudad | `044` |
| `PHONE_REQUIRED_LEN` | Longitud esperada del número completo al normalizar | `10` |
| `PHONE_CITYCODE_LEN` | Longitud del código de ciudad al normalizar | `7` |
| `PEARLPBX_PUBLIC_URL` | URL base pública de la interfaz web (usada para los enlaces a grabaciones en los webhooks de CRM) | `http://localhost:8000` |

---

## 5. Usuarios y roles

### Grupos de usuarios

El sistema usa el modelo de usuarios estándar de Django.

#### El grupo "Report Viewer"

Los usuarios de este grupo tienen acceso a:

- Dashboard (`/dashboard/`)
- Parking (monitoreo de ULINE, `/dashboard/ulines/`)
- Reports (`/reports/`)
- Lists (`/lists/`)

Creación del grupo:

1. Panel de administración → Authentication and Authorization → Groups → Add Group.
2. Nombre: `Report Viewer`.
3. Asigna los permisos necesarios (o ninguno — el acceso se controla en el código mediante `HEADER_MENU_PAGES`).

#### Niveles de acceso en Django

| Nivel | `is_superuser` | `is_staff` | Acceso |
|--------|---------------|------------|--------|
| Superuser | true | true | Acceso completo, incluido Apply Changes |
| Staff | false | true | Panel de administración (ver/editar objetos) |
| Report Viewer | false | false | Dashboard, Reports, Lists |
| Normal | false | false | Solo página de inicio (si ha iniciado sesión) |

### Creación de un usuario

1. Ve a `/admin/auth/user/add/`.
2. Rellena **Username**, **Password**.
3. Haz clic en **Save and continue editing**.
4. En la pestaña **Permissions**:
   - **Superuser status** — marca la casilla para acceso completo.
   - **Staff status** — márcala para acceder al panel de administración.
5. En la pestaña **Groups**, añade el usuario al grupo "Report Viewer" (si es necesario).

### Menú de navegación (HEADER_MENU_PAGES)

`settings.py` define los elementos del menú vinculados a roles:

| Elemento | Rol | URL |
|-------|------|-----|
| Dashboard | admin, superuser, Report Viewer | `/dashboard/` |
| Parking (ULINE) | admin, superuser, Report Viewer | `/dashboard/ulines/` |
| Reports | admin, superuser, Report Viewer | `/reports/` |
| Lists | admin, superuser, Report Viewer | `/lists/` |
| Admin panel | superuser | `/admin` |

---

## 6. Transportes SIP

Los transportes SIP definen cómo Asterisk escucha y envía tráfico SIP. Corresponde al modelo `SIPTransport`.

### Creación de un transporte

1. Panel de administración → PBX Setup → SIP Transports → Add SIP Transport.
2. Campos:

| Campo | Descripción |
|------|------|
| **Description** | Descripción (p. ej. "UDP para usuarios remotos") |
| **Name** | Nombre único (p. ej. `transport-udp-nat`). Se valida como un contexto de Asterisk |
| **Protocol** | `UDP`, `TCP`, `TLS`, `WSS` |
| **Bind** | Dirección IP en la que escuchar (p. ej. `0.0.0.0:5060`) |
| **Local Nets** | Redes locales (separadas por comas, p. ej. `192.168.0.0/16,10.0.0.0/8`) |
| **External Media Address** | Dirección IP externa para el medio (NAT) |
| **External Signaling Address** | Dirección IP externa para la señalización (NAT) |

#### Configuración TLS (solo para el protocolo TLS)

| Campo | Descripción |
|------|------|
| **Method** | Método TLS (default, tlsv1, tlsv1_1, tlsv1_2, sslv2, sslv3, sslv23) |
| **Verify Server** | Verificar el servidor |
| **Allow Reload** | Permitir la recarga del certificado |
| **Cert File** | Contenido del certificado (se guarda en `ASTERISK_CONFIG_DIR/certificate/`) |
| **Priv Key File** | Contenido de la clave privada |
| **CA List File** | Cadena de CA |

### Recomendaciones

- Para uso general, crea un transporte UDP en el puerto 5060.
- Para soporte WebRTC, crea un transporte WSS.
- Cuando trabajes detrás de NAT, rellena `External Media/Signaling Address`.

---

## 7. Usuarios SIP

Los usuarios SIP son los abonados internos de la red telefónica. Corresponde al modelo `SIPUser`.

### Creación de un abonado

1. Panel de administración → PBX Setup → SIP Users → Add SIP User.
2. Campos:

| Campo | Descripción |
|------|------|
| **Name** | Nombre del abonado (se muestra en el sistema) |
| **Username** | Usuario de autenticación para el teléfono SIP |
| **Extension** | Número interno. Si se deja en blanco, se genera automáticamente |
| **Secret** | Contraseña para la autenticación SIP |
| **Transport** | Transporte PJSIP que usa el abonado |
| **Routing Table** | Tabla de enrutamiento para llamadas salientes |
| **NAT** | Habilitar el manejo de NAT para el abonado (booleano) |
| **Auth Type** | Tipo de autenticación: `userpass` o `md5` |
| **Allowed Extension** | Restringe desde qué extensión puede registrarse este abonado |
| **Custom Settings** | Configuración adicional para las secciones `endpoint`, `auth`, `aor` |

### Generación automática de extensión

Si el campo **Extension** se deja en blanco, el sistema genera automáticamente el siguiente número libre en formato `2XX`. El rango de búsqueda lo define la configuración de enrutamiento (`PEARLPBX_DEFAULT_ROUTING_PREFIX`).

### Campos de Custom Settings

Para parámetros de PJSIP que no están en el formulario principal, usa estos campos:

- **Custom Endpoint Settings** — parámetros adicionales para la sección `[endpoint]`.
- **Custom Auth Settings** — parámetros adicionales para la sección `[auth]`.
- **Custom AOR Settings** — parámetros adicionales para la sección `[aor]`.

Cada campo acepta texto en formato `parameter = value`, uno por línea. Estos valores se añaden a las secciones correspondientes del `pjsip.conf` generado.

---

## 8. Peers SIP (troncales)

Los peers SIP son conexiones externas con proveedores telefónicos u otras PBX. Corresponde al modelo `SIPPeer`.

### Creación de un troncal

1. Panel de administración → PBX Setup → SIP Peers → Add SIP Peer.
2. Campos:

#### Generic

| Campo | Descripción |
|------|------|
| **Name** | Nombre único del troncal |
| **Description** | Descripción (p. ej. "Operador Kyivstar") |
| **Transport** | Transporte para la conexión |
| **Routing Table** | Tabla de enrutamiento para llamadas salientes |

#### Authentication

| Campo | Descripción |
|------|------|
| **Username** | Usuario de autenticación en el lado del operador |
| **Contact User** | Usuario de contacto para la autenticación |
| **Auth Type** | `userpass` o `md5` |
| **Secret** | Contraseña |
| **Custom Auth Settings** | Parámetros adicionales de auth |

#### Connection

| Campo | Descripción |
|------|------|
| **Registration URI** | URI para registrarse con el operador (`sip:operator.ua:5060`) |
| **Contact URI** | URI al que dirigir las llamadas (`sip:operator.ua:5060`) |
| **Match Hosts** | Direcciones IP del operador para hacer coincidir llamadas entrantes (separadas por comas) |

**Formación del contacto AOR:** si **Contact URI** no está rellenado, el sistema usa **Registration URI** como contacto del AOR (con una advertencia en los registros — esto puede ser incorrecto si el registrador y el host de medios son distintos). Si no se rellena ninguno de los dos campos, el AOR queda sin contacto estático.

Cuando **Registration There** está habilitado, el AOR del troncal recibe de inmediato un contacto "bootstrap" (`max_contacts=1`, `remove_existing=yes`), incluso antes del primer registro exitoso — de lo contrario las llamadas salientes no tendrían adónde ir en el intervalo previo al REGISTER. Tras un REGISTER exitoso, este contacto se reemplaza por el que realmente envía el operador.

#### Registration

| Campo | Descripción |
|------|------|
| **Registration Here** | Registrarse en el lado de Asterisk (`True/False`) |
| **Registration There** | Registrarse en el lado del operador (`True/False`) |

#### Advanced (colapsado)

| Campo | Descripción |
|------|------|
| **NAT** | Habilitar el manejo de NAT para el troncal (booleano) |
| **Custom AOR Settings** | Parámetros adicionales del AOR |

### Grupos de troncales

Ver [Grupos de troncales](#9-grupos-de-troncales).

---

## 9. Grupos de troncales

Permiten agrupar varios troncales para failover — si el primer troncal no está disponible, la llamada se enruta automáticamente al siguiente. Corresponde al modelo `TrunkGroup`.

### Creación de un grupo

1. Panel de administración → PBX Setup → Trunk Groups → Add Trunk Group.
2. Campos:
   - **Name** — nombre del grupo.
   - **SIP Peers** — selecciona los troncales de la lista. El orden importa: el primer troncal tiene prioridad.

El manejo del grupo se realiza a través del servidor FastAGI (handler `dial-trunk-group`).

---

## 10. Plan de marcado (Dialplan)

El sistema usa la sintaxis AEL (Asterisk Extension Language) para el plan de marcado.

### Contextos (DialplanContext)

Un contexto es un grupo lógico de extensiones en el plan de marcado de Asterisk.

**Creación de un contexto:**

1. Panel de administración → PBX Setup → Dialplan Contexts → Add Dialplan Context.
2. Campos:
   - **Name** — nombre único del contexto. Los nombres de contextos y de tablas de enrutamiento comparten un mismo espacio de nombres.
   - **Description** — descripción.

**Nota:** Los contextos y las tablas de enrutamiento no pueden tener el mismo nombre.

### Extensiones (DialplanExtension)

Una extensión es un número o patrón individual dentro de un contexto, con un cuerpo de plan de marcado escrito en AEL.

**Creación de una extensión:**

1. Desde el contexto (inline) o directamente: PBX Setup → Dialplan Extensions → Add.
2. Campos:

| Campo | Descripción |
|------|------|
| **Context** | Contexto padre |
| **Ext** | Número o patrón (validación AEL) |
| **Dialplan** | Cuerpo de la extensión en AEL |
| **Description** | Descripción |

**Validación:** El campo `ext` se valida mediante `validate_asterisk_extension_prefix`. El plan de marcado se valida mediante `AsteriskDialplanValidator` para comprobar la sintaxis AEL.

**Ejemplo de plan de marcado:**

```ael
{
    Answer();
    Wait(1);
    Playback(hello);
    Hangup();
}
```

### Macros (DialplanMacro)

Los macros de AEL son bloques de plan de marcado reutilizables.

**Creación de un macro:**

1. Panel de administración → PBX Setup → Dialplan Macros → Add.
2. Campos: **Name**, **Description**, **Macro** (cuerpo del macro en AEL).

### Variables globales (DialplanGlobalVariable)

Permiten definir entradas con nombre que van al bloque `globals { }` al principio del
`extensions.ael` generado.

1. Panel de administración → PBX Setup → Dialplan Global Variables → Add.
2. Campos: **Name**, **Value**.
3. El nombre se valida como un identificador correcto; el valor no puede contener `;`
   ni saltos de línea.

### Nota sobre los nombres

Como `DialplanContext` y `RoutingTable` comparten un espacio de nombres, no se puede crear un contexto y una tabla de enrutamiento con el mismo nombre. El formulario de administración del contexto comprueba la unicidad mediante `DialplanContextAdminForm`.

---

## 11. Enrutamiento de llamadas

El enrutamiento de llamadas determina cómo se gestionan las llamadas salientes en función del prefijo del número.

### Tablas de enrutamiento (RoutingTable)

Una tabla de enrutamiento agrupa registros de enrutamiento. Los nombres de tabla comparten espacio de nombres con los contextos del plan de marcado.

**Creación:**

1. PBX Setup → Routing Tables → Add Routing Table.
2. **Name** — nombre de la tabla (único, no puede coincidir con un contexto).

### Registros de enrutamiento (RoutingRecord)

Cada registro define a qué contexto se enruta una llamada según el prefijo del número.

| Campo | Descripción |
|------|------|
| **Prefix** | Prefijo del número (p. ej. `_2XX` — internas, `_380` — Ucrania) |
| **Name** | Nombre del registro |
| **Context** | Contexto del plan de marcado a usar |
| **Routing Table** | Tabla de enrutamiento |

**Orden:** Los registros se procesan en el orden definido por el campo `name`. El sistema también admite la sintaxis AEL para prefijos (un `_` inicial indica un patrón).

**Registros típicos:**

| Prefix | Propósito |
|--------|-------------|
| `_2XX` | Extensiones internas |
| `_0[1-9]X.` | Llamadas locales |
| `_380` | Llamadas dentro de Ucrania |
| `_X.` | Todo lo demás (catch-all) |

---

## 12. Colas

### Creación de una cola

1. Panel de administración → PBX Setup → Queues → Add Queue.
2. Campos principales:

| Campo | Descripción |
|------|------|
| **Name** | Nombre único de la cola |
| **Strategy** | Estrategia de distribución de llamadas (`ringall`, `leastrecent`, `fewestcalls`, `random`, `rrmemory`, `rrordered`, `linear`, `wrandom`) |
| **Music Class** | Clase de MOH para la música en espera |

### Añadir miembros a la cola

**Añadir en bloque desde el formulario:**

1. En el formulario de la cola, busca la sección **Add Members**.
2. Selecciona usuarios SIP de la lista `Add SIP Users`.
3. Al guardar, se crea un registro `QueueMember` con interfaz `PJSIP/{username}` para cada usuario seleccionado.
4. Los miembros de cola ya existentes no se modifican.

**Añadir individualmente:**

- Usa el formulario inline **Queue members** en la página de la cola.
- O crea un registro directamente: PBX Setup → Queue Members → Add.

Campos de un miembro de cola:

| Campo | Descripción |
|------|------|
| **Member Name** | Nombre del agente (se muestra en el dashboard) |
| **Interface** | Interfaz del agente (p. ej. `PJSIP/101`) |
| **State Interface** | Interfaz usada para rastrear el estado |
| **Queue** | Cola |
| **Penalty** | Penalización (determina la prioridad) |
| **Ring In Use** | Llamar al agente aunque su interfaz ya esté ocupada con otra llamada |
| **Wrapuptime** | Tiempo de "postllamada" individual para este agente (sobrescribe el valor de la cola) |

### Queue Rules (reglas de cola)

Las reglas definen cómo cambian las penalizaciones de los agentes según cuánto tiempo lleva esperando una llamada en la cola.

**Creación de una regla:**

1. Panel de administración → PBX Setup → Queue Rules → Add Queue Rule.
2. Añade pasos de escalado (Penalty Changes):
   - **Seconds** — después de cuántos segundos aplicar la regla.
   - **Max Penalty** — penalización máxima.
   - **Min Penalty** — penalización mínima.
   - **Raise Penalty** — incremento de la penalización.
   - **Order** — orden de aplicación.

**Asociar una regla a una cola:**

En el formulario de la cola, sección **Queue Rules**, selecciona una regla de la lista `Default Rule`. El enlace `Edit Rule` abre la página de edición de la regla en una nueva pestaña.

### Anuncios de cola

Se configuran en la sección **Announcements** del formulario de la cola:

- **Announce** — archivo de sonido para el anuncio.
- **Queue Announce** — anuncio del nombre de la cola.
- **Queue Announcement** — elección del tipo de anuncio.
- **Announce Frequency** — frecuencia de los anuncios (seg).
- **Announce Holdtime** — anunciar el tiempo de espera.
- **Announce Position** — anunciar la posición en la cola.

### Configuración adicional (sección Advanced)

La sección colapsada **Advanced** expone todos los parámetros de colas de Asterisk:

- timeout, retry, maxlen, wrapuptime
- autopause, autopausedelay
- context, service_level, weight, autofill, ringinuse
- joinempty, leavewhenempty
- monitor_format
- timeoutpriority, timeoutrestart
- periodic_announce, random_periodic_announce
- setqueuevar
- y otros.

### Configuración global de colas (CallQueueGlobalSettings)

Disponible en el panel de administración: PBX Setup → Call Queue Global Settings. Aquí puedes definir parámetros globales que se aplican a todas las colas, incluyendo `shared_lastcall`, `setvar`, `persistent_members`, `autofill`, `monitor_type`, `negative_penalty_invalid`, `force_longest_waiting_caller`.

---

## 13. Música en espera (MOH)

### Clases de MOH (MusicOnHold)

1. Panel de administración → PBX Setup → Music On Hold → Add Music On Hold.
2. Campos:

| Campo | Descripción |
|------|------|
| **Name** | Nombre de la clase de MOH |
| **Mode** | Modo: `files` (reproducir archivos), `playlist` (lista de reproducción), `custom` |
| **Directory** | Directorio con los archivos |
| **Sort** | Orden de los archivos: `alpha`, `random`, `randstart` |

### Listas de reproducción MOH (MusicOnHoldPlaylistEntry)

Se añaden inline en el formulario de la clase MOH:

| Campo | Descripción |
|------|------|
| **File** | Nombre del archivo |
| **URL** | Dirección del stream (si está en modo playlist) |
| **MOH Class** | Clase de MOH |

---

## 14. Archivos de sonido

El sistema permite subir archivos de sonido para usarlos en el plan de marcado mediante el modelo `SoundFile`.

1. Panel de administración → PBX Setup → Sound Files → Add Sound File.
2. Campos:

| Campo | Descripción |
|------|------|
| **Language** | Idioma del archivo (p. ej. `uk`, `en`) |
| **Name** | Nombre del archivo (sin extensión) |
| **File** | Archivo de audio a subir |

Los archivos se almacenan mediante el backend personalizado `SoundsFileSystemStorage`, que copia los archivos al directorio correspondiente de Asterisk.

---

## 15. Apply Changes

**Apply Changes** es el mecanismo clave del sistema: genera los archivos de configuración de Asterisk a partir de la base de datos, crea una copia de seguridad y recarga Asterisk.

### Acceso

Apply Changes solo está disponible para un **superuser**. Ruta: `/admin/apply`.

### Proceso

1. **Revisar los cambios:** La página `/admin/apply` muestra todos los archivos de configuración que se generarán, con su contenido.
2. **Aplicar:** Marca la casilla "Apply Changes" y pulsa el botón.
3. **Copia de seguridad:** El sistema crea un archivo `tar.gz` de la configuración actual en `ASTERISK_BACKUP_DIR`.
4. **Generación de archivos:** Escribe los archivos en `ASTERISK_ROOT_DIR + ASTERISK_CONFIG_DIR`.
5. **Certificados TLS:** Si hay transportes TLS, los certificados se escriben en `{CONFIG_DIR}/certificate/`.
6. **Versionado:** Cada archivo se guarda en la BD (`ConfigurationFile`) con una versión. Si el contenido no ha cambiado, la versión no se incrementa.
7. **SystemConfiguration:** Se crea una instantánea de la configuración actual, referenciando todos los `ConfigurationFile`.
8. **Recarga de Asterisk:** Se ejecuta un comando AMI:
   - **Soft reload** — recarga de módulos (`module reload`).
   - **Hard restart** — reinicio completo de Asterisk (`restart gracefully`).

### Qué archivos se generan

| Archivo | Función generadora | Descripción |
|------|-------------------|------|
| `/etc/asterisk/pjsip.conf` | `make_pjsip_conf()` | Transportes, endpoints, auth, AOR, registros |
| `/etc/asterisk/extensions.ael` | `make_extensions_ael()` | Plan de marcado, macros, enrutamiento |
| `/etc/asterisk/queues.conf` | `make_queues_conf()` | Colas y configuración global |
| `/etc/asterisk/queuerules.conf` | `make_queuerules_conf()` | Reglas de escalado de colas |
| `/etc/asterisk/manager.conf` | `make_manager_conf()` | Usuarios AMI (managers) |
| `/etc/asterisk/musiconhold.conf` | `make_musiconhold_conf()` | Clases de MOH y listas de reproducción |
| Archivos adicionales | Definidos por el usuario | Mediante el modelo `ConfigurationFile` |

### Archivos de configuración personalizados (ConfigurationFile)

El modelo `ConfigurationFile` permite añadir archivos de configuración arbitrarios de Asterisk:

1. Panel de administración → PBX Setup → Configuration Files → Add.
2. Campos: **Name**, **Description**, **Path** (ruta relativa a `ASTERISK_ROOT_DIR`), **Content**.
3. En cada Apply Changes, los archivos con la versión más reciente se incluyen en el conjunto de configuración.

Esto permite gestionar archivos que no se generan automáticamente (p. ej. `features.conf`, `cdr.conf`, `logger.conf`).

### Ver el historial

Los modelos `ConfigurationFile` y `SystemConfiguration` guardan el historial de cambios. Cada SystemConfiguration es una instantánea del estado de la configuración en el momento del Apply, lo que permite rastrear qué archivos y en qué versiones se aplicaron. La instantánea también incluye referencias a archivos binarios (modelo `BinaryFile`, p. ej. certificados TLS) aplicados junto con las configuraciones de texto.

---

## 16. Servicios

El sistema incluye varios servicios independientes, cada uno ejecutándose como su propio proceso. Todos los servicios tienen su propio entorno virtual y unidad systemd.

### Información general

Todos los servicios se ejecutan como el usuario `asterisk`.

| Servicio | Unidad systemd | Puerto | Función |
|--------|-------------|------|-------------|
| Django | `PearlPBX2.service` | 8000 | Aplicación web |
| Dashboard Listener | `pearlpbx2-dashboard.service` | — | AMI → Redis |
| Callback Daemon | `pearlpbx2-callback.service` | — | Callbacks |
| FastAGI Server | `pearlpbx2-fastagi.service` | 4573 | Handlers de AGI |

**Nota:** las unidades se instalan y gestionan mediante Ansible (`ansible/roles/services/`); las plantillas de archivos `.service` en `services/` en la raíz del repositorio están desactualizadas y no coinciden con los nombres realmente desplegados.

### Dashboard Listener

**Directorio:** `services/dashboard/`

El servicio se conecta a Asterisk vía AMI y escucha todos los eventos, publicándolos en Redis Pub/Sub en el canal `asterisk:events`.

**Datos en Redis:**

| Clave | Descripción |
|------|------|
| `asterisk:channels:*` | Canales activos |
| `asterisk:channels:all` | Todos los canales (JSON) |
| `asterisk:queue:{name}` | Estado de la cola (agentes, llamadas) |
| `parking:uline:*` | Estado de los slots de parking |
| `statistics:*` | Estadísticas de llamadas |

**Ejecución:**

```bash
cd services/dashboard
source .python-venv/bin/activate
python dashboard_listener.py
```

**Comprobación del funcionamiento:**

```bash
systemctl status pearlpbx2-dashboard.service
journalctl -u pearlpbx2-dashboard.service -f
```

**Dependencias:** `redis`, `asterisk-ami`

**Notificaciones de Slack para llamadas perdidas (opcional):** el servicio puede enviar un mensaje agregado a Slack cuando los llamantes abandonan una cola sin respuesta. Todas las llamadas perdidas dentro de la ventana de debounce se agrupan en un único mensaje por cola. Se configura mediante variables en `services/dashboard/env`:

| Variable | Descripción | Valor por defecto |
|--------|------|-----------------|
| `SLACK_MISSED_CALL_WEBHOOK_URL` | URL del webhook entrante de Slack. Vacío deshabilita la función | — (deshabilitado) |
| `MISSED_CALL_DEBOUNCE_SECONDS` | Ventana para agrupar llamadas perdidas en un único mensaje | `60` |

### Callback Daemon

**Directorio:** `services/callback/`

El servicio monitorea la tabla `callback_number` en la base de datos. Cuando aparece un registro con estado `NEW`, el servicio:

1. Bloquea el registro mediante `SELECT FOR UPDATE SKIP LOCKED` (evitando condiciones de carrera en modo multiproceso).
2. Llama a AMI `Originate` para crear una llamada saliente.
3. Actualiza el estado a `PENDING`, `ANSWERED` o `BUSY`.

**Ejecución:**

```bash
cd services/callback
source .python-venv/bin/activate
python callback.py
```

**Parámetros:**

```bash
python callback.py --db_host=localhost --ami_user=admin --ami_pass=secret
python callback.py --process_count=4   # modo multiproceso
python callback.py --dump_config      # ver la configuración
```

**Dependencias:** `psycopg2-binary`, `asterisk-ami`, `requests`

### FastAGI Server

**Directorio:** `services/fastagi/`

Un servidor FastAGI construido sobre Twisted + StarPy. Escucha en el puerto 4573 y gestiona las solicitudes AGI de Asterisk.

**Handlers:**

| Handler | Función | Variable que se define |
|---------|-------------|--------------------------|
| `blacklist` | Comprobar un número contra la lista negra | `BLACKLISTED` (0/1) |
| `whitelist` | Comprobar un número contra la lista permitida | `WHITELISTED` (0/1) |
| `customlist` | Comprobar contra una lista con nombre | `CUSTOM_LISTED` (0/1) |
| `dial-trunk-group` | Llamar a través de un grupo de troncales (failover) | `TRUNK_GROUP_DIALLED` (0/1) |
| `mixmonitor` | Iniciar la grabación de la llamada | `MIXMONITOR` (0/1) |
| `add-callback` | Añadir una solicitud de callback | `CALLBACK_ADDED` (0/1) |
| `queue-status` | Comprobar la disponibilidad de la cola | `READYTORECEIVE`, `QUEUECALLERS` |
| `parking-uline` | Asignar un slot de parking | `ULINE` (número de slot o 0) |

**ULINE Redis Manager** — gestiona los slots de parking (1–199) mediante un script Lua atómico en Redis.

**Ejecución:**

```bash
cd services/fastagi
source venv/bin/activate
python fastagi.py
```

**Dependencias:** `twisted`, `starpy`, `psycopg2-binary`, `redis`

### Scripts AGI clásicos (notificaciones de Slack)

**Directorio:** `services/agi/`

A diferencia del FastAGI Server (un servicio independiente en el puerto 4573), estos son scripts AGI clásicos (`missed_call.py`, `unmatched_call.py`) que Asterisk ejecuta directamente desde el plan de marcado para notificaciones puntuales a Slack sobre llamadas perdidas y no coincidentes. La funcionalidad compartida (en particular `notify_slack()`) se extrae en `agi_common.py`.

**Configuración:** `/etc/PearlPBX/AGI/env`.

### Ejemplo de uso de FastAGI en el plan de marcado

```ael
context check_blacklist {
    _X. => {
        AGI(agi://127.0.0.1:4573/blacklist);
        if ("${BLACKLISTED}" = "1") {
            Hangup();
        }
    }
}
```

---

## 17. Webhooks (CRM)

Los webhooks permiten enviar automáticamente al sistema CRM solicitudes JSON POST sobre eventos de llamada: dos cadenas independientes — entrante (`call.incoming` → `call.answered`/`call.missed` → `call.ended`, llamadas desde el exterior o vía un troncal) y saliente (`call.outgoing` → `call.outgoing_answered` → `call.outgoing_ended`, llamadas iniciadas por un usuario SIP, nunca un troncal). Implementado en `apps/webhooks/` — la entrega la gestiona el Dashboard Listener a partir de eventos AMI.

**Una descripción detallada de los formatos de payload, la verificación de firma y ejemplos de handler** está en una guía dedicada: [crm-integration.md](crm-integration.md) (y una versión simplificada para desarrolladores de CRM: [crm-integrator-guide.md](crm-integrator-guide.md)). Esta sección solo cubre la configuración de un webhook en el panel de administración.

### Creación de un webhook

1. Panel de administración → Webhooks → Add Webhook.
2. Campos:

| Campo | Descripción |
|------|------|
| **Name** | Nombre único del webhook |
| **Description** | Descripción (para tu propia referencia) |
| **Is Active** | Habilitar/deshabilitar el envío sin eliminar la configuración |
| **URL** | Endpoint en el lado del CRM al que se envía el JSON POST |
| **Send Incoming** | Enviar un evento al inicio de una llamada entrante |
| **Send Ended** | Enviar un evento cuando finaliza una llamada entrante (requiere que Send Incoming esté habilitado, de lo contrario la llamada nunca fue "anunciada") |
| **Send Missed** | Enviar un evento cuando se pierde una llamada en una cola (requiere seleccionar al menos una cola) |
| **Send Answered** | Enviar un evento cuando un agente de la cola contesta una llamada (requiere seleccionar al menos una cola) |
| **Send Outgoing** | Enviar un evento cuando un usuario SIP inicia una llamada saliente (requiere seleccionar al menos una Routing table; nunca se dispara para un troncal) |
| **Send Outgoing Answered** | Enviar un evento cuando la parte llamada contesta (requiere que Send Outgoing esté habilitado) |
| **Send Outgoing Ended** | Enviar un evento cuando finaliza una llamada saliente (requiere que Send Outgoing esté habilitado) |
| **Contexts** | Contextos del plan de marcado cuyas llamadas entrantes disparan la cadena entrante (Send Incoming, etc.) |
| **Routing tables** | Tablas de enrutamiento de usuarios SIP cuyas llamadas salientes disparan la cadena saliente (Send Outgoing, etc.) |
| **Queues** | Colas cuyas incorporaciones disparan eventos de la cadena entrante relacionados con colas |
| **Headers** | Cabeceras HTTP adicionales en formato JSON (p. ej. `{"Authorization": "Bearer ..."}`) |
| **Secret** | Secreto compartido para la firma HMAC-SHA256 del cuerpo de la solicitud (cabecera `X-PearlPBX-Signature`) |
| **Timeout** | Tiempo de espera de la solicitud HTTP en segundos (por defecto 5) |
| **Retries** | Número de reintentos de entrega tras un fallo (por defecto 1) |
| **Payload Template** | Plantilla JSON personalizada para el cuerpo de la solicitud con sustituciones `${placeholder}`; al vaciar el campo se usa la plantilla predeterminada integrada para cada tipo de evento |

**Nota:** si un webhook no tiene ningún contexto, tabla de enrutamiento o cola seleccionados, el formulario de administración exige al menos uno de ellos (de lo contrario no está claro qué llamadas deberían disparar el envío). Los eventos entrantes (Send Incoming, etc.) requieren además Contexts o Queues; los eventos salientes (Send Outgoing, etc.) requieren Routing tables.

---

## 18. API REST

El sistema ofrece una API REST para integración externa. Documentación detallada: [API.md](API.md), además de un Swagger UI en vivo en `/api/v1/docs/` y un esquema OpenAPI en `/api/v1/schema/`.

Para la integración con sistemas CRM (webhooks de llamadas, sección 17 anterior) y el acceso a grabaciones de llamadas vía la API, consulta la guía dedicada: [crm-integration.md](crm-integration.md).

### Resumen breve

La API está construida sobre Django REST Framework (`DefaultRouter` + `ViewSet`s, `apps/api/`).

**URL base:** `/api/v1/`

**Autenticación:** basada en tokens vía DRF `TokenAuthentication` (cabecera `Authorization: Token <key>`). Ya no hay restricciones por IP. Un token se crea con:

```bash
python manage.py drf_create_token <username>
```

Sin un token válido, las solicitudes devuelven `401 Unauthorized`.

**Endpoints:**

| Endpoint | Métodos | Función |
|----------|--------|-------------|
| `/api/v1/blacklist/` | GET, POST | Listar / crear entradas de lista negra |
| `/api/v1/blacklist/<uuid>/` | GET, PUT, PATCH, DELETE | Ver / modificar / eliminar una entrada |
| `/api/v1/whitelist/` | GET, POST | Listar / crear números permitidos |
| `/api/v1/whitelist/<uuid>/` | GET, PUT, PATCH, DELETE | Ver / modificar / eliminar una entrada |
| `/api/v1/contacts/` | GET, POST | Listar / crear contactos |
| `/api/v1/contacts/<uuid>/` | GET, PUT, PATCH, DELETE | Ver / modificar / eliminar un contacto |
| `/api/v1/lists/` | GET, POST | Listar listas con nombre / crear una nueva |
| `/api/v1/lists/<uuid>/` | GET, PATCH, DELETE | Ver / renombrar / eliminar una lista |
| `/api/v1/lists/<uuid>/entries/` | GET, POST | Ver / añadir entradas a una lista |
| `/api/v1/lists/<uuid>/entries/<uuid>/` | DELETE | Eliminar una entrada de una lista |
| `/api/v1/calls/originate/` | POST | Iniciar una llamada saliente vía AMI (devuelve 503 si `DEVMODE=without_asterisk_on_localhost`) |
| `/api/v1/calls/conference/` | POST | Unir a varios participantes en una sala ConfBridge compartida vía AMI |
| `/api/v1/queues/members/pause/` | POST | Pausar/reanudar un miembro de cola vía AMI `QueuePause` |
| `/api/v1/queues/members/` | GET | Listar los miembros de una cola y su estado actual (opcional `?queue=<name>`) |
| `/api/v1/recordings/<uniqueid>/` | GET | Obtener el archivo de audio de una grabación de llamada (soporta solicitudes Range) |
| `/api/v1/docs/`, `/api/v1/redoc/`, `/api/v1/schema/` | GET | Swagger/Redoc UI y esquema OpenAPI |

**Códigos de estado:** 200, 201, 204, 400, 401, 404, 409.

**Formato de respuesta:** JSON.

---

## 19. Aprovisionamiento de teléfonos

El sistema admite la configuración automática de teléfonos SIP mediante TFTP.

### El modelo PhoneDevice

| Campo | Descripción |
|------|------|
| **MAC Address** | Dirección MAC del teléfono (única) |
| **SIP User** | Usuario SIP vinculado |
| **Telephone Type** | Tipo de teléfono: `spa502g`, `spa504g`, `gxp1200`, `softphone`, `webrtc`, `other` |
| **SIP Server** | Dirección del servidor SIP que recibirá el dispositivo en su configuración |

### Proceso de aprovisionamiento

1. Registra el teléfono en el sistema (añade un PhoneDevice).
2. Vincúlalo a un usuario SIP existente.
3. Los archivos de configuración se generan en el directorio `TFTP_DIR`.
4. El teléfono recibe su configuración vía TFTP al arrancar.

---

## 20. Mantenimiento

### Copias de seguridad

El sistema crea automáticamente una copia de seguridad en cada Apply Changes:

- Se guarda un archivo `tar.gz` en `ASTERISK_BACKUP_DIR`.
- Formato del nombre: `asterisk-{timestamp}.tar.gz`.
- La copia de seguridad incluye toda la configuración actual de Asterisk.

Además, la instalación con Ansible configura dos tareas cron diarias:

- **Copia de seguridad de PostgreSQL** (`bin/pg_backup_pearlpbx2.sh`) — diariamente a las 01:30.
- **Copia de seguridad de `/etc/asterisk`** (`bin/backup_asterisk.sh`) — diariamente a las 02:30. Archiva `/etc/asterisk`
  en un `tar.gz` y lo guarda en `BACKUP_DIR` (por defecto `/var/backups/asterisk-etc`) con un
  período de retención `RETENTION_DAYS` (por defecto 14 días). La configuración está en
  `/etc/PearlPBX/backup_asterisk/env` (plantilla `backup_asterisk.env.j2`); opcionalmente puedes definir
  `SLACK_WEBHOOK_URL` para notificaciones de fallo.

### Migración desde PearlPBX1

El directorio `migrate_from_PearlPBX1/` contiene scripts e instrucciones para migrar desde la primera versión del sistema.

### Actualización del sistema

Para actualizar, usa `update.sh`, o `git pull` seguido de la aplicación de migraciones:

```bash
git pull
source .python-venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
systemctl restart PearlPBX2
```

### Registro (logging)

El sistema registra eventos a través del mecanismo estándar de logging de Django:

- logger **core** — nivel INFO (reducido deliberadamente desde DEBUG, para evitar que los payloads de eventos AMI — que contienen caller ID/datos personales — terminen en journald).
- logger **django** — nivel INFO.
- logger **apps** — nivel INFO, `propagate=False`.
- logger **\_\_main\_\_** — nivel INFO.

Los registros se escriben en la consola (stdout). Para producción, se recomienda configurar el registro en un archivo o en un sistema de logging centralizado.

### Monitoreo de servicios

```bash
# Comprobar el estado de todos los servicios
systemctl status PearlPBX2.service pearlpbx2-dashboard.service pearlpbx2-callback.service pearlpbx2-fastagi.service asterisk.service

# Ver los registros
journalctl -u PearlPBX2.service -f
journalctl -u pearlpbx2-dashboard.service -f
journalctl -u pearlpbx2-callback.service -f
journalctl -u pearlpbx2-fastagi.service -f
```

---

*Documento creado para PearlPBX2 v2.7.2. La interfaz del sistema y las rutas pueden variar según la configuración.*
