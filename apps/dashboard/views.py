import re
import json
import logging
from datetime import timedelta
from functools import wraps

import redis
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from asterisk.ami import AMIClient, SimpleAction

from core.models import SIPUser, SIPPeer
from apps.reports.models import QueueLog
from apps.reports.services.lost_and_found import build_lost_and_found

logger = logging.getLogger(__name__)

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-/@]+$")


def _get_redis():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def staff_required_json(view_func):
    """Restrict a JSON control endpoint to staff users (403 JSON otherwise)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


@login_required
def operator_panel(request):
    """Operator Dashboard - main page"""
    return render(request, "dashboard/operator_panel.html")


@login_required
def new_dashboard(request):
    """Render the new dark-theme live operator dashboard."""
    return render(request, "dashboard/new_dashboard.html")


@login_required
@require_http_methods(["GET"])
def get_sip_endpoints(request):
    """Return internal SIP user usernames and external SIP peer names from the DB.

    Used by the frontend to classify PJSIP channel endpoints as internal
    (registered users) or external (trunks / providers).
    """
    users = list(SIPUser.objects.values_list("username", flat=True))
    peers = list(SIPPeer.objects.values_list("name", flat=True))
    return JsonResponse({"users": users, "peers": peers})


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
    """Get all active channels"""
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
    """Get a specific channel"""
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
    """Get all active calls (with bridge)"""
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
            r.scan_iter("parking:uline:*"),
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

            ulines.append(
                {
                    "n": n,
                    "uniqueid": uniqueid,
                    "channel": data.get("channel", ""),
                    "caller_id": data.get("caller_id", ""),
                    "provider": data.get("provider", ""),
                    "allocated_at": data.get("allocated_at", ""),
                    "age_seconds": age_seconds,
                    "ttl": ttl,
                    "alive": channel_alive,
                }
            )

        from django.conf import settings

        uline_min = getattr(settings, "PARKING_ULINE_MIN", 1)
        uline_max = getattr(settings, "PARKING_ULINE_MAX", 199)
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
        context = {
            "ulines": [],
            "stats": {},
            "dashboard_alive": False,
            "redis_error": True,
        }

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
        keys = list(r.scan_iter("parking:uline:*")) + list(r.scan_iter("parking:uid:*"))
        if keys:
            r.delete(*keys)
        count = len(keys)
        logger.warning(f"ULINE flush by {request.user}: {count} keys deleted")
        return JsonResponse({"deleted": count})
    except redis.exceptions.ConnectionError:
        return JsonResponse({"error": "Redis unavailable"}, status=503)


@login_required
@csrf_protect
@require_http_methods(["POST"])
@staff_required_json
def hangup_channel(request):
    """Send AMI Hangup action for the given channel."""
    try:
        body = json.loads(request.body)
        channel = body.get("channel", "")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Invalid request body"}, status=400)

    if not channel or not _VALID_NAME_RE.match(channel):
        return JsonResponse({"error": "Invalid channel name"}, status=400)

    client = None
    try:
        client = AMIClient(
            address=settings.ASTERISK_MANAGER_HOST,
            port=settings.ASTERISK_MANAGER_PORT,
        )
        client.login(
            username=settings.ASTERISK_MANAGER_USERNAME,
            secret=settings.ASTERISK_MANAGER_SECRET,
        )
        future = client.send_action(SimpleAction("Hangup", Channel=channel))
        response = future.response
    except Exception as e:
        logger.error(f"AMI hangup error for {channel}: {e}")
        return JsonResponse({"error": str(e)}, status=502)
    finally:
        if client is not None:
            try:
                client.logoff()
            except Exception:
                pass

    if response is None:
        return JsonResponse({"error": "No response from AMI"}, status=502)

    if response.status == "Success":
        logger.info(f"Hangup sent for {channel} by {request.user}")
        return JsonResponse({"ok": True})

    return JsonResponse({"error": response.status}, status=400)


@login_required
@csrf_protect
@require_http_methods(["POST"])
@staff_required_json
def pause_queue_member(request):
    """Send AMI QueuePause/QueueUnpause action for the given interface."""
    try:
        body = json.loads(request.body)
        interface = body.get("interface", "")
        paused = body.get("paused")
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Invalid request body"}, status=400)

    logger.info(f"QueuePause request: interface={interface!r} paused={paused!r} user={request.user}")

    if not interface or not _VALID_NAME_RE.match(interface):
        return JsonResponse({"error": "Invalid interface name", "received": repr(interface)}, status=400)

    if not isinstance(paused, bool):
        return JsonResponse({"error": "paused must be a boolean", "received": repr(paused), "type": type(paused).__name__}, status=400)

    client = None
    try:
        client = AMIClient(
            address=settings.ASTERISK_MANAGER_HOST,
            port=settings.ASTERISK_MANAGER_PORT,
        )
        client.login(
            username=settings.ASTERISK_MANAGER_USERNAME,
            secret=settings.ASTERISK_MANAGER_SECRET,
        )
        future = client.send_action(
            SimpleAction("QueuePause", Interface=interface, Paused="true" if paused else "false")
        )
        response = future.response
    except Exception as e:
        logger.error(f"AMI QueuePause error for {interface}: {e}")
        return JsonResponse({"error": str(e)}, status=502)
    finally:
        if client is not None:
            try:
                client.logoff()
            except Exception:
                pass

    if response is None:
        return JsonResponse({"error": "No response from AMI"}, status=502)

    logger.info(f"QueuePause AMI response: status={response.status!r} headers={dict(response.headers) if hasattr(response, 'headers') else response}")

    if response.status == "Success":
        action = "paused" if paused else "unpaused"
        logger.info(f"Queue member {interface} {action} by {request.user}")
        return JsonResponse({"ok": True})

    return JsonResponse({"error": response.status}, status=400)


@login_required
@require_http_methods(["GET"])
def get_missed_calls(request):
    """Return today's unresolved missed calls (ABANDON without callback) for a queue."""
    queue = request.GET.get("queue", "").strip()
    if not queue:
        return JsonResponse({"error": "queue parameter required"}, status=400)

    minutes = getattr(settings, "DASHBOARD_MISSED_CALL_WINDOW_MINUTES", 0)
    now = timezone.now()
    if minutes:
        since = now - timedelta(minutes=minutes)
    else:
        local_now = timezone.localtime(now)
        since = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    qs = QueueLog.objects.filter(queuename=queue, event="ABANDON", time__gte=since)
    rows = build_lost_and_found(qs, unresolved_only=True, normalize=True)

    result = []
    seen = set()
    for row in rows:
        cid = row["callerid"]
        if not cid or cid in seen:
            continue
        seen.add(cid)
        result.append({
            "caller_id": cid,
            "time_hhmm": timezone.localtime(row["abandon_time"]).strftime("%H:%M"),
            "abandon_time": row["abandon_time"].isoformat(),
        })

    return JsonResponse(result, safe=False)


@login_required
@require_http_methods(["GET"])
def get_channels_by_type(request, channel_type):
    """Get channels by type (PJSIP, DAHDI, Local, etc.)"""
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
