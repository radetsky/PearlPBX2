from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.permissions import IsStaff
from apps.api.serializers import SIPUserSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from core.models import SIPUser


@extend_schema_view(
    create=extend_schema(
        responses={
            201: SIPUserSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: SIPUserSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: SIPUserSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
)
class SIPUserViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """SIP extensions (accounts).

    Every method requires a staff or superuser account — this resource exposes
    dial-out credentials (plaintext `secret`, and `realm`/`md5_cred` for
    WebRTC/MD5 authentication).

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. Deleting a SIP user cascades
    to any `PhoneDevice` provisioned for it.
    """

    queryset = SIPUser.objects.select_related(
        "transport", "routing_table", "created_by", "modified_by"
    ).order_by("username")
    serializer_class = SIPUserSerializer
    permission_classes = [IsStaff]
    filter_fields = ["username", "extension"]
    search_fields = ["name", "username", "extension"]
