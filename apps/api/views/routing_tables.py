from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Value
from django.db.models.functions import Coalesce

from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.exceptions import Conflict
from apps.api.permissions import IsStaff
from apps.api.serializers import RoutingTableSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import RoutingTable


@extend_schema_view(
    create=extend_schema(
        responses={
            201: RoutingTableSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: RoutingTableSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: RoutingTableSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Routing table deleted."),
            409: OpenApiResponse(
                description="Routing table is still used by a SIP user, peer, "
                "routing record, callback service or webhook."
            ),
        }
    ),
)
class RoutingTableViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """Routing tables.

    Every method requires a staff or superuser account.

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. `name` doubles as an AEL
    dialplan context name, so it must not collide with a `DialplanContext`
    name. Deleting a table still in use returns 409 instead of a raw 500 or
    a webhook silently losing its routing-table filter.
    """

    queryset = (
        RoutingTable.objects.select_related("created_by", "modified_by")
        .annotate(
            routing_records_count=Coalesce(
                Count("routing_records", distinct=True), Value(0)
            )
        )
        .order_by("name")
    )
    serializer_class = RoutingTableSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name"]
    search_fields = ["name"]

    def perform_destroy(self, instance):
        # RoutingTable.delete() itself already checks webhooks.exists() (so
        # admin/shell deletes are covered too) — catch its ValidationError
        # here instead of re-checking, to scan once and to report 409
        # instead of the generic 400 apps.api.exceptions falls back to.
        try:
            super().perform_destroy(instance)
        except DjangoValidationError as e:
            raise Conflict("; ".join(e.messages))
