#!/usr/bin/env python3
import sys

from agi_common import CONFIG_PATH, load_config, notify_slack, read_agi_variables, send_verbose


def main():
    config = load_config(CONFIG_PATH)
    agi_vars = read_agi_variables()

    src = agi_vars.get("agi_arg_1", "unknown")
    dst = agi_vars.get("agi_arg_2", "unknown")
    channel = agi_vars.get("agi_arg_3", "unknown")

    try:
        notify_slack(
            config,
            "SLACK_UNMATCHED_CALL_WEBHOOK_URL",
            "*Unmatched inbound call*",
            [("From", src), ("To (DID)", dst), ("Channel", channel)],
            agi_vars,
        )
        verbose_msg = f"PearlPBX2 slack: sent src={src} dst={dst}"
    except Exception as e:
        print(f"PearlPBX2 slack error: {e}", file=sys.stderr)
        verbose_msg = "PearlPBX2 slack: error, check asterisk log"

    send_verbose(verbose_msg)


if __name__ == "__main__":
    main()
    sys.exit(0)
