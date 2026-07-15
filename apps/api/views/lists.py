from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from apps.api.models import CustomListNames, CustomListEntries
from apps.api.serializers import (
    CustomListNameSerializer,
    CustomListEntrySerializer,
    BlacklistSerializer,
    WhitelistSerializer,
    ContactSerializer,
)
from core.models import Blacklist, Whitelist, Contact


class AuditMixin:
    """Set created_by / modified_by from the authenticated user."""

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, modified_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(modified_by=user)


class UpsertCreateMixin:
    """POST performs update_or_create; 201 on create, 200 on update.

    Subclass sets `upsert_lookup_fields` (used as the lookup) — the rest of the
    validated data becomes `defaults`.
    """

    upsert_lookup_fields: list[str] = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lookup = {f: data.pop(f) for f in self.upsert_lookup_fields}
        user = request.user if request.user.is_authenticated else None
        obj, created = self.get_queryset().model.objects.update_or_create(
            **lookup,
            defaults={**data, "modified_by": user},
        )
        if created:
            obj.created_by = user
            obj.save(update_fields=["created_by"])
        out = self.get_serializer(obj)
        return Response(
            out.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


def _list_schema(serializer):
    """OpenAPI responses for upsert-style list viewsets (create + update paths)."""
    conflict = OpenApiResponse(description="Uniqueness constraint would be violated.")
    invalid = OpenApiResponse(description="Invalid request body.")
    return extend_schema_view(
        create=extend_schema(
            responses={200: serializer, 201: serializer, 400: invalid, 409: conflict}
        ),
        update=extend_schema(responses={200: serializer, 400: invalid, 409: conflict}),
        partial_update=extend_schema(
            responses={200: serializer, 400: invalid, 409: conflict}
        ),
    )


@_list_schema(BlacklistSerializer)
class BlacklistViewSet(UpsertCreateMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Blacklist.objects.all().order_by("callerid")
    serializer_class = BlacklistSerializer
    upsert_lookup_fields = ["callerid", "destination"]


@_list_schema(WhitelistSerializer)
class WhitelistViewSet(UpsertCreateMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Whitelist.objects.all().order_by("callerid")
    serializer_class = WhitelistSerializer
    upsert_lookup_fields = ["callerid", "destination"]


@_list_schema(ContactSerializer)
class ContactViewSet(UpsertCreateMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Contact.objects.all().order_by("callerid")
    serializer_class = ContactSerializer
    upsert_lookup_fields = ["callerid"]


@extend_schema_view(
    update=extend_schema(
        responses={
            200: CustomListNameSerializer,
            400: OpenApiResponse(description='Empty or missing "name".'),
        }
    ),
    partial_update=extend_schema(
        responses={
            200: CustomListNameSerializer,
            400: OpenApiResponse(description='Empty or missing "name".'),
        }
    ),
)
class CustomListViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = CustomListNames.objects.all().order_by("name")
    serializer_class = CustomListNameSerializer

    def update(self, request, *args, **kwargs):
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"error": 'Missing "name"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    @extend_schema(
        methods=["GET"],
        responses=CustomListEntrySerializer(many=True),
    )
    @extend_schema(
        methods=["POST"],
        request=CustomListEntrySerializer,
        responses={201: CustomListEntrySerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def entries(self, request, pk=None):
        parent = self.get_object()
        if request.method == "GET":
            qs = parent.entries.all().order_by("callerid")
            page = self.paginate_queryset(qs)
            serializer = CustomListEntrySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = CustomListEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        serializer.save(list_name=parent, created_by=user, modified_by=user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CustomListEntryDetailView(APIView):
    """Delete a single entry scoped to its parent list."""

    @extend_schema(responses={204: OpenApiResponse(description="Entry deleted")})
    def delete(self, request, pk, entry_pk):
        entry = get_object_or_404(CustomListEntries, pk=entry_pk, list_name__id=pk)
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
