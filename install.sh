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

# Parse optional -v flag for verbose ansible output
ANSIBLE_VERBOSITY=""
if [ "${1:-}" = "-v" ]; then
  ANSIBLE_VERBOSITY="-v"
fi

# Recover from interrupted dpkg/apt (safe no-op if not needed)
dpkg --configure -a 2>/dev/null || true

apt-get update -qq
apt-get install -y ansible

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ansible-playbook $ANSIBLE_VERBOSITY \
  -i "$SCRIPT_DIR/ansible/inventory/localhost.yml" \
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
echo "======================================================"
echo ""
echo " Optional — configure MP3 backup sync:"
echo ""
echo "  Edit /etc/PearlPBX/syncmp3/env and set BACKUP_DIR"
echo "  (e.g. a mounted NAS or iSCSI volume)."
echo "  Sync runs daily at 03:00 via cron."
echo "======================================================"
echo ""
echo " Optional — enable Slack server alerts:"
echo ""
echo "  1. Create a Slack Incoming Webhook:"
echo "     https://api.slack.com/apps → New App → Incoming Webhooks"
echo ""
echo "  2. Paste the webhook URL into:"
echo "     /etc/PearlPBX/system_monitor/env"
echo ""
echo "  Alerts fire every 15 min (disk, CPU, memory, services)."
echo "======================================================"
echo ""
echo " Optional — catch unmatched inbound calls and notify Slack:"
echo ""
echo "  1. Create a Slack Incoming Webhook:"
echo "     https://api.slack.com/apps → New App → Incoming Webhooks"
echo ""
echo "  2. Paste the webhook URL into:"
echo "     /etc/PearlPBX/AGI/env"
echo ""
echo "  3. Add to your catch-all dialplan extension:"
echo "     AGI(unmatched_call.py,\${CALLERID(num)},\${EXTEN},\${CHANNEL});"
echo "     See: services/agi/README.md for missed_call.py as well"
echo "======================================================"
echo ""
echo " Re-run notes (if you interrupted the install):"
echo "  - If apt was interrupted: sudo dpkg --configure -a"
echo "  - If env file is corrupt: sudo rm /etc/PearlPBX/PearlPBX2/env"
echo "    then re-run this script"
echo "======================================================"
