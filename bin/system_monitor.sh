#!/bin/bash
set -euo pipefail

# ================================================================
# Configuration
# ================================================================
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../xxx"
SLACK_CHANNEL="#alerts-server"
HOSTNAME=$(hostname)

SERVICES=("asterisk" "postgresql" "gunicorn")

WARN_THRESHOLD=80
CRIT_THRESHOLD=90

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
# Main
# ================================================================
check_services
check_disks

