#!/bin/bash
set -euo pipefail

# ================================================================
# Configuration
# ================================================================
MONITOR_DIR="/var/spool/asterisk/monitor"
LOG_FILE="/var/log/wav2mp3_monitor.log"
LAME_OPTS="-b 64 -m m"   # 64kbps, mono (sufficient for telephony)

# ================================================================
# Functions
# ================================================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

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

    # Skip if file is in use by Asterisk (open by a process)
    if lsof "$WAV_FILE" > /dev/null 2>&1; then
        log "SKIP (in use): ${WAV_FILE}"
        COUNT_SKIP=$(( COUNT_SKIP + 1 ))
        continue
    fi

    # Convert
    if lame $LAME_OPTS "$WAV_FILE" "$MP3_FILE" > /dev/null 2>&1; then
        log "OK: ${WAV_FILE} → ${MP3_FILE}"
        rm -f "$WAV_FILE"
        COUNT_OK=$(( COUNT_OK + 1 ))
    else
        log "FAIL: ${WAV_FILE}"
        # Remove incomplete MP3 if it was created
        rm -f "$MP3_FILE"
        COUNT_FAIL=$(( COUNT_FAIL + 1 ))
    fi

done < <(find "$MONITOR_DIR" -type f -name "*.wav" -print0)

log "====== Done: OK=${COUNT_OK} | FAIL=${COUNT_FAIL} | SKIP=${COUNT_SKIP} ======"


