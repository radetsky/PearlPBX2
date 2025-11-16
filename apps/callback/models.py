from django.db import models
from django.db.models.functions import Now


class CallbackNumber(models.Model):
    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    src = models.CharField(max_length=16, default='', blank=True, db_default='')
    dst = models.CharField(max_length=16, null=False, blank=False)
    updated = models.DateTimeField(null=True, blank=True)
    dial_status = models.CharField(max_length=16, default='', blank=True, null=False, db_default='')
    service_name = models.CharField(max_length=64, default='', blank=True, null=False, db_default='')
    schedule_time = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        indexes = [
            models.Index(fields=['created']),
            models.Index(fields=['dst']),
            models.Index(fields=['updated']),
            models.Index(fields=['service_name']),
            models.Index(fields=['schedule_time']),
        ]
        db_table = 'callback_number'