# PearlPBX2 `v2.0.0`

Web-based management interface for [Asterisk PBX](https://www.asterisk.org/), built with Django. Manages SIP endpoints, call routing, queues, and dialplan through a web UI — and generates Asterisk configuration files directly from the database.

## Features

- **SIP management** — PJSIP transports, endpoints (users), trunks (peers)
- **Dialplan editor** — contexts and extensions in Asterisk AEL syntax with validation
- **Call routing** — prefix-based routing tables
- **Queue management** — queues, members, rules, announcements
- **Real-time operator dashboard** — live call monitoring via WebSocket
- **CDR & reports** — call detail records, queue logs, callback reports, call recordings
- **Analytics reports** — queue calls, agent calls, outbound calls, missed calls, missed by hour, call duration, queue activity (hourly/daily) with Chart.js charts
- **Callback queue** — automated outbound callback system
- **Phone provisioning** — TFTP-based autoconfiguration for SIP phones
- **REST API** — blacklist/whitelist management
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
- `apps/callback/` — callback queue models and views
- `apps/provision/` — phone provisioning via TFTP
- `apps/api/` — REST API for blacklist/whitelist
- `services/callback/` — standalone daemon: monitors DB, initiates calls via AMI
- `services/dashboard/` — standalone daemon: AMI event listener → Redis
- `services/fastagi/` — standalone FastAGI server (blacklist, recording, routing)

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

See [docs/install_asterisk.md](docs/install_asterisk.md) for full installation including Asterisk compilation, PostgreSQL setup, nginx configuration, and systemd unit files.

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

Django runs under the `asterisk` OS user to have write access to `/etc/asterisk`. See [INSTALL.md](INSTALL.md) for details.

## Standalone Services

Each service under `services/` runs as a separate process with its own virtual environment:

| Service | Description |
|---|---|
| `services/dashboard/` | AMI event listener → Redis (required for operator dashboard) |
| `services/callback/` | Callback queue daemon — initiates outbound calls via AMI |
| `services/fastagi/` | FastAGI server — blacklist checks, recording, queue status |

Each service has its own `env.sample` and README with setup instructions.

## URL Structure

| URL | Description |
|---|---|
| `/admin/` | Django admin — manage all PBX entities |
| `/admin/apply` | Apply configuration changes to Asterisk |
| `/dashboard/` | Real-time operator panel |
| `/reports/` | CDR, recordings, queue logs, callback reports |
| `/reports/analytics/` | Analytics reports with charts (queues, agents, missed calls, etc.) |
| `/api/v1/` | REST API |

## Contributing

Contributions are welcome. Please open an issue before submitting a pull request for significant changes.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
