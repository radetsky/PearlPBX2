#!/bin/bash
set -euo pipefail

if [ "$(id -un)" != "root" ]; then
    exec sudo "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/var/log/pearlpbx2-asterisk-update.log"
STATE_FILE="/var/backups/asterisk-upgrade/state.json"
RESOLVE_SCRIPT="$SCRIPT_DIR/bin/pearlpbx2_resolve_asterisk_rollback.py"

usage() {
    echo "Usage: $0 [--version X.Y.Z] [-y] [--force] [--no-wait] [--timeout SEC]"
    echo "       $0 --rollback [-n STEPS] [--restore-configs] [--restore-sounds] [-y]"
    echo "       $0 -l"
    echo ""
    echo "  --version X.Y.Z     target Asterisk version (default: asterisk_version in group_vars/all.yml)"
    echo "  --force              re-run even if already on the target version"
    echo "  --no-wait            skip the graceful drain, stop Asterisk immediately"
    echo "  --timeout SEC        seconds to wait for active calls to drain (default: 900)"
    echo "  --rollback           restore the previous Asterisk version from its backup"
    echo "  -n, --steps STEPS    (with --rollback) how many upgrades to roll back (default: 1)"
    echo "  --restore-configs    (with --rollback) also restore /etc/asterisk from the backup"
    echo "  --restore-sounds     (with --rollback) also restore /var/lib/asterisk from the backup"
    echo "  -y, --yes            skip the confirmation prompt"
    echo "  -l, --list           show upgrade history and exit, no upgrade or rollback"
}

# Prompts for a typed "yes" unless -y/--yes was given; aborts otherwise.
confirm_or_abort() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    read -r -p "Type 'yes' to proceed: " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
}

# Runs an ansible-playbook invocation, tee'd to $LOG_FILE, failing loudly on
# error (tee itself always exits 0, so PIPESTATUS is what actually matters).
run_playbook_or_fail() {
    local label="$1"
    shift
    ansible-playbook -i inventory/localhost.yml "$@" 2>&1 | tee "$LOG_FILE"
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        echo ""
        echo "$label FAILED. See $LOG_FILE for details." >&2
        return 1
    fi
}

ROLLBACK=0
STEPS=1
ASSUME_YES=0
LIST_ONLY=0
FORCE=0
NO_WAIT=0
TIMEOUT=""
RESTORE_CONFIGS=0
RESTORE_SOUNDS=0
VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            VERSION="${2:?missing value for $1}"
            shift 2
            ;;
        --rollback)
            ROLLBACK=1
            shift
            ;;
        -n|--steps)
            STEPS="${2:?missing value for $1}"
            shift 2
            ;;
        --restore-configs)
            RESTORE_CONFIGS=1
            shift
            ;;
        --restore-sounds)
            RESTORE_SOUNDS=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --no-wait)
            NO_WAIT=1
            shift
            ;;
        --timeout)
            TIMEOUT="${2:?missing value for $1}"
            shift 2
            ;;
        -y|--yes)
            ASSUME_YES=1
            shift
            ;;
        -l|--list)
            LIST_ONLY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ "$LIST_ONLY" -eq 1 ]; then
    if [ ! -f "$STATE_FILE" ]; then
        echo "No asterisk-upgrade ledger found at $STATE_FILE — no upgrades recorded yet."
        exit 0
    fi
    python3 -c "
import json

with open('$STATE_FILE') as f:
    history = json.load(f).get('history', [])

print(f'{\"steps back\":<12}{\"timestamp\":<22}{\"from\":<12}to')
for i, entry in enumerate(reversed(history), start=1):
    print(f'{i:<12}{entry[\"timestamp\"]:<22}{entry[\"from_version\"]:<12}{entry[\"to_version\"]}')
"
    exit 0
fi

cd "$SCRIPT_DIR/ansible"

if [ "$ROLLBACK" -eq 1 ]; then
    if [ ! -f "$STATE_FILE" ]; then
        echo "ERROR: no asterisk-upgrade ledger found at $STATE_FILE" >&2
        echo "Nothing has been recorded to roll back to yet." >&2
        exit 1
    fi

    RESOLVED="$(python3 "$RESOLVE_SCRIPT" "$STATE_FILE" --steps "$STEPS")" || exit 1
    IFS=$'\t' read -r CURRENT_VERSION TARGET_VERSION BACKUP_DIR <<< "$(python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d['current_version'], d['target_version'], d['backup_dir'], sep='\t')
" <<< "$RESOLVED")"

    echo ""
    echo "======================================================"
    echo " Asterisk Rollback"
    echo "======================================================"
    echo ""
    echo " Currently running version       : $CURRENT_VERSION"
    echo " Rolling back $STEPS step(s) to  : $TARGET_VERSION"
    echo " Restoring from                  : $BACKUP_DIR"
    echo ""
    echo " This will:"
    echo "   - gracefully stop Asterisk (waits for active calls to end)"
    echo "   - restore the previous binaries, modules and headers"
    [ "$RESTORE_CONFIGS" -eq 1 ] && echo "   - restore /etc/asterisk from the backup"
    [ "$RESTORE_SOUNDS" -eq 1 ] && echo "   - restore /var/lib/asterisk from the backup"
    echo "   - restart Asterisk and the AMI-connected services"
    echo ""
    echo " Full log: $LOG_FILE"
    echo " Run '$0 --list' to see the full upgrade history."
    echo "======================================================"
    echo ""

    confirm_or_abort

    EXTRA_ARGS=("-e" "steps=$STEPS")
    [ "$RESTORE_CONFIGS" -eq 1 ] && EXTRA_ARGS+=("-e" "restore_configs=true")
    [ "$RESTORE_SOUNDS" -eq 1 ] && EXTRA_ARGS+=("-e" "restore_sounds=true")

    run_playbook_or_fail "Rollback" rollback-asterisk.yml "${EXTRA_ARGS[@]}" || exit 1

    echo ""
    echo "======================================================"
    echo " Rollback complete — now running Asterisk $TARGET_VERSION"
    echo "======================================================"
    echo ""
    exit 0
fi

echo ""
echo "======================================================"
echo " Asterisk Upgrade"
echo "======================================================"
echo ""
[ -n "$VERSION" ] && echo " Target version                  : $VERSION"
echo " This will:"
echo "   - back up /etc/asterisk, the binaries/modules/headers, and /var/lib/asterisk"
echo "   - compile the new version while Asterisk keeps serving calls"
echo "   - gracefully stop Asterisk (waits for active calls to end, or use --no-wait)"
echo "   - install the new binaries/modules only — configs, sounds, logs, spool untouched"
echo "   - restart Asterisk and the AMI-connected services"
echo ""
echo " Full log: $LOG_FILE"
echo " Roll back afterwards with: $0 --rollback"
echo "======================================================"
echo ""

confirm_or_abort

EXTRA_ARGS=()
[ -n "$VERSION" ] && EXTRA_ARGS+=("-e" "asterisk_version=$VERSION")
[ "$FORCE" -eq 1 ] && EXTRA_ARGS+=("-e" "asterisk_force_upgrade=true")
[ "$NO_WAIT" -eq 1 ] && EXTRA_ARGS+=("-e" "asterisk_graceful_stop_timeout=0")
[ -n "$TIMEOUT" ] && EXTRA_ARGS+=("-e" "asterisk_graceful_stop_timeout=$TIMEOUT")

if ! run_playbook_or_fail "Upgrade" update-asterisk.yml "${EXTRA_ARGS[@]}"; then
    echo "If Asterisk was already stopped or partially installed, roll back with: $0 --rollback" >&2
    exit 1
fi

echo ""
echo "======================================================"
echo " Asterisk upgrade complete."
echo " Roll back with: $0 --rollback"
echo "======================================================"
echo ""
