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
        if not cleaned.get("contexts") and not cleaned.get("queues"):
            raise ValidationError(
                _("Select at least one context or queue to define which calls trigger this webhook.")
            )
        if cleaned.get("send_ended") and not cleaned.get("send_incoming"):
            raise ValidationError(
                _(
                    "Ended events are sent only for calls announced by an incoming "
                    "event, so 'Send ended' requires 'Send incoming'."
                )
            )
        if cleaned.get("send_missed") and not cleaned.get("queues"):
            raise ValidationError(
                _("Missed-call events are queue based: select at least one queue.")
            )
        if cleaned.get("send_answered") and not cleaned.get("queues"):
            raise ValidationError(
                _("Answered-call events are queue based: select at least one queue.")
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
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "url"]
    filter_horizontal = ["contexts", "queues"]


admin.site.register(Webhook, WebhookAdmin)
