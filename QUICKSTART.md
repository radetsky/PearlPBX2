# PearlPBX2 — Quick Start

Two ways to get PearlPBX2 running, depending on what you're doing. See [README.md](README.md) for the full feature list, architecture, and configuration reference.

## Requirements

- Python 3.10+ / Django 5.2
- PostgreSQL 14+
- Redis 7+
- Asterisk 22+ with `res_pjsip`, `res_agi`, `cdr_pgsql`

(Docker Compose below provides all of these except your own clone of the repo.)

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

To pull in updates later, run `sudo ./update.sh` from the same directory — it runs `ansible/update.yml`, which keeps a rollback history (`rollback.sh`) in case an update needs to be reverted.

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

Open `http://localhost:8000/admin/`, log in, configure SIP endpoints/trunks/routing, then use **Admin → Apply Changes** to push the generated config to Asterisk.

Notes:
- `django` runs migrations and `collectstatic` automatically on every start (`docker-entrypoint.sh`) — no manual `migrate` step needed.
- `asterisk-init` seeds a minimal AMI-enabled `manager.conf` before Asterisk's first boot, so `fastagi`/`dashboard-listener` come up connected immediately; "Apply Changes" later overwrites it with the real generated config using the same credentials.
- The callback daemon is opt-in (it originates real outbound calls): `docker compose --profile callback up -d callback-service`.
- A `docker-compose.override.yml` is picked up automatically and gives the `django` container source hot-reload for local development; run `docker compose -f docker-compose.yml up -d` to skip it.
