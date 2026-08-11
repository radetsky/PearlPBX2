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
            )
            if enabled
        ]
        # A SIP user's PJSIP context is its routing table's name (see
        # core/conf.py make_pjsip_conf_users), so outbound calls are matched
        # by merging routing table names into the same context list used for
        # inbound DialplanContext matches.
        contexts = [c.name for c in wh.contexts.all()] + [
            rt.name for rt in wh.routing_tables.all()
        ]
        webhooks.append(
            {
                "name": wh.name,
                "url": wh.url,
                "events": events,
                "contexts": contexts,
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_webhooks_config():
    config = serialize_webhooks()
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        client.set(WEBHOOKS_CONFIG_KEY, json.dumps(config))
    finally:
        client.close()
