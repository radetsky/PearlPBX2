#!/bin/bash
set -euo pipefail

ENV_FILE="/etc/PearlPBX/pg_backup/env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: config file not found: ${ENV_FILE}" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-pearlpbx2}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgresql/pearlpbx2}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${DATE}.sql.gz"
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
                \"title\": \":red_circle: pg_backup failed\",
                \"text\": \"$1\",
                \"footer\": \"${HOSTNAME} • $(date '+%Y-%m-%d %H:%M:%S')\"
            }]
        }" \
        "$SLACK_WEBHOOK_URL" > /dev/null || \
        echo "WARNING: failed to send Slack alert (webhook unavailable)" >&2
}

cleanup_old_backups() {
    log "Deleting backups older than ${RETENTION_DAYS} days..."
    find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    log "Cleanup complete."
}

mkdir -p "$BACKUP_DIR"

log "====== Backup started ======"
log "File: ${BACKUP_FILE}"

if sudo -u "$DB_USER" pg_dump -d "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    log "Backup created successfully. Size: ${SIZE}"
else
    log "ERROR: backup failed!"
    rm -f "$BACKUP_FILE"
    slack_error "Failed to create ${DB_NAME} DB backup on \`${HOSTNAME}\`"
    exit 1
fi

# Set permissions
chmod 640 "$BACKUP_FILE"
chown root:root "$BACKUP_FILE"

# Rotate old backups
cleanup_old_backups

log "====== Backup complete ======"
