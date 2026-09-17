#!/bin/bash
set -euo pipefail

if [ "$(id -un)" != "root" ]; then
    exec sudo "$0" "$@"
fi

LOG_FILE="/var/log/pearlpbx2-install.log"

echo ""
echo "======================================================"
echo " PearlPBX2 Installer"
echo "======================================================"
echo ""
echo " WARNING: Asterisk 22 will be compiled from source."
echo " This step takes 15-30 minutes depending on your CPU."
echo " Do not interrupt the process."
echo ""
echo " Full log: $LOG_FILE"
echo " For verbose output, run:"
echo "   sudo bash install.sh -v"
echo ""
echo " If you need to re-run after interruption, see notes"
echo " at the bottom of this script."
echo "======================================================"
echo ""

# Parse flags: -v (verbose ansible output), --domain <fqdn>, --email <addr>
ANSIBLE_VERBOSITY=""
EXTRA_VARS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -v)
      ANSIBLE_VERBOSITY="-v"
      shift
      ;;
    --domain)
      EXTRA_VARS+=(-e "pearlpbx2_domain=$2")
      shift 2
      ;;
    --email)
      EXTRA_VARS+=(-e "pearlpbx2_acme_email=$2")
      shift 2
      ;;
    -h|--help)
      echo "Usage: sudo ./install.sh [-v] [--domain <fqdn>] [--email <address>]"
      echo ""
      echo "  --domain   Public FQDN to request a Let's Encrypt certificate for."
      echo "             Without it, the installer tries an IP-address certificate"
      echo "             automatically, falling back to self-signed."
      echo "  --email    Let's Encrypt account email (optional)."
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Recover from interrupted dpkg/apt (safe no-op if not needed)
dpkg --configure -a 2>/dev/null || true

apt-get update -qq
apt-get install -y ansible

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ansible-playbook $ANSIBLE_VERBOSITY \
  -i "$SCRIPT_DIR/ansible/inventory/localhost.yml" \
  "${EXTRA_VARS[@]}" \
  "$SCRIPT_DIR/ansible/install.yml" \
  2>&1 | tee "$LOG_FILE"

# tee exits 0 even if ansible failed — check the exit code
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  echo ""
  echo "Installation FAILED. See $LOG_FILE for details." >&2
  exit 1
fi

echo ""
echo "======================================================"
echo " PearlPBX2 installation complete!"
echo "======================================================"
echo ""
echo " Next step — create the admin user:"
echo ""
echo "   ./manage.sh createsuperuser"
echo ""
echo " Then open: https://$(hostname)/admin/"
echo ""

TLS_MODE_FILE="/etc/PearlPBX/tls-mode"
if [ -r "$TLS_MODE_FILE" ] && [ "$(cat "$TLS_MODE_FILE")" = "letsencrypt" ]; then
  echo " TLS: a trusted Let's Encrypt certificate is active and renews"
  echo " automatically (systemctl list-timers pearlpbx2-certbot-renew)."
else
  echo " TLS: using a self-signed certificate; your browser will warn on"
  echo " first visit. For a trusted certificate, re-run:"
  echo "   sudo ./install.sh --domain <your-domain> --email <you@example.com>"
fi
echo ""
echo " For optional integrations and re-run notes, see:"
echo "   docs/en/quickstart.md (also docs/ua, docs/es)"
echo "======================================================"
