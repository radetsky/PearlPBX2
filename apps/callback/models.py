from django.db import models
from django.db.models.functions import Now

from core.models import DialplanContext

class CallbackService(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    context_outbound = models.ForeignKey(
        DialplanContext,
        on_delete=models.PROTECT,
        related_name='callback_services',
        null=True,
        blank=True,
    )
    context_inbound = models.ForeignKey(
        DialplanContext,
        on_delete=models.PROTECT,
        related_name='callback_services_inbound',
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'callback_service'

class CallbackNumber(models.Model):

    DIAL_STATUS_CHOICES = [
        ('NEW', 'New'),
        ('ANSWERED', 'Answered'),
        ('BUSY', 'Busy'),
        ('PENDING', 'Pending'),
    ]

    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    src = models.CharField(max_length=16, default='', blank=True, db_default='')
    dst = models.CharField(max_length=16, null=False, blank=False)
    updated = models.DateTimeField(null=True, blank=True)
    dial_status = models.CharField(
        max_length=16,
        choices=DIAL_STATUS_CHOICES,
        default='NEW',
        blank=True,
        null=False,
        db_default='NEW',
    )
    schedule_time = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    service = models.ForeignKey(
        CallbackService,
        on_delete=models.PROTECT,
        related_name='callback_numbers',
    )

    def __str__(self):
        return f"{self.src} -> {self.dst} ({self.dial_status})"

    class Meta:
        indexes = [
            models.Index(fields=['created']),
            models.Index(fields=['dst']),
            models.Index(fields=['updated']),
            models.Index(fields=['service']),
            models.Index(fields=['schedule_time']),
        ]
        db_table = 'callback_number'