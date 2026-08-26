from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ImproperlyConfigured


class ReportViewPermissionMixin(PermissionRequiredMixin):
    """
    Mixin that checks if user has specific permission based on view name or explicit permission.
    Can be used with auto-detection or manual permission specification.
    """

    VIEW_PERMISSION_MAPPING = {
        "CDRReportView": "view_cdr_report",
        "MonitorReportView": "view_call_recordings",
        "AudioFileView": "view_call_recordings",
        "AudioFileByUniqueidView": "view_call_recordings",
        "QueueLogReportView": "view_queue_reports",
        "QueueLogRecordsByCallIdView": "view_queue_reports",
        "CallbackNumberReportView": "view_callback_statistics",
        "RoutingTableReportView": "view_routing_report",
        "AnalyticsQueueCallsView": "view_analytics_reports",
        "AnalyticsAgentCallsView": "view_analytics_reports",
        "AnalyticsOutboundCallsView": "view_analytics_reports",
        "AnalyticsMissedCallsView": "view_analytics_reports",
        "AnalyticsMissedByHourView": "view_analytics_reports",
        "AnalyticsCallDurationView": "view_analytics_reports",
        "AnalyticsQueueActivityView": "view_analytics_reports",
        "AnalyticsDestinationCallsView": "view_analytics_reports",
    }

    # Optional: explicitly set permission (overrides auto-detection)
    required_permission = None

    permission_denied_message = "You don't have permission to access this page."

    def get_permission_required(self):
        if self.required_permission:
            return (f"auth.{self.required_permission}",)

        view_name = self.__class__.__name__
        permission = self.VIEW_PERMISSION_MAPPING.get(view_name)

        if not permission:
            raise ImproperlyConfigured(
                f"View {view_name} doesn't have permission mapping. "
                f"Either add it to VIEW_PERMISSION_MAPPING or set required_permission attribute."
            )

        return (f"auth.{permission}",)
