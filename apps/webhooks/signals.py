import logging

from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_migrate,
    post_save,
)

logger = logging.getLogger(__name__)


def _resync():
    from apps.webhooks.sync import sync_webhooks_config

    try:
        sync_webhooks_config()
    except Exception as e:
        logger.error(f"Failed to sync webhooks config to Redis: {e}")


def on_webhook_saved(sender, **kwargs):
    _resync()


def on_webhook_deleted(sender, **kwargs):
    _resync()


def on_webhook_m2m_changed(sender, action, **kwargs):
    if action.startswith("post_"):
        _resync()


def on_post_migrate(sender, **kwargs):
    if getattr(sender, "name", "") == "apps.webhooks":
        _resync()


def connect():
    from apps.webhooks.models import Webhook

    post_save.connect(on_webhook_saved, sender=Webhook, dispatch_uid="webhooks_sync_save")
    post_delete.connect(
        on_webhook_deleted, sender=Webhook, dispatch_uid="webhooks_sync_delete"
    )
    m2m_changed.connect(
        on_webhook_m2m_changed,
        sender=Webhook.contexts.through,
        dispatch_uid="webhooks_sync_contexts",
    )
    m2m_changed.connect(
        on_webhook_m2m_changed,
        sender=Webhook.routing_tables.through,
        dispatch_uid="webhooks_sync_routing_tables",
    )
    m2m_changed.connect(
        on_webhook_m2m_changed,
        sender=Webhook.queues.through,
        dispatch_uid="webhooks_sync_queues",
    )
    post_migrate.connect(on_post_migrate, dispatch_uid="webhooks_sync_migrate")
