*Also available in: [English](admin-guide.md) | [Українська](../ua/admin-guide.md) | [Español](../es/admin-guide.md)*

# PearlPBX2 Administrator Guide

**Version:** 2.7.2

---

## Contents

1. [Introduction](#1-introduction)
2. [System Architecture](#2-system-architecture)
3. [Installation (overview)](#3-installation-overview)
4. [Configuration via Environment Variables](#4-configuration-via-environment-variables)
5. [Users and Roles](#5-users-and-roles)
6. [SIP Transports](#6-sip-transports)
7. [SIP Users](#7-sip-users)
8. [SIP Peers (Trunks)](#8-sip-peers-trunks)
9. [Trunk Groups](#9-trunk-groups)
10. [Dialplan](#10-dialplan)
11. [Call Routing](#11-call-routing)
12. [Queues](#12-queues)
13. [Music on Hold (MOH)](#13-music-on-hold-moh)
14. [Sound Files](#14-sound-files)
15. [Apply Changes](#15-apply-changes)
16. [Services](#16-services)
17. [Webhooks (CRM)](#17-webhooks-crm)
18. [REST API](#18-rest-api)
19. [Phone Provisioning](#19-phone-provisioning)
20. [Maintenance](#20-maintenance)

---

## 1. Introduction

PearlPBX2 is a web-based management interface for Asterisk PBX, built on Django. The system lets you manage SIP endpoints, trunks, dialplan, routing, queues, and other Asterisk objects through a web interface, automatically generating Asterisk configuration files from the database.

### Key features

- Management of PJSIP transports, endpoints, and trunks
- Dialplan editor with AEL syntax support and validation
- Prefix-based call routing
- Queues with escalation, announcements, and global settings support
- Real-time operator dashboard (WebSocket)
- CDR, call recordings, queue logs
- Analytics with charts (Chart.js)
- Automated callbacks
- Phone provisioning (TFTP)
- REST API for external integration
- Apply Changes — config generation and Asterisk reload in one click

### Who is an administrator

An administrator is a user with **superuser** rights (is_superuser=True). Only a superuser can:

- apply configuration changes to Asterisk (`/admin/apply`);
- manage all PBX objects through the admin panel;
- create and edit other users.

Users with **staff** rights (is_staff=True) can view the admin panel, but without access to Apply Changes.

---

## 2. System Architecture

### General diagram

```
Browser ──WebSocket──► Django Channels ◄── Redis ◄── Dashboard Listener ◄── Asterisk AMI
Browser ──HTTP──────► Django (ASGI) ◄──── PostgreSQL
                            │
                            └──► /etc/asterisk/*.conf  (config generation)

Asterisk FastAGI ◄──────────► FastAGI Service (port 4573)
Callback daemon ─────────────► Asterisk AMI (outbound calls)
```

### Components

| Component | Purpose |
|-----------|---------|
| **Django (ASGI)** | Web application, HTTP + WebSocket, port 8000 |
| **PostgreSQL** | Database for all PBX objects |
| **Redis** | Message channel for WebSocket, queue/channel state storage |
| **Dashboard Listener** | Service that listens to Asterisk AMI events and publishes them to Redis |
| **Callback Daemon** | Service that monitors the DB callback queue and initiates calls via AMI |
| **FastAGI Server** | FastAGI service for dialplan handling (list checks, call recording, routing, parking) |

### Data flow

1. **Configuration:** Admin UI → Django Models → `core/conf.py` → `/etc/asterisk/*.conf` files → Asterisk reload
2. **Dashboard:** Asterisk AMI events → Dashboard Listener → Redis Pub/Sub → Django Channels → WebSocket → Browser
3. **Callback:** DB request → Callback Daemon (SELECT FOR UPDATE) → AMI Originate → outbound call
4. **FastAGI:** Asterisk dialplan → AGI(agi://localhost:4573/handler) → FastAGI server → channel variables

### Django components

| Module | Purpose |
|--------|---------|
| `core/` | Central models, config generator, validators, admin interface |
| `apps/dashboard/` | WebSocket operator dashboard |
| `apps/reports/` | CDR, recordings, logs, analytics |
| `apps/lists/` | CRUD for number lists |
| `apps/callback/` | Models and views for callbacks |
| `apps/provision/` | Phone provisioning |
| `apps/api/` | REST API |
| `apps/webhooks/` | Webhooks for CRM integration (call events) |

---

## 3. Installation (overview)

### System requirements

- **Python** 3.10+
- **Django** 5.2
- **PostgreSQL** 14+
- **Redis** 7+
- **Asterisk** 22+ (with `res_pjsip`, `res_agi`, `cdr_pgsql` modules)

### Quick start (development)

```bash
# Create a virtual environment
python3 -m venv .python-venv
source .python-venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp env.sample .env
# Edit .env — DB, AMI, DEVMODE, etc.

# Initialize the database
python manage.py migrate
python manage.py createsuperuser

# Run the development server
python manage.py runserver
```

### Production environment

```bash
# Via uvicorn (ASGI + WebSocket)
uvicorn pbx.asgi:application --host 0.0.0.0 --port 8000 --workers 3
```

**Important:** Django must run as the `asterisk` user to access `/etc/asterisk`.

### Detailed instructions

- Docker deployment: `docker-compose.yml` (django, asterisk, postgres, redis, fastagi, dashboard-listener, callback)
- Ansible deployment (recommended for bare-metal production): `ansible/install.yml` (9 roles: system, postgres, redis, asterisk, pearlpbx2, services, nginx, tftp, firewall)

### Operating modes (DEVMODE)

| Mode | Value | Description |
|------|-------|------|
| Production | `Production` | Secure cookies, no debug |
| Staging | `Staging` | Test server |
| Development | `Development` | Debug mode, development on a VPS |
| without_asterisk_on_localhost | `without_asterisk_on_localhost` | Local development without Asterisk |

---

## 4. Configuration via Environment Variables

All settings are supplied via environment variables. Example: [env.sample](../../env.sample).

### Required variables

| Variable | Description | Default |
|----------|------|-----------------|
| `DEVMODE` | Operating mode | `Development` |
| `DJANGO_SECRET_KEY` | Django secret key (required in Production) | — |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_NAME` | Database name | `pearlpbx2` |
| `DB_USER` | Database user | `pearlpbx2` |
| `DB_PASS` | Database password | — |
| `ASTERISK_MANAGER_HOST` | Asterisk AMI host | `127.0.0.1` |
| `ASTERISK_MANAGER_USERNAME` | AMI username | `django` |
| `ASTERISK_MANAGER_SECRET` | AMI password | — |

### Optional variables

| Variable | Description | Default |
|----------|------|-----------------|
| `ALLOWED_HOSTS` | Allowed hosts (comma-separated) | `127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Trusted CSRF origins | — |
| `ASTERISK_ROOT_DIR` | Asterisk root directory | `/tmp` |
| `ASTERISK_CONFIG_DIR` | Asterisk config directory | `/etc/asterisk` |
| `ASTERISK_BACKUP_DIR` | Backup directory | `/tmp/backup/asterisk` |
| `ASTERISK_MONITOR_DIR` | Call recordings directory | `/var/spool/asterisk/monitor` |
| `ASTERISK_BACKUP_MONITOR_DIR` | Recording backup directory (iSCSI) | — |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `TFTP_DIR` | TFTP provisioning directory | `/var/lib/tftpboot` |
| `DASHBOARD_MISSED_CALL_WINDOW_MINUTES` | Missed-call window | `0` (current day) |
| `PHONE_COUNTRY_CODE` | Country code for normalization | `380` |
| `PHONE_LOCAL_CODE` | City code | `044` |
| `PHONE_REQUIRED_LEN` | Expected full-number length during normalization | `10` |
| `PHONE_CITYCODE_LEN` | City code length during normalization | `7` |
| `PEARLPBX_PUBLIC_URL` | Public base URL of the web interface (used for call-recording links in CRM webhooks) | `http://localhost:8000` |

---

## 5. Users and Roles

### User groups

The system uses Django's standard user model.

#### The "Report Viewer" group

Users in this group have access to:

- Dashboard (`/dashboard/`)
- Parking (ULINE monitoring, `/dashboard/ulines/`)
- Reports (`/reports/`)
- Lists (`/lists/`)

Creating the group:

1. Admin panel → Authentication and Authorization → Groups → Add Group.
2. Name: `Report Viewer`.
3. Assign the necessary permissions (or none — access is controlled in code via `HEADER_MENU_PAGES`).

#### Django access levels

| Level | `is_superuser` | `is_staff` | Access |
|--------|---------------|------------|--------|
| Superuser | true | true | Full access, including Apply Changes |
| Staff | false | true | Admin panel (view/edit objects) |
| Report Viewer | false | false | Dashboard, Reports, Lists |
| Regular | false | false | Homepage only (if logged in) |

### Creating a user

1. Go to `/admin/auth/user/add/`.
2. Fill in **Username**, **Password**.
3. Click **Save and continue editing**.
4. On the **Permissions** tab:
   - **Superuser status** — check for full access.
   - **Staff status** — check for admin panel access.
5. On the **Groups** tab, add the user to the "Report Viewer" group (if needed).

### Navigation menu (HEADER_MENU_PAGES)

`settings.py` defines menu items tied to roles:

| Item | Role | URL |
|-------|------|-----|
| Dashboard | admin, superuser, Report Viewer | `/dashboard/` |
| Parking (ULINE) | admin, superuser, Report Viewer | `/dashboard/ulines/` |
| Reports | admin, superuser, Report Viewer | `/reports/` |
| Lists | admin, superuser, Report Viewer | `/lists/` |
| Admin panel | superuser | `/admin` |

---

## 6. SIP Transports

SIP transports define how Asterisk listens for and sends SIP traffic. Corresponds to the `SIPTransport` model.

### Creating a transport

1. Admin panel → PBX Setup → SIP Transports → Add SIP Transport.
2. Fields:

| Field | Description |
|------|------|
| **Description** | Description (e.g. "UDP for remote users") |
| **Name** | Unique name (e.g. `transport-udp-nat`). Validated as an Asterisk context |
| **Protocol** | `UDP`, `TCP`, `TLS`, `WSS` |
| **Bind** | IP address to listen on (e.g. `0.0.0.0:5060`) |
| **Local Nets** | Local networks (comma-separated, e.g. `192.168.0.0/16,10.0.0.0/8`) |
| **External Media Address** | External IP address for media (NAT) |
| **External Signaling Address** | External IP address for signaling (NAT) |

#### TLS settings (TLS protocol only)

| Field | Description |
|------|------|
| **Method** | TLS method (default, tlsv1, tlsv1_1, tlsv1_2, sslv2, sslv3, sslv23) |
| **Verify Server** | Verify the server |
| **Allow Reload** | Allow certificate reload |
| **Cert File** | Certificate content (stored in `ASTERISK_CONFIG_DIR/certificate/`) |
| **Priv Key File** | Private key content |
| **CA List File** | CA chain |

### Recommendations

- For general use, create a UDP transport on port 5060.
- For WebRTC support, create a WSS transport.
- When working behind NAT, fill in `External Media/Signaling Address`.

---

## 7. SIP Users

SIP users are the internal subscribers of the phone network. Corresponds to the `SIPUser` model.

### Creating a subscriber

1. Admin panel → PBX Setup → SIP Users → Add SIP User.
2. Fields:

| Field | Description |
|------|------|
| **Name** | Subscriber's name (shown in the system) |
| **Username** | Authentication username for the SIP phone |
| **Extension** | Internal number. If left blank, one is generated automatically |
| **Secret** | Password for SIP authentication |
| **Transport** | PJSIP transport the subscriber uses |
| **Routing Table** | Routing table for outbound calls |
| **NAT** | Enable NAT handling for the subscriber (boolean) |
| **Auth Type** | Authentication type: `userpass` or `md5` |
| **Allowed Extension** | Restricts which extension this subscriber is allowed to register from |
| **Custom Settings** | Additional settings for the `endpoint`, `auth`, `aor` sections |

### Automatic extension generation

If the **Extension** field is left blank, the system automatically generates the next free number in `2XX` format. The search range is defined by the routing settings (`PEARLPBX_DEFAULT_ROUTING_PREFIX`).

### Custom Settings fields

For PJSIP parameters not present on the main form, use these fields:

- **Custom Endpoint Settings** — additional parameters for the `[endpoint]` section.
- **Custom Auth Settings** — additional parameters for the `[auth]` section.
- **Custom AOR Settings** — additional parameters for the `[aor]` section.

Each field accepts text in `parameter = value` format, one per line. These values are appended to the corresponding sections of the generated `pjsip.conf`.

---

## 8. SIP Peers (Trunks)

SIP peers are external connections to telephone providers or other PBXs. Corresponds to the `SIPPeer` model.

### Creating a trunk

1. Admin panel → PBX Setup → SIP Peers → Add SIP Peer.
2. Fields:

#### Generic

| Field | Description |
|------|------|
| **Name** | Unique trunk name |
| **Description** | Description (e.g. "Kyivstar carrier") |
| **Transport** | Transport for the connection |
| **Routing Table** | Routing table for outbound calls |

#### Authentication

| Field | Description |
|------|------|
| **Username** | Authentication username on the provider's side |
| **Contact User** | Contact user for authentication |
| **Auth Type** | `userpass` or `md5` |
| **Secret** | Password |
| **Custom Auth Settings** | Additional auth parameters |

#### Connection

| Field | Description |
|------|------|
| **Registration URI** | URI to register with the provider (`sip:operator.ua:5060`) |
| **Contact URI** | URI to send calls to (`sip:operator.ua:5060`) |
| **Match Hosts** | Provider IP addresses for matching inbound calls (comma-separated) |

**Building the AOR contact:** if **Contact URI** is not filled in, the system uses **Registration URI** as the AOR contact instead (with a warning in the logs — this may be incorrect if the registrar and media host differ). If neither field is filled in, the AOR is left without a static contact.

When **Registration There** is enabled, the trunk's AOR immediately gets a "bootstrap" contact (`max_contacts=1`, `remove_existing=yes`), even before the first successful registration — otherwise outbound calls have nowhere to go in the interval before REGISTER. After a successful REGISTER, this contact is replaced by the one actually sent by the provider.

#### Registration

| Field | Description |
|------|------|
| **Registration Here** | Register on Asterisk's side (`True/False`) |
| **Registration There** | Register on the provider's side (`True/False`) |

#### Advanced (collapsed)

| Field | Description |
|------|------|
| **NAT** | Enable NAT handling for the trunk (boolean) |
| **Custom AOR Settings** | Additional AOR parameters |

### Trunk groups

See [Trunk Groups](#9-trunk-groups).

---

## 9. Trunk Groups

Let you group several trunks together for failover — if the first trunk is unreachable, the call is automatically routed to the next one. Corresponds to the `TrunkGroup` model.

### Creating a group

1. Admin panel → PBX Setup → Trunk Groups → Add Trunk Group.
2. Fields:
   - **Name** — group name.
   - **SIP Peers** — select trunks from the list. Order matters: the first trunk has priority.

Group handling is done through the FastAGI server (`dial-trunk-group` handler).

---

## 10. Dialplan

The system uses AEL (Asterisk Extension Language) syntax for the dialplan.

### Contexts (DialplanContext)

A context is a logical group of extensions in the Asterisk dialplan.

**Creating a context:**

1. Admin panel → PBX Setup → Dialplan Contexts → Add Dialplan Context.
2. Fields:
   - **Name** — unique context name. Context names and routing table names share a single namespace.
   - **Description** — description.

**Note:** Contexts and routing tables cannot share the same name.

### Extensions (DialplanExtension)

An extension is an individual number or pattern within a context, with a dialplan body written in AEL.

**Creating an extension:**

1. From the context (inline) or directly: PBX Setup → Dialplan Extensions → Add.
2. Fields:

| Field | Description |
|------|------|
| **Context** | Parent context |
| **Ext** | Number or pattern (AEL validation) |
| **Dialplan** | Extension body in AEL |
| **Description** | Description |

**Validation:** The `ext` field is validated by `validate_asterisk_extension_prefix`. The dialplan is validated by `AsteriskDialplanValidator` to check AEL syntax.

**Example dialplan:**

```ael
{
    Answer();
    Wait(1);
    Playback(hello);
    Hangup();
}
```

### Macros (DialplanMacro)

AEL macros are reusable dialplan blocks.

**Creating a macro:**

1. Admin panel → PBX Setup → Dialplan Macros → Add.
2. Fields: **Name**, **Description**, **Macro** (macro body in AEL).

### Global variables (DialplanGlobalVariable)

Let you define named entries that go into the `globals { }` block at the top of the
generated `extensions.ael`.

1. Admin panel → PBX Setup → Dialplan Global Variables → Add.
2. Fields: **Name**, **Value**.
3. The name is validated as a valid identifier; the value cannot contain `;`
   or line breaks.

### A note on names

Because `DialplanContext` and `RoutingTable` share a namespace, you cannot create a context and a routing table with the same name. The context admin form checks uniqueness via `DialplanContextAdminForm`.

---

## 11. Call Routing

Call routing determines how outbound calls are handled based on the number prefix.

### Routing tables (RoutingTable)

A routing table groups routing records. Table names share a namespace with dialplan contexts.

**Creating one:**

1. PBX Setup → Routing Tables → Add Routing Table.
2. **Name** — table name (unique, cannot match a context name).

### Routing records (RoutingRecord)

Each record defines which context a call is routed to based on the number prefix.

| Field | Description |
|------|------|
| **Prefix** | Number prefix (e.g. `_2XX` — internal, `_380` — Ukraine) |
| **Name** | Record name |
| **Context** | Dialplan context for handling |
| **Routing Table** | Routing table |

**Ordering:** Records are processed in the order defined by the `name` field. The system also supports AEL syntax for prefixes (a leading `_` denotes a pattern).

**Typical records:**

| Prefix | Purpose |
|--------|-------------|
| `_2XX` | Internal extensions |
| `_0[1-9]X.` | Local calls |
| `_380` | Calls within Ukraine |
| `_X.` | Everything else (catch-all) |

---

## 12. Queues

### Creating a queue

1. Admin panel → PBX Setup → Queues → Add Queue.
2. Main fields:

| Field | Description |
|------|------|
| **Name** | Unique queue name |
| **Strategy** | Call distribution strategy (`ringall`, `leastrecent`, `fewestcalls`, `random`, `rrmemory`, `rrordered`, `linear`, `wrandom`) |
| **Music Class** | MOH class for on-hold music |

### Adding queue members

**Bulk add via the form:**

1. In the queue form, find the **Add Members** section.
2. Select SIP users from the `Add SIP Users` list.
3. On save, a `QueueMember` record with interface `PJSIP/{username}` is created for each selected user.
4. Existing queue members are left unchanged.

**Adding individually:**

- Use the inline **Queue members** form on the queue page.
- Or create a record directly: PBX Setup → Queue Members → Add.

Queue member fields:

| Field | Description |
|------|------|
| **Member Name** | Agent's name (shown in the dashboard) |
| **Interface** | Agent's interface (e.g. `PJSIP/101`) |
| **State Interface** | Interface used to track state |
| **Queue** | Queue |
| **Penalty** | Penalty (determines priority) |
| **Ring In Use** | Ring the agent even if their interface is already busy with another call |
| **Wrapuptime** | Individual "wrap-up time" for this agent (overrides the queue's value) |

### Queue Rules

Rules define how agents' penalties change based on how long a call has waited in the queue.

**Creating a rule:**

1. Admin panel → PBX Setup → Queue Rules → Add Queue Rule.
2. Add escalation steps (Penalty Changes):
   - **Seconds** — after how many seconds to apply the rule.
   - **Max Penalty** — maximum penalty.
   - **Min Penalty** — minimum penalty.
   - **Raise Penalty** — penalty increase.
   - **Order** — order of application.

**Attaching a rule to a queue:**

In the queue form, **Queue Rules** section, select a rule from the `Default Rule` list. The `Edit Rule` link opens the rule's edit page in a new tab.

### Queue announcements

Configured in the **Announcements** section of the queue form:

- **Announce** — sound file for the announcement.
- **Queue Announce** — announcement of the queue name.
- **Queue Announcement** — choice of announcement type.
- **Announce Frequency** — announcement frequency (sec).
- **Announce Holdtime** — announce hold time.
- **Announce Position** — announce position in the queue.

### Additional settings (Advanced section)

The collapsed **Advanced** section exposes all of Asterisk's queue parameters:

- timeout, retry, maxlen, wrapuptime
- autopause, autopausedelay
- context, service_level, weight, autofill, ringinuse
- joinempty, leavewhenempty
- monitor_format
- timeoutpriority, timeoutrestart
- periodic_announce, random_periodic_announce
- setqueuevar
- and others.

### Global queue settings (CallQueueGlobalSettings)

Available via the admin panel: PBX Setup → Call Queue Global Settings. Here you can set global parameters that apply to all queues, including `shared_lastcall`, `setvar`, `persistent_members`, `autofill`, `monitor_type`, `negative_penalty_invalid`, `force_longest_waiting_caller`.

---

## 13. Music on Hold (MOH)

### MOH classes (MusicOnHold)

1. Admin panel → PBX Setup → Music On Hold → Add Music On Hold.
2. Fields:

| Field | Description |
|------|------|
| **Name** | MOH class name |
| **Mode** | Mode: `files` (play files), `playlist` (playlist), `custom` |
| **Directory** | Directory with files |
| **Sort** | File sort order: `alpha`, `random`, `randstart` |

### MOH playlists (MusicOnHoldPlaylistEntry)

Added inline in the MOH class form:

| Field | Description |
|------|------|
| **File** | File name |
| **URL** | Stream address (if in playlist mode) |
| **MOH Class** | MOH class |

---

## 14. Sound Files

The system lets you upload sound files for use in the dialplan via the `SoundFile` model.

1. Admin panel → PBX Setup → Sound Files → Add Sound File.
2. Fields:

| Field | Description |
|------|------|
| **Language** | File language (e.g. `uk`, `en`) |
| **Name** | File name (without extension) |
| **File** | Audio file to upload |

Files are stored via the custom `SoundsFileSystemStorage` backend, which copies files into the appropriate Asterisk directory.

---

## 15. Apply Changes

**Apply Changes** is the system's key mechanism: it generates Asterisk configuration files from the database, creates a backup, and reloads Asterisk.

### Access

Apply Changes is available only to a **superuser**. Path: `/admin/apply`.

### Process

1. **Review changes:** The `/admin/apply` page shows all configuration files that will be generated, with their content.
2. **Apply:** Check the "Apply Changes" box and click the button.
3. **Backup:** The system creates a `tar.gz` archive of the current configuration in `ASTERISK_BACKUP_DIR`.
4. **File generation:** Writes files into `ASTERISK_ROOT_DIR + ASTERISK_CONFIG_DIR`.
5. **TLS certificates:** If there are TLS transports, certificates are written to `{CONFIG_DIR}/certificate/`.
6. **Versioning:** Each file is stored in the DB (`ConfigurationFile`) with a version. If the content hasn't changed, the version isn't incremented.
7. **SystemConfiguration:** A snapshot of the current configuration is created, referencing all `ConfigurationFile` rows.
8. **Asterisk reload:** An AMI command is run:
   - **Soft reload** — module reload (`module reload`).
   - **Hard restart** — full Asterisk restart (`restart gracefully`).

### Which files are generated

| File | Generator function | Description |
|------|-------------------|------|
| `/etc/asterisk/pjsip.conf` | `make_pjsip_conf()` | Transports, endpoints, auth, AOR, registrations |
| `/etc/asterisk/extensions.ael` | `make_extensions_ael()` | Dialplan, macros, routing |
| `/etc/asterisk/queues.conf` | `make_queues_conf()` | Queues and global settings |
| `/etc/asterisk/queuerules.conf` | `make_queuerules_conf()` | Queue escalation rules |
| `/etc/asterisk/manager.conf` | `make_manager_conf()` | AMI users (managers) |
| `/etc/asterisk/musiconhold.conf` | `make_musiconhold_conf()` | MOH classes and playlists |
| Additional files | User-defined | Via the `ConfigurationFile` model |

### Custom configuration files (ConfigurationFile)

The `ConfigurationFile` model lets you add arbitrary Asterisk configuration files:

1. Admin panel → PBX Setup → Configuration Files → Add.
2. Fields: **Name**, **Description**, **Path** (relative to `ASTERISK_ROOT_DIR`), **Content**.
3. On every Apply Changes, the files with the latest version are included in the config set.

This lets you manage files that aren't generated automatically (e.g. `features.conf`, `cdr.conf`, `logger.conf`).

### Viewing history

The `ConfigurationFile` and `SystemConfiguration` models store change history. Each SystemConfiguration is a snapshot of the configuration state at the moment of Apply, letting you trace which files and versions were applied and when. The snapshot also includes references to binary files (the `BinaryFile` model, e.g. TLS certificates) applied together with the text configs.

---

## 16. Services

The system includes several standalone services, each running as its own process. All services have their own virtual environment and systemd unit.

### General information

All services run as the `asterisk` user.

| Service | systemd unit | Port | Purpose |
|--------|-------------|------|-------------|
| Django | `PearlPBX2.service` | 8000 | Web application |
| Dashboard Listener | `pearlpbx2-dashboard.service` | — | AMI → Redis |
| Callback Daemon | `pearlpbx2-callback.service` | — | Callbacks |
| FastAGI Server | `pearlpbx2-fastagi.service` | 4573 | AGI handlers |

**Note:** the units are installed and managed via Ansible (`ansible/roles/services/`); the `.service` file templates under `services/` at the repo root are stale and don't match the names actually deployed.

### Dashboard Listener

**Directory:** `services/dashboard/`

The service connects to Asterisk via AMI and listens to all events, publishing them to Redis Pub/Sub on the `asterisk:events` channel.

**Data in Redis:**

| Key | Description |
|------|------|
| `asterisk:channels:*` | Active channels |
| `asterisk:channels:all` | All channels (JSON) |
| `asterisk:queue:{name}` | Queue state (agents, calls) |
| `parking:uline:*` | Parking slot state |
| `statistics:*` | Call statistics |

**Running it:**

```bash
cd services/dashboard
source .python-venv/bin/activate
python dashboard_listener.py
```

**Checking it's running:**

```bash
systemctl status pearlpbx2-dashboard.service
journalctl -u pearlpbx2-dashboard.service -f
```

**Dependencies:** `redis`, `asterisk-ami`

**Slack notifications for missed calls (optional):** the service can send an aggregated Slack message when callers leave a queue unanswered. All missed calls within the debounce window are grouped into a single message per queue. Configured via variables in `services/dashboard/env`:

| Variable | Description | Default |
|--------|------|-----------------|
| `SLACK_MISSED_CALL_WEBHOOK_URL` | Slack incoming webhook URL. Empty disables the feature | — (disabled) |
| `MISSED_CALL_DEBOUNCE_SECONDS` | Window for grouping missed calls into a single message | `60` |

### Callback Daemon

**Directory:** `services/callback/`

The service monitors the `callback_number` table in the database. When a record with status `NEW` appears, the service:

1. Locks the record via `SELECT FOR UPDATE SKIP LOCKED` (preventing race conditions in multiprocessing mode).
2. Calls AMI `Originate` to create an outbound call.
3. Updates the status to `PENDING`, `ANSWERED`, or `BUSY`.

**Running it:**

```bash
cd services/callback
source .python-venv/bin/activate
python callback.py
```

**Parameters:**

```bash
python callback.py --db_host=localhost --ami_user=admin --ami_pass=secret
python callback.py --process_count=4   # multiprocess mode
python callback.py --dump_config      # preview configuration
```

**Dependencies:** `psycopg2-binary`, `asterisk-ami`, `requests`

### FastAGI Server

**Directory:** `services/fastagi/`

A FastAGI server built on Twisted + StarPy. Listens on port 4573 and handles AGI requests from Asterisk.

**Handlers:**

| Handler | Purpose | Variable set |
|---------|-------------|--------------------------|
| `blacklist` | Check a number against the blocklist | `BLACKLISTED` (0/1) |
| `whitelist` | Check a number against the allowlist | `WHITELISTED` (0/1) |
| `customlist` | Check against a named list | `CUSTOM_LISTED` (0/1) |
| `dial-trunk-group` | Call via a trunk group (failover) | `TRUNK_GROUP_DIALLED` (0/1) |
| `mixmonitor` | Start call recording | `MIXMONITOR` (0/1) |
| `add-callback` | Add a callback request | `CALLBACK_ADDED` (0/1) |
| `queue-status` | Check queue availability | `READYTORECEIVE`, `QUEUECALLERS` |
| `parking-uline` | Allocate a parking slot | `ULINE` (slot number or 0) |

**ULINE Redis Manager** — manages parking slots (1–199) via an atomic Lua script in Redis.

**Running it:**

```bash
cd services/fastagi
source venv/bin/activate
python fastagi.py
```

**Dependencies:** `twisted`, `starpy`, `psycopg2-binary`, `redis`

### Classic AGI scripts (Slack notifications)

**Directory:** `services/agi/`

Unlike the FastAGI Server (a separate service on port 4573), these are classic AGI scripts (`missed_call.py`, `unmatched_call.py`) that Asterisk runs directly from the dialplan for point-specific Slack notifications about missed and unmatched calls. Shared functionality (notably `notify_slack()`) is factored out into `agi_common.py`.

**Configuration:** `/etc/PearlPBX/AGI/env`.

### Example of using FastAGI in the dialplan

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

Webhooks let you automatically send a CRM system JSON POST requests about call events: two independent chains — inbound (`call.incoming` → `call.answered`/`call.missed` → `call.ended`, calls from outside or via a trunk) and outbound (`call.outgoing` → `call.outgoing_answered` → `call.outgoing_ended`, calls initiated by a SIP user, never a trunk). Implemented in `apps/webhooks/` — delivery is handled by the Dashboard Listener based on AMI events.

**A detailed description of payload formats, signature verification, and handler examples** is in a dedicated guide: [crm-integration.md](crm-integration.md) (and a simplified version for CRM developers: [crm-integrator-guide.md](crm-integrator-guide.md)). This section covers only setting up a webhook in the admin panel.

### Creating a webhook

1. Admin panel → Webhooks → Add Webhook.
2. Fields:

| Field | Description |
|------|------|
| **Name** | Unique webhook name |
| **Description** | Description (for your own reference) |
| **Is Active** | Enable/disable sending without deleting the configuration |
| **URL** | Endpoint on the CRM side where the JSON POST is sent |
| **Send Incoming** | Send an event at the start of an inbound call |
| **Send Ended** | Send an event when an inbound call ends (requires Send Incoming to be enabled, otherwise the call was never "announced") |
| **Send Missed** | Send an event when a call is missed in a queue (requires at least one queue to be selected) |
| **Send Answered** | Send an event when a queue agent answers a call (requires at least one queue to be selected) |
| **Send Outgoing** | Send an event when a SIP user initiates an outbound call (requires at least one Routing table to be selected; never fires for a trunk) |
| **Send Outgoing Answered** | Send an event when the called party picks up (requires Send Outgoing to be enabled) |
| **Send Outgoing Ended** | Send an event when an outbound call ends (requires Send Outgoing to be enabled) |
| **Contexts** | Dialplan contexts whose inbound calls trigger the inbound chain (Send Incoming, etc.) |
| **Routing tables** | Routing tables of SIP users whose outbound calls trigger the outbound chain (Send Outgoing, etc.) |
| **Queues** | Queues whose joins trigger queue-related inbound-chain events |
| **Headers** | Extra HTTP headers as JSON (e.g. `{"Authorization": "Bearer ..."}`) |
| **Secret** | Shared secret for the HMAC-SHA256 signature of the request body (`X-PearlPBX-Signature` header) |
| **Timeout** | HTTP request timeout in seconds (default 5) |
| **Retries** | Number of retry attempts after a failed delivery (default 1) |
| **Payload Template** | Custom JSON template for the request body with `${placeholder}` substitutions; clearing the field falls back to the built-in default template for each event type |

**Note:** if a webhook has no context, routing table, or queue selected, the admin form requires at least one of them (otherwise it's unclear which calls should trigger delivery). Inbound events (Send Incoming, etc.) additionally require Contexts or Queues; outbound events (Send Outgoing, etc.) require Routing tables.

---

## 18. REST API

The system provides a REST API for external integration. Detailed documentation: [API.md](API.md), plus a live Swagger UI at `/api/v1/docs/` and an OpenAPI schema at `/api/v1/schema/`.

For CRM system integration (call webhooks, section 17 above) and access to call recordings via the API, see the dedicated guide: [crm-integration.md](crm-integration.md).

### Brief overview

The API is built on Django REST Framework (`DefaultRouter` + `ViewSet`s, `apps/api/`).

**Base URL:** `/api/v1/`

**Authentication:** token-based via DRF `TokenAuthentication` (header `Authorization: Token <key>`). There are no more IP-based restrictions. A token is created with:

```bash
python manage.py drf_create_token <username>
```

Without a valid token, requests return `401 Unauthorized`.

**Endpoints:**

| Endpoint | Methods | Purpose |
|----------|--------|-------------|
| `/api/v1/blacklist/` | GET, POST | List / create blocklist entries |
| `/api/v1/blacklist/<uuid>/` | GET, PUT, PATCH, DELETE | View / update / delete an entry |
| `/api/v1/whitelist/` | GET, POST | List / create allowed numbers |
| `/api/v1/whitelist/<uuid>/` | GET, PUT, PATCH, DELETE | View / update / delete an entry |
| `/api/v1/contacts/` | GET, POST | List / create contacts |
| `/api/v1/contacts/<uuid>/` | GET, PUT, PATCH, DELETE | View / update / delete a contact |
| `/api/v1/lists/` | GET, POST | List named lists / create a new one |
| `/api/v1/lists/<uuid>/` | GET, PATCH, DELETE | View / rename / delete a list |
| `/api/v1/lists/<uuid>/entries/` | GET, POST | View / add entries to a list |
| `/api/v1/lists/<uuid>/entries/<uuid>/` | DELETE | Remove an entry from a list |
| `/api/v1/calls/originate/` | POST | Initiate an outbound call via AMI (returns 503 if `DEVMODE=without_asterisk_on_localhost`) |
| `/api/v1/calls/conference/` | POST | Bring several participants into a shared ConfBridge room via AMI |
| `/api/v1/queues/members/pause/` | POST | Pause/unpause a queue member via AMI `QueuePause` |
| `/api/v1/queues/members/` | GET | List queue members and their current state (optional `?queue=<name>`) |
| `/api/v1/recordings/<uniqueid>/` | GET | Fetch a call recording audio file (supports Range requests) |
| `/api/v1/docs/`, `/api/v1/redoc/`, `/api/v1/schema/` | GET | Swagger/Redoc UI and OpenAPI schema |

**Status codes:** 200, 201, 204, 400, 401, 404, 409.

**Response format:** JSON.

---

## 19. Phone Provisioning

The system supports automatic SIP phone configuration via TFTP.

### The PhoneDevice model

| Field | Description |
|------|------|
| **MAC Address** | Phone's MAC address (unique) |
| **SIP User** | Linked SIP user |
| **Telephone Type** | Phone type: `spa502g`, `spa504g`, `gxp1200`, `softphone`, `webrtc`, `other` |
| **SIP Server** | SIP server address the device will receive in its configuration |

### Provisioning process

1. Register the phone in the system (add a PhoneDevice).
2. Link it to an existing SIP user.
3. Configuration files are generated into the `TFTP_DIR` directory.
4. The phone gets its configuration via TFTP on boot.

---

## 20. Maintenance

### Backups

The system automatically creates a backup on every Apply Changes:

- A `tar.gz` archive is stored in `ASTERISK_BACKUP_DIR`.
- Filename format: `asterisk-{timestamp}.tar.gz`.
- The backup includes the entire current Asterisk configuration.

In addition, the Ansible installation sets up two daily cron jobs:

- **PostgreSQL backup** (`bin/pg_backup_pearlpbx2.sh`) — daily at 01:30.
- **`/etc/asterisk` backup** (`bin/backup_asterisk.sh`) — daily at 02:30. Archives `/etc/asterisk`
  into a `tar.gz` and stores it in `BACKUP_DIR` (default `/var/backups/asterisk-etc`) with a
  `RETENTION_DAYS` retention period (default 14 days). Configuration lives at
  `/etc/PearlPBX/backup_asterisk/env` (template `backup_asterisk.env.j2`); you can optionally set
  `SLACK_WEBHOOK_URL` for failure notifications.

### Migrating from PearlPBX1

The `migrate_from_PearlPBX1/` directory contains scripts and instructions for migrating from the first version of the system.

### Updating the system

To update, use `update.sh`, or `git pull` followed by applying migrations:

```bash
git pull
source .python-venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
systemctl restart PearlPBX2
```

### Logging

The system logs events through Django's standard logging mechanism:

- **core** logger — INFO level (deliberately lowered from DEBUG, to avoid AMI event payloads — which contain caller ID/PII — landing in journald).
- **django** logger — INFO level.
- **apps** logger — INFO level, `propagate=False`.
- **\_\_main\_\_** logger — INFO level.

Logs are written to the console (stdout). For production, it's recommended to configure logging to a file or a centralized logging system.

### Monitoring services

```bash
# Check the status of all services
systemctl status PearlPBX2.service pearlpbx2-dashboard.service pearlpbx2-callback.service pearlpbx2-fastagi.service asterisk.service

# View logs
journalctl -u PearlPBX2.service -f
journalctl -u pearlpbx2-dashboard.service -f
journalctl -u pearlpbx2-callback.service -f
journalctl -u pearlpbx2-fastagi.service -f
```

---

*Document created for PearlPBX2 v2.7.2. The system's interface and paths may vary depending on configuration.*
