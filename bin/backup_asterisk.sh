#!/bin/bash
set -uo pipefail

ENV_FILE="/etc/PearlPBX/backup_asterisk/env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: config file not found: ${ENV_FILE}" >&2
    echo "Create it with BACKUP_DIR, retention settings, and optionally SLACK_WEBHOOK_URL" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

if [[ -z "${BACKUP_DIR:-}" ]]; then
    echo "ERROR: BACKUP_DIR is not set in ${ENV_FILE}" >&2
    exit 1
fi

SOURCE_DIR="${SOURCE_DIR:-/etc/asterisk}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/asterisk_etc_${DATE}.tar.gz"
HOSTNAME=$(hostname)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

slack_error() {
    [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && return 0
    curl -s --max-time 10 -X POST \
        -H 'Content-type: application/json' \
        --data "{
            \"username\": \"ServerBot\",
            \"icon_emoji\": \":robot_face:\",
            \"attachments\": [{
                \"color\": \"#ff0000\",
                \"title\": \":red_circle: backup_asterisk failed\",
                \"text\": \"$1\",
                \"footer\": \"${HOSTNAME} • $(date '+%Y-%m-%d %H:%M:%S')\"
            }]
        }" \
        "$SLACK_WEBHOOK_URL" > /dev/null || \
        echo "WARNING: failed to send Slack alert (webhook unavailable)" >&2
}

die() {
    log "ERROR: $*"
    slack_error "$* on \`${HOSTNAME}\`"
    exit 1
}

[[ -d "$SOURCE_DIR" ]] || die "Source directory not found: ${SOURCE_DIR}"
[[ -d "$BACKUP_DIR" ]] || die "Backup directory not found: ${BACKUP_DIR} (is the mount available?)"

log "====== backup_asterisk started ======"

log "Archiving ${SOURCE_DIR} → ${BACKUP_FILE}..."
if tar -czf "$BACKUP_FILE" -C "$(dirname "$SOURCE_DIR")" "$(basename "$SOURCE_DIR")"; then
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    log "Backup created successfully. Size: ${SIZE}"
else
    rm -f "$BACKUP_FILE"
    die "Failed to archive ${SOURCE_DIR} to ${BACKUP_FILE}"
fi

chmod 640 "$BACKUP_FILE"
chown root:root "$BACKUP_FILE"

log "Cleaning backups older than ${RETENTION_DAYS}d..."
find "$BACKUP_DIR" -maxdepth 1 -type f -name "asterisk_etc_*.tar.gz" -mtime +"$RETENTION_DAYS" -delete

log "====== backup_asterisk done ======"
