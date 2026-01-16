# AI Coding Agent Guidelines for PearlPBX2

Welcome to the PearlPBX2 codebase! This document provides essential knowledge to help AI coding agents be productive and aligned with the project's architecture, workflows, and conventions.

## Project Overview
PearlPBX2 is a modular telephony platform built on Asterisk PBX. It integrates various services for call management, dashboards, and reporting. The project is structured as a Django application with additional Python-based services for specific tasks.

### Key Components
- **Django Apps**: Located in `apps/`, these include `api`, `callback`, `dashboard`, `provision`, and `reports`. Each app has its own models, views, and templates.
- **Core Services**: Found in `core/`, this includes utilities, validators, and shared logic.
- **Standalone Services**: Independent Python services for specific tasks:
  - `callback`: Processes callback requests via Asterisk AMI.
  - `express`: FastAGI service for Express Taxi API integration.
  - `dashboard`: WebSocket-based operator dashboard.
- **Configuration Files**: Located in `contrib/configs/`, these define Asterisk settings.

### Data Flow
- **Callback Service**: Monitors a PostgreSQL database for callback requests and triggers calls via Asterisk AMI.
- **Dashboard**: Uses Redis and Django Channels to provide real-time updates to users.
- **Express Service**: Handles FastAGI requests and communicates with external APIs.

## Developer Workflows

### Setting Up the Environment
1. Clone the repository.
2. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running Services
- **Django Server**:
  ```bash
  python manage.py runserver
  ```
- **Callback Service**:
  ```bash
  python services/callback/callback.py
  ```
- **Express Service**:
  ```bash
  sudo systemctl start express-fastagi
  ```

### Testing
Run Django tests:
```bash
python manage.py test
```

### Debugging
- Use `LOGLEVEL` environment variables to adjust logging verbosity.
- For the callback service, use `--dump_config` to verify settings.

## Project-Specific Conventions
- **Form Validation**: Custom validators (e.g., `validate_alphanumeric`, `min3len`) are defined in `core/forms.py`.
- **Password Fields**: Use `PasswordWithToggleInput` for secure input handling.
- **Routing Tables**: Ensure unique names between `RoutingTable` and `DialplanContext`.
- **Dialplan Templates**: Use Asterisk AEL syntax for defining dialplans.

## Integration Points
- **Asterisk AMI**: Used for call management in the callback service.
- **Redis**: Provides real-time messaging for the dashboard.
- **External APIs**: The express service communicates with the Express Taxi API.

## Key Files and Directories
- `apps/`: Django apps for extended functionality.
- `core/`: Core app utilities and models.
- `services/`: Standalone Python services.
- `contrib/configs/`: Asterisk configuration files.
- `templates/`: HTML templates for Django apps.

## Examples
### Adding a New SIP User
1. Update `SIPUserForm` in `core/forms.py`.
2. Ensure validators like `validate_alphanumeric` are applied.
3. Test the form using Django's admin interface.

### Modifying Dialplans
1. Edit `DialplanExtensionForm` in `core/forms.py`.
2. Use the `DIALPLAN_TEMPLATE` as a starting point.
3. Validate using `AsteriskDialplanValidator`.

## Very important Notes
- Always check for existing solutions in the internet, at least at GitHub, before implementing new features
- Always check the Django and Asterisk documentation for best practices
- Follow security best practices, especially when handling user input and authentication
- If Django admin forms can not implement the required logic, create custom views and templates, then refuse using admin for that part. Just say "Django admin is not suitable for this task" as the answer.


---

For further details, refer to the `README.md` files in each service directory.