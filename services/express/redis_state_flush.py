#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis State Flush Tool
Emergency tool to inspect and clear PearlPBX2 Redis state.

Usage:
  python redis_state_flush.py               # show current key counts
  python redis_state_flush.py --ulines      # delete express:uline:* and express:uid:*
  python redis_state_flush.py --channels    # delete asterisk:channel:*, asterisk:uid:*
  python redis_state_flush.py --queues      # delete asterisk:queue:*
  python redis_state_flush.py --all         # delete everything above
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from pathlib import Path

for candidate in (Path(__file__).parent / ".env", Path(__file__).parent / "env"):
    if candidate.exists():
        load_dotenv(candidate)
        break

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def get_client():
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        print(f"Cannot connect to Redis ({REDIS_URL}): {e}")
        sys.exit(1)


def count_keys(client, pattern: str) -> int:
    return sum(1 for _ in client.scan_iter(pattern))


def delete_pattern(client, pattern: str) -> int:
    keys = list(client.scan_iter(pattern))
    if keys:
        client.delete(*keys)
    return len(keys)


def show_status(client):
    patterns = {
        "ULINE slots   (express:uline:*)": "express:uline:*",
        "ULINE uid map (express:uid:*)":   "express:uid:*",
        "Channels      (asterisk:channel:*)": "asterisk:channel:*",
        "Channel uid   (asterisk:uid:*)":  "asterisk:uid:*",
        "Queues        (asterisk:queue:*)": "asterisk:queue:*",
        "Channels all  (asterisk:channels:all)": "asterisk:channels:all",
    }
    print(f"\nRedis: {REDIS_URL}\n")
    print(f"{'Key pattern':<45} {'Count':>6}")
    print("-" * 53)
    for label, pattern in patterns.items():
        n = count_keys(client, pattern)
        print(f"{label:<45} {n:>6}")
    print()


def flush(client, ulines=False, channels=False, queues=False):
    if not any([ulines, channels, queues]):
        return

    print(f"\nRedis: {REDIS_URL}\n")

    if ulines:
        n1 = delete_pattern(client, "express:uline:*")
        n2 = delete_pattern(client, "express:uid:*")
        print(f"Deleted {n1} express:uline:* keys")
        print(f"Deleted {n2} express:uid:* keys")

    if channels:
        n1 = delete_pattern(client, "asterisk:channel:*")
        n2 = delete_pattern(client, "asterisk:uid:*")
        n3 = delete_pattern(client, "asterisk:channels:all")
        print(f"Deleted {n1} asterisk:channel:* keys")
        print(f"Deleted {n2} asterisk:uid:* keys")
        print(f"Deleted {n3} asterisk:channels:all keys")

    if queues:
        n = delete_pattern(client, "asterisk:queue:*")
        print(f"Deleted {n} asterisk:queue:* keys")

    print()


def main():
    parser = argparse.ArgumentParser(description="Redis State Flush Tool")
    parser.add_argument("--ulines",   action="store_true", help="Flush ULINE state (express:*)")
    parser.add_argument("--channels", action="store_true", help="Flush channel state (asterisk:channel:*, asterisk:uid:*)")
    parser.add_argument("--queues",   action="store_true", help="Flush queue state (asterisk:queue:*)")
    parser.add_argument("--all",      action="store_true", help="Flush everything")
    args = parser.parse_args()

    client = get_client()

    if args.all:
        args.ulines = args.channels = args.queues = True

    if not any([args.ulines, args.channels, args.queues]):
        show_status(client)
        return

    print("The following will be DELETED:")
    if args.ulines:   print("  - express:uline:*  express:uid:*")
    if args.channels: print("  - asterisk:channel:*  asterisk:uid:*  asterisk:channels:all")
    if args.queues:   print("  - asterisk:queue:*")

    answer = input("\nContinue? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    flush(client, ulines=args.ulines, channels=args.channels, queues=args.queues)
    show_status(client)


if __name__ == "__main__":
    main()
