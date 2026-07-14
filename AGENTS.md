# AGENTS.md

## What is this

Django 5.2 web UI for managing Asterisk PBX. Models in `core/models.py` generate Asterisk config files (`pjsip.conf`, `extensions.ael`, `queues.conf`, etc.) via `core/conf.py`. The admin "Apply Changes" button writes configs to disk and reloads Asterisk.

## Running tests

```bash
# Docker-based (preferred — needs Docker running)
make test              # full suite
make test-quick        # stop on first fail, no coverage
make test-app APP=core # single app

# Local (needs PostgreSQL + Redis running, DEVMODE=without_asterisk_on_localhost)
source .python-venv/bin/activate
pytest                 # runs core + apps (see pytest.ini testpaths)
pytest core/tests.py   # single file
pytest -k test_name    # single test by name
```

Test deps: `requirements-test.txt` (pytest, pytest-django, pytest-cov, factory-boy).

No conftest.py at root. Tests use `django.test.TestCase` directly. The `DEVMODE` env var must be set for settings to load; test Docker compose sets it to `without_asterisk_on_localhost`.

## Services (standalone processes)

Each under `services/` with its own `.python-venv/` and `requirements.txt`. NOT Django apps — independent daemons.

| Service | Entry point | What it does |
|---|---|---|
| `services/callback/` | `callback.py` | Polls DB for callback requests, originates calls via AMI |
| `services/dashboard/` | `dashboard_listener.py` | AMI events → Redis (for WebSocket dashboard) |
| `services/fastagi/` | `fastagi.py` | FastAGI server: blacklist, recording, ULINE parking |
| `services/agi/` | `missed_call.py`, `unmatched_call.py` | Classic AGI scripts, spawned per-call by Asterisk |

Service tests run separately: `cd services/fastagi && pytest tests/`.

## Key architecture gotchas

- **Django runs as user `asterisk`** to write `/etc/asterisk`. Dev mode uses `ASTERISK_ROOT_DIR=/tmp` to avoid needing root.
- **Config generation** (`core/conf.py`): all functions like `make_pjsip_conf()`, `make_extensions_ael()` query the DB and return string content. The `ApplyChangesView` in `pbx/admin.py` calls these, writes to disk, and triggers AMI reload.
- **DEVMODE** controls security: `Production`/`Staging` enforce secure cookies, require `DJANGO_SECRET_KEY` and `ASTERISK_MANAGER_SECRET`. `Development` and `without_asterisk_on_localhost` use insecure defaults.
- **RoutingTable + DialplanContext** names must be unique across both models (enforced in validators).
- **Asterisk dialplan** uses AEL syntax. Validated by `AsteriskDialplanValidator` in `core/validators.py`. Every step must end with `;`. Block constructs (if/else/while) use `{}` braces.
- **i18n**: 3 languages (uk, en, es). Locale files in `locale/`. Default language is Ukrainian. Use `gettext_lazy` (`_()`) for all user-facing strings.
- **WebSocket**: Django Channels with Redis backend. ASGI entrypoint in `pbx/asgi.py`. Dashboard consumer in `apps/dashboard/`.
- **Services use `SELECT ... FOR UPDATE SKIP LOCKED`** for safe multi-process DB access (callback service).

## Adding new Asterisk config output

1. Add model fields in `core/models.py`
2. Add/update generator function in `core/conf.py`
3. Wire it into `ApplyChangesView._build_cfgfiles()` in `pbx/admin.py`
4. Add tests in `core/tests.py`

## Django admin custom admin site

`pbx/apps.py` defines `MyAdminConfig` replacing default admin. Custom admin site in `pbx/admin.py` (`MyAdminSite`). The "Apply Changes" button is a custom view at `/admin/apply`.

## Environment setup

```bash
cp env.sample .env
# Edit .env — critical vars:
#   DEVMODE=without_asterisk_on_localhost
#   DB_HOST, DB_NAME, DB_USER, DB_PASS
#   ASTERISK_MANAGER_HOST, ASTERISK_MANAGER_USERNAME, ASTERISK_MANAGER_SECRET
#   REDIS_URL
```

No linting, formatting, or type-checking tools are configured in this repo. No pre-commit hooks. No CI workflows.
