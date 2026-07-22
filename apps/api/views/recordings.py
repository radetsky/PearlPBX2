import mimetypes
import os

from django.http import Http404

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.reports.services.recordings import find_recording_path_by_uniqueid
from apps.reports.views import _serve_audio_file_response


class RecordingByUniqueidView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(description="The recording audio file (wav or mp3). Supports Range requests."),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            404: OpenApiResponse(description="No recording exists for this uniqueid."),
        },
        summary="Fetch a call recording by Asterisk uniqueid",
        description=(
            "Returns the recorded call audio for the given Asterisk uniqueid. "
            "The URL is deterministic and is delivered to CRM systems in webhook "
            "payloads as recording_url."
        ),
        tags=["recordings"],
    )
    def get(self, request, uniqueid):
        file_path = find_recording_path_by_uniqueid(uniqueid)
        if not file_path:
            raise Http404("No recording exists for this uniqueid")

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "audio/mpeg" if file_path.endswith(".mp3") else "audio/wav"

        filename = os.path.basename(file_path)
        return _serve_audio_file_response(request, file_path, content_type, filename)
