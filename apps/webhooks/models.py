import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import DialplanContext, Queue, RoutingTable

TEMPLATE_VARIABLES = frozenset(
    {
        "event",
        "uniqueid",
        "caller_id_num",
        "caller_id_name",
        "exten",
        "context",
        "queue",
        "timestamp",
        "duration",
        "cause",
        "cause_txt",
        "answered_time",
        "billsec",
        "recorded",
        "recording_expected",
        "recording_url",
        "recording_file",
        "missed",
        "wait_time",
        "member_name",
        "member_interface",
        "member_number",
        "ringtime",
        "holdtime",
        "answered_by_member",
        "answered_by_interface",
        "direction",
        "dest_channel",
        "dial_status",
        "answered",
        "linkedid",
        "channel",
        "channel_vars",
    }
)

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _collect_placeholders(value):
    if isinstance(value, str):
        return set(_PLACEHOLDER_RE.findall(value))
    if isinstance(value, dict):
        found = set()
        for v in value.values():
            found |= _collect_placeholders(v)
        return found
    if isinstance(value, list):
        found = set()
        for v in value:
            found |= _collect_placeholders(v)
        return found
    return set()


def default_payload_template():
    """Full example template listing every available placeholder.

    Shown as the starting point in the admin "Add Webhook" form. Fields not
    relevant to a given event render as empty strings (see webhook_sender.py),
    so this single template is safe to use unmodified for every event type.
    Clear the field to fall back to the built-in per-event default payload.
    """
    return {name: f"${{{name}}}" for name in sorted(TEMPLATE_VARIABLES)}


def validate_payload_template(value):
    """Template must be a JSON object; ${...} placeholders must be known variables."""
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValidationError(_("Payload template must be a JSON object."))
    unknown = _collect_placeholders(value) - TEMPLATE_VARIABLES
    if unknown:
        raise ValidationError(
            _("Unknown placeholders: %(names)s. Allowed: %(allowed)s"),
            params={
                "names": ", ".join(sorted(unknown)),
                "allowed": ", ".join(sorted(TEMPLATE_VARIABLES)),
            },
        )


class Webhook(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    url = models.URLField(
        max_length=512,
        help_text=_("Endpoint that receives the JSON POST (CRM side)."),
    )
    send_incoming = models.BooleanField(
        default=True,
        help_text=_("Send an event when an incoming call starts."),
    )
    send_ended = models.BooleanField(
        default=True,
        help_text=_(
            "Send an event when a call ends. Only calls announced by an "
            "incoming event are reported, so this requires incoming events."
        ),
    )
    send_missed = models.BooleanField(
        default=False,
        help_text=_("Send an event when a caller abandons a queue (missed call)."),
    )
    send_answered = models.BooleanField(
        default=False,
        help_text=_("Send an event when a queue member answers a call."),
    )
    send_outgoing = models.BooleanField(
        default=False,
        help_text=_(
            "Send an event when a SIP user (not a trunk) places an outgoing call."
        ),
    )
    send_outgoing_answered = models.BooleanField(
        default=False,
        help_text=_("Send an event when the called party answers an outgoing call."),
    )
    send_outgoing_ended = models.BooleanField(
        default=False,
        help_text=_("Send an event when an outgoing call ends."),
    )
    contexts = models.ManyToManyField(
        DialplanContext,
        blank=True,
        related_name="webhooks",
        help_text=_("Incoming calls entering these contexts trigger the webhook."),
    )
    routing_tables = models.ManyToManyField(
        RoutingTable,
        blank=True,
        related_name="webhooks",
        help_text=_(
            "Filters the outgoing-call chain (call.outgoing / call.outgoing_answered "
            "/ call.outgoing_ended): only calls placed by SIP users assigned to "
            "these routing tables trigger it. Trunks (SIPPeer) never trigger the "
            "outgoing chain, even if they share a routing table with a SIP user."
        ),
    )
    queues = models.ManyToManyField(
        Queue,
        blank=True,
        related_name="webhooks",
        help_text=_("Calls joining these queues trigger the webhook."),
    )
    headers = models.JSONField(
        blank=True,
        default=dict,
        help_text=_('Extra HTTP headers, e.g. {"Authorization": "Bearer ..."}.'),
    )
    secret = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_(
            "Optional shared secret. When set, requests carry an HMAC-SHA256 "
            "signature of the body in the X-PearlPBX-Signature header."
        ),
    )
    timeout = models.PositiveSmallIntegerField(
        default=5, help_text=_("HTTP timeout per attempt, seconds.")
    )
    retries = models.PositiveSmallIntegerField(
        default=1, help_text=_("Extra delivery attempts after a failure.")
    )
    payload_template = models.JSONField(
        null=True,
        blank=True,
        default=default_payload_template,
        validators=[validate_payload_template],
        help_text=_(
            "Custom JSON body. String values may use ${placeholders}; "
            "pre-filled with every available placeholder as a starting point. "
            "Clear the field (empty/null) to use the built-in default payload "
            "shape instead, which varies per event."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "webhook"
        verbose_name = _("Webhook")
        verbose_name_plural = _("Webhooks")
