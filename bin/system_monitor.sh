#!/bin/bash
set -uo pipefail

ENV_FILE="/etc/PearlPBX/system_monitor/env"
STATE_DIR="/var/lib/pearlpbx2/monitor-state"
REPEAT_HOURS=4

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: config file not found: ${ENV_FILE}" >&2
    echo "Create it with:" >&2
    echo "  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/..." >&2
    echo "  SLACK_CHANNEL=#alerts-server" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "ERROR: SLACK_WEBHOOK_URL is not set in ${ENV_FILE}" >&2
    exit 1
fi

HOSTNAME=$(hostname)

SERVICES=(
    "asterisk"
    "postgresql"
    "redis-server"
    "PearlPBX2"
    "pearlpbx2-callback"
    "pearlpbx2-dashboard"
    "pearlpbx2-fastagi"
)

DISK_WARN_THRESHOLD=80
DISK_CRIT_THRESHOLD=90
CPU_WARN_THRESHOLD=2
CPU_CRIT_THRESHOLD=4
MEM_WARN_THRESHOLD=80
MEM_CRIT_THRESHOLD=90

IGNORE_FS="tmpfs|devtmpfs|udev|overlay|squashfs"

mkdir -p "$STATE_DIR"

should_send() {
    local check="$1" current="$2"
    local state_file="${STATE_DIR}/${check}.state"
    local last_state="ok" last_sent=0

    if [[ -f "$state_file" ]]; then
        { read -r last_state; read -r last_sent; } < "$state_file"
    fi

    local now repeat_sec
    now=$(date +%s)
    repeat_sec=$(( REPEAT_HOURS * 3600 ))

    if [[ "$current" != "$last_state" ]] || \
       [[ "$current" != "ok" && $(( now - last_sent )) -ge $repeat_sec ]]; then
        printf '%s\n%s\n' "$current" "$now" > "$state_file"
        return 0
    fi
    return 1
}

slack_send() {
    local color="$1" title="$2" message="$3" emoji="$4"
    curl -s --max-time 10 -X POST \
        -H 'Content-type: application/json' \
        --data "{
            \"username\": \"ServerBot\",
            \"icon_emoji\": \":robot_face:\",
            \"attachments\": [{
                \"color\": \"${color}\",
                \"title\": \"${emoji} ${title}\",
                \"text\": \"${message}\",
                \"footer\": \"${HOSTNAME} • $(date '+%Y-%m-%d %H:%M:%S')\"
            }]
        }" \
        "$SLACK_WEBHOOK_URL" > /dev/null || \
        echo "WARNING: failed to send Slack alert (webhook unavailable)" >&2
}

slack_warning()  { slack_send "#ffcc00" "$1" "$2" ":warning:"; }
slack_critical() { slack_send "#ff0000" "$1" "$2" ":red_circle:"; }
slack_ok()       { slack_send "#36a64f" "$1" "$2" ":white_check_mark:"; }

check_services() {
    local failed=()
    for svc in "${SERVICES[@]}"; do
        systemctl is-active --quiet "$svc" || failed+=("$svc")
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        local list
        list=$(printf '`%s`\n' "${failed[@]}")
        if should_send "services" "critical"; then
            slack_critical "Services are down" \
                "Failed on \`${HOSTNAME}\`:\n${list}\n\n\`journalctl -u <service> -n 30 --no-pager\`"
        fi
    else
        should_send "services" "ok" && \
            slack_ok "Services recovered" "All services are running on \`${HOSTNAME}\`"
    fi
}

check_disks() {
    local warnings=() criticals=()

    while read -r usage mount; do
        if [[ "$usage" -ge "$DISK_CRIT_THRESHOLD" ]]; then
            criticals+=("${mount} — *${usage}%*")
        elif [[ "$usage" -ge "$DISK_WARN_THRESHOLD" ]]; then
            warnings+=("${mount} — *${usage}%*")
        fi
    done < <(LC_ALL=C df -h | grep -vE "^Filesystem|${IGNORE_FS}" | awk '{gsub(/%/,"",$5); print $5, $6}')

    if [[ ${#criticals[@]} -gt 0 ]]; then
        local list; list=$(printf '%s\n' "${criticals[@]}")
        should_send "disks" "critical" && \
            slack_critical "Disk usage critical" \
                "On \`${HOSTNAME}\` (>=${DISK_CRIT_THRESHOLD}%):\n${list}\n\n\`du -sh /var/spool/asterisk/monitor/* 2>/dev/null | sort -rh | head -10\`"
    elif [[ ${#warnings[@]} -gt 0 ]]; then
        local list; list=$(printf '%s\n' "${warnings[@]}")
        should_send "disks" "warning" && \
            slack_warning "Disk usage warning" \
                "On \`${HOSTNAME}\` (>=${DISK_WARN_THRESHOLD}%):\n${list}"
    else
        should_send "disks" "ok" && \
            slack_ok "Disk usage normal" "All filesystems OK on \`${HOSTNAME}\`"
    fi
}

check_cpu() {
    local cores load1 load_int threshold_warn threshold_crit
    cores=$(nproc)
    load1=$(LC_ALL=C uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' ')
    load_int=$(echo "$load1" | awk '{printf "%d", $1 * 100}')
    threshold_warn=$(( cores * CPU_WARN_THRESHOLD * 100 ))
    threshold_crit=$(( cores * CPU_CRIT_THRESHOLD * 100 ))

    if [[ "$load_int" -ge "$threshold_crit" ]]; then
        should_send "cpu" "critical" && \
            slack_critical "CPU load critical" \
                "Load average on \`${HOSTNAME}\`: *${load1}* (${cores} cores, threshold: ${CPU_CRIT_THRESHOLD}x)\n\`top -bn1 | head -20\`"
    elif [[ "$load_int" -ge "$threshold_warn" ]]; then
        should_send "cpu" "warning" && \
            slack_warning "CPU load warning" \
                "Load average on \`${HOSTNAME}\`: *${load1}* (${cores} cores, threshold: ${CPU_WARN_THRESHOLD}x)"
    else
        should_send "cpu" "ok" && \
            slack_ok "CPU load normal" "Load average on \`${HOSTNAME}\`: *${load1}*"
    fi
}

check_memory() {
    local total used pct
    read -r total used < <(LC_ALL=C free -m | awk '/^Mem:/ {print $2, $3}')
    pct=$(( used * 100 / total ))

    if [[ "$pct" -ge "$MEM_CRIT_THRESHOLD" ]]; then
        should_send "memory" "critical" && \
            slack_critical "Memory usage critical" \
                "On \`${HOSTNAME}\`: *${pct}%* used (${used}MB / ${total}MB)\n\`ps aux --sort=-%mem | head -10\`"
    elif [[ "$pct" -ge "$MEM_WARN_THRESHOLD" ]]; then
        should_send "memory" "warning" && \
            slack_warning "Memory usage warning" \
                "On \`${HOSTNAME}\`: *${pct}%* used (${used}MB / ${total}MB)"
    else
        should_send "memory" "ok" && \
            slack_ok "Memory usage normal" "On \`${HOSTNAME}\`: *${pct}%* used (${used}MB / ${total}MB)"
    fi
}

check_startup_test() {
    local state_file="${STATE_DIR}/startup_test.state"
    [[ -f "$state_file" ]] && return 0

    echo "First run detected, sending test alert to Slack..."
    if curl -s --max-time 10 -X POST \
        -H 'Content-type: application/json' \
        --data "{
            \"username\": \"ServerBot\",
            \"icon_emoji\": \":robot_face:\",
            \"attachments\": [{
                \"color\": \"#36a64f\",
                \"title\": \":white_check_mark: system_monitor started\",
                \"text\": \"Monitoring is active on \`${HOSTNAME}\`\",
                \"footer\": \"${HOSTNAME} • $(date '+%Y-%m-%d %H:%M:%S')\"
            }]
        }" \
        "$SLACK_WEBHOOK_URL" > /dev/null; then
        echo "ok" > "$state_file"
        echo "Test alert sent successfully."
    else
        echo "ERROR: failed to send test alert to Slack. Will retry on next run." >&2
    fi
}

check_startup_test
check_services
check_disks
check_cpu
check_memory
