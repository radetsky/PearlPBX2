#!/usr/bin/env python3
"""Resolve which deployed commit and migration state a rollback should target.

Reads the deploy-state ledger written by ansible/update.yml
(a JSON object with a "history" list of {timestamp, previous_commit,
new_commit, migrations_before} entries, oldest first) and prints a single
JSON object describing the rollback target for the requested number of
steps. Used by both rollback.sh (preview) and ansible/rollback.yml
(execution) so the two never disagree on which commit is "N steps back".
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
        print(f"ERROR: no deploy-state ledger at {args.state_file}", file=sys.stderr)
        sys.exit(1)

    history = state.get("history", [])
    if not history:
        print("ERROR: deploy-state ledger has no history entries", file=sys.stderr)
        sys.exit(1)

    if args.steps > len(history):
        print(
            f"ERROR: only {len(history)} step(s) of history available, "
            f"cannot roll back {args.steps} step(s)",
            file=sys.stderr,
        )
        sys.exit(1)

    target_index = len(history) - args.steps
    target_entry = history[target_index]
    target_commit = target_entry["previous_commit"]

    if not target_commit:
        print(
            "ERROR: this is the oldest recorded deployment — cannot roll back further",
            file=sys.stderr,
        )
        sys.exit(1)

    result = {
        "current_commit": history[-1]["new_commit"],
        "target_commit": target_commit,
        "target_migrations": target_entry["migrations_before"],
        "remaining_history": history[:target_index],
        "available_steps": len(history),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
