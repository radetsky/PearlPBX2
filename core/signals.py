import logging

logger = logging.getLogger(__name__)


def on_sipuser_post_delete(sender, instance, **kwargs):
    """Remove QueueMember rows left pointing at a deleted SIPUser's endpoint.

    QueueMember.interface is free text (e.g. "PJSIP/101"), not a foreign key,
    so nothing else in the ORM cleans it up — see core.conf.make_queues_conf(),
    which emits every QueueMember unconditionally.
    """
    from core.models import QueueMember, SIPPeer

    interface = instance.standard_pjsip_user
    # A SIPPeer sharing the same name would collapse to the same PJSIP
    # endpoint (core.conf.py's [name] section naming) — leave it alone.
    if SIPPeer.objects.filter(name=instance.username).exists():
        return
    QueueMember.objects.filter(interface=interface).delete()


def connect():
    from django.db.models.signals import post_delete

    from core.models import SIPUser

    post_delete.connect(
        on_sipuser_post_delete,
        sender=SIPUser,
        dispatch_uid="core_cleanup_sipuser_queue_members",
    )
