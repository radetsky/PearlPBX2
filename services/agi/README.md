# Classic AGI Scripts

Classic AGI scripts for PearlPBX2. Unlike the FastAGI service (`services/fastagi/`), these are
**not** long-running daemons — Asterisk launches each script as a child process per call and
communicates via stdin/stdout. No network port, no virtualenv, no systemd unit required.

All scripts read configuration from `/etc/PearlPBX/AGI/env`. Use `PEARLPBX_AGI_ENV` env variable
to override the config path (useful for local testing).

## Scripts

### `unmatched_call.py` — unmatched inbound DID

Sends a Slack message when a call hits a catch-all extension with no routing match.
Uses `SLACK_WEBHOOK_URL`.

Dialplan usage:
```
NoOp(UNMATCHED src=${CALLERID(num)} dst=${EXTEN} chan=${CHANNEL});
AGI(unmatched_call.py,${CALLERID(num)},${EXTEN},${CHANNEL});
Hangup();
```

### `missed_call.py` — missed call

Sends a Slack message when a call was not answered.
Uses `SLACK_MISSED_CALL_WEBHOOK_URL`.

Dialplan usage (typically in `h` extension after `Dial()`):
```
h => {
    GotoIf($["${DIALSTATUS}" != "NOANSWER"]?end);
    AGI(missed_call.py,${CALLERID(num)},${EXTEN},${CHANNEL});
    end: NoOp();
}
```

## Configuration

File: `/etc/PearlPBX/AGI/env`

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_MISSED_CALL_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_TIMEOUT=4
SLACK_USERNAME=PearlPBX2
```

| Variable                           | Used by            | Description                          |
|------------------------------------|--------------------|--------------------------------------|
| `SLACK_UNMATCHED_CALL_WEBHOOK_URL` | unmatched_call.py  | Slack Incoming Webhook URL           |
| `SLACK_MISSED_CALL_WEBHOOK_URL`    | missed_call.py     | Slack Incoming Webhook URL           |
| `SLACK_TIMEOUT`                    | both               | HTTP POST timeout in seconds (def 4) |
| `SLACK_USERNAME`                   | both               | Bot display name in Slack            |

To create a webhook: https://api.slack.com/apps → New App → Incoming Webhooks

## Manual deployment (without Ansible)

```bash
cp unmatched_call.py missed_call.py /var/lib/asterisk/agi-bin/
chmod 755 /var/lib/asterisk/agi-bin/unmatched_call.py /var/lib/asterisk/agi-bin/missed_call.py
chown asterisk:asterisk /var/lib/asterisk/agi-bin/unmatched_call.py /var/lib/asterisk/agi-bin/missed_call.py

mkdir -p /etc/PearlPBX/AGI
cp env.sample /etc/PearlPBX/AGI/env
chmod 640 /etc/PearlPBX/AGI/env
chown root:asterisk /etc/PearlPBX/AGI/env

vim /etc/PearlPBX/AGI/env
```

## Testing locally

```bash
PEARLPBX_AGI_ENV=./env.sample python3 unmatched_call.py <<'EOF'
agi_uniqueid: 1718000000.42
agi_arg_1: 380671234567
agi_arg_2: 380441234567
agi_arg_3: PJSIP/trunk-in-00000042

EOF
```

## Error handling

All scripts always exit with code `0` — a Slack error never interrupts the call.
Errors are printed to stderr (visible in `asterisk -rvvv` and `/var/log/asterisk/messages`).
