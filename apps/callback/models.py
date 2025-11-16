from django.db import models

class CallbackNumber(models.Model):
    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(auto_created=True, auto_now_add=True)
    src = models.CharField(max_length=16, default='', blank=True)
    dst = models.CharField(max_length=16, null=False, blank=False)
    updated = models.DateTimeField(null=True, blank=True)
    dial_status = models.CharField(max_length=16, default='', blank=False)
    service_name = models.CharField(max_length=64, default='', blank=True)
    schedule_time = models.DateTimeField(auto_created=True, auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['created']),
            models.Index(fields=['dst']),
            models.Index(fields=['updated']),
            models.Index(fields=['service_name']),
            models.Index(fields=['schedule_time']),
        ]