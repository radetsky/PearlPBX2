from django.conf import settings

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from apps.api.serializers import (
    QueueMemberPauseSerializer,
    QueueMemberStatusSerializer,
    QueueMemberListSerializer,
)
from apps.api.views.common import asterisk_disabled_response, ami_unavailable_response
from core.ami import AsteriskManagementInterface


class QueueMemberPauseView(APIView):
    @extend_schema(
        request=QueueMemberPauseSerializer,
        responses={
            200: OpenApiResponse(description="Pause state updated."),
            400: OpenApiResponse(description="Invalid request body."),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            404: OpenApiResponse(description="Interface not found in the queue(s)."),
            502: OpenApiResponse(description="AMI error or Asterisk unreachable."),
            503: OpenApiResponse(description="Asterisk is disabled in this DEVMODE."),
        },
        summary="Pause or unpause a queue member",
        tags=["queues"],
    )
    def post(self, request):
        serializer = QueueMemberPauseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        disabled = asterisk_disabled_response()
        if disabled:
            return disabled

        try:
            with AsteriskManagementInterface(timeout=settings.ASTERISK_AMI_QUICK_TIMEOUT) as ami:
                response = ami.queue_pause(
                    interface=data["interface"],
                    paused=data["paused"],
                    queue=data.get("queue") or None,
                )
        except Exception:
            return ami_unavailable_response()

        if response is None:
            return Response(
                {"detail": "AMI queue pause timed out."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if response.is_error():
            message = response.keys.get("Message", "QueuePause failed.")
            # Asterisk's only signal for "no such member" is this message text;
            # there is no distinct error code to match on instead.
            if "not found" in message.lower():
                return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": message}, status=status.HTTP_502_BAD_GATEWAY)

        action = "paused" if data["paused"] else "unpaused"
        return Response({"status": action}, status=status.HTTP_200_OK)


class QueueMemberListView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="queue",
                description="Limit results to one queue. Omit to list members of every queue.",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: QueueMemberListSerializer,
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            502: OpenApiResponse(description="AMI error or Asterisk unreachable."),
            503: OpenApiResponse(description="Asterisk is disabled in this DEVMODE."),
        },
        summary="List queue members and their current status",
        tags=["queues"],
    )
    def get(self, request):
        disabled = asterisk_disabled_response()
        if disabled:
            return disabled

        queue = request.query_params.get("queue") or None

        try:
            with AsteriskManagementInterface(timeout=settings.ASTERISK_AMI_QUICK_TIMEOUT) as ami:
                events = ami.queue_members(queue=queue)
        except Exception:
            return ami_unavailable_response()

        members = [QueueMemberStatusSerializer.from_ami_event(event) for event in events]
        serializer = QueueMemberListSerializer({"members": members})
        return Response(serializer.data, status=status.HTTP_200_OK)
