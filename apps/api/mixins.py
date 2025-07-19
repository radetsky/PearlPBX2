from django.conf import settings
from django.http import HttpResponseForbidden


class AllowedHostsIPMixin:
    """
    Mixin to restrict access to views based on client IP address.
    Allowed IPs are specified in settings.PEARLPBX_API_ALLOWED_HOSTS.
    """

    def dispatch(self, request, *args, **kwargs):
        allowed_ips = getattr(
            settings, "PEARLPBX_API_ALLOWED_HOSTS", ["127.0.0.1", "::1"]
        )
        ip = self.get_client_ip(request)
        if ip not in allowed_ips:
            return HttpResponseForbidden("Access denied: IP not allowed.")
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def get_client_ip(request):
        # Handles X-Forwarded-For if behind a proxy
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
