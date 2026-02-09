# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Standalone Python daemon that polls PostgreSQL for callback requests and initiates outbound calls via Asterisk AMI. Runs as a systemd service under the `asterisk` user. Not a Django app — this is an independent process with its own venv and dependencies.

## Commands

```bash
# Activate virtual environment
source .python-venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (requires env vars or CLI args for DB/AMI credentials)
python callback.py

# Verify configuration without starting
python callback.py --dump_config

# Multi-process mode
python callback.py --process_count=4

# Insert test callback entries (for testing)
python test_insert.py --src=0441234567 --dst=0501234567 --service-name=MyService
python test_insert.py --src=0441234567 --service-name=MyService --count=10 --randomize
```

Production deployment: `sudo systemctl start pearlpbx-callback` (unit file: `../Callback.service`)

## Architecture

**Single file service** (`callback.py`): `Callback` class handles the full lifecycle:
1. `select_first_available()` — queries `callback_number` JOIN `callback_service` JOIN `dialplan_contexts`, uses `SELECT ... FOR UPDATE SKIP LOCKED` for safe multi-process operation
2. Updates row status to `PENDING`
3. `call_dst()` — sends AMI `Originate` action with outbound/inbound context pair
4. Updates status to `ANSWERED` or `BUSY` based on AMI response
5. `event_listener()` — tracks `DialEnd` events for active calls

**Multi-process**: uses `os.fork()` — parent + N-1 children, each running independent polling loops. Row locking prevents duplicate processing.

**AMI reconnection**: automatic on disconnect via `on_disconnect()` callback.

## Configuration

Environment variables (from `.env` or `env.sample`), overridable by CLI args:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` — PostgreSQL connection
- `AMI_HOST`, `AMI_PORT`, `AMI_USER`, `AMI_PASS` — Asterisk Manager Interface
- `VA_PROCESS_COUNT` — number of worker processes
- `LOGLEVEL` — Python logging level as int (10=DEBUG, 20=INFO)

## Database Tables

The service reads from these Django-managed tables (do NOT modify schema here — changes go through Django migrations in the main project):
- `callback_number` — queue of numbers to call (`dial_status`: NEW → PENDING → ANSWERED/BUSY)
- `callback_service` — service config with `context_outbound_id` and `context_inbound_id`
- `dialplan_contexts` — Asterisk context names

## Key Patterns

- **Row locking**: `FOR UPDATE SKIP LOCKED` prevents race conditions between processes
- **Transaction management**: `autocommit = False`, explicit `commit()`/`rollback()`
- **Call flow**: `Local/{dst}@{context_outbound}/n` channel originates into `{context_inbound}` context — two contexts needed for proper CDR and recording (see README.md for dialplan examples)
- **CDR**: disable CDR in inbound context (`Set(CDR_PROP(disable)=1)`) to avoid duplicate records; record calls only in outbound context

## Dependencies

`psycopg2-binary`, `asterisk-ami`, `requests` — see `requirements.txt`
