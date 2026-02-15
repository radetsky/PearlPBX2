from django.views.decorators.http import require_http_methods
import redis
import json
from django.http import JsonResponse

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def operator_panel(request):
    """Operator Dashboard - головна сторінка"""
    return render(request, "dashboard/operator_panel.html")


@login_required
@require_http_methods(["GET"])
def get_queue_state(request, queue_name):
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    state_key = f"asterisk:queue:{queue_name}"
    state = r.get(state_key)

    if state:
        return JsonResponse(json.loads(state))
    else:
        return JsonResponse({"members": {}, "calls": {}, "stats": {"waiting": 0}})


@login_required
@require_http_methods(["GET"])
def get_all_queues(request):
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    # Знаходимо всі ключі черг
    queue_keys = r.keys("asterisk:queue:*")
    queues = {}

    for key in queue_keys:
        queue_name = key.replace("asterisk:queue:", "")
        state = r.get(key)
        if state:
            queues[queue_name] = json.loads(state)

    return JsonResponse(queues)


@login_required
@require_http_methods(["GET"])
def get_all_channels(request):
    """Отримати всі активні канали"""
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    channels = r.get("asterisk:channels:all")

    if channels:
        return JsonResponse(json.loads(channels))
    else:
        return JsonResponse({})


@login_required
@require_http_methods(["GET"])
def get_channel(request, channel_name):
    """Отримати конкретний канал"""
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    channel = r.get(f"asterisk:channel:{channel_name}")

    if channel:
        return JsonResponse(json.loads(channel))
    else:
        return JsonResponse({"error": "Channel not found"}, status=404)


@login_required
@require_http_methods(["GET"])
def get_active_calls(request):
    """Отримати всі активні дзвінки (з bridge)"""
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    channels_data = r.get("asterisk:channels:all")

    if not channels_data:
        return JsonResponse({"calls": []})

    channels = json.loads(channels_data)

    # Фільтруємо тільки канали в bridge
    active_calls = []
    processed_bridges = set()

    for channel_name, channel_data in channels.items():
        bridge_id = channel_data.get("bridge_id")

        if bridge_id and bridge_id not in processed_bridges:
            # Знаходимо всі канали в цьому bridge
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
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    channels_data = r.get("asterisk:channels:all")

    if not channels_data:
        return JsonResponse({})

    channels = json.loads(channels_data)

    # Фільтруємо по типу
    filtered_channels = {
        name: data for name, data in channels.items() if name.startswith(channel_type)
    }

    return JsonResponse(filtered_channels)
