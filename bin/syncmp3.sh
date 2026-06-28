#!/bin/bash
set -uo pipefail

ENV_FILE="/etc/PearlPBX/syncmp3/env"

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

MONITOR_DIR="${MONITOR_DIR:-/var/spool/asterisk/monitor}"
LOCAL_MP3_DAYS="${LOCAL_MP3_DAYS:-5}"
LOCAL_WAV_DAYS="${LOCAL_WAV_DAYS:-1}"
BACKUP_MP3_DAYS="${BACKUP_MP3_DAYS:-30}"
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
                \"title\": \":red_circle: syncmp3 failed\",
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

[[ -d "$MONITOR_DIR" ]] || die "Source directory not found: ${MONITOR_DIR}"
[[ -d "$BACKUP_DIR"  ]] || die "Backup directory not found: ${BACKUP_DIR} (is the mount available?)"

log "====== syncmp3 started ======"

log "Syncing *.mp3 from ${MONITOR_DIR} → ${BACKUP_DIR}..."
rsync -a --include="*/" --include="*.mp3" --exclude="*" \
    "${MONITOR_DIR}/" "${BACKUP_DIR}/" || \
    die "rsync from ${MONITOR_DIR} to ${BACKUP_DIR} failed"

log "Cleaning local files older than ${LOCAL_MP3_DAYS}d (mp3) / ${LOCAL_WAV_DAYS}d (wav)..."
find "$MONITOR_DIR" -type f -name "*.mp3" -mtime +"$LOCAL_MP3_DAYS" -delete
find "$MONITOR_DIR" -type f -name "*.wav" -mtime +"$LOCAL_WAV_DAYS" -delete

log "Cleaning backup files older than ${BACKUP_MP3_DAYS}d..."
find "$BACKUP_DIR" -type f -name "*.mp3" -mtime +"$BACKUP_MP3_DAYS" -delete

log "====== syncmp3 done ======"
