from django.db import IntegrityError

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "Resource already exists or violates a uniqueness constraint."},
            status=status.HTTP_409_CONFLICT,
        )
    return None
