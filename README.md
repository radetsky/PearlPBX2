# PearlPBX2 `v2.7.2`

[![License: PolyForm Shield 1.0.0](https://img.shields.io/badge/License-PolyForm%20Shield%201.0.0-blue.svg)](https://polyformproject.org/licenses/shield/1.0.0)
[![Quick Start](https://img.shields.io/badge/docs-Quick%20Start-brightgreen.svg)](docs/en/quickstart.md)

Web-based management interface for [Asterisk PBX](https://www.asterisk.org/), built with Django. Manages SIP endpoints, call routing, queues, and dialplan through a web UI — and generates Asterisk configuration files directly from the database.

## Features

- **Welcome dashboard** — live system status on the home page: DB counts, Asterisk version/uptime, active calls, queue occupancy, 14-day CDR chart, quick navigation links
- **SIP management** — PJSIP transports, endpoints (users), trunks (peers)
- **Dialplan editor** — contexts and extensions in Asterisk AEL syntax with validation
- **Call routing** — prefix-based routing tables
- **Queue management** — queues, members, rules, announcements
- **Real-time operator dashboard** — dark-theme live dashboard (`/dashboard/live/`) with five tabs: Overview, Queues, PJSIP, Bridged, Channels; WebSocket status indicator, hangup actions, queue agent info in call modal, agent state restored after Asterisk restart; old dashboard preserved at `/dashboard/old/`
- **CDR & reports** — call detail records with direction/channel filters, queue logs, callback reports with duration and recordings, call recordings browser
- **Analytics reports** — queue calls, calls by destination number, agent calls, outbound calls, missed calls (with link to queue log), missed by hour, call duration, queue activity (hourly/daily, exclude-contacts filter) with Chart.js charts
- **Callback queue** — automated outbound callback system with configurable AMI timeout (`--ami_timeout`)
- **Phone provisioning** — TFTP-based autoconfiguration for SIP phones
- **Lists** — web CRUD UI for Blocklist, Allowlist, and Contacts; accessible to Report Viewer group without admin access
- **REST API** — DRF-based endpoints for blacklist/whitelist/contacts management, call control (`/calls/originate/`), and ConfBridge conference calls (`/calls/conference/`); documented in [`docs/en/API.md`](docs/en/API.md) and [`docs/en/openapi.yaml`](docs/en/openapi.yaml)
- **CRM webhooks** — configurable JSON POST notifications for two independent call chains, driven from the dashboard listener: inbound (incoming, answered, missed, ended) and outbound (outgoing, outgoing answered, outgoing ended — placed by a SIP user, never a trunk); call recording lookup via `GET /api/v1/recordings/<uniqueid>/`
- **Token authentication** — dashboard WebSocket and read-only JSON API accept a DRF auth token in addition to a Django session, for CRM/external integrations
- **Slack notifications** — aggregated alerts for missed queue calls, plus per-call notifications from classic AGI scripts
- **Ansible deployment** — install/update playbooks plus a rollback procedure (`rollback.sh`) to revert code, migrations, and services to a prior deployment; daily cron backups of PostgreSQL and `/etc/asterisk`
- **Apply Changes** — one-click config regeneration and Asterisk reload

## Architecture

```
Browser ──WebSocket──► Django Channels ◄── Redis ◄── Dashboard Listener ◄── Asterisk AMI
Browser ──HTTP──────► Django (ASGI) ◄──── PostgreSQL
                           │
                           └──► /etc/asterisk/*.conf  (config generation)

Asterisk FastAGI ◄──────────► FastAGI Service (port 4573)
Callback daemon ─────────────► Asterisk AMI (outbound calls)
```

**Core components:**
- `core/` — Django models, config generator (`conf.py`), validators, admin interface
- `apps/dashboard/` — WebSocket operator panel (real-time call events)
- `apps/reports/` — CDR, recordings, queue log, routing reports
- `apps/lists/` — web CRUD UI for blocklist, allowlist, contacts
- `apps/callback/` — callback queue models and views
- `apps/provision/` — phone provisioning via TFTP
- `apps/api/` — REST API for blacklist/whitelist, call control, and recordings
- `apps/webhooks/` — CRM webhook definitions and delivery sync
- `services/callback/` — standalone daemon: monitors DB, initiates calls via AMI
- `services/dashboard/` — standalone daemon: AMI event listener → Redis
- `services/fastagi/` — standalone FastAGI server (blacklist, recording, routing)
- `services/agi/` — classic AGI scripts called directly by Asterisk dialplan (missed call, unmatched DID → Slack)

## Requirements

- Python 3.10+
- Django 5.2
- PostgreSQL 14+
- Redis 7+
- Asterisk 22+ with `res_pjsip`, `res_agi`, `cdr_pgsql`
- Debian or Ubuntu (required only for the Ansible production install; the Docker Compose path is OS-independent)

## Quick Start

See [docs/en/quickstart.md](docs/en/quickstart.md) for two ways to get running: Ansible (production install) and Docker Compose (recommended for evaluation/development). Also available in [Українська](docs/ua/quickstart.md) and [Español](docs/es/quickstart.md).

## Documentation

| | English | Українська | Español |
|---|---|---|---|
| Quick Start | [quickstart.md](docs/en/quickstart.md) | [quickstart.md](docs/ua/quickstart.md) | [quickstart.md](docs/es/quickstart.md) |
| Admin Guide | [admin-guide.md](docs/en/admin-guide.md) | [admin-guide.md](docs/ua/admin-guide.md) | [admin-guide.md](docs/es/admin-guide.md) |
| User Guide | [user-guide.md](docs/en/user-guide.md) | [user-guide.md](docs/ua/user-guide.md) | [user-guide.md](docs/es/user-guide.md) |
| CRM Webhooks | [crm-integration.md](docs/en/crm-integration.md) | [crm-integration.md](docs/ua/crm-integration.md) | [crm-integration.md](docs/es/crm-integration.md) |
| CRM Integrator Guide | [crm-integrator-guide.md](docs/en/crm-integrator-guide.md) | [crm-integrator-guide.md](docs/ua/crm-integrator-guide.md) | [crm-integrator-guide.md](docs/es/crm-integrator-guide.md) |
| REST API | [API.md](docs/en/API.md) / [openapi.yaml](docs/en/openapi.yaml) | [API.md](docs/ua/API.md) | [API.md](docs/es/API.md) |

`openapi.yaml` is the single machine-readable OpenAPI schema (also served live at `/api/v1/schema/`) and is not translated.

## Configuration

All configuration is done via environment variables. Copy `env.sample` to `.env` and adjust:

| Variable | Description |
|---|---|
| `DEVMODE` | `Production` / `Staging` / `Development` / `without_asterisk_on_localhost` |
| `DJANGO_SECRET_KEY` | Django secret key (required in production) |
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS` | PostgreSQL credentials |
| `ASTERISK_MANAGER_HOST` | Asterisk AMI host |
| `ASTERISK_MANAGER_USERNAME` | AMI username |
| `ASTERISK_MANAGER_SECRET` | AMI password |
| `ASTERISK_CONFIG_DIR` | Path to Asterisk config dir (default: `/etc/asterisk`) |
| `REDIS_URL` | Redis URL (default: `redis://localhost:6379/0`) |
| `TFTP_DIR` | TFTP root directory for phone provisioning |

Django runs under the `asterisk` OS user to have write access to `/etc/asterisk`; the Ansible `asterisk` role sets this up automatically on a bare-metal install.

## Standalone Services

Each service under `services/` runs as a separate process with its own virtual environment:

| Service | Description |
|---|---|
| `services/dashboard/` | AMI event listener → Redis (required for operator dashboard); optional Slack notifications for missed queue calls |
| `services/callback/` | Callback queue daemon — initiates outbound calls via AMI |
| `services/fastagi/` | FastAGI server — blacklist checks, recording, queue status |
| `services/agi/` | Classic AGI scripts (per-call Slack: missed call, unmatched DID); no daemon, Asterisk spawns per call |

Each service has its own `env.sample` and README with setup instructions.

## URL Structure

| URL | Description |
|---|---|
| `/` | Home — live system status, DB counts, CDR chart, quick links |
| `/admin/` | Django admin — manage all PBX entities |
| `/admin/apply` | Apply configuration changes to Asterisk |
| `/dashboard/` | Redirects to new live operator dashboard |
| `/dashboard/live/` | Real-time dashboard — Overview, Queues, PJSIP, Bridged, Channels tabs |
| `/dashboard/api/queues/` | JSON — queue member data for dashboard |
| `/dashboard/old/` | Legacy operator panel (preserved) |
| `/reports/` | CDR, recordings, queue logs, callback reports |
| `/reports/analytics/` | Analytics reports with charts (queues, agents, missed calls, etc.) |
| `/lists/` | Blocklist, Allowlist, Contacts — CRUD UI for Report Viewer group |
| `/api/v1/` | REST API |
| `/api/homepage-status/` | JSON endpoint — live Asterisk/Redis status for home page |

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, code style, and testing requirements.

## License

This project is licensed under the [PolyForm Shield License 1.0.0](LICENSE).

You may use, modify, and distribute PearlPBX2 for any purpose — including running your own commercial telephony deployment — except to provide a product or service that competes with PearlPBX2 or with any product the copyright holder provides using this software. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for the full terms. Commercial partnership or a license for a competing use requires a separate written agreement with the copyright holder.

### Third-party dependency licenses

All direct dependencies (Django app and the three standalone `services/`) were scanned with [`pip-licenses`](https://pypi.org/project/pip-licenses/) on 2026-08-11. Everything resolves to permissive licenses — MIT, BSD, Apache-2.0, PSF-2.0, or MPL-2.0 — except `psycopg2-binary`, which is LGPL. LGPL governs the driver package itself; importing/using it as a library does not place PearlPBX2's own code under LGPL terms, so this does not conflict with the PolyForm Shield license above. No GPL/AGPL dependency is present in any component actually shipped in the Docker images or a production install.

To reproduce:

```bash
pip install pip-licenses
pip-licenses --from=mixed --order=license   # run inside each of: repo root .python-venv, services/fastagi, services/dashboard, services/callback
```
