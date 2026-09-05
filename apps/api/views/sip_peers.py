from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.exceptions import Conflict
from apps.api.permissions import IsStaff
from apps.api.serializers import SIPPeerSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import SIPPeer


@extend_schema_view(
    create=extend_schema(
        responses={
            201: SIPPeerSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: SIPPeerSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: SIPPeerSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Peer deleted."),
            409: OpenApiResponse(description="Peer is still a member of a trunk group."),
        }
    ),
)
class SIPPeerViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """SIP trunks/uplinks.

    Every method requires a staff or superuser account — this resource exposes
    dial-out credentials (plaintext `secret` and the derived `md5_cred`).

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. Deleting a peer that still
    belongs to a `TrunkGroup` returns 409 rather than silently shrinking the
    group.
    """

    queryset = (
        SIPPeer.objects.select_related("transport", "routing_table", "created_by", "modified_by")
        .prefetch_related("trunk_groups")
        .order_by("name")
    )
    serializer_class = SIPPeerSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name", "routing_table"]
    search_fields = ["name", "description", "username"]

    def perform_destroy(self, instance):
        # .all() (not .values_list()) reuses the trunk_groups prefetch_related()
        # cache from the viewset's queryset instead of issuing a second query.
        groups = [group.name for group in instance.trunk_groups.all()]
        if groups:
            raise Conflict(
                f"Still a member of trunk group(s): {', '.join(sorted(groups))}."
            )
        super().perform_destroy(instance)
