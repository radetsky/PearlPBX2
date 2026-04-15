"""
Shared logic for Lost and Found: given a QueueLog queryset of ABANDON events,
returns per-row resolution status from CDR (incoming callback or outgoing operator call).

Used by:
- apps.reports.views.QueueReportView.get_lost_and_found_data (full report)
- apps.dashboard.views.get_missed_calls (unresolved_only=True, normalize=True)
"""

from django.db.models import Q

from core.utils import normalize_phone
from apps.reports.models import CDR, QueueLog


def build_lost_and_found(
    queueset,
    *,
    unresolved_only: bool = False,
    limit: int | None = None,
    normalize: bool = False,
) -> list[dict]:
    """
    For each ABANDON event in *queueset* find whether the caller was reached afterwards.

    Args:
        queueset:        QueueLog queryset pre-filtered by time/queue.
        unresolved_only: When True, drop rows where any callback was found.
        limit:           Cap on ABANDON rows to process (e.g. 50 for the report).
        normalize:       When True, compare phones via normalize_phone so that
                         "0672381745" matches "+380672381745" in CDR.
    Returns:
        List of dicts: abandon_time, callerid, callid, queuename,
                       incoming_time, incoming_dstchannel,
                       outgoing_time, outgoing_channel
    """
    def _norm(v: str) -> str:
        return normalize_phone(v) if normalize else v

    lost_qs = queueset.filter(event="ABANDON").order_by("-time").values(
        "callid", "time", "queuename", "agent", "data1"
    )
    if limit:
        lost_qs = lost_qs[:limit]
    lost_calls = list(lost_qs)

    if not lost_calls:
        return []

    callids = [r["callid"] for r in lost_calls]

    # CDR.uniqueid == QueueLog.callid in Asterisk — preferred source for raw callerid.
    cdr_src_by_callid = {
        row["uniqueid"]: row["src"]
        for row in CDR.objects.filter(uniqueid__in=callids).values("uniqueid", "src")
    }

    enterqueue_callerid = {
        row["callid"]: row["data2"]
        for row in QueueLog.objects.filter(
            event="ENTERQUEUE", callid__in=callids
        ).values("callid", "data2")
    }

    # Build callerid maps: raw (for DB filtering) and normalised (for Python matching).
    raw_callerid_map: dict[str, str] = {}
    callerid_map: dict[str, str] = {}
    for row in lost_calls:
        callid = row["callid"]
        raw = (
            cdr_src_by_callid.get(callid)
            or enterqueue_callerid.get(callid)
            or row.get("agent")
            or row.get("data1")
            or callid
        )
        raw_callerid_map[callid] = raw or ""
        callerid_map[callid] = _norm(raw) if raw else ""

    min_abandon = min(r["time"] for r in lost_calls)
    cdr_qs = CDR.objects.filter(start__gt=min_abandon, disposition="ANSWERED")

    # When normalize=False, phone numbers are already in consistent format — filter in DB.
    # When normalize=True, CDR may use different prefixes (e.g. +380 vs 0), so we skip
    # the src/dst filter and rely on Python normalization to match correctly.
    if not normalize:
        raw_callerids = {v for v in raw_callerid_map.values() if v}
        cdr_qs = cdr_qs.filter(Q(src__in=raw_callerids) | Q(dst__in=raw_callerids))

    cdrs = list(cdr_qs.values("src", "dst", "start", "dstchannel", "channel"))

    # Index by normalised number; lists are kept sorted ascending by start time.
    incoming_by_src: dict[str, list] = {}
    outgoing_by_dst: dict[str, list] = {}
    for cdr in cdrs:
        incoming_by_src.setdefault(_norm(cdr["src"]), []).append((cdr["start"], cdr["dstchannel"]))
        outgoing_by_dst.setdefault(_norm(cdr["dst"]), []).append((cdr["start"], cdr["channel"]))

    for lst in incoming_by_src.values():
        lst.sort(key=lambda x: x[0])
    for lst in outgoing_by_dst.values():
        lst.sort(key=lambda x: x[0])

    results = []
    for row in lost_calls:
        callid = row["callid"]
        abandon_time = row["time"]
        callerid = callerid_map.get(callid, "")

        incoming_time = None
        incoming_dstchannel = None
        outgoing_time = None
        outgoing_channel = None

        if callerid:
            for start, dstchannel in incoming_by_src.get(callerid, []):
                if start > abandon_time:
                    incoming_time = start
                    incoming_dstchannel = dstchannel
                    break

            for start, channel in outgoing_by_dst.get(callerid, []):
                if start > abandon_time:
                    outgoing_time = start
                    outgoing_channel = channel
                    break

        if unresolved_only and (incoming_time is not None or outgoing_time is not None):
            continue

        results.append({
            "abandon_time": abandon_time,
            "callerid": callerid,
            "callid": callid,
            "queuename": row.get("queuename", ""),
            "incoming_time": incoming_time,
            "incoming_dstchannel": incoming_dstchannel,
            "outgoing_time": outgoing_time,
            "outgoing_channel": outgoing_channel,
        })

    return results
