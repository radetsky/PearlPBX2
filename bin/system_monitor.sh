#!/bin/bash
set -euo pipefail

# ================================================================
# Configuration
# ================================================================
ENV_FILE="/etc/PearlPBX/monitor/env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: config file not found: ${ENV_FILE}" >&2
    echo "" >&2
    echo "Create it with the following content:" >&2
    echo "" >&2
    echo "  mkdir -p $(dirname "$ENV_FILE")" >&2
    echo "  cat > ${ENV_FILE} <<EOF" >&2
    echo "  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx" >&2
    echo "  SLACK_CHANNEL=#alerts-server" >&2
    echo "  EOF" >&2
    echo "  chmod 600 ${ENV_FILE}" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "ERROR: SLACK_WEBHOOK_URL is not set in ${ENV_FILE}" >&2
    exit 1
fi

SLACK_CHANNEL="${SLACK_CHANNEL:-#alerts-server}"
HOSTNAME=$(hostname)

SERVICES=(
    "asterisk" "postgresql" "gunicorn" "redis"
    "callback" "dashboard" "express" "fastagi"
)

WARN_THRESHOLD=80
CRIT_THRESHOLD=90

CPU_WARN_THRESHOLD=2      # load average warn: N x CPU cores
CPU_CRIT_THRESHOLD=4      # load average crit: N x CPU cores
MEM_WARN_THRESHOLD=80     # memory used %
MEM_CRIT_THRESHOLD=90     # memory used %

# Filesystems to ignore
IGNORE_FS="tmpfs|devtmpfs|udev|overlay|squashfs"

# ================================================================
# Slack
# ================================================================
slack_send() {
    local color="$1"
    local title="$2"
    local message="$3"
    local emoji="$4"

    curl -s -X POST \
        -H 'Content-type: application/json' \
        --data "{
            \"channel\": \"${SLACK_CHANNEL}\",
            \"username\": \"ServerBot\",
            \"icon_emoji\": \":robot_face:\",
            \"attachments\": [{
                \"color\": \"${color}\",
                \"title\": \"${emoji} ${title}\",
                \"text\": \"${message}\",
                \"footer\": \"${HOSTNAME} • $(date '+%Y-%m-%d %H:%M:%S')\"
            }]
        }" \
        "$SLACK_WEBHOOK_URL" > /dev/null
}

slack_warning()  { slack_send "#ffcc00" "$1" "$2" ":warning:"; }
slack_critical() { slack_send "#ff0000" "$1" "$2" ":red_circle:"; }
slack_ok()       { slack_send "#36a64f" "$1" "$2" ":white_check_mark:"; }

# ================================================================
# Service status
# ================================================================
check_services() {
    local failed=()

    for SERVICE in "${SERVICES[@]}"; do
        if ! systemctl is-active --quiet "$SERVICE"; then
            failed+=("$SERVICE")
        fi
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        local list
        list=$(printf '`%s`\n' "${failed[@]}")
        slack_critical \
            "Services are down" \
            "Failed services on \`${HOSTNAME}\`:\n${list}\n\nDiagnostics:\n\`journalctl -u <service> -n 30 --no-pager\`"
    fi
}

# ================================================================
# Filesystems
# ================================================================
check_disks() {
    local warnings=()
    local criticals=()

    while IFS= read -r line; do
        local usage mount
        usage=$(echo "$line" | awk '{print $5}' | tr -d '%')
        mount=$(echo "$line" | awk '{print $6}')

        if [[ "$usage" -ge "$CRIT_THRESHOLD" ]]; then
            criticals+=("${mount} — *${usage}%*")
        elif [[ "$usage" -ge "$WARN_THRESHOLD" ]]; then
            warnings+=("${mount} — *${usage}%*")
        fi
    done < <(LC_ALL=C df -h | grep -vE "^Filesystem|${IGNORE_FS}")

    if [[ ${#criticals[@]} -gt 0 ]]; then
        local list
        list=$(printf '%s\n' "${criticals[@]}")
        slack_critical \
            "Disk usage critical" \
            "Critical disk usage on \`${HOSTNAME}\` (>=${CRIT_THRESHOLD}%):\n${list}\n\n\`du -sh /var/spool/asterisk/monitor/* 2>/dev/null | sort -rh | head -10\`"
    fi

    if [[ ${#warnings[@]} -gt 0 ]]; then
        local list
        list=$(printf '%s\n' "${warnings[@]}")
        slack_warning \
            "Disk usage warning" \
            "High disk usage on \`${HOSTNAME}\` (>=${WARN_THRESHOLD}%):\n${list}"
    fi
}

# ================================================================
# CPU load
# ================================================================
check_cpu() {
    local cores load1 load_int threshold_warn threshold_crit
    cores=$(nproc)
    load1=$(LC_ALL=C uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' ')
    # Convert float to integer * 100 for comparison (e.g. 1.75 -> 175)
    load_int=$(echo "$load1" | awk '{printf "%d", $1 * 100}')
    threshold_warn=$(( cores * CPU_WARN_THRESHOLD * 100 ))
    threshold_crit=$(( cores * CPU_CRIT_THRESHOLD * 100 ))

    if [[ "$load_int" -ge "$threshold_crit" ]]; then
        slack_critical \
            "CPU load critical" \
            "Load average on \`${HOSTNAME}\`: *${load1}* (${cores} cores, threshold: ${CPU_CRIT_THRESHOLD}x)\n\`top -bn1 | head -20\`"
    elif [[ "$load_int" -ge "$threshold_warn" ]]; then
        slack_warning \
            "CPU load warning" \
            "Load average on \`${HOSTNAME}\`: *${load1}* (${cores} cores, threshold: ${CPU_WARN_THRESHOLD}x)"
    fi
}

# ================================================================
# Memory
# ================================================================
check_memory() {
    local total used pct
    total=$(LC_ALL=C free -m | awk '/^Mem:/ {print $2}')
    used=$(LC_ALL=C free -m  | awk '/^Mem:/ {print $3}')
    pct=$(( used * 100 / total ))

    if [[ "$pct" -ge "$MEM_CRIT_THRESHOLD" ]]; then
        slack_critical \
            "Memory usage critical" \
            "Memory on \`${HOSTNAME}\`: *${pct}%* used (${used}MB / ${total}MB)\n\`ps aux --sort=-%mem | head -10\`"
    elif [[ "$pct" -ge "$MEM_WARN_THRESHOLD" ]]; then
        slack_warning \
            "Memory usage warning" \
            "Memory on \`${HOSTNAME}\`: *${pct}%* used (${used}MB / ${total}MB)"
    fi
}

# ================================================================
# Main
# ================================================================
check_services
check_disks
check_cpu
check_memory

