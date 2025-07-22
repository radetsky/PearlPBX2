from django.db import models


class CDR(models.Model):
    calldate = models.DateTimeField()
    clid = models.CharField(max_length=80, blank=True)
    src = models.CharField(max_length=80, blank=True)
    dst = models.CharField(max_length=80, blank=True)
    dcontext = models.CharField(max_length=80, blank=True)
    channel = models.CharField(max_length=80, blank=True)
    dstchannel = models.CharField(max_length=80, blank=True)
    lastapp = models.CharField(max_length=80, blank=True)
    lastdata = models.CharField(max_length=80, blank=True)
    duration = models.IntegerField()
    billsec = models.IntegerField()
    disposition = models.CharField(max_length=45, blank=True)
    amaflags = models.IntegerField()
    accountcode = models.CharField(max_length=20, blank=True)
    uniqueid = models.CharField(max_length=32, blank=True)
    userfield = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "cdr"
        managed = False

    def __str__(self):
        return f"{self.src} -> {self.dst} ({self.calldate})"
