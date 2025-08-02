from django.urls import path
from apps.reports.views import CDRReportView, MonitorReportView, AudioFileView

urlpatterns = [
    path("cdr/", CDRReportView.as_view(), name="cdr_report"),
    path("monitor/", MonitorReportView.as_view(), name="monitor_report"),
    path("audio/<uuid:record_id>/", AudioFileView.as_view(), name="audio_file"),
]
