from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.permissions import IsStaff
from apps.api.serializers import RoutingRecordSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import RoutingRecord


@extend_schema_view(
    create=extend_schema(
        responses={
            201: RoutingRecordSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: RoutingRecordSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: RoutingRecordSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
)
class RoutingRecordViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """Prefix-based routing rules within a `RoutingTable`.

    Every method requires a staff or superuser account.

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. `context` and
    `routing_table` are required even though nullable in the DB — a null
    `context` would literally emit `goto None,${EXTEN},1;` into the
    generated dialplan, and a record with no `routing_table` never appears
    in any table's block.
    """

    queryset = (
        RoutingRecord.objects.select_related(
            "context", "routing_table", "created_by", "modified_by"
        )
        .order_by("routing_table__name", "prefix")
    )
    serializer_class = RoutingRecordSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name", "prefix", "routing_table", "context"]
    search_fields = ["name", "prefix"]
