import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.environ.get("PEARLPBX_AGI_ENV", "/etc/PearlPBX/AGI/env")


def load_config(path):
    config = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip().strip('"').strip("'")
    except OSError as e:
        print(f"config load error: {e}", file=sys.stderr)
    return config


def read_agi_variables():
    variables = {}
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            break
        if ": " in line:
            key, _, value = line.partition(": ")
            variables[key] = value
    return variables


def send_verbose(message):
    try:
        sys.stdout.write(f'VERBOSE "{message}" 1\n')
        sys.stdout.flush()
        sys.stdin.readline()
    except Exception:
        pass


def post_to_slack(webhook_url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def notify_slack(config, webhook_key, title, fields, agi_vars):
    """Build and send a Slack notification from AGI context.

    config       — dict from load_config()
    webhook_key  — env var name for the webhook URL (e.g. 'SLACK_MISSED_CALL_WEBHOOK_URL')
    title        — bold first line of the message (e.g. '*Missed call*')
    fields       — list of (label, value) pairs rendered as '*Label:* `value`'
    agi_vars     — dict from read_agi_variables(), used to append UniqueID if present
    """
    webhook_url = config.get(webhook_key, "")
    if not webhook_url:
        raise ValueError(f"{webhook_key} not set in config")

    try:
        timeout = int(config.get("SLACK_TIMEOUT", "4"))
    except ValueError:
        timeout = 4
    username = config.get("SLACK_USERNAME", "PearlPBX2")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [title] + [f"*{label}:* `{value}`" for label, value in fields]
    lines.append(f"*Time:* {timestamp}")
    uniqueid = agi_vars.get("agi_uniqueid", "")
    if uniqueid:
        lines.append(f"*UniqueID:* `{uniqueid}`")

    text = "\n".join(lines)
    return post_to_slack(webhook_url, {"text": text, "username": username}, timeout)
