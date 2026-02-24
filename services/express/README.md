# Express AGI Service

Integration service between Asterisk PBX and Express Taxi dispatching system.

## Overview

Two cooperating services handle the Express Taxi integration:

1. **`express_fastagi.py`** — FastAGI server (Twisted, port 4574). Called first from
   the dialplan. Allocates a **ULINE** (unique line number, 1-199) and sets it as an
   Asterisk channel variable (`ULINE`). No HTTP calls.

2. **`express_agi.py`** — Standalone AGI script. Called from the queue or dialplan
   after the FastAGI. Reads the `ULINE` channel variable plus caller info
   (`CALLERID`, `YTAXIPROV`, `YTAXICLASS`, `MEMBERINTERFACE`) and fires the HTTP GET
   to the Express Taxi API. No Redis dependency.

The ULINE doubles as the **parking slot number**: when an operator parks a call,
Asterisk uses `Park(PARKINGEXTEN=${ULINE})` to park it at exactly that slot.
Another operator can retrieve it by dialing the slot number (e.g. `42`).

## Files

| File | Description |
|------|-------------|
| `uline_redis.py` | Shared `ULineRedisManager` class — all Redis I/O lives here |
| `express_fastagi.py` | FastAGI server (Twisted, port 4574) — ULINE allocation only, no HTTP |
| `express_agi.py` | Standalone AGI script — HTTP notifier only, no Redis dependency |
| `redis_state_flush.py` | Emergency CLI tool to inspect and clear Redis state |
| `requirements.txt` | Dependencies for FastAGI server (Twisted, redis, dotenv) |
| `requirements-agi.txt` | Dependencies for standalone AGI script (requests, dotenv) |

## ULINE Lifecycle

```
Incoming call
  ├─ FastAGI called (express_fastagi.py)
  │    └─ allocate_uline(uniqueid, channel, ...)   [Lua script, atomic]
  │         ├─ HSET express:uline:{N}  { uniqueid, channel, caller_id, ... }
  │         ├─ SET  express:uid:{uniqueid}  N
  │         └─ SET VARIABLE ULINE=N    ← Asterisk channel variable
  └─ Standalone AGI called (express_agi.py)
       └─ GET VARIABLE ULINE  (reads value set above)
            └─ HTTP GET → Express Taxi API

Operator parks the call
  └─ Park(PARKINGEXTEN=${ULINE})
       └─ call waits at slot N
       └─ ULINE state in Redis is unchanged
          (CDR uniqueid does not change on park/unpark)

Another operator picks up
  └─ ParkedCall(default, N)
       └─ ULINE state in Redis is unchanged

Call ends (Hangup AMI event)
  └─ dashboard_listener.py
       ├─ DEL asterisk:channel:{channel}
       └─ DEL asterisk:uid:{uniqueid}
            └─ express_fastagi.py sweep (every 5 min) sees
               that asterisk:uid:{uniqueid} is gone → releases ULINE
               DEL express:uline:{N}
               DEL express:uid:{uniqueid}
```

### Why ULINE is tied to CDR(uniqueid), not to channel name

The channel name changes during parking (`PJSIP/customer-xxx` becomes a
`Local/` channel inside the parking lot). The CDR `uniqueid` is stable for the
entire lifetime of the call, so it is used as the key for reverse lookup.

## Redis Keys

| Key | TTL | Value | Written by | Deleted by |
|-----|-----|-------|-----------|------------|
| `express:uline:{N}` | 3600s | Hash: uniqueid, channel, cdr_start, allocated_at, caller_id, provider | express AGI | sweep or Redis TTL |
| `express:uid:{uniqueid}` | 3600s | String: N | express AGI | sweep or Redis TTL |
| `asterisk:uid:{uniqueid}` | 3600s | String: channel name | dashboard_listener | dashboard on Hangup |
| `asterisk:channel:{channel}` | 3600s | JSON: full channel data | dashboard_listener | dashboard on Hangup |
| `asterisk:channels:all` | 3600s | JSON: all active channels | dashboard_listener | Redis TTL |

### `asterisk:uid:{uniqueid}` — call liveness indicator

`dashboard_listener.py` writes this key on **every** Newchannel **and** Newstate AMI
event (not only on channel creation). This makes the key restart-safe: if the
dashboard service restarts and loses its in-memory state, it continues refreshing
`asterisk:uid:{uniqueid}` on every Newstate event it receives, even for calls that
were already active before the restart. The key is deleted on Hangup.

The ULINE sweep reads this key as its **sole liveness signal** for a call:
- Key present → call is alive, do not release ULINE.
- Key absent → call has ended (or was never seen), ULINE can be released.

### Restart-safety mechanism

`update_uid_state()` is called in `handle_newstate` **outside** the
`if channel in self.channels_state:` guard:

```python
if channel in self.channels_state:
    # update in-memory state (skipped after dashboard restart)
    ...

# Always refresh the uid mapping regardless of in-memory state
await self.update_uid_state(uniqueid, channel)
```

After a dashboard restart, `channels_state` is empty, so the in-memory guard is
never entered. But `update_uid_state()` still runs on every Newstate event, keeping
`asterisk:uid:{uniqueid}` alive for all ongoing calls. This prevents the sweep from
falsely releasing ULINEs for calls that are still active.

### `asterisk:channels:all` — dashboard liveness indicator

The sweep uses this key to detect whether `dashboard_listener` is running:

```
dashboard alive → key exists  → sweep can safely release orphaned ULINEs
dashboard down  → key absent  → sweep skips auto-release to avoid false positives
```

The key is refreshed on every channel event (TTL 3600 s). If the dashboard is
stopped, the key expires within an hour. During that window the sweep is intentionally
conservative and will not release any ULINEs.

## Orphan Cleanup

ULINEs are released in three ways, in order of priority:

1. **Normal path** — dashboard receives the Hangup AMI event, deletes
   `asterisk:uid:{uniqueid}`, and the next sweep run releases the ULINE.
2. **Periodic sweep** — `express_fastagi.py` runs `sweep_ulines()` every
   `ULINE_SWEEP_INTERVAL` seconds (default 300). Any ULINE whose
   `asterisk:uid:{uniqueid}` key is missing (and dashboard is alive) is released.
3. **Redis TTL** — all keys expire after `ULINE_TTL` seconds (default 3600).
   This is the last-resort fallback if both the dashboard and sweep fail.

## Configuration

All settings are read from the `.env` file in the service directory or from
environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `ULINE_MIN` | `1` | Lowest ULINE number |
| `ULINE_MAX` | `199` | Highest ULINE number |
| `ULINE_TTL` | `3600` | Key TTL in seconds (1 hour) |
| `ULINE_SWEEP_INTERVAL` | `300` | Orphan sweep interval in seconds |
| `FASTAGI_HOST` | `0.0.0.0` | FastAGI listen address |
| `FASTAGI_PORT` | `4574` | FastAGI listen port |
| `DEFAULT_EXPRESS_URL` | — | Express Taxi API endpoint |
| `DEFAULT_EXPRESS_PROVIDER` | — | Default provider ID |
| `DEFAULT_EXPRESS_CLASS` | `0` | Default car class |
| `HTTP_TIMEOUT` | `10` | Express API request timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |

### Per-call provider and class override (channel variables)

`express_agi.py` resolves provider and car class using a fallback chain.
Set these channel variables in the dialplan to override the defaults per call:

| Channel variable | Fallback | Description |
|-----------------|----------|-------------|
| `YTAXIPROV` | `EXPRESS_PROVIDER` env → `DEFAULT_EXPRESS_PROVIDER` env | Provider ID sent to the Express API |
| `YTAXICLASS` | `EXPRESS_CLASS` env → `DEFAULT_EXPRESS_CLASS` env (default `0`) | Car class sent to the Express API |

Example dialplan usage:
```
exten => s,1,Set(YTAXIPROV=mycompany)
same => n,Set(YTAXICLASS=2)
same => n,AGI(agi://localhost:4574)
same => n,Queue(express-queue,,,,AGI(express_agi.py))
```

## Dialplan Integration

**Critical ordering rule:** FastAGI (`express_fastagi.py`) **must** be called
**before** the Queue (or before `express_agi.py` is invoked). FastAGI sets the
`ULINE` channel variable; `express_agi.py` reads it. If the order is reversed,
`ULINE` will be absent and `express_agi.py` will skip the Express API notification.

### Incoming call (allocate ULINE + notify Express)

Step 1 — allocate ULINE via FastAGI (sets `ULINE` channel variable, no HTTP):
```
same => n,AGI(agi://localhost:4574)
```

Step 2 — notify Express API via standalone AGI (reads `ULINE`, fires HTTP GET).
Call this inside the Queue `agi` parameter or immediately after it:
```
same => n,AGI(express_agi.py)
```

Both steps together in a context:
```
exten => s,1,AGI(agi://localhost:4574)
same => n,Queue(express-queue,,,,AGI(express_agi.py))
```

If FastAGI fails to allocate a ULINE (all 199 slots busy or Redis is down),
`express_agi.py` detects `ULINE=0` and skips the HTTP notification with an error
log. The call continues normally — only the Express API is not notified.

### Parking

```
same => n,NoOp(PARKINGEXTEN=${ULINE})
same => n,Park()
same => n,Hangup()
```

### Retrieving a parked call

```
_[1-9]! => {
    ParkedCall(default,${EXTEN});
}
```

## Emergency Flush

```bash
# Show current key counts
python redis_state_flush.py

# Delete all ULINE state
python redis_state_flush.py --ulines

# Delete all channel state (asterisk:channel:*, asterisk:uid:*)
python redis_state_flush.py --channels

# Delete everything (ULINE + channels + queues)
python redis_state_flush.py --all
```

From FastAGI CLI:
```bash
python express_fastagi.py --flush-ulines
```

## Installation

### FastAGI server (systemd)

```bash
cd services/express
python3 -m venv .python-venv
source .python-venv/bin/activate
pip install -r requirements.txt

# copy systemd unit and enable
sudo systemctl enable express-fastagi
sudo systemctl start express-fastagi
```

### Standalone AGI script

```bash
sudo apt install python3-dotenv python3-requests
sudo cp express_agi.py /var/lib/asterisk/agi-bin/
sudo cp .env /var/lib/asterisk/agi-bin/
```

## Visual Monitor

Active ULINEs can be monitored in the PearlPBX2 web interface at `/dashboard/ulines/`.

The page shows:
- Current total / used / free ULINE counts
- Per-ULINE table: slot number, liveness status, channel, uniqueid, caller ID, age, Redis TTL
- Color coding: **green** = channel alive in Redis, **yellow** = orphan candidate
- Auto-refreshes every 10 seconds
- "Flush all ULINEs" button (superuser only)
