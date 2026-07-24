# PearlPBX2 `v2.6.0`

Web-based management interface for [Asterisk PBX](https://www.asterisk.org/), built with Django. Manages SIP endpoints, call routing, queues, and dialplan through a web UI — and generates Asterisk configuration files directly from the database.

## Features

- **Welcome dashboard** — live system status on the home page: DB counts, Asterisk version/uptime, active calls, queue occupancy, 14-day CDR chart, quick navigation links
- **SIP management** — PJSIP transports, endpoints (users), trunks (peers)
- **Dialplan editor** — contexts and extensions in Asterisk AEL syntax with validation
- **Call routing** — prefix-based routing tables
- **Queue management** — queues, members, rules, announcements
- **Real-time operator dashboard** — dark-theme live dashboard (`/dashboard/live/`) with five tabs: Overview, Queues, PJSIP, Bridged, Channels; WebSocket status indicator, hangup actions, queue agent info in call modal, agent state restored after Asterisk restart; old dashboard preserved at `/dashboard/old/`
- **CDR & reports** — call detail records with direction/channel filters, queue logs, callback reports with duration and recordings, call recordings browser
- **Analytics reports** — queue calls, agent calls, outbound calls, missed calls (with link to queue log), missed by hour, call duration, queue activity (hourly/daily, exclude-contacts filter) with Chart.js charts
- **Callback queue** — automated outbound callback system with configurable AMI timeout (`--ami_timeout`)
- **Phone provisioning** — TFTP-based autoconfiguration for SIP phones
- **Lists** — web CRUD UI for Blocklist, Allowlist, and Contacts; accessible to Report Viewer group without admin access
- **REST API** — DRF-based endpoints for blacklist/whitelist/contacts management, call control (`/calls/originate/`), and ConfBridge conference calls (`/calls/conference/`); documented in `docs/openapi.yaml`
- **CRM webhooks** — configurable JSON POST notifications for call events (incoming, answered, ended/missed), driven from the dashboard listener; call recording lookup via `GET /api/v1/recordings/<uniqueid>/`
- **Token authentication** — dashboard WebSocket and read-only JSON API accept a DRF auth token in addition to a Django session, for CRM/external integrations
- **Slack notifications** — aggregated alerts for missed queue calls, plus per-call notifications from classic AGI scripts
- **Ansible deployment** — install/update playbooks plus a rollback procedure (`rollback.sh`) to revert code, migrations, and services to a prior deployment
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

## Quick Start

```bash
# Clone and set up virtual environment
git clone https://github.com/yourusername/PearlPBX2.git
cd PearlPBX2
python3 -m venv .python-venv
source .python-venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp env.sample .env
# Edit .env — set DB credentials, AMI credentials, DEVMODE, etc.

# Initialize database
python manage.py migrate
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

For production deployment with WebSocket support:

```bash
uvicorn pbx.asgi:application --host 0.0.0.0 --port 8000
```

See [docs/en/install_asterisk.md](docs/en/install_asterisk.md) for full installation including Asterisk compilation, PostgreSQL setup, nginx configuration, and systemd unit files.

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

Django runs under the `asterisk` OS user to have write access to `/etc/asterisk`. See [docs/en/INSTALL.md](docs/en/INSTALL.md) for details.

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

Contributions are welcome. Please open an issue before submitting a pull request for significant changes.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
