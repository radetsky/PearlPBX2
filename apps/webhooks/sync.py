"""Serialize active webhooks into Redis for the dashboard AMI listener.

The listener has no database access; it reads the `webhooks:config` key on
startup and on every health-check tick, so admin changes apply without a
service restart.
"""

import json
from datetime import datetime, timezone

import redis
from django.conf import settings

WEBHOOKS_CONFIG_KEY = "webhooks:config"


def _serialize_sip_users():
    """Map PJSIP endpoint name -> routing table name, SIP users only.

    Used by the listener to tell an outgoing call placed by a SIP user apart
    from one placed by a trunk (SIPPeer): both endpoint kinds can end up with
    a context equal to a routing table's name (see core/conf.py), so the
    endpoint name is the only reliable signal. Excludes users skipped during
    pjsip.conf generation (no transport/routing table), matching
    core.conf.get_users_excluded_from_pjsip.
    """
    from core.conf import get_users_excluded_from_pjsip

    excluded_ids = get_users_excluded_from_pjsip().values_list("pk", flat=True)
    from core.models import SIPUser

    users = SIPUser.objects.exclude(pk__in=excluded_ids).select_related("routing_table")
    return {user.username: user.routing_table.name for user in users}


def serialize_webhooks():
    from apps.webhooks.models import Webhook

    webhooks = []
    qs = Webhook.objects.filter(is_active=True).prefetch_related(
        "contexts", "routing_tables", "queues"
    )
    for wh in qs:
        events = [
            event
            for event, enabled in (
                ("incoming", wh.send_incoming),
                ("ended", wh.send_ended),
                ("missed", wh.send_missed),
                ("answered", wh.send_answered),
                ("outgoing", wh.send_outgoing),
                ("outgoing_answered", wh.send_outgoing_answered),
                ("outgoing_ended", wh.send_outgoing_ended),
            )
            if enabled
        ]
        webhooks.append(
            {
                "name": wh.name,
                "url": wh.url,
                "events": events,
                "contexts": [c.name for c in wh.contexts.all()],
                "routing_tables": [rt.name for rt in wh.routing_tables.all()],
                "queues": [q.name for q in wh.queues.all()],
                "headers": wh.headers or {},
                "secret": wh.secret,
                "timeout": wh.timeout,
                "retries": wh.retries,
                "payload_template": wh.payload_template,
            }
        )
    return {
        "webhooks": webhooks,
        "base_url": settings.PEARLPBX_PUBLIC_URL.rstrip("/"),
        "sip_users": _serialize_sip_users(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_webhooks_config():
    config = serialize_webhooks()
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        client.set(WEBHOOKS_CONFIG_KEY, json.dumps(config))
    finally:
        client.close()
