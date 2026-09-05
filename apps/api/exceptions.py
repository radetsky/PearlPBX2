from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(APIException):
    """A 409 for cases the caller can resolve (e.g. delete a still-referenced row)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflict."
    default_code = "conflict"


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProtectedError):
        names = sorted({str(obj) for obj in exc.protected_objects})
        return Response(
            {"detail": f"Still referenced by: {', '.join(names)}."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "Resource already exists or violates a uniqueness constraint."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, DjangoValidationError):
        # Safety net for model-level validation that raises Django's
        # ValidationError from clean()/save()/delete() instead of DRF's —
        # e.g. RoutingTable.save() / TrunkGroup.clean()/delete() — so a gap
        # in a serializer's own pre-check surfaces as 400, not 500.
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": list(exc.messages)}
        return Response(detail, status=status.HTTP_400_BAD_REQUEST)
    return None
