from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.webhooks.models import Webhook
from core.widgets import PasswordWithToggleInput


class WebhookAdminForm(forms.ModelForm):
    class Meta:
        model = Webhook
        fields = "__all__"
        widgets = {"secret": PasswordWithToggleInput()}

    def clean(self):
        cleaned = super().clean()
        contexts = cleaned.get("contexts")
        routing_tables = cleaned.get("routing_tables")
        queues = cleaned.get("queues")

        if not contexts and not routing_tables and not queues:
            raise ValidationError(
                _(
                    "Select at least one context, routing table, or queue to "
                    "define which calls trigger this webhook."
                )
            )

        inbound_events = (
            cleaned.get("send_incoming")
            or cleaned.get("send_ended")
            or cleaned.get("send_missed")
            or cleaned.get("send_answered")
        )
        if inbound_events and not contexts and not queues:
            raise ValidationError(
                _(
                    "Incoming/ended/missed/answered events are matched by context "
                    "or queue (routing tables only match the outgoing-call chain): "
                    "select at least one context or queue."
                )
            )

        outgoing_events = (
            cleaned.get("send_outgoing")
            or cleaned.get("send_outgoing_answered")
            or cleaned.get("send_outgoing_ended")
        )
        if outgoing_events and not routing_tables:
            raise ValidationError(
                _(
                    "Outgoing-call events are matched by routing table: select at "
                    "least one routing table."
                )
            )

        if cleaned.get("send_ended") and not cleaned.get("send_incoming"):
            raise ValidationError(
                _(
                    "Ended events are sent only for calls announced by an incoming "
                    "event, so 'Send ended' requires 'Send incoming'."
                )
            )
        if cleaned.get("send_missed") and not queues:
            raise ValidationError(
                _("Missed-call events are queue based: select at least one queue.")
            )
        if cleaned.get("send_answered") and not queues:
            raise ValidationError(
                _("Answered-call events are queue based: select at least one queue.")
            )
        if cleaned.get("send_outgoing_answered") and not cleaned.get("send_outgoing"):
            raise ValidationError(
                _(
                    "Outgoing-answered events are sent only for calls announced by "
                    "an outgoing event, so 'Send outgoing answered' requires 'Send "
                    "outgoing'."
                )
            )
        if cleaned.get("send_outgoing_ended") and not cleaned.get("send_outgoing"):
            raise ValidationError(
                _(
                    "Outgoing-ended events are sent only for calls announced by an "
                    "outgoing event, so 'Send outgoing ended' requires 'Send "
                    "outgoing'."
                )
            )
        return cleaned


class WebhookAdmin(admin.ModelAdmin):
    form = WebhookAdminForm
    list_display = [
        "name",
        "url",
        "is_active",
        "send_incoming",
        "send_ended",
        "send_missed",
        "send_answered",
        "send_outgoing",
        "send_outgoing_answered",
        "send_outgoing_ended",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "url"]
    filter_horizontal = ["contexts", "routing_tables", "queues"]


admin.site.register(Webhook, WebhookAdmin)
