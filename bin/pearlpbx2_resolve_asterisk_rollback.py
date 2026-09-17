#!/usr/bin/env python3
"""Resolve which pre-upgrade backup an Asterisk rollback should restore.

Reads the asterisk-upgrade ledger written by ansible/roles/asterisk_update
(a JSON object with a "history" list of {timestamp, from_version, to_version,
backup_dir} entries, oldest first) and prints a single JSON object
describing the rollback target for the requested number of steps. Used by
both update-asterisk.sh (preview) and ansible/rollback-asterisk.yml
(execution) so the two never disagree on which upgrade is "N steps back".
"""
import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("state_file")
    parser.add_argument("--steps", type=int, default=1)
    args = parser.parse_args()

    if args.steps < 1:
        print("ERROR: --steps must be >= 1", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.state_file) as f:
            state = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: no asterisk-upgrade ledger at {args.state_file}", file=sys.stderr)
        sys.exit(1)

    history = state.get("history", [])
    if not history:
        print("ERROR: asterisk-upgrade ledger has no history entries", file=sys.stderr)
        sys.exit(1)

    if args.steps > len(history):
        print(
            f"ERROR: only {len(history)} upgrade(s) of history available, "
            f"cannot roll back {args.steps} step(s)",
            file=sys.stderr,
        )
        sys.exit(1)

    target_index = len(history) - args.steps
    target_entry = history[target_index]

    result = {
        "current_version": history[-1]["to_version"],
        "target_version": target_entry["from_version"],
        "backup_dir": target_entry["backup_dir"],
        "upgraded_at": target_entry["timestamp"],
        "remaining_history": history[:target_index],
        "available_steps": len(history),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
