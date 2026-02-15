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
