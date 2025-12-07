# Callback Service

A Python-based callback service for Asterisk PBX that processes callback requests from a PostgreSQL database and initiates calls via the Asterisk Manager Interface (AMI).

## Features

- Monitors a PostgreSQL database for pending callback requests
- Initiates outbound calls via Asterisk AMI
- Supports multi-process operation for handling multiple callbacks concurrently
- Automatic AMI reconnection on disconnect
- Transaction-safe database operations with row locking

## Requirements

- Python 3.8+
- PostgreSQL database
- Asterisk PBX with AMI enabled

## Installation

1. Clone the repository or copy the callback service files:

```bash
cd /path/to/services/callback
```

2. Create and activate a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The service can be configured via **environment variables** or **command-line arguments**. Command-line arguments take priority over environment variables.

### Environment Variables

| Variable          | Default           | Description                                      |
|-------------------|-------------------|--------------------------------------------------|
| `DB_HOST`         | `127.0.0.1`       | PostgreSQL database host                         |
| `DB_PORT`         | `5432`            | PostgreSQL database port                         |
| `DB_NAME`         | `callback_db`     | Database name                                    |
| `DB_USER`         | `callback_user`   | Database user                                    |
| `DB_PASS`         | `callback_pass`   | Database password                                |
| `DB_TABLE`        | `callback_number` | Database table for callback entries              |
| `AMI_HOST`        | `127.0.0.1`       | Asterisk Manager Interface host                  |
| `AMI_PORT`        | `5038`            | Asterisk Manager Interface port                  |
| `AMI_USER`        | `ami_user`        | AMI username                                     |
| `AMI_PASS`        | `ami_pass`        | AMI password                                     |
| `VA_PROCESS_COUNT`| `1`               | Number of worker processes to spawn              |
| `LOGLEVEL`        | `20` (INFO)       | Logging level (10=DEBUG, 20=INFO, 30=WARNING)    |

### Command-Line Arguments

```bash
python callback.py --help
```

| Argument          | Description                                      |
|-------------------|--------------------------------------------------|
| `--db_host`       | Database host                                    |
| `--db_port`       | Database port                                    |
| `--db_name`       | Database name                                    |
| `--db_user`       | Database user                                    |
| `--db_pass`       | Database password                                |
| `--db_table`      | Database table to use for callbacks              |
| `--ami_host`      | Asterisk Manager Interface host                  |
| `--ami_port`      | Asterisk Manager Interface port                  |
| `--ami_user`      | Asterisk Manager Interface user                  |
| `--ami_pass`      | Asterisk Manager Interface password              |
| `--process_count` | Number of processes to spawn                     |
| `--loglevel`      | Logging level (default: INFO)                    |
| `--dump_config`   | Dump configuration and exit                      |

## Running

### Basic Usage

```bash
python callback.py
```

### With Environment Variables

```bash
export DB_HOST=localhost
export DB_NAME=pearlpbx
export DB_USER=postgres
export DB_PASS=secret
export AMI_USER=admin
export AMI_PASS=secret

python callback.py
```

### With Command-Line Arguments

```bash
python callback.py --db_host=localhost --db_name=pearlpbx --ami_user=admin --ami_pass=secret
```

### Multi-Process Mode

To run with multiple worker processes:

```bash
python callback.py --process_count=4
```

### Dump Configuration

To verify configuration without starting the service:

```bash
python callback.py --dump_config
```

## Database Schema

The service expects the following database tables:

- `callback_number` - Contains callback requests with fields:
  - `id` - Primary key
  - `src` - Source caller ID
  - `dst` - Destination number to call
  - `service_id` - Reference to callback_service
  - `dial_status` - Status: NEW, PENDING, ANSWERED, BUSY
  - `schedule_time` - When to initiate the callback
  - `created` - Creation timestamp
  - `updated` - Last update timestamp

- `callback_service` - Service configuration with:
  - `id` - Primary key
  - `is_active` - Whether service is enabled
  - `context_outbound_id` - Reference to outbound dialplan context
  - `context_inbound_id` - Reference to inbound dialplan context

- `dialplan_contexts` - Dialplan context definitions

## Asterisk Dialplan Notes

### CDR Considerations

To create a single CDR record that shows "source number called mobile destination" and correctly links to the recorded conversation, you need proper outbound and inbound contexts.

**Important:**
- Do NOT add `Hangup()` in the outbound context, as it will create a separate CDR
- Disable CDR creation in the inbound context
- Record the conversation only in the outbound context

### Example Dialplan Configuration

Outbound context with call recording:

```
context mobile-out {
    _X! => {
        NoOp(CALL BEGIN >>>> :'${CALLERID(name)}'@<${CALLERID(num)}>);
        Set(CHANNEL(language)=ua);
        Set(TIMEOUT(absolute)=3600);
        AGI(agi://127.0.0.1:4573/mixmonitor,${CALLERID(num)},${EXTEN});
        AGI(agi://127.0.0.1:4573/dial-trunk-group,dinstar-group,${EXTEN},3);
    }
}
```

Inbound context (CDR disabled, no recording here):

```
context callback_in {
    _X! => {
        Set(CDR_PROP(disable)=1);
        NoOp(CALL BEGIN >>>> :'${CALLERID(name)}'@<${CALLERID(num)}>);
        Set(CHANNEL(language)=ua);
        Set(TIMEOUT(absolute)=3600);
        Answer();
        Wait(1);
        Queue(DEFAULT);
        Hangup();
    }
}
```

## License

Part of PearlPBX2 project.