from django.db.models import Count, Value
from django.db.models.functions import Coalesce

from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.permissions import IsStaff
from apps.api.serializers import SIPTransportSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import SIPTransport


@extend_schema_view(
    create=extend_schema(
        responses={
            201: SIPTransportSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: SIPTransportSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: SIPTransportSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Transport deleted."),
            409: OpenApiResponse(
                description="Transport is still used by a SIP user or peer."
            ),
        }
    ),
)
class SIPTransportViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """PJSIP transports.

    Every method requires a staff or superuser account — `cert_file` and
    `priv_key_file` carry TLS certificate/private key material in plaintext.

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. Deleting a transport still in
    use by a `SIPUser` or `SIPPeer` returns 409 instead of failing at the
    database level.
    """

    queryset = (
        SIPTransport.objects.select_related("created_by", "modified_by")
        .annotate(
            sip_users_count=Coalesce(
                Count("sip_user_transport", distinct=True), Value(0)
            ),
            sip_peers_count=Coalesce(
                Count("sip_peer_transport", distinct=True), Value(0)
            ),
        )
        .order_by("name")
    )
    serializer_class = SIPTransportSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name", "protocol"]
    search_fields = ["name", "description"]
