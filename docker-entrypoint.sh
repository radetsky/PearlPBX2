#!/bin/sh
set -e

python manage.py migrate --noinput

# First-run bootstrap, mirroring ansible/install.yml's one-time seed_quickstart +
# apply_changes steps (ansible/update.yml never repeats them — a redeploy only
# migrates and restarts). The marker lives on the shared asterisk_config volume
# since that's what apply_changes actually populates, so it naturally resets
# together with a fresh Asterisk config volume.
QUICKSTART_MARKER="${ASTERISK_CONFIG_DIR:-/etc/asterisk}/.pearlpbx2-quickstart-applied"

if [ ! -f "$QUICKSTART_MARKER" ]; then
    echo "First run detected — seeding quick-start data and applying Asterisk config..."
    python manage.py seed_quickstart
    python manage.py apply_changes
    touch "$QUICKSTART_MARKER"
else
    echo "Quick-start already applied (see $QUICKSTART_MARKER), skipping seed/apply"
fi

python manage.py collectstatic --noinput --clear

exec "$@"
