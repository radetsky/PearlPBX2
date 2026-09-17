from django.db.models import Count, Value
from django.db.models.functions import Coalesce

from rest_framework import viewsets
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiResponse

from apps.api.permissions import IsStaff
from apps.api.serializers import (
    DialplanContextSerializer,
    DialplanExtensionSerializer,
    DialplanMacroSerializer,
)
from apps.api.views.lists import AuditMixin, DialplanGuardedDestroyMixin, FilteredQuerySetMixin
from core.models import DialplanContext, DialplanExtension, DialplanMacro


@extend_schema_view(
    create=extend_schema(
        responses={
            201: DialplanContextSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: DialplanContextSerializer,
            400: OpenApiResponse(
                description="Invalid request body, name collides with a "
                "RoutingTable, or renaming the auto-generated context."
            ),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: DialplanContextSerializer,
            400: OpenApiResponse(
                description="Invalid request body, name collides with a "
                "RoutingTable, or renaming the auto-generated context."
            ),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Context deleted."),
            409: OpenApiResponse(
                description="Context is still referenced by a DialplanExtension "
                "or RoutingRecord (PROTECT), used by a webhook's context "
                "filter, or is the auto-generated context."
            ),
        }
    ),
)
class DialplanContextViewSet(
    FilteredQuerySetMixin, AuditMixin, DialplanGuardedDestroyMixin, viewsets.ModelViewSet
):
    """Dialplan contexts (core.conf.make_dialplan_contexts()).

    Every method requires a staff or superuser account.

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin. The auto-generated
    "PEARLPBX-Users" context (rendered live from SIPUser data by
    core.conf.make_local_users_context()) cannot be renamed or deleted here,
    and extensions cannot be created inside it — see
    DialplanExtensionViewSet.
    """

    queryset = (
        DialplanContext.objects.select_related("created_by", "modified_by")
        .annotate(extensions_count=Coalesce(Count("extensions", distinct=True), Value(0)))
        .order_by("name")
    )
    serializer_class = DialplanContextSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name"]
    search_fields = ["name", "description"]


@extend_schema_view(
    create=extend_schema(
        responses={
            201: DialplanExtensionSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: DialplanExtensionSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: DialplanExtensionSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
)
class DialplanExtensionViewSet(FilteredQuerySetMixin, AuditMixin, viewsets.ModelViewSet):
    """Dialplan extensions within a DialplanContext
    (core.conf.make_dialplan_contexts()).

    Every method requires a staff or superuser account.

    `dialplan` must reference only macros that already exist —
    core.validators.validate_dialplan_field resolves the allowed macro set
    from the database at request time, so create a DialplanMacro before an
    extension that calls it with `&name();`.
    """

    queryset = DialplanExtension.objects.select_related(
        "context", "created_by", "modified_by"
    ).order_by("context__name", "ext")
    serializer_class = DialplanExtensionSerializer
    permission_classes = [IsStaff]
    filter_fields = ["context", "ext"]
    search_fields = ["ext", "description", "dialplan", "context__name"]


@extend_schema_view(
    create=extend_schema(
        responses={
            201: DialplanMacroSerializer,
            400: OpenApiResponse(description="Invalid request body."),
        }
    ),
    update=extend_schema(
        responses={
            200: DialplanMacroSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a macro still "
                "referenced by dialplan."
            ),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: DialplanMacroSerializer,
            400: OpenApiResponse(
                description="Invalid request body, or renaming a macro still "
                "referenced by dialplan."
            ),
        }
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(description="Macro deleted."),
            409: OpenApiResponse(description="Macro is still referenced by dialplan."),
        }
    ),
)
class DialplanMacroViewSet(
    FilteredQuerySetMixin, AuditMixin, DialplanGuardedDestroyMixin, viewsets.ModelViewSet
):
    """Dialplan macros (core.conf.make_dialplan_macros()).

    Every method requires a staff or superuser account.

    `name` is looked up by AEL as a literal `&name();` call embedded in
    extension bodies (and in Settings.local_users_dial_template). Renaming
    or deleting a macro still called that way is rejected (400/409) rather
    than silently breaking the generated dialplan.
    """

    queryset = DialplanMacro.objects.select_related("created_by", "modified_by").order_by("name")
    serializer_class = DialplanMacroSerializer
    permission_classes = [IsStaff]
    filter_fields = ["name"]
    search_fields = ["name", "description", "macro"]
