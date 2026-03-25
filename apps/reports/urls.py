from django.urls import path
from apps.reports.views import (
    AnalyticsAgentCallsView,
    AnalyticsCallDurationView,
    AnalyticsQueueActivityView,
    AnalyticsMissedByHourView,
    AnalyticsMissedCallsView,
    AnalyticsOutboundCallsView,
    AnalyticsQueueCallsView,
    CDRReportView,
    MonitorReportView,
    AudioFileView,
    QueueLogReportView,
    QueueLogRecordsByCallIdView,
    CallbackNumberReportView,
    RoutingTableReportView,
)

urlpatterns = [
    path("cdr/", CDRReportView.as_view(), name="cdr_report"),
    path("monitor/", MonitorReportView.as_view(), name="monitor_report"),
    path("audio/<uuid:record_id>/", AudioFileView.as_view(), name="audio_file"),
    path("queuelog/", QueueLogReportView.as_view(), name="queuelog_report"),
    path(
        "queuelog/records/<str:callid>/",
        QueueLogRecordsByCallIdView.as_view(),
        name="queuelog_records_by_callid",
    ),
    path("callback/", CallbackNumberReportView.as_view(), name="callback_report"),
    path("routing/", RoutingTableReportView.as_view(), name="routing_report"),
    path(
        "analytics/queue-calls/",
        AnalyticsQueueCallsView.as_view(),
        name="analytics_queue_calls",
    ),
    path(
        "analytics/agent-calls/",
        AnalyticsAgentCallsView.as_view(),
        name="analytics_agent_calls",
    ),
    path(
        "analytics/outbound-calls/",
        AnalyticsOutboundCallsView.as_view(),
        name="analytics_outbound_calls",
    ),
    path(
        "analytics/missed-calls/",
        AnalyticsMissedCallsView.as_view(),
        name="analytics_missed_calls",
    ),
    path(
        "analytics/missed-by-hour/",
        AnalyticsMissedByHourView.as_view(),
        name="analytics_missed_by_hour",
    ),
    path(
        "analytics/call-duration/",
        AnalyticsCallDurationView.as_view(),
        name="analytics_call_duration",
    ),
    path(
        "analytics/queue-activity/",
        AnalyticsQueueActivityView.as_view(),
        name="analytics_queue_activity",
    ),
]
