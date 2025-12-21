from django.urls import path
from apps.reports.views import (
    CDRReportView,
    MonitorReportView,
    AudioFileView,
    QueueLogReportView,
    QueueLogRecordsByCallIdView,
    CallbackNumberReportView,
)

urlpatterns = [
    path("cdr/", CDRReportView.as_view(), name="cdr_report"),
    path("monitor/", MonitorReportView.as_view(), name="monitor_report"),
    path("audio/<uuid:record_id>/", AudioFileView.as_view(), name="audio_file"),
    path("queuelog/", QueueLogReportView.as_view(), name="queuelog_report"),
    path("queuelog/records/<str:callid>/", QueueLogRecordsByCallIdView.as_view(), name="queuelog_records_by_callid"),
    path("callback/", CallbackNumberReportView.as_view(), name="callback_report"),
]
