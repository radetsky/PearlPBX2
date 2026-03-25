"""
ULine Redis Manager for parking slot allocation.
Slots range: PARKING_ULINE_MIN (default 1) to PARKING_ULINE_MAX (default 199).
Redis keys: parking:uline:{N} (hash), parking:uid:{uniqueid} (string).
"""

import os
import logging
from datetime import datetime, timezone

import redis

logger = logging.getLogger("PBX.ULineRedis")

_ALLOC_SCRIPT = """
local min_slot = tonumber(ARGV[1])
local max_slot = tonumber(ARGV[2])
local uniqueid  = ARGV[3]
local channel   = ARGV[4]
local cdr_start = ARGV[5]
local caller_id = ARGV[6]
local ttl       = tonumber(ARGV[7])
local now       = ARGV[8]

local uid_key = "parking:uid:" .. uniqueid
local existing = redis.call("GET", uid_key)
if existing then
    return existing
end

for n = min_slot, max_slot do
    local uline_key = "parking:uline:" .. n
    if redis.call("EXISTS", uline_key) == 0 then
        redis.call("HSET", uline_key,
            "uniqueid",    uniqueid,
            "channel",     channel,
            "cdr_start",   cdr_start,
            "caller_id",   caller_id,
            "allocated_at", now
        )
        redis.call("EXPIRE", uline_key, ttl)
        redis.call("SET", uid_key, tostring(n))
        redis.call("EXPIRE", uid_key, ttl)
        return tostring(n)
    end
end
return nil
"""


class ULineRedisManager:
    def __init__(self, redis_client: redis.Redis | None = None):
        self.min_slot = int(os.environ.get("PARKING_ULINE_MIN", 1))
        self.max_slot = int(os.environ.get("PARKING_ULINE_MAX", 199))
        self.ttl = 3600

        if redis_client is not None:
            self.redis = redis_client
        else:
            host = os.environ.get("REDIS_HOST", "localhost")
            port = int(os.environ.get("REDIS_PORT", 6379))
            self.redis = redis.Redis(host=host, port=port, decode_responses=True)

        self._alloc_script = self.redis.register_script(_ALLOC_SCRIPT)

    def allocate(
        self,
        uniqueid: str,
        channel: str,
        cdr_start: str,
        caller_id: str,
    ) -> int | None:
        now = datetime.now(timezone.utc).isoformat()
        result = self._alloc_script(
            args=[
                self.min_slot,
                self.max_slot,
                uniqueid,
                channel,
                cdr_start,
                caller_id,
                self.ttl,
                now,
            ]
        )
        if result is None:
            logger.warning("No free parking ULINE slots available")
            return None
        n = int(result)
        logger.info(f"Allocated parking:uline:{n} for uniqueid={uniqueid}")
        return n

    def release(self, uniqueid: str) -> bool:
        uid_key = f"parking:uid:{uniqueid}"
        n_str = self.redis.get(uid_key)
        if n_str is None:
            logger.debug(f"No ULINE mapping found for uniqueid={uniqueid}")
            return False
        uline_key = f"parking:uline:{n_str}"
        self.redis.delete(uline_key, uid_key)
        logger.info(f"Released parking:uline:{n_str} for uniqueid={uniqueid}")
        return True

    def flush_all(self) -> int:
        uline_keys = list(self.redis.scan_iter("parking:uline:*"))
        uid_keys = list(self.redis.scan_iter("parking:uid:*"))
        all_keys = uline_keys + uid_keys
        if all_keys:
            self.redis.delete(*all_keys)
        count = len(all_keys)
        logger.info(f"Flushed {count} parking ULINE keys")
        return count

    def get_stats(self) -> dict:
        total = self.max_slot - self.min_slot + 1
        used = sum(1 for _ in self.redis.scan_iter("parking:uline:*"))
        free = total - used
        usage_percent = round(used / total * 100, 1) if total else 0
        return {
            "used": used,
            "total": total,
            "free": free,
            "usage_percent": usage_percent,
        }
