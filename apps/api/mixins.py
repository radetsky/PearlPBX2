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
        # Only trust X-Forwarded-For when the direct peer is a configured trusted
        # proxy. Otherwise the header is client-controlled and would let anyone
        # spoof an allowed IP.
        remote_addr = request.META.get("REMOTE_ADDR")
        if remote_addr not in getattr(settings, "PEARLPBX_API_TRUSTED_PROXIES", []):
            return remote_addr
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return remote_addr
