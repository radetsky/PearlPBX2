from django.conf import settings
from django.db.models import Count, Value
from django.db.models.functions import Coalesce

from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
)

from apps.api.permissions import IsStaff
from apps.api.serializers import (
    QueueMemberPauseSerializer,
    QueueMemberStatusSerializer,
    QueueMemberListSerializer,
    QueueSerializer,
    QueueMemberSerializer,
)
from apps.api.views.common import asterisk_disabled_response, ami_unavailable_response
from apps.api.views.lists import AuditMixin, DialplanGuardedDestroyMixin, FilteredQuerySetMixin
from core.ami import AsteriskManagementInterface
from core.models import Queue, QueueMember

# The two views below (QueueMemberPauseView, QueueMemberListView) talk to
# Asterisk's live AMI state — pause flags, call counters, device status —
# and have no DB-backed equivalent. QueueViewSet/QueueMemberViewSet further
# down are the opposite: plain DB CRUD for the static configuration that
# ends up in queues.conf after "Apply Changes". Don't confuse the two —
# GET /api/v1/queues/members/ (AMI) and GET /api/v1/queue-members/ (DB) both
# answer "who's in this queue", from entirely different sources of truth.


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


@extend_schema_view(
    create=extend_schema(
        responses={
            201: QueueSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: QueueSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a queue still "
                "referenced by dialplan."
            ),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: QueueSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a queue still "
                "referenced by dialplan."
            ),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Queue deleted."),
            409: OpenApiResponse(description="Queue is still referenced by dialplan."),
        }
    ),
)
class QueueViewSet(
    FilteredQuerySetMixin, AuditMixin, DialplanGuardedDestroyMixin, viewsets.ModelViewSet
):
    """A call queue's static configuration (see the module docstring for how
    this differs from the AMI-backed views above).

    Every method requires a staff or superuser account.

    `name` is looked up by Asterisk's app_queue from a literal
    `Queue(<name>,...)` AEL app-call embedded in dialplan text. Renaming or
    deleting a queue still referenced that way is rejected (400/409) rather
    than silently breaking call routing.
    """

    queryset = (
        Queue.objects.select_related(
            "music_class", "queue_announcement", "defaultrule", "created_by", "modified_by"
        )
        .annotate(members_count=Coalesce(Count("members", distinct=True), Value(0)))
        .order_by("name")
    )
    serializer_class = QueueSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name", "strategy"]
    search_fields = ["name"]
    lookup_value_regex = "[0-9]+"


@extend_schema_view(
    create=extend_schema(
        responses={
            201: QueueMemberSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: QueueMemberSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: QueueMemberSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
)
class QueueMemberViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """A queue's static member list (see the module docstring for how this
    differs from the AMI-backed views above).

    Every method requires a staff or superuser account — this writes DB
    configuration, unlike the AMI views above which only require
    authentication, since it changes what reaches queues.conf, not just
    runtime pause state.
    """

    queryset = QueueMember.objects.select_related(
        "queue", "created_by", "modified_by"
    ).order_by("queue__name", "member_name")
    serializer_class = QueueMemberSerializer
    permission_classes = [IsStaff]
    filter_fields = ["queue", "interface"]
    search_fields = ["member_name", "interface", "state_interface", "queue__name"]
