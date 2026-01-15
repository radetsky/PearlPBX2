# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PearlPBX2 is a Django-based web management interface for Asterisk PBX. The system dynamically generates Asterisk configuration files (pjsip.conf, extensions.ael, etc.) from database models and provides real-time monitoring through WebSocket-based dashboards. Django runs under the `asterisk` user to directly manage `/etc/asterisk` configuration files and sound files.

## Architecture

### Core Components

**Django Application (`core/`)**
- Central models for all Asterisk entities (SIPUser, SIPPeer, SIPTransport, DialplanContext, DialplanExtension, Queue, etc.)
- Configuration generator (`core/conf.py`) that translates Django models into Asterisk config files
- Custom form validators for Asterisk-specific syntax (extensions, contexts, AEL dialplan)
- Template context processors for consistent UI rendering
- Admin interface with "Apply Changes" button to regenerate Asterisk configs

**Django Apps (`apps/`)**
- `api`: REST API endpoints for external integrations
- `callback`: Models and views for callback queue functionality
- `dashboard`: WebSocket-based operator dashboard (real-time call monitoring)
- `provision`: Phone provisioning (TFTP config generation)
- `reports`: Call detail records (CDR) and reporting interface

**Standalone Services (`services/`)**
- `callback/`: Python daemon that monitors PostgreSQL for callback requests and initiates calls via Asterisk AMI
- `express/`: FastAGI service for Express Taxi API integration with ULINE (Unique Line Number) management for call parking
- `dashboard/`: AMI event listener that publishes to Redis for WebSocket consumers
- `fastagi/`: General-purpose FastAGI server framework

### Data Flow

1. **Configuration Management**: Admin UI → Django Models → `core/conf.py` → Asterisk config files → Asterisk reload
2. **Real-time Dashboard**: Asterisk AMI Events → Dashboard Service → Redis → Django Channels → WebSocket → Browser
3. **Callback System**: PostgreSQL callback queue → Callback Service → Asterisk AMI → Outbound calls
4. **Express Integration**: Asterisk FastAGI → Express Service → ULINE allocation → External API notification

### Key Architectural Patterns

**Configuration Generation**
- All Asterisk configuration is generated from Django models via functions in `core/conf.py`
- Functions like `make_pjsip_conf_transports()`, `make_pjsip_conf_peers()`, `make_extensions_ael()` build config file content
- The "Apply Changes" admin action triggers config regeneration and Asterisk reload
- Backups are created before overwriting configs (ASTERISK_BACKUP_DIR setting)

**Django Channels Architecture**
- ASGI application configured in `pbx/asgi.py` with WebSocket routing
- Redis channel layer for inter-process communication (callback service → Django → WebSocket clients)
- Dashboard app uses consumers to push real-time call events to connected browsers

**Database Models Structure**
- Base `AuditFields` model provides created_at/created_by/modified_at/modified_by to all models
- SIP entities: SIPTransport → SIPUser/SIPPeer (trunk) relationship
- Routing: RoutingTable → RoutingRecord (prefix-based routing rules)
- Dialplan: DialplanContext → DialplanExtension (Asterisk AEL syntax)

**Services Architecture**
- Each service in `services/` has its own virtual environment and systemd unit file
- Services use environment variables for configuration (DB credentials, AMI credentials)
- Express service manages ULINE allocation (1-199) for parking slot assignment
- Callback service uses multiprocessing with database row locking to prevent race conditions

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .python-venv
source .python-venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (copy and edit)
cp env.sample .env
# Edit .env with your database credentials, Asterisk AMI settings, etc.
```

### Database Operations
```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Make new migrations after model changes
python manage.py makemigrations
```

### Running the Application
```bash
# Development server
python manage.py runserver

# Production (with gunicorn)
gunicorn pbx.wsgi:application --bind 0.0.0.0:8000

# ASGI server for WebSocket support
uvicorn pbx.asgi:application --host 0.0.0.0 --port 8000
```

### Static Files
```bash
# Collect static files for production
python manage.py collectstatic
```

### Standalone Services

**Callback Service**
```bash
cd services/callback
source .python-venv/bin/activate

# Run with environment variables
python callback.py

# Run with command-line args
python callback.py --db_host=localhost --ami_user=admin --ami_pass=secret

# Multi-process mode
python callback.py --process_count=4

# Verify configuration
python callback.py --dump_config
```

**Express FastAGI Service**
```bash
# Using systemd (production)
sudo systemctl start express-fastagi
sudo systemctl status express-fastagi
sudo journalctl -u express-fastagi -f

# Manual run (development)
cd /opt/express-fastagi
source venv/bin/activate
python express_fastagi.py
```

**Dashboard Service**
```bash
cd services/dashboard
source .python-venv/bin/activate
python listener.py
```

## Critical Project-Specific Rules

### Configuration File Management
- NEVER manually edit files in `/etc/asterisk` - always use the Django admin interface
- Configuration changes require clicking "Apply Changes" in admin to take effect
- The system creates backups in ASTERISK_BACKUP_DIR before applying changes
- Config file locations are controlled by environment variables: ASTERISK_ROOT_DIR, ASTERISK_CONFIG_DIR

### Django Admin Limitations
- If Django admin forms cannot implement required logic, create custom views and templates
- Do not force complex workflows into the admin interface - it's acceptable to say "Django admin is not suitable for this task"
- The admin interface has a custom "Apply Changes" view at `/admin/apply` that triggers config regeneration

### Form Validation
- Use validators from `core/validators.py` for Asterisk-specific syntax validation
- Key validators: `validate_alphanumeric`, `validate_bind_ip`, `validate_asterisk_context`, `validate_asterisk_extension_prefix`
- Dialplan extensions use Asterisk AEL syntax and must be validated with `AsteriskDialplanValidator`
- RoutingTable and DialplanContext names must be unique across both models
- Password fields should use `PasswordWithToggleInput` widget from `core/widgets.py`

### Security Considerations
- Django runs as user `asterisk` to access `/etc/asterisk` (see INSTALL.md)
- AMI credentials are stored in environment variables, never hardcoded
- Production mode requires DJANGO_SECRET_KEY, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE enabled
- DEVMODE setting controls security features: "Production", "Staging", "Development", "without_asterisk_on_localhost"

### Database Considerations
- Always use PostgreSQL (default engine configured in settings)
- Callback service uses row-level locking (`SELECT FOR UPDATE`) to prevent race conditions
- CDR records must be carefully managed - see callback service README for dialplan examples
- When using callbacks, disable CDR in inbound context to avoid duplicate records

### Asterisk Integration Points
- AMI (Manager Interface): Port 5038, configured via ASTERISK_MANAGER_* environment variables
- FastAGI: Services listen on custom ports (e.g., 4574 for Express)
- Configuration files: Generated to ASTERISK_CONFIG_DIR, typically `/etc/asterisk`
- Sound files: Managed via custom storage backends (`core/storages.py`)
- TFTP provisioning: Files written to TFTP_DIR for phone autoconfiguration

### Real-time Features
- Dashboard requires Redis running on localhost:6379
- WebSocket connections handled by Django Channels with Redis channel layer
- Dashboard service subscribes to AMI events and publishes to Redis
- Install Redis: `sudo apt install redis-server`

### Environment Variables
All services can be configured via environment variables. Key variables are documented in `env.sample`. Always check existing documentation before implementing new features.

## Project Settings

**Django Settings Module**: `pbx.settings`

**Key Settings**:
- ASGI_APPLICATION: `pbx.asgi.application` (for WebSocket support)
- INSTALLED_APPS includes custom admin config: `pbx.apps.MyAdminConfig`
- Template context processors: `core.context_processors.template_config_context_processor`, `core.context_processors.header_menu_context_processor`
- HEADER_MENU_PAGES defines navigation menu with role-based access

**Custom PBX Settings** (not standard Django):
- ASTERISK_ROOT_DIR, ASTERISK_CONFIG_DIR, ASTERISK_BACKUP_DIR
- ASTERISK_MANAGER_HOST, ASTERISK_MANAGER_PORT, ASTERISK_MANAGER_USERNAME, ASTERISK_MANAGER_SECRET
- ASTERISK_MONITOR_DIR (call recording storage)
- TFTP_DIR (phone provisioning)
- PEARLPBX_DEFAULT_ROUTING_TABLE, PEARLPBX_DEFAULT_ROUTING_RECORD, PEARLPBX_DEFAULT_ROUTING_PREFIX

## URL Structure

- `/admin/` - Django admin interface
- `/admin/apply` - Apply configuration changes to Asterisk
- `/dashboard/` - Real-time operator dashboard
- `/reports/` - CDR and call reports
- `/api/v1/` - REST API endpoints
- `/` - Core application views (login, etc.)

## Testing

```bash
# Run all tests
python manage.py test

# Run tests for a specific app
python manage.py test core
python manage.py test apps.api
python manage.py test apps.callback
python manage.py test apps.dashboard
python manage.py test apps.provision
python manage.py test apps.reports

# Run a specific test class
python manage.py test core.tests.TestClassName

# Run a single test method
python manage.py test core.tests.TestClassName.test_method_name

# Verbose output
python manage.py test --verbosity=2
```
