from typing import Any
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import resolve_url
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.core.exceptions import PermissionDenied, ImproperlyConfigured


class ReportViewPermissionMixin(AccessMixin):
    """
    Mixin that checks if user has specific permission based on view name or explicit permission.
    Can be used with auto-detection or manual permission specification.
    """

    request: HttpRequest

    # Permission mapping based on view class names
    VIEW_PERMISSION_MAPPING = {
        "CDRReportView": "view_cdr_report",
        "MonitorReportView": "view_call_recordings",
        "AudioFileView": "view_call_recordings",
        "QueueLogReportView": "view_queue_reports",
        "QueueLogRecordsByCallIdView": "view_queue_reports",
        "CallbackNumberReportView": "view_callback_statistics",
        "RoutingTableReportView": "view_routing_report",
        "AnalyticsQueueCallsView": "view_analytics_reports",
        "AnalyticsAgentCallsView": "view_analytics_reports",
        "AnalyticsOutboundCallsView": "view_analytics_reports",
    }

    # Optional: explicitly set permission (overrides auto-detection)
    required_permission = None

    # Optional: redirect instead of raising 403
    login_url = None
    permission_denied_message = "You don't have permission to access this page."
    redirect_field_name = REDIRECT_FIELD_NAME
    raise_exception = False

    def get_required_permission(self):
        """
        Get the required permission for this view.
        First checks for explicit required_permission, then uses view name mapping.
        """
        if self.required_permission:
            return self.required_permission

        view_name = self.__class__.__name__
        permission = self.VIEW_PERMISSION_MAPPING.get(view_name)

        if not permission:
            raise ImproperlyConfigured(
                f"View {view_name} doesn't have permission mapping. "
                f"Either add it to VIEW_PERMISSION_MAPPING or set required_permission attribute."
            )

        return permission

    def has_permission(self):
        """
        Check if user has the required permission.
        Superusers always have access.
        """
        if not self.request.user.is_authenticated:
            return False

        # Superuser has access to everything
        if self.request.user.is_superuser:
            return True

        permission = self.get_required_permission()

        # Check if user has permission directly or through group
        return self.request.user.has_perm(f"auth.{permission}")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """
        Check permission before dispatching to view.
        """
        if not self.has_permission():
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    def handle_no_permission(self):
        """
        Handle case when user doesn't have permission.
        """
        if self.raise_exception or self.request.user.is_authenticated:
            raise PermissionDenied(self.get_permission_denied_message())

        # Redirect to login if user is not authenticated
        path = self.request.get_full_path()
        resolved_login_url = resolve_url(self.get_login_url())
        login_scheme, login_netloc = (
            resolve_url(resolved_login_url).split("://", 1)[0],
            resolve_url(resolved_login_url).split("://", 1)[1].split("/", 1)[0],
        )
        current_scheme, current_netloc = self.request.scheme, self.request.get_host()

        if (not login_scheme or login_scheme == current_scheme) and (
            not login_netloc or login_netloc == current_netloc
        ):
            path = self.request.get_full_path()

        return HttpResponseRedirect(
            f"{resolved_login_url}?{self.redirect_field_name}={path}"
        )
