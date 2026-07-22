#!/bin/bash
# Safely rename the hand-written PearlPBX2 systemd units to the naming
# convention expected by ansible/roles/services (pearlpbx2-dashboard,
# pearlpbx2-callback, pearlpbx2-fastagi), without touching EnvironmentFile=
# paths or secrets — those were already verified to match on 10.0.0.1.
#
# Usage:
#   sudo ./rename_pearlpbx2_services.sh [--dry-run] <dashboard|callback|fastagi|all>
#   sudo ./rename_pearlpbx2_services.sh --cleanup   <dashboard|callback|fastagi|all>
#
# Step 1 (default action) renames one service (or all three): stops and
# disables the old unit, installs a new unit file with the same content
# under the new name, enables and starts it, and verifies it stays active.
# On any failure it rolls back to the old unit automatically. The old unit
# file is intentionally left in place (disabled) after a successful rename.
#
# Step 2 (--cleanup) is a separate, explicit action: it only removes the old
# unit file, and only after confirming the new unit is currently active.
# Run it once you are satisfied the renamed service is stable.
set -uo pipefail

DRY_RUN=0
CLEANUP=0
UNIT_DIR="/etc/systemd/system"
VERIFY_ATTEMPTS=3
VERIFY_INTERVAL=2

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

usage() {
    echo "Usage: $0 [--dry-run] <dashboard|callback|fastagi|all>" >&2
    echo "       $0 --cleanup <dashboard|callback|fastagi|all>" >&2
    exit 1
}

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "ERROR: this script must be run as root (it calls systemctl)." >&2
        exit 1
    fi
}

# Map a short service key to "OLD_UNIT NEW_UNIT".
resolve() {
    case "$1" in
        dashboard) echo "Dashboard pearlpbx2-dashboard" ;;
        callback)  echo "Callback pearlpbx2-callback" ;;
        fastagi)   echo "FastAGI pearlpbx2-fastagi" ;;
        *)
            echo "ERROR: unknown service key '$1' (expected dashboard, callback, fastagi, or all)" >&2
            exit 1
            ;;
    esac
}

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: $*"
    else
        "$@"
    fi
}

is_active() {
    systemctl is-active --quiet "$1"
}

# Poll a unit's active state a few times before trusting it — a service can
# crash-loop and briefly report "active" right after start.
wait_stable() {
    local unit="$1"
    local i
    for ((i = 1; i <= VERIFY_ATTEMPTS; i++)); do
        sleep "$VERIFY_INTERVAL"
        if ! is_active "$unit"; then
            return 1
        fi
    done
    return 0
}

rollback() {
    local old="$1" new="$2"
    log "ROLLBACK: reverting to ${old}.service"
    run systemctl stop "${new}.service" 2>/dev/null || true
    run systemctl disable "${new}.service" 2>/dev/null || true
    run rm -f "${UNIT_DIR}/${new}.service"
    run systemctl daemon-reload
    run systemctl enable "${old}.service"
    run systemctl start "${old}.service"
    if is_active "${old}.service"; then
        log "ROLLBACK: ${old}.service is active again."
    else
        log "ROLLBACK FAILED: ${old}.service did not come back up. Investigate manually." >&2
    fi
}

rename_one() {
    local key="$1"
    local pair old new
    pair=$(resolve "$key")
    old=$(awk '{print $1}' <<<"$pair")
    new=$(awk '{print $2}' <<<"$pair")

    log "=== Renaming ${old}.service -> ${new}.service ==="

    if [[ ! -f "${UNIT_DIR}/${old}.service" ]]; then
        echo "ERROR: ${UNIT_DIR}/${old}.service not found — nothing to rename." >&2
        return 1
    fi

    if systemctl is-enabled --quiet "${new}.service" 2>/dev/null && is_active "${new}.service"; then
        log "SKIP: ${new}.service already exists and is active — assuming already renamed."
        return 0
    fi

    log "Stopping and disabling ${old}.service ..."
    run systemctl stop "${old}.service"
    run systemctl disable "${old}.service"

    log "Installing ${new}.service (same content, new unit name) ..."
    run install -m 644 "${UNIT_DIR}/${old}.service" "${UNIT_DIR}/${new}.service"

    run systemctl daemon-reload
    run systemctl enable "${new}.service"
    run systemctl start "${new}.service"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: would verify ${new}.service stays active, and roll back on failure."
        return 0
    fi

    log "Verifying ${new}.service stays active (${VERIFY_ATTEMPTS} x ${VERIFY_INTERVAL}s) ..."
    if wait_stable "${new}.service"; then
        log "OK: ${new}.service is active and stable."
        log "Old unit file ${UNIT_DIR}/${old}.service is still present but disabled."
        log "Once you're satisfied, run: $0 --cleanup ${key}"
        return 0
    else
        echo "ERROR: ${new}.service failed to stay active." >&2
        systemctl status "${new}.service" --no-pager || true
        rollback "$old" "$new"
        return 1
    fi
}

cleanup_one() {
    local key="$1"
    local pair old new
    pair=$(resolve "$key")
    old=$(awk '{print $1}' <<<"$pair")
    new=$(awk '{print $2}' <<<"$pair")

    log "=== Cleaning up old unit for ${key} (${old}.service) ==="

    if [[ ! -f "${UNIT_DIR}/${old}.service" ]]; then
        log "SKIP: ${UNIT_DIR}/${old}.service already gone."
        return 0
    fi

    if ! is_active "${new}.service"; then
        echo "ERROR: ${new}.service is not active — refusing to remove ${old}.service." >&2
        echo "       Fix ${new}.service first, or roll back before cleaning up." >&2
        return 1
    fi

    log "Removing ${UNIT_DIR}/${old}.service ..."
    run rm -f "${UNIT_DIR}/${old}.service"
    run systemctl daemon-reload
    log "OK: ${old}.service unit file removed."
}

main() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=1 ;;
            --cleanup) CLEANUP=1 ;;
            -h|--help) usage ;;
            *) args+=("$1") ;;
        esac
        shift
    done

    [[ "${#args[@]}" -eq 1 ]] || usage
    local target="${args[0]}"

    require_root

    local keys=()
    if [[ "$target" == "all" ]]; then
        keys=(dashboard callback fastagi)
    else
        keys=("$target")
    fi

    local failures=0
    for key in "${keys[@]}"; do
        if [[ "$CLEANUP" -eq 1 ]]; then
            cleanup_one "$key" || failures=$((failures + 1))
        else
            rename_one "$key" || failures=$((failures + 1))
        fi
    done

    if [[ "$failures" -gt 0 ]]; then
        echo "Completed with ${failures} failure(s) — see log above." >&2
        exit 1
    fi
    log "Done."
}

main "$@"
