import math

from django.conf import settings

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.api.serializers import OriginateSerializer, ConferenceSerializer
from apps.api.views.common import asterisk_disabled_response, ami_unavailable_response
from core.ami import AsteriskManagementInterface


def _classify_originate_response(response) -> tuple[bool, str]:
    """
    Classify a single AMI Originate response.

    Returns (ok, message): ok is False for a timed-out (None) or error response,
    True otherwise; message is the AMI "Message" field (or a fallback string).
    """
    if response is None:
        return False, "AMI originate timed out."
    if response.is_error():
        return False, response.keys.get("Message", "Originate failed.")
    return True, response.keys.get("Message", "")


class OriginateView(APIView):
    @extend_schema(
        request=OriginateSerializer,
        responses={
            200: OpenApiResponse(description="Call originated successfully."),
            400: OpenApiResponse(description="Invalid request body."),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            502: OpenApiResponse(description="AMI error or Asterisk unreachable."),
            503: OpenApiResponse(description="Asterisk is disabled in this DEVMODE."),
        },
        summary="Originate a call",
        tags=["calls"],
    )
    def post(self, request):
        serializer = OriginateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        disabled = asterisk_disabled_response()
        if disabled:
            return disabled

        ami_kwargs = serializer.to_ami_kwargs()
        wait_seconds = (
            math.ceil(ami_kwargs["timeout_ms"] / 1000) + settings.ASTERISK_AMI_RESPONSE_MARGIN
        )

        try:
            with AsteriskManagementInterface(timeout=wait_seconds) as ami:
                response = ami.originate(**ami_kwargs)
        except Exception:
            return ami_unavailable_response()

        ok, message = _classify_originate_response(response)
        if not ok:
            return Response({"detail": message}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {"status": "originated", "message": message},
            status=status.HTTP_200_OK,
        )


class ConferenceView(APIView):
    @extend_schema(
        request=ConferenceSerializer,
        responses={
            202: OpenApiResponse(
                description="Conference legs queued (see per-party results)."
            ),
            400: OpenApiResponse(description="Invalid request body."),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            502: OpenApiResponse(description="AMI error or Asterisk unreachable."),
            503: OpenApiResponse(description="Asterisk is disabled in this DEVMODE."),
        },
        summary="Originate several parties into a shared ConfBridge conference room",
        tags=["calls"],
    )
    def post(self, request):
        serializer = ConferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        disabled = asterisk_disabled_response()
        if disabled:
            return disabled

        room, ami_kwargs_list = serializer.to_originate_kwargs_list()
        timeout_ms = serializer.validated_data["timeout_ms"]
        wait_seconds = (
            math.ceil(timeout_ms / 1000) + settings.ASTERISK_AMI_RESPONSE_MARGIN
        )

        try:
            with AsteriskManagementInterface(timeout=wait_seconds) as ami:
                # Send every leg's Originate first (send_action only writes to the
                # socket and returns) and only then wait on each future's response,
                # so all legs dial in parallel instead of one after another.
                pending = [
                    (ami_kwargs["channel"], ami.send_originate(**ami_kwargs))
                    for ami_kwargs in ami_kwargs_list
                ]
                results = []
                for channel, future in pending:
                    ok, message = _classify_originate_response(future.response)
                    results.append(
                        {"channel": channel, "queued": ok, "detail": message}
                    )
        except Exception:
            return ami_unavailable_response()

        # Actual answer/hangup progress for each leg is reported separately
        # through the call.* webhooks, matched by the resulting call uniqueid.
        return Response(
            {"room": room, "results": results},
            status=status.HTTP_202_ACCEPTED,
        )
