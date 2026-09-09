#!/usr/bin/env bash
#
# PearlPBX2 one-line production installer.
#
#   curl -fsSL https://pearlpbx2.com/quickstart-install.sh | sudo bash
#
# Clones PearlPBX2 over HTTPS and runs the production Ansible installer
# (install.sh) non-interactively, then creates an admin user with a
# generated password. Debian/Ubuntu only. Must run as root.

main() {
set -euo pipefail

REPO_URL="https://github.com/radetsky/PearlPBX2.git"
REF="${PEARLPBX2_REF:-main}"
DIR="${PEARLPBX2_DIR:-/opt/PearlPBX2}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root. Try:" >&2
    echo "  curl -fsSL https://pearlpbx2.com/quickstart-install.sh | sudo bash" >&2
    exit 1
fi

if [ ! -r /etc/os-release ]; then
    echo "Cannot detect the OS (/etc/os-release missing). Debian/Ubuntu required." >&2
    exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
    debian:*|ubuntu:*|*:*debian*|*:*ubuntu*) ;;
    *)
        echo "Unsupported OS: ${PRETTY_NAME:-unknown}. PearlPBX2 install.sh requires Debian or Ubuntu." >&2
        exit 1
        ;;
esac

echo "==> Installing prerequisites (git, ca-certificates, openssl)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git ca-certificates openssl >/dev/null

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

echo "==> Running the production installer (install.sh)..."
echo "    This compiles Asterisk from source and takes 15-30 minutes."
if [ -r /dev/tty ]; then
    bash "${DIR}/install.sh" < /dev/tty
else
    bash "${DIR}/install.sh" < /dev/null
fi

ADMIN_PASS="$(gen_secret)"
ADMIN_CREATED=1
if ! DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASS}" \
    sudo -u asterisk env DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASS}" \
    /usr/local/PearlPBX2/manage.sh createsuperuser --noinput \
    --username admin --email admin@localhost; then
    ADMIN_CREATED=0
fi

FQDN="$(hostname -f 2>/dev/null || hostname)"
PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo ""
echo "======================================================"
echo " PearlPBX2 quick-start install complete!"
echo "======================================================"
echo ""
echo " Admin URL:  https://${FQDN}/admin/"
[ -n "${PRIMARY_IP}" ] && echo "             https://${PRIMARY_IP}/admin/"
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
echo " The TLS certificate is self-signed; your browser will warn on"
echo " first visit."
echo ""
echo " First test calls (echo test, internal call, IVR, ...):"
echo "   ${DIR}/docs/en/quickstart.md"
echo ""
echo " To update later: sudo ${DIR}/update.sh"
echo "======================================================"
}

main "$@"
