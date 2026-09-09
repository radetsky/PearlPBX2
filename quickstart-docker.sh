#!/usr/bin/env bash
#
# PearlPBX2 one-line Docker playground.
#
#   curl -fsSL https://pearlpbx2.com/quickstart-docker.sh | bash
#
# Clones PearlPBX2 over HTTPS, generates a .env, and brings up the
# production-like docker compose stack, then creates an admin user with
# a generated password. Requires Docker + Docker Compose to be installed
# already — this script only checks for them.

main() {
set -euo pipefail

REPO_URL="https://github.com/radetsky/PearlPBX2.git"
REF="${PEARLPBX2_REF:-main}"
DIR="${PEARLPBX2_DIR:-${PWD}/PearlPBX2}"
COMPOSE="docker compose -f docker-compose.yml"

if ! command -v git >/dev/null 2>&1; then
    echo "git is required. Install it first (e.g. 'apt-get install git' or 'brew install git')." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but was not found." >&2
    echo "Install it first: https://docs.docker.com/get-docker/" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose (v2, 'docker compose') is required but was not found." >&2
    echo "Install it first: https://docs.docker.com/compose/install/" >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but the daemon is not reachable." >&2
    echo "Is Docker running? Are you in the 'docker' group (or using sudo)?" >&2
    exit 1
fi

gen_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 24
    else
        LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24
    fi
}

echo "==> Fetching PearlPBX2 (${REF}) into ${DIR}..."
if [ -d "${DIR}/.git" ]; then
    git -C "${DIR}" fetch --quiet origin "${REF}"
    git -C "${DIR}" checkout --quiet "${REF}"
    git -C "${DIR}" pull --quiet origin "${REF}"
elif [ -e "${DIR}" ]; then
    echo "Error: ${DIR} exists and is not a git repository. Set PEARLPBX2_DIR to a different path." >&2
    exit 1
else
    git clone --quiet --branch "${REF}" "${REPO_URL}" "${DIR}"
fi

cd "${DIR}"

if [ ! -f .env ]; then
    echo "==> Generating .env..."
    PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    ALLOWED_HOSTS="localhost,127.0.0.1,pearlpbx2"
    [ -n "${PRIMARY_IP}" ] && ALLOWED_HOSTS="${ALLOWED_HOSTS},${PRIMARY_IP}"
    cat > .env <<EOF
DB_NAME=pearlpbx2
DB_USER=pearlpbx2
DB_PASS=$(gen_secret)
DJANGO_SECRET_KEY=$(gen_secret)$(gen_secret)
ASTERISK_MANAGER_USERNAME=admin
ASTERISK_MANAGER_SECRET=$(gen_secret)
DEVMODE=Development
ALLOWED_HOSTS=${ALLOWED_HOSTS}
EOF
    chmod 600 .env
else
    echo "==> Reusing existing .env"
fi

echo "==> Starting the stack (docker compose up -d --build)..."
echo "    First run downloads/builds images and Asterisk sound files — this can take a while."
${COMPOSE} up -d --build

echo "==> Waiting for the app to come up..."
READY=0
for _ in $(seq 1 180); do
    if curl -fsS -o /dev/null "http://localhost:8000/admin/login/" 2>/dev/null; then
        READY=1
        break
    fi
    sleep 5
done

if [ "${READY}" -ne 1 ]; then
    echo "Timed out waiting for the app to start. Recent logs:" >&2
    ${COMPOSE} logs --tail=100 pearlpbx2 >&2
    exit 1
fi

ADMIN_PASS="$(gen_secret)"
ADMIN_CREATED=1
if ! ${COMPOSE} exec -T -e DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASS}" pearlpbx2 \
    python manage.py createsuperuser --noinput --username admin --email admin@localhost; then
    ADMIN_CREATED=0
fi

echo ""
echo "======================================================"
echo " PearlPBX2 Docker quick-start is up!"
echo "======================================================"
echo ""
echo " Admin URL:  http://localhost:8000/admin/"
echo ""
if [ "${ADMIN_CREATED}" -eq 1 ]; then
    echo " Login:      admin"
    echo " Password:   ${ADMIN_PASS}"
    echo ""
    echo " CHANGE THIS PASSWORD AFTER FIRST LOGIN."
else
    echo " Admin user 'admin' already exists — password unchanged."
fi
echo ""
echo " Demo data is already seeded and applied to Asterisk: SIP users"
echo " 201-210, echo test 130, IVR 140, Sales/Support queues 141/142."
echo " See ${DIR}/docs/en/quickstart.md for test call scenarios."
echo ""
echo " SIP:  5060/udp+tcp   RTP: 10000-10099/udp"
echo ""
echo " Stop:      (cd ${DIR} && ${COMPOSE} down)"
echo " Stop+wipe: (cd ${DIR} && ${COMPOSE} down -v)"
echo " Callback service (opt-in): ${COMPOSE} --profile callback up -d callback-service"
echo "======================================================"
}

main "$@"
