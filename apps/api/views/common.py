from django.conf import settings

from rest_framework import status
from rest_framework.response import Response


def asterisk_disabled_response():
    """Return a 503 Response if Asterisk is disabled in this DEVMODE, else None."""
    if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
        return Response(
            {"detail": "Asterisk is disabled in this DEVMODE."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def ami_unavailable_response():
    """Standard 502 Response for an unreachable or failed AMI connection."""
    return Response(
        {"detail": "AMI unavailable."},
        status=status.HTTP_502_BAD_GATEWAY,
    )
