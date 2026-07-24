#!/bin/bash
set -euo pipefail

if [ "$(id -un)" != "root" ]; then
    exec sudo "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/var/log/pearlpbx2-rollback.log"
STATE_FILE="/var/backups/pearlpbx2/deploy_state/state.json"
RESOLVE_SCRIPT="$SCRIPT_DIR/bin/pearlpbx2_resolve_rollback_target.py"

usage() {
    echo "Usage: $0 [-n STEPS] [-y] [-l]"
    echo ""
    echo "  -n, --steps STEPS   how many deployments to roll back (default: 1)"
    echo "  -y, --yes           skip the confirmation prompt"
    echo "  -l, --list          show deploy history and exit, no rollback"
}

STEPS=1
ASSUME_YES=0
LIST_ONLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--steps)
            STEPS="${2:?missing value for $1}"
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

if [ ! -f "$STATE_FILE" ]; then
    echo "ERROR: no deploy-state ledger found at $STATE_FILE" >&2
    echo "Nothing has been recorded to roll back to yet." >&2
    exit 1
fi

if [ "$LIST_ONLY" -eq 1 ]; then
    python3 -c "
import json

with open('$STATE_FILE') as f:
    history = json.load(f).get('history', [])

print(f'{\"steps back\":<12}{\"timestamp\":<22}{\"commit\":<10}came from')
for i, entry in enumerate(reversed(history), start=1):
    prev = entry['previous_commit'][:8] or '(none)'
    print(f'{i:<12}{entry[\"timestamp\"]:<22}{entry[\"new_commit\"][:8]:<10}{prev}')
"
    exit 0
fi

RESOLVED="$(python3 "$RESOLVE_SCRIPT" "$STATE_FILE" --steps "$STEPS")" || exit 1
CURRENT_COMMIT="$(echo "$RESOLVED" | python3 -c "import json,sys; print(json.load(sys.stdin)['current_commit'])")"
TARGET_COMMIT="$(echo "$RESOLVED" | python3 -c "import json,sys; print(json.load(sys.stdin)['target_commit'])")"

echo ""
echo "======================================================"
echo " PearlPBX2 Rollback"
echo "======================================================"
echo ""
echo " Currently deployed commit      : $CURRENT_COMMIT"
echo " Rolling back $STEPS step(s) to commit : $TARGET_COMMIT"
echo ""
echo " This will:"
echo "   - revert Django migrations to the state recorded for that commit"
echo "   - git checkout that commit and re-sync the code"
echo "   - reinstall Python dependencies for that version"
echo "   - restart PearlPBX2 and auxiliary services"
echo ""
echo " Full log: $LOG_FILE"
echo " Run '$0 --list' to see the full deploy history."
echo "======================================================"
echo ""

if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "Type 'yes' to proceed: " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
fi

cd "$SCRIPT_DIR/ansible"

ansible-playbook -i inventory/localhost.yml rollback.yml -e "steps=$STEPS" 2>&1 | tee "$LOG_FILE"

# tee exits 0 even if ansible failed — check the exit code
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    echo ""
    echo "Rollback FAILED. See $LOG_FILE for details." >&2
    exit 1
fi

echo ""
echo "======================================================"
echo " Rollback complete — now running commit $TARGET_COMMIT"
echo "======================================================"
echo ""
