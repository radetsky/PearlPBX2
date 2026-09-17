from django.conf import settings

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.permissions import IsStaff
from apps.api.serializers import PhoneDeviceSerializer
from apps.api.views.lists import AuditMixin, FilteredQuerySetMixin
from apps.provision.models import PhoneDevice
from apps.provision.provisioning_manager import PhoneProvisioningManager


@extend_schema_view(
    create=extend_schema(
        responses={
            201: PhoneDeviceSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: PhoneDeviceSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: PhoneDeviceSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
)
class PhoneDeviceViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """A provisioned phone device. Every method requires a staff or
    superuser account.

    Saving here only updates the database. A device's TFTP config file is
    only (re)written by the `provision` action below, or by the admin's
    "Apply configurations" action — neither runs implicitly on save.
    """

    queryset = PhoneDevice.objects.select_related(
        "sip_user", "created_by", "modified_by"
    ).order_by("-created_at")
    serializer_class = PhoneDeviceSerializer
    permission_classes = [IsStaff]
    filter_fields = ["mac_address", "sip_user", "telephone_type"]
    search_fields = ["mac_address", "sip_user__username", "sip_user__name"]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="Config file generated."),
            400: OpenApiResponse(description="Provisioning failed (see 'error')."),
        },
        summary="Generate this device's TFTP config file",
    )
    @action(detail=True, methods=["post"])
    def provision(self, request, pk=None):
        device = self.get_object()
        manager = PhoneProvisioningManager(settings.TFTP_DIR)
        result = manager.provision_device(device)
        if not result["success"]:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
