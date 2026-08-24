# PearlPBX2 — Quick Start

Two ways to get PearlPBX2 running, depending on what you're doing. See [README.md](README.md) for the full feature list, architecture, and configuration reference.

## Requirements

- **Option 1 (Ansible)**: a bare Debian or Ubuntu host, that's it. `install.sh`
  installs Ansible itself, and `install.yml` provisions everything else —
  Python, PostgreSQL, Redis, and Asterisk 22 (compiled from source) — on the
  target host. Nothing to install by hand first.
- **Option 2 (Docker Compose)**: just Docker and Docker Compose. The stack
  (Python 3.10+/Django 5.2, PostgreSQL 14+, Redis 7+, Asterisk 22+ with
  `res_pjsip`/`res_agi`/`cdr_pgsql`) runs entirely in containers.

## What you get out of the box

A fresh install seeds a working demo PBX, not an empty database. After the first
migration/deploy run, you already have:

| Extensions | What it is |
|---|---|
| `201`–`210` | 10 SIP users (`ppbxuser201`…`ppbxuser210`), random passwords |
| `130` | Echo test |
| `131` / `132` | Log a queue member in / out (`PauseQueueMember`) |
| `140` | Test the IVR from an internal phone |
| `141` | Sales queue |
| `142` | Support queue |

Plus:

- Two queues, **Sales** and **Support**, with all 10 users as members
- An English IVR (`ivr-main`): "press 1 for Sales, press 2 for Support", 2 retries on
  timeout/invalid digit before it falls back to Sales
- An example SIP trunk, `myprovider` (`csbc.myprovider.net`, user `test` / `secret`) —
  a placeholder to replace with your real provider (see
  [Replace the example trunk](#replace-the-example-trunk))
- Two routing tables: **Incoming** (any inbound call → the IVR) and **Outgoing**
  (all 10 users route through it: internal extensions, the `130`–`142` numbers, and
  anything else out via `myprovider`)

This is seeded by `manage.py seed_quickstart`, which only runs once, on a fresh
install — see [Notes / next steps](#notes--next-steps) for how that's guarded.

## Option 1: Ansible (production install)

Requires a Debian or Ubuntu host (the playbook uses `apt` and systemd directly — no other distros are supported).

Provisions Asterisk (compiled from source), PostgreSQL, Redis, nginx, systemd units, and the firewall on a fresh host — no manual steps:

```bash
git clone https://github.com/radetsky/PearlPBX2.git
cd PearlPBX2
sudo ./install.sh
```

`install.sh` installs Ansible itself if needed and runs `ansible/install.yml` (add `-v` for verbose Ansible output), logging to `/var/log/pearlpbx2-install.log`. When it finishes, create the admin user with:

```bash
./manage.sh createsuperuser
```

then open `https://<your-host>/admin/`.

To pull in updates later, run `sudo ./update.sh` from the same directory — it runs `ansible/update.yml`, which keeps a rollback history (`rollback.sh`) in case an update needs to be reverted. `update.sh` never re-seeds the quick-start data described above, so it's safe to run on a live system.

See `ansible/group_vars/all.yml` for the variables it uses (install dir, DB name, Asterisk version, etc.) and `ansible/roles/` for what each role does.

## Option 2: Docker Compose (recommended — evaluation, development)

```bash
git clone https://github.com/radetsky/PearlPBX2.git
cd PearlPBX2

cp env.sample .env
# Edit .env — set DB credentials, then generate and fill in:
#   DJANGO_SECRET_KEY:       openssl rand -hex 50
#   ASTERISK_MANAGER_SECRET: openssl rand -base64 48

docker compose up -d
docker compose exec django python manage.py createsuperuser
```

Open `http://localhost:8000/admin/`, log in, and go straight to
[Apply Changes](#apply-changes) — the quick-start data above is already in the
database, it just needs to be pushed out to Asterisk once.

Notes:
- `django` runs migrations and the quick-start seed automatically on every start (`docker-entrypoint.sh`) — no manual `migrate` step needed. The seed only acts once; subsequent restarts are a no-op.
- `asterisk-init` seeds a minimal AMI-enabled `manager.conf` before Asterisk's first boot, so `fastagi`/`dashboard-listener` come up connected immediately; "Apply Changes" later overwrites it with the real generated config using the same credentials.
- The callback daemon is opt-in (it originates real outbound calls): `docker compose --profile callback up -d callback-service`.
- A `docker-compose.override.yml` is picked up automatically and gives the `django` container source hot-reload for local development; run `docker compose -f docker-compose.yml up -d` to skip it.

## Get your SIP credentials

The 201–210 passwords are generated randomly and only ever stored in the database.
In the admin, go to **SIP Users**, open **201** (or any other), and reveal the
**Password** field — these instructions use **201** and **202**.

## Register two softphones

In any SIP client (Zoiper, Linphone, a desk phone, …), register two accounts using
the credentials above:

- **Server**: your PBX host/IP
- **Transport**: UDP, port `5060`
- **Username / Password**: `ppbxuser201` / the password from the admin (and likewise for 202)

## Apply Changes

Nothing above reaches Asterisk until you push it. In the admin UI go to
**Admin → Apply Changes** (`/admin/apply`). This regenerates `extensions.ael`,
`pjsip.conf`, `queues.conf`, `queuerules.conf`, `manager.conf`, `musiconhold.conf`,
and `confbridge.conf` from the database, backs up the previous versions, and
reloads Asterisk. Run this once now, and again after any change made through the
admin UI.

## Test call scenarios

Do these in order — each one builds on the last.

| # | Scenario | Dial | Expect / verify |
|---|---|---|---|
| 1 | Echo test | `130` | You hear your own voice looped back. `asterisk -rx "core show channels"` shows the call. |
| 2 | Internal call | 201 dials `202` | 202 rings. `asterisk -rx "pjsip show endpoints"` shows both as `Avail`. |
| 3 | Transfer | Mid-call, blind-transfer with `#1` or attended with `#2`, target `202` or `141` | See [Transfer](#transfer) below — needs `TRANSFER_CONTEXT`. |
| 4 | Outbound to the outside world | Dial any external number | Fails until you [replace the example trunk](#replace-the-example-trunk). Then `asterisk -rx "pjsip show registrations"` should show `myprovider` as `Registered`. |
| 5 | IVR from an internal phone | `140`, then press `1` or `2` | You land in Sales or Support. `asterisk -rx "queue show Sales"` shows the call. |
| 6 | Production inbound call | Call your DID from the outside world | Routed via **Incoming** → `ivr-main`. `asterisk -rx "pjsip set logger on"` to watch the SIP trace live. |

(Docker Compose: prefix each `asterisk -rx "..."` with `docker compose exec asterisk`.)

### Transfer

Transfer feature codes come from `contrib/configs/features.conf`:
`#1` = blind transfer, `#2` = attended transfer (`[featuremap]` section). Both
require the `t`/`T` options on the `Dial()` the call came in on — already present
on every seeded extension (e.g. `Dial(PJSIP/${EXTEN}@myprovider,120,tT)`).

Once a transfer is initiated, Asterisk resolves the dialed digits through the
**`TRANSFER_CONTEXT`** global variable rather than the channel's own context —
seeded to:

```
globals {
    TRANSFER_CONTEXT=Outgoing;
}
```

This is why users are on the `Outgoing` routing table: it's what lets a transfer
target be either an internal extension (`_2XX`) or an external number (`_X.`) via
`myprovider`, from a single, consistent context.

## Replace the example trunk

`myprovider` (`csbc.myprovider.net` / `test` / `secret`) is a placeholder — it
will never register. In **Admin → SIP Uplinks and Peers → myprovider**, replace:

- `registration_uri` / `contact_uri` / `match_hosts` — your provider's SBC hostname
- `username` / `secret` — your account credentials

Then [Apply Changes](#apply-changes) and check:

```bash
asterisk -rx "pjsip show registrations"
```

`myprovider` should move from `Rejected`/`No response` to `Registered`.

## Notes / next steps

- **International calls are blocked by default.** The `Outgoing` table routes
  `_00X!` (international prefixes) into the `international-calls` context, which
  just hangs up — a safe default so a fresh install with example credentials
  never becomes a toll-fraud vector. Remove or repoint that
  `DialplanExtension` once you're ready to allow them.
- **`Outgoing` vs the legacy `PEARLPBX` table.** `PEARLPBX` still exists (it's
  `settings.PEARLPBX_DEFAULT_ROUTING_TABLE`, used as a fallback elsewhere) but no
  SIP user is routed through it anymore after the quick-start seed runs — they're
  all on `Outgoing`.
- **Multiple trunks / least-cost routing.** The seeded `outbound-external`
  context dials `myprovider` directly. For more than one trunk, switch to
  `AGI(agi://127.0.0.1:4573/dial-trunk-group,...)` — see
  `services/fastagi/README.md` for trunk groups with failover.
- **Music on hold** for the queues uses `contrib/moh/on_hold_music.wav` — replace
  the files under the `default` MOH class with your own.
- **Call recording** is not enabled by default; see `docs/ua/admin-guide.md` for
  `MixMonitor` setup.
- **The quick-start seed itself** is `manage.py seed_quickstart` — it checks
  whether any `Queue`, `SIPPeer`, or `Incoming`/`Outgoing` routing table already
  exists and does nothing if so, so it's safe even if invoked by hand. Ansible's
  `install.yml` calls it once, gated on the same "first install on this host"
  check used for secret generation; `update.yml` never calls it at all.
