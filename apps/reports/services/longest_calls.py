"""
Build the "longest calls" report: the top calls of a day (or a multi-day
window), ranked by duration, with a link to the call recording when one exists.

Used by:
- apps.reports.management.commands.mail_report (daily email)
"""

import datetime
import os

from django.conf import settings
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from apps.reports.models import CDR
from apps.reports.services.channels import peer_channel_regex
from core.models import MonitorFilenames


def day_bounds(report_date, days=1):
    """Return the aware [start, end) datetime range covering `days` days ending on report_date.

    Both ends are anchored to a calendar-date midnight rather than derived by
    adding a fixed number of hours, so the range stays correct across a
    Europe/Kyiv DST transition (which never falls on midnight).
    """
    tz = timezone.get_current_timezone()
    first_day = report_date - datetime.timedelta(days=days - 1)
    start = timezone.make_aware(datetime.datetime.combine(first_day, datetime.time.min), tz)
    end = timezone.make_aware(
        datetime.datetime.combine(report_date + datetime.timedelta(days=1), datetime.time.min),
        tz,
    )
    return start, end


def _absolute_url(path):
    return settings.PEARLPBX_PUBLIC_URL.rstrip("/") + path


def recording_urls(uniqueids):
    """Map CDR uniqueid -> absolute recording URL, for calls with a file on disk.

    A single bulk query regardless of how many uniqueids are passed, to avoid
    the N+1 filesystem/DB lookups that CDR.get_audio_url() does per row.
    """
    uniqueids = list(uniqueids)
    if not uniqueids:
        return {}

    urls = {}
    remaining = []
    for uid in uniqueids:
        if any(
            os.path.exists(os.path.join(settings.ASTERISK_MONITOR_DIR, uid + ext))
            for ext in (".mp3", ".wav")
        ):
            urls[uid] = _absolute_url(reverse("audio_file_by_uniqueid", kwargs={"uniqueid": uid}))
        else:
            remaining.append(uid)

    if remaining:
        # cdr_uniqueid is unique, so at most one row per id - no ordering needed.
        for mf in MonitorFilenames.objects.filter(cdr_uniqueid__in=remaining):
            if mf.cdr_uniqueid not in urls and mf.audio_file_exists():
                urls[mf.cdr_uniqueid] = _absolute_url(
                    reverse("audio_file_by_uniqueid", kwargs={"uniqueid": mf.cdr_uniqueid})
                )

    return urls


def external_filter_available():
    """Whether --external-only can be applied (i.e. at least one SIPPeer trunk exists)."""
    return peer_channel_regex() is not None


def build_longest_calls(report_date, *, days=1, limit=10, answered_only=True, external_only=False):
    """Return the top `limit` longest calls ending on report_date, longest first.

    Each Asterisk call can produce more than one CDR row sharing the same
    uniqueid (transfers, ForkCDR, ...), so rows are grouped by uniqueid and
    only the longest leg of each call is kept - otherwise a single long call
    could occupy several slots in the table.

    If external_only is requested but no SIPPeer trunk is configured, the
    filter is silently skipped (nothing to match against) rather than
    producing an empty report; use external_filter_available() to warn a
    caller about this beforehand.

    Returns a list of dicts: start, src, dst, channel, dstchannel, duration,
    disposition, uniqueid, recording_url (absolute URL or None).
    """
    start, end = day_bounds(report_date, days=days)

    qs = CDR.objects.filter(start__gte=start, start__lt=end)
    if answered_only:
        qs = qs.filter(disposition="ANSWERED")

    if external_only:
        pattern = peer_channel_regex()
        if pattern is not None:
            qs = qs.filter(Q(channel__regex=pattern) | Q(dstchannel__regex=pattern))

    top = (
        qs.values("uniqueid")
        .annotate(max_duration=Max("duration"))
        .order_by("-max_duration", "uniqueid")[:limit]
    )
    uniqueids = [row["uniqueid"] for row in top]
    if not uniqueids:
        return []

    # Pick the single longest leg per uniqueid, preserving the ranked order above.
    longest_leg = {}
    for cdr in qs.filter(uniqueid__in=uniqueids).order_by("-duration"):
        longest_leg.setdefault(cdr.uniqueid, cdr)

    urls = recording_urls(uniqueids)

    rows = []
    for uid in uniqueids:
        cdr = longest_leg.get(uid)
        if cdr is None:
            continue
        rows.append(
            {
                "start": cdr.start,
                "src": cdr.src,
                "dst": cdr.dst,
                "channel": cdr.channel,
                "dstchannel": cdr.dstchannel,
                "duration": cdr.duration or 0,
                "disposition": cdr.disposition,
                "uniqueid": cdr.uniqueid,
                "recording_url": urls.get(uid),
            }
        )
    return rows
