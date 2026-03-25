# FastAGI Service

FastAGI server for PearlPBX2 using Twisted and StarPy. Provides various AGI handlers for Asterisk dialplan integration.

## Features

- **blacklist** - Check if caller ID is in blacklist
- **whitelist** - Check if caller ID is in whitelist
- **customlist** - Check if caller ID is in a custom named list
- **dial-trunk-group** - Dial through trunk group with automatic failover and retry
- **mixmonitor** - Start call recording based on monitor settings
- **add-callback** - Add callback request to the database
- **queue-status** - Check queue availability (ready operators and waiting callers)
- **parking-uline** - Allocate a unique parking slot (ULINE) for a call via Redis

## Installation

```bash
cd services/fastagi

# Create virtual environment
python3 -m venv .python-venv
source .python-venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Configuration is done via environment variables:

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | postgres | Database name |
| `DB_USER` | user | Database user |
| `DB_PASS` | pass | Database password |

### Redis (for queue-status and parking-uline)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis server port |

### Parking ULINE

| Variable | Default | Description |
|----------|---------|-------------|
| `PARKING_ULINE_MIN` | 1 | First parking slot number |
| `PARKING_ULINE_MAX` | 199 | Last parking slot number |
| `ULINE_SWEEP_INTERVAL` | 300 | Seconds between stale-slot sweep runs |

### Asterisk AMI (fallback for queue-status)

| Variable | Default | Description |
|----------|---------|-------------|
| `AMI_HOST` | 127.0.0.1 | Asterisk AMI host |
| `AMI_PORT` | 5038 | Asterisk AMI port |
| `AMI_USER` | admin | AMI username |
| `AMI_PASS` | admin | AMI password |

## Running

### Development

```bash
source .python-venv/bin/activate
python fastagi.py
```

Server listens on `127.0.0.1:4573` by default.

### Production (systemd)

Create `/etc/systemd/system/FastAGI.service`:

```ini
[Unit]
Description=PearlPBX FastAGI Service
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=asterisk
Group=asterisk
WorkingDirectory=/opt/pearlpbx/services/fastagi
Environment=DB_HOST=localhost
Environment=DB_PORT=5432
Environment=DB_NAME=pearlpbx
Environment=DB_USER=pearlpbx
Environment=DB_PASS=secret
Environment=REDIS_HOST=localhost
Environment=REDIS_PORT=6379
Environment=AMI_HOST=127.0.0.1
Environment=AMI_PORT=5038
Environment=AMI_USER=admin
Environment=AMI_PASS=secret
ExecStart=/opt/pearlpbx/services/fastagi/.python-venv/bin/python fastagi.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable FastAGI
sudo systemctl start FastAGI
```

## AGI Handlers

### blacklist

Check if caller ID is in the blacklist.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/blacklist,${CALLERID(num)},${EXTEN});
if (${BLACKLISTED} = 1) {
    Hangup();
}
```

**Channel variables set:**
- `BLACKLISTED` - "1" if blacklisted, "0" otherwise

---

### whitelist

Check if caller ID is in the whitelist.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/whitelist,${CALLERID(num)},${EXTEN});
if (${WHITELISTED} = 1) {
    // VIP caller handling
}
```

**Channel variables set:**
- `WHITELISTED` - "1" if whitelisted, "0" otherwise

---

### customlist

Check if caller ID is in a custom named list.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/customlist,vip_customers,${CALLERID(num)},${EXTEN});
if (${CUSTOM_LISTED} = 1) {
    // Handle VIP customer
}
```

**Arguments:**
1. List name
2. Caller ID
3. Destination (optional)

**Channel variables set:**
- `CUSTOM_LISTED` - "1" if in list, "0" otherwise

---

### dial-trunk-group

Dial through a trunk group with automatic failover and retry logic.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/dial-trunk-group,my_trunk_group,${EXTEN},5);
if (${TRUNK_GROUP_DIALLED} = 0) {
    Playback(all-circuits-busy);
    Hangup();
}
```

**Arguments:**
1. Trunk group name
2. Extension to dial
3. Maximum attempts (default: 5)

**Channel variables set:**
- `TRUNK_GROUP_DIALLED` - "1" if call answered, "0" otherwise

**Behavior:**
- Shuffles trunk peers randomly
- Retries on BUSY (10s delay), NOANSWER/CHANUNAVAIL/CONGESTION (1s delay)
- Cycles through all peers in the group

---

### mixmonitor

Start call recording based on global and per-caller/destination settings.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/mixmonitor,${CALLERID(num)},${EXTEN});
// Recording starts automatically if enabled
```

**Arguments:**
1. Caller ID (source)
2. Destination

**Channel variables set:**
- `MIXMONITOR` - "1" if recording started, "0" otherwise

**Recording path:** `/var/spool/asterisk/monitor/YYYY/MM/DD/HH_MM_SS_{src}_{dst}.wav`

---

### add-callback

Add a callback request to the database for the callback service to process.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/add-callback,${CALLERID(num)},${EXTEN},support_queue,30);
if (${CALLBACK_ADDED} = 1) {
    Playback(callback-scheduled);
}
```

**Arguments:**
1. Caller ID (source number to call back)
2. Destination (number caller was trying to reach)
3. Service name (callback service identifier)
4. Delay in seconds (default: 5)

**Channel variables set:**
- `CALLBACK_ADDED` - "1" if callback scheduled, "0" otherwise

---

### parking-uline

Allocate a unique parking line number (ULINE) for the current call. Slot is stored in Redis with a TTL of 1 hour. A background sweep releases slots whose call channel is no longer active.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/parking-uline);
if (${ULINE} = 0) {
    // No free slots — handle overflow
    Hangup();
}
NoOp(Parking slot: ${ULINE});
```

**Channel variables set:**
- `ULINE` - Allocated slot number (1–199 by default), or "0" if no slots available

**Redis keys written:**
- `parking:uline:{N}` — hash with `uniqueid`, `channel`, `caller_id`, `cdr_start`, `allocated_at`; TTL 3600 s
- `parking:uid:{uniqueid}` — string mapping uniqueid → slot number; TTL 3600 s

**Slot lifecycle:**
1. Allocated by `parking-uline` AGI call via atomic Lua script
2. Released automatically by sweep job when call channel disappears (requires dashboard service running)
3. Released by `flush` action from the ULINE monitor in the web UI

---

### queue-status

Check queue status before routing calls. Returns count of available operators and waiting callers.

**Dialplan (AEL):**
```
AGI(agi://127.0.0.1:4573/queue-status,${QUEUE_NAME});
if (${READYTORECEIVE} > 0) {
    Queue(${QUEUE_NAME});
} else if (${QUEUECALLERS} > 10) {
    Playback(queue-full);
    Hangup();
} else {
    Playback(all-operators-busy);
    // Offer callback
}
```

**Arguments:**
1. Queue name

**Channel variables set:**
- `READYTORECEIVE` - Count of available operators (Status=1, Paused=0)
- `QUEUECALLERS` - Count of callers waiting in queue

**Data sources:**
1. **Primary:** Redis cache at `asterisk:queue:{name}` (populated by dashboard service)
2. **Fallback:** Direct AMI query if Redis is unavailable

## Testing

Unit tests cover `ULineRedisManager` and `sweep_parking_ulines`. They use `fakeredis` with Lua support — no real Redis or Asterisk needed.

### Setup

`pytest` and `fakeredis[lua]` are already listed in `requirements.txt` and will be installed with the regular install step.

If you need to install them separately:

```bash
pip install pytest "fakeredis[lua]"
```

### Run all tests

```bash
cd services/fastagi
source .python-venv/bin/activate
pytest tests/ -v
```

### Run specific test files

```bash
# ULineRedisManager only (allocate, release, flush_all, get_stats)
pytest tests/test_uline_redis.py -v

# sweep_parking_ulines only
pytest tests/test_sweep.py -v
```

### Test coverage

| Test file | What is tested |
|-----------|---------------|
| `tests/test_uline_redis.py` | `ULineRedisManager`: slot allocation (Lua atomicity, idempotency, TTL, full-range), release, flush, stats |
| `tests/test_sweep.py` | `sweep_parking_ulines`: skips when dashboard offline, releases stale slots, keeps active slots, reschedules via reactor |

---

## Database Tables

The service uses the following database tables:

- `blacklist` - Blacklisted caller IDs
- `whitelist` - Whitelisted caller IDs
- `custom_list_entries` / `custom_lists_names` - Custom named lists
- `core_trunkgroup` / `core_trunkgroup_sip_peers` / `core_sippeer` - Trunk groups
- `core_monitor` / `core_settings` - Monitor settings
- `core_monitor_filenames` - Generated recording filenames
- `callback_number` / `callback_service` - Callback requests

## Logging

Logs are written to stdout with DEBUG level by default. Logger name: `PBX.FastAGI`.

## Integration with Dashboard Service

The `queue-status` handler uses Redis data populated by the dashboard service (`services/dashboard`). For real-time queue status, ensure the dashboard service is running:

```bash
# Check Redis data
redis-cli GET asterisk:queue:YOUR_QUEUE_NAME
```

If the dashboard service is not running or Redis is unavailable, the handler falls back to direct AMI queries.
