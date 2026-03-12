from django.db import models

from core.models import MonitorFilenames


class QueueLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    time = models.DateTimeField(null=True, blank=True)
    callid = models.CharField(max_length=80, blank=True)
    queuename = models.CharField(max_length=256, blank=True)
    agent = models.CharField(max_length=80, blank=True)
    event = models.CharField(max_length=32, blank=True)
    data1 = models.CharField(max_length=100, blank=True)
    data2 = models.CharField(max_length=100, blank=True)
    data3 = models.CharField(max_length=100, blank=True)
    data4 = models.CharField(max_length=100, blank=True)
    data5 = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "queue_log"
        managed = True
        indexes = [
            models.Index(fields=["time"], name="idx_ql_time"),
            models.Index(fields=["callid"], name="idx_ql_callid"),
            models.Index(fields=["queuename"], name="idx_ql_queuename"),
            models.Index(fields=["agent"], name="idx_ql_agent"),
            models.Index(fields=["event"], name="idx_ql_event"),
            models.Index(fields=["event", "callid"], name="idx_ql_event_callid"),
        ]

    def __str__(self):
        return f"{self.time} {self.queuename} {self.agent} {self.event}"


class CDR(models.Model):
    id = models.AutoField(primary_key=True)
    accountcode = models.CharField(max_length=80, blank=True)
    src = models.CharField(max_length=80, blank=True)
    dst = models.CharField(max_length=80, blank=True)
    dcontext = models.CharField(max_length=80, blank=True)
    clid = models.CharField(max_length=80, blank=True)
    channel = models.CharField(max_length=80, blank=True)
    dstchannel = models.CharField(max_length=80, blank=True)
    lastapp = models.CharField(max_length=80, blank=True)
    lastdata = models.CharField(max_length=80, blank=True)
    start = models.DateTimeField(null=True, blank=True)
    answer = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    billsec = models.IntegerField(null=True, blank=True)
    disposition = models.CharField(max_length=45, blank=True)
    amaflags = models.CharField(max_length=45, blank=True)
    userfield = models.CharField(max_length=256, blank=True)
    uniqueid = models.CharField(max_length=150, blank=False, null=False, db_index=True)
    linkedid = models.CharField(max_length=150, blank=True)
    peeraccount = models.CharField(max_length=80, blank=True)
    sequence = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "cdr"
        managed = False
        unique_together = [["uniqueid", "sequence"]]
        indexes = [
            models.Index(fields=["src"], name="idx_cdr_src"),
            models.Index(fields=["dst"], name="idx_cdr_dst"),
            models.Index(fields=["channel"], name="idx_cdr_channel"),
            models.Index(fields=["dstchannel"], name="idx_cdr_dstchannel"),
            models.Index(fields=["start"], name="idx_cdr_start"),
            models.Index(fields=["end"], name="idx_cdr_end"),
            models.Index(fields=["duration"], name="idx_cdr_duration"),
            models.Index(fields=["billsec"], name="idx_cdr_billsec"),
            models.Index(fields=["disposition"], name="idx_cdr_disposition"),
            models.Index(fields=["uniqueid"], name="idx_cdr_uniqueid_uniqueid"),
            models.Index(fields=["linkedid"], name="idx_cdr_linkedid"),
            models.Index(fields=["uniqueid", "sequence"], name="idx_cdr_uniqueid_seq"),
        ]

    def __str__(self):
        return f"{self.start} {self.src} -> {self.dst} (ID: {self.uniqueid})"

    def get_audio_url(self):
        try:
            filename_object = MonitorFilenames.objects.get(cdr_uniqueid=self.uniqueid)
            if not filename_object:
                return None
            return filename_object.get_audio_url()
        except MonitorFilenames.DoesNotExist:
            return None
