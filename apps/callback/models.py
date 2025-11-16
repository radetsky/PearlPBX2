from django.db import models

# Create your models here.
class CallbackNumber(models.Model):
    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    src = models.CharField(max_length=16, default='', blank=False)
    dst = models.CharField(max_length=16, default='', blank=False)
    updated = models.DateTimeField(null=True, blank=True)
    dial_status = models.CharField(max_length=16, default='', blank=False)
    service_name = models.CharField(max_length=64, default='', blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['created']),
            models.Index(fields=['dst']),
            models.Index(fields=['updated']),
            models.Index(fields=['service_name']),
        ]
