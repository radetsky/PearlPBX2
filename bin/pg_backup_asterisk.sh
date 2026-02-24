#!/bin/bash
set -euo pipefail

# ================================================================
# Configuration
# ================================================================
DB_USER="asterisk"
BACKUP_DIR="/var/backups/postgresql/asterisk"
LOG_FILE="/var/log/pg_backup_asterisk.log"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/asterisk_${DATE}.sql.gz"

# Rotation: how many days to keep backups
RETENTION_DAYS=30

# Email notification (leave empty to disable)
NOTIFY_EMAIL=""

# ================================================================
# Functions
# ================================================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}
notify() {
    local status="$1"
    local message="$2"
    if [[ -n "$NOTIFY_EMAIL" ]]; then
        echo "$message" | mail -s "[BACKUP] Asterisk DB — ${status}" "$NOTIFY_EMAIL"
    fi
}

cleanup_old_backups() {
    log "Deleting backups older than ${RETENTION_DAYS} days..."
    find "$BACKUP_DIR" -name "asterisk_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
    log "Cleanup complete."
}

# ================================================================
# Main logic
# ================================================================
mkdir -p "$BACKUP_DIR"

log "====== Backup started ======"
log "File: ${BACKUP_FILE}"

# Dump database and compress
if sudo -u "$DB_USER" pg_dump -d asterisk | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    log "Backup created successfully. Size: ${SIZE}"
    notify "SUCCESS" "Asterisk DB backup created successfully: ${BACKUP_FILE} (${SIZE})"
else
    log "ERROR: backup failed!"
    rm -f "$BACKUP_FILE"
    notify "FAILED" "Failed to create Asterisk DB backup on $(hostname)"
    exit 1
fi

# Set permissions
chmod 640 "$BACKUP_FILE"
chown root:root "$BACKUP_FILE"

# Rotate old backups
cleanup_old_backups

log "====== Backup complete ======"


