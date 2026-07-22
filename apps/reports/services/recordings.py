"""Recording file resolution shared by the reports UI and the REST API."""

import os
import re

from django.conf import settings

from core.models import MonitorFilenames

UNIQUEID_RE = re.compile(r"^[\d.]+$")


def find_recording_path_by_uniqueid(uniqueid):
    """Resolve the audio file path for an Asterisk uniqueid, or None.

    Probes the legacy flat layout ({MONITOR_DIR}/{uniqueid}.ext) first, then
    falls back to the MonitorFilenames record (new YYYY/MM/DD/... layout).
    """
    if not uniqueid or not UNIQUEID_RE.match(uniqueid):
        return None

    for ext in (".mp3", ".wav"):
        candidate = os.path.join(settings.ASTERISK_MONITOR_DIR, uniqueid + ext)
        if os.path.exists(candidate):
            return candidate

    record = (
        MonitorFilenames.objects.filter(cdr_uniqueid=uniqueid)
        .order_by("-created")
        .first()
    )
    if record and record.audio_file_exists():
        return record.get_audio_file_path()
    return None
