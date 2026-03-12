from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import SIPUser, AuditFields


class PhoneDevice(AuditFields):
    USER_TELEPHONE_TYPE_CHOICES = [
        ("spa502g", "Cisco SPA502G"),
        ("spa504g", "Cisco SPA504G"),
        ("gxp1200", "Grandstream GXP1200"),
        ("softphone", "Softphone"),
        ("webrtc", "WebRTC"),
        ("other", "Other"),
    ]

    telephone_type = models.CharField(
        max_length=32,
        choices=USER_TELEPHONE_TYPE_CHOICES,
        default="other",
        help_text=_("Type of telephone device"),
        verbose_name=_("Telephone type"),
    )
    mac_address = models.CharField(
        max_length=17,
        unique=True,
        help_text=_("MAC address of the device"),
        verbose_name=_("MAC Address"),
    )
    sip_user = models.ForeignKey(
        SIPUser,
        related_name="devices",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("SIP user associated with this device"),
        verbose_name=_("SIP User"),
    )
    sip_server = models.CharField(
        max_length=255,
        help_text=_("SIP server address"),
        verbose_name=_("SIP Server"),
        null=False,
        blank=False,
        default="",
    )

    class Meta(AuditFields.Meta):
        verbose_name = _("Phone Device")
        verbose_name_plural = _("Phone Devices")
        ordering = ["-created_at"]

    def __str__(self):
        if self.sip_user:
            return f"{self.mac_address} ({self.sip_user.username})"
        return f"{self.mac_address} ({dict(self.USER_TELEPHONE_TYPE_CHOICES).get(self.telephone_type, self.telephone_type)})"
