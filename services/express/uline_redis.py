#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ULine Redis Manager
Shared ULINE state storage for express_fastagi.py and express_agi.py.

Redis keys:
  express:uline:{N}     - Hash: uniqueid, channel, cdr_start, allocated_at, caller_id, provider
  express:uid:{uniqueid} - String: ULINE number N
Both keys have TTL = ULINE_TTL seconds (default 3600).
"""

import os
import logging
from datetime import datetime
from typing import Optional

import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ULINE_MIN = int(os.getenv("ULINE_MIN", 1))
ULINE_MAX = int(os.getenv("ULINE_MAX", 199))
ULINE_TTL = int(os.getenv("ULINE_TTL", 3600))

# Atomically allocate a ULINE slot.
# KEYS[1]  = express:uid:{uniqueid}  (String: reverse lookup)
# ARGV[1]  = uline_min
# ARGV[2]  = uline_max
# ARGV[3]  = ttl (seconds)
# ARGV[4]  = uniqueid
# ARGV[5]  = channel
# ARGV[6]  = cdr_start
# ARGV[7]  = caller_id
# ARGV[8]  = provider
# ARGV[9]  = allocated_at (ISO string)
# Returns: {n, is_new} where is_new=1 for new allocation, 0 for existing; n=-1 if no free slots
ALLOCATE_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
if existing then
    return {tonumber(existing), 0}
end

local ttl = tonumber(ARGV[3])
for n = tonumber(ARGV[1]), tonumber(ARGV[2]) do
    local uline_key = 'express:uline:' .. n
    local claimed = redis.call('HSETNX', uline_key, 'uniqueid', ARGV[4])
    if claimed == 1 then
        redis.call('HSET', uline_key,
            'channel',      ARGV[5],
            'cdr_start',    ARGV[6],
            'caller_id',    ARGV[7],
            'provider',     ARGV[8],
            'allocated_at', ARGV[9]
        )
        redis.call('EXPIRE', uline_key, ttl)
        redis.call('SET', KEYS[1], tostring(n), 'EX', ttl)
        return {n, 1}
    end
end

return {-1, 0}
"""


class ULineRedisManager:
    """
    Manages ULINE allocation in Redis.

    ULINE is a unique integer (ULINE_MIN..ULINE_MAX) assigned to each active call.
    It doubles as the Asterisk parking slot number.
    Tied to CDR(uniqueid) — stable across Park/Unpark.
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._allocate_script = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
            self._allocate_script = self._client.register_script(ALLOCATE_SCRIPT)
        return self._client

    def _uline_key(self, n: int) -> str:
        return f"express:uline:{n}"

    def _uid_key(self, uniqueid: str) -> str:
        return f"express:uid:{uniqueid}"

    def allocate(
        self,
        uniqueid: str,
        channel: str,
        cdr_start: str,
        caller_id: str,
        provider: str,
    ) -> Optional[int]:
        """
        Allocate a ULINE for a call.

        Returns the allocated ULINE number, or None if all slots are busy.
        Idempotent: if uniqueid already has a ULINE, returns the existing one.
        Uses a Lua script for atomic allocation to prevent race conditions and
        WRONGTYPE errors that occurred with the previous SET NX + HSET pattern.
        """
        now = datetime.now().isoformat()
        # Trigger lazy client init (also registers the script)
        _ = self.client
        result = self._allocate_script(
            keys=[self._uid_key(uniqueid)],
            args=[
                str(ULINE_MIN),
                str(ULINE_MAX),
                str(ULINE_TTL),
                uniqueid,
                channel,
                cdr_start,
                caller_id,
                provider,
                now,
            ],
        )
        n, is_new = int(result[0]), bool(result[1])
        if n == -1:
            logger.error(f"No free ULINEs in range {ULINE_MIN}-{ULINE_MAX}")
            return None
        if is_new:
            logger.info(f"Allocated new ULINE {n} for uniqueid={uniqueid} channel={channel}")
        else:
            logger.info(f"Reusing existing ULINE {n} for uniqueid={uniqueid} channel={channel}")
        return n

    def release(self, uniqueid: str) -> bool:
        """
        Release the ULINE associated with uniqueid.
        Returns True if released, False if not found.
        """
        n_str = self.client.get(self._uid_key(uniqueid))
        if n_str is None:
            logger.warning(f"release: no ULINE found for uniqueid={uniqueid}")
            return False

        pipe = self.client.pipeline()
        pipe.delete(self._uline_key(int(n_str)))
        pipe.delete(self._uid_key(uniqueid))
        pipe.execute()

        logger.info(f"Released ULINE {n_str} for uniqueid={uniqueid}")
        return True

    def get_stats(self) -> dict:
        """Return total/used/free ULINE counts."""
        total = ULINE_MAX - ULINE_MIN + 1
        keys = list(self.client.scan_iter("express:uline:*"))
        used = len(keys)
        return {
            "total": total,
            "used": used,
            "free": total - used,
            "usage_percent": round(used / total * 100, 1) if total else 0,
        }

    def list_all(self) -> list:
        """Return list of all active ULINE dicts (for monitoring)."""
        result = []
        now = datetime.now()
        for key in sorted(self.client.scan_iter("express:uline:*")):
            data = self.client.hgetall(key)
            if not data:
                continue
            n = int(key.split(":")[-1])
            ttl = self.client.ttl(key)
            try:
                allocated_at = datetime.fromisoformat(data.get("allocated_at", ""))
                age_seconds = int((now - allocated_at).total_seconds())
            except (ValueError, TypeError):
                age_seconds = 0
            result.append({
                "n": n,
                "uniqueid": data.get("uniqueid", ""),
                "channel": data.get("channel", ""),
                "caller_id": data.get("caller_id", ""),
                "provider": data.get("provider", ""),
                "cdr_start": data.get("cdr_start", ""),
                "allocated_at": data.get("allocated_at", ""),
                "age_seconds": age_seconds,
                "ttl": ttl,
            })
        return result

    def flush_all(self) -> int:
        """Delete all express:uline:* and express:uid:* keys. Returns count deleted."""
        keys = (
            list(self.client.scan_iter("express:uline:*"))
            + list(self.client.scan_iter("express:uid:*"))
        )
        if keys:
            self.client.delete(*keys)
        logger.warning(f"Flushed {len(keys)} ULINE keys from Redis")
        return len(keys)
