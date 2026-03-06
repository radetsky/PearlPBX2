import re
import json
import logging

import redis
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-/]+$")


def _get_redis():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@login_required
def operator_panel(request):
    """Operator Dashboard - головна сторінка"""
    return render(request, "dashboard/operator_panel.html")


@login_required
@require_http_methods(["GET"])
def get_queue_state(request, queue_name):
    if not _VALID_NAME_RE.match(queue_name):
        return JsonResponse({"error": "Invalid queue name"}, status=400)

    try:
        r = _get_redis()
        state = r.get(f"asterisk:queue:{queue_name}")
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_queue_state")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    if state:
        return JsonResponse(json.loads(state))
    return JsonResponse({"members": {}, "calls": {}, "stats": {"waiting": 0}})


@login_required
@require_http_methods(["GET"])
def get_all_queues(request):
    try:
        r = _get_redis()
        queue_keys = r.keys("asterisk:queue:*")
        queues = {}
        for key in queue_keys:
            queue_name = key.replace("asterisk:queue:", "")
            state = r.get(key)
            if state:
                queues[queue_name] = json.loads(state)
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_all_queues")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    return JsonResponse(queues)


@login_required
@require_http_methods(["GET"])
def get_all_channels(request):
    """Отримати всі активні канали"""
    try:
        r = _get_redis()
        channels = r.get("asterisk:channels:all")
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_all_channels")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    if channels:
        return JsonResponse(json.loads(channels))
    return JsonResponse({})


@login_required
@require_http_methods(["GET"])
def get_channel(request, channel_name):
    """Отримати конкретний канал"""
    if not _VALID_NAME_RE.match(channel_name):
        return JsonResponse({"error": "Invalid channel name"}, status=400)

    try:
        r = _get_redis()
        channel = r.get(f"asterisk:channel:{channel_name}")
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_channel")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    if channel:
        return JsonResponse(json.loads(channel))
    return JsonResponse({"error": "Channel not found"}, status=404)


@login_required
@require_http_methods(["GET"])
def get_active_calls(request):
    """Отримати всі активні дзвінки (з bridge)"""
    try:
        r = _get_redis()
        channels_data = r.get("asterisk:channels:all")
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_active_calls")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    if not channels_data:
        return JsonResponse({"calls": []})

    channels = json.loads(channels_data)

    active_calls = []
    processed_bridges = set()

    for channel_name, channel_data in channels.items():
        bridge_id = channel_data.get("bridge_id")

        if bridge_id and bridge_id not in processed_bridges:
            bridged_channels = [
                ch for ch in channels.values() if ch.get("bridge_id") == bridge_id
            ]

            if len(bridged_channels) >= 2:
                active_calls.append(
                    {
                        "bridge_id": bridge_id,
                        "channels": bridged_channels,
                        "duration": channel_data.get("duration", 0),
                    }
                )
                processed_bridges.add(bridge_id)

    return JsonResponse({"calls": active_calls})


@login_required
def uline_monitor(request):
    """ULINE Monitor — shows active ULINEs and their liveness status."""
    try:
        r = _get_redis()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        dashboard_alive = r.exists("asterisk:channels:all")

        sorted_keys = sorted(
            r.scan_iter("express:uline:*"),
            key=lambda k: int(k.split(":")[-1]),
        )

        # Pipeline pass 1: hgetall + ttl for all ULINE keys
        pipe1 = r.pipeline()
        for key in sorted_keys:
            pipe1.hgetall(key)
            pipe1.ttl(key)
        pipe1_results = pipe1.execute()

        # Build intermediate list and collect uniqueids for liveness check
        raw_ulines = []
        for i, key in enumerate(sorted_keys):
            data = pipe1_results[i * 2]
            ttl = pipe1_results[i * 2 + 1]
            if not data:
                continue
            raw_ulines.append((key, data, ttl))

        uniqueids = [data.get("uniqueid", "") for _, data, _ in raw_ulines]

        # Pipeline pass 2: exists check for each uniqueid
        pipe2 = r.pipeline()
        for uid in uniqueids:
            if uid:
                pipe2.exists(f"asterisk:uid:{uid}")
            else:
                pipe2.exists("__nonexistent__")
        pipe2_results = pipe2.execute()

        ulines = []
        for idx, (key, data, ttl) in enumerate(raw_ulines):
            n = int(key.split(":")[-1])
            uniqueid = data.get("uniqueid", "")
            channel_alive = bool(pipe2_results[idx]) if uniqueid else False

            try:
                allocated_at = datetime.fromisoformat(data.get("allocated_at", ""))
                age_seconds = int((now - allocated_at).total_seconds())
            except (ValueError, TypeError):
                age_seconds = 0

            ulines.append({
                "n": n,
                "uniqueid": uniqueid,
                "channel": data.get("channel", ""),
                "caller_id": data.get("caller_id", ""),
                "provider": data.get("provider", ""),
                "allocated_at": data.get("allocated_at", ""),
                "age_seconds": age_seconds,
                "ttl": ttl,
                "alive": channel_alive,
            })

        from django.conf import settings
        uline_min = getattr(settings, "ULINE_MIN", 1)
        uline_max = getattr(settings, "ULINE_MAX", 199)
        total = uline_max - uline_min + 1
        used = len(ulines)

        context = {
            "ulines": ulines,
            "stats": {
                "total": total,
                "used": used,
                "free": total - used,
                "usage_percent": round(used / total * 100, 1) if total else 0,
            },
            "dashboard_alive": dashboard_alive,
        }

    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in uline_monitor")
        context = {"ulines": [], "stats": {}, "dashboard_alive": False, "redis_error": True}

    return render(request, "dashboard/ulines.html", context)


@login_required
@require_http_methods(["POST"])
def uline_flush(request):
    """Flush all ULINEs from Redis (admin only)."""
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Superuser only")
    try:
        r = _get_redis()
        keys = (
            list(r.scan_iter("express:uline:*"))
            + list(r.scan_iter("express:uid:*"))
        )
        if keys:
            r.delete(*keys)
        count = len(keys)
        logger.warning(f"ULINE flush by {request.user}: {count} keys deleted")
        return JsonResponse({"deleted": count})
    except redis.exceptions.ConnectionError:
        return JsonResponse({"error": "Redis unavailable"}, status=503)


@login_required
@require_http_methods(["GET"])
def get_channels_by_type(request, channel_type):
    """Отримати канали по типу (PJSIP, DAHDI, Local, etc.)"""
    if not _VALID_NAME_RE.match(channel_type):
        return JsonResponse({"error": "Invalid channel type"}, status=400)

    try:
        r = _get_redis()
        channels_data = r.get("asterisk:channels:all")
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection failed in get_channels_by_type")
        return JsonResponse({"error": "Redis unavailable"}, status=503)

    if not channels_data:
        return JsonResponse({})

    channels = json.loads(channels_data)

    filtered_channels = {
        name: data for name, data in channels.items() if name.startswith(channel_type)
    }

    return JsonResponse(filtered_channels)
