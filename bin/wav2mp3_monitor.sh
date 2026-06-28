#!/bin/bash
set -euo pipefail

# ================================================================
# Configuration
# ================================================================
MONITOR_DIR="/var/spool/asterisk/monitor"
LAME_OPTS=(-b 64 -m m)   # 64kbps, mono (sufficient for telephony)
MIN_AGE_SECONDS=10        # skip files modified within the last N seconds

# ================================================================
# Functions
# ================================================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# ================================================================
# Prerequisites
# ================================================================
command -v lsof >/dev/null 2>&1 || { echo "ERROR: lsof not found"; exit 1; }
command -v lame >/dev/null 2>&1 || { echo "ERROR: lame not found"; exit 1; }

# ================================================================
# Main logic
# ================================================================
if [[ ! -d "$MONITOR_DIR" ]]; then
    log "ERROR: directory ${MONITOR_DIR} does not exist"
    exit 1
fi

# Counters
COUNT_OK=0
COUNT_FAIL=0
COUNT_SKIP=0

log "====== Starting WAV to MP3 conversion ======"

while IFS= read -r -d '' WAV_FILE; do

    MP3_FILE="${WAV_FILE%.wav}.mp3"

    # Skip recently modified files — may still be written to by Asterisk
    FILE_MTIME=$(stat -c %Y "$WAV_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [[ $(( NOW - FILE_MTIME )) -lt "$MIN_AGE_SECONDS" ]]; then
        log "SKIP (too recent): ${WAV_FILE}"
        COUNT_SKIP=$(( COUNT_SKIP + 1 ))
        continue
    fi

    # Skip if file is still open by any process
    if lsof "$WAV_FILE" > /dev/null 2>&1; then
        log "SKIP (in use): ${WAV_FILE}"
        COUNT_SKIP=$(( COUNT_SKIP + 1 ))
        continue
    fi

    # Convert
    if lame "${LAME_OPTS[@]}" "$WAV_FILE" "$MP3_FILE" > /dev/null 2>&1; then
        MP3_SIZE=$(stat -c%s "$MP3_FILE" 2>/dev/null || echo 0)
        if [[ "$MP3_SIZE" -gt 0 ]]; then
            log "OK: ${WAV_FILE} -> ${MP3_FILE}"
            rm -f "$WAV_FILE"
            COUNT_OK=$(( COUNT_OK + 1 ))
        else
            log "FAIL (empty output): ${WAV_FILE}"
            rm -f "$MP3_FILE"
            COUNT_FAIL=$(( COUNT_FAIL + 1 ))
        fi
    else
        log "FAIL: ${WAV_FILE}"
        rm -f "$MP3_FILE"
        COUNT_FAIL=$(( COUNT_FAIL + 1 ))
    fi

done < <(find "$MONITOR_DIR" -type f -iname "*.wav" -print0)

log "====== Done: OK=${COUNT_OK} | FAIL=${COUNT_FAIL} | SKIP=${COUNT_SKIP} ======"
