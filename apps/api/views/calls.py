import math

from django.conf import settings

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.api.serializers import OriginateSerializer
from core.ami import AsteriskManagementInterface


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

        if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
            return Response(
                {"detail": "Asterisk is disabled in this DEVMODE."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        ami_kwargs = serializer.to_ami_kwargs()
        wait_seconds = math.ceil(ami_kwargs["timeout_ms"] / 1000) + 5

        try:
            with AsteriskManagementInterface(timeout=wait_seconds) as ami:
                response = ami.originate(**ami_kwargs)
        except Exception:
            return Response(
                {"detail": "AMI unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response is None:
            return Response(
                {"detail": "AMI originate timed out."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.is_error():
            return Response(
                {"detail": response.keys.get("Message", "Originate failed.")},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"status": "originated", "message": response.keys.get("Message", "")},
            status=status.HTTP_200_OK,
        )
