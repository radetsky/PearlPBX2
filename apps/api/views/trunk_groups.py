from django.db.models import Count, Value
from django.db.models.functions import Coalesce

from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.exceptions import Conflict
from apps.api.permissions import IsStaff
from apps.api.serializers import TrunkGroupSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import TrunkGroup


@extend_schema_view(
    create=extend_schema(
        responses={
            201: TrunkGroupSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: TrunkGroupSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a group still "
                "referenced by dialplan."
            ),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: TrunkGroupSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a group still "
                "referenced by dialplan."
            ),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Trunk group deleted."),
            409: OpenApiResponse(
                description="Trunk group is still referenced by dialplan."
            ),
        }
    ),
)
class TrunkGroupViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """Trunk groups (failover sets of SIPPeers).

    Every method requires a staff or superuser account.

    `name` is looked up by services/fastagi/fastagi.py via raw SQL from a
    literal `dial-trunk-group,<name>,` AGI call embedded in dialplan text.
    Renaming or deleting a group still referenced that way is rejected
    (400/409) rather than silently breaking call routing.
    """

    queryset = (
        TrunkGroup.objects.select_related("created_by", "modified_by")
        .prefetch_related("sip_peers")
        .annotate(sip_peers_count=Coalesce(Count("sip_peers", distinct=True), Value(0)))
        .order_by("name")
    )
    serializer_class = TrunkGroupSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name"]
    search_fields = ["name"]

    def perform_destroy(self, instance):
        refs = instance.find_dialplan_references(instance.name)
        if refs:
            raise Conflict(f"Still referenced by dialplan: {', '.join(refs)}.")
        super().perform_destroy(instance)
