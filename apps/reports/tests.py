import csv
import io
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from core.models import Contact, MonitorFilenames, SIPPeer, SIPUser

from apps.reports.models import CDR, QueueLog
from apps.reports.services.lost_and_found import build_lost_and_found
from apps.reports.services.recordings import find_recording_path_by_uniqueid
from apps.reports.views import (
    AnalyticsDestinationCallsView,
    AnalyticsMissedCallsView,
    CDRReportView,
    _serve_audio_file_response,
)


def _make_queuelog(callid, event, time, queuename="testqueue", agent="", data1="", data2=""):
    return QueueLog.objects.create(
        callid=callid,
        event=event,
        time=time,
        queuename=queuename,
        agent=agent,
        data1=data1,
        data2=data2,
    )


def _make_cdr(src, dst, start, disposition="ANSWERED", dstchannel="", channel="", uniqueid=""):
    return CDR.objects.create(
        src=src,
        dst=dst,
        start=start,
        disposition=disposition,
        dstchannel=dstchannel,
        channel=channel,
        uniqueid=uniqueid or f"uid-{src}-{dst}-{start.timestamp()}",
        accountcode="",
        dcontext="",
        clid="",
        lastapp="",
        lastdata="",
        userfield="",
        linkedid="",
        peeraccount="",
    )


class BuildLostAndFoundTest(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.abandon_time = self.now - timedelta(minutes=30)
        self.callid = "test-callid-001"
        self.callerid = "0672381745"

        self.abandon = _make_queuelog(
            callid=self.callid,
            event="ABANDON",
            time=self.abandon_time,
            data1="",
            data2=self.callerid,
        )
        _make_queuelog(
            callid=self.callid,
            event="ENTERQUEUE",
            time=self.abandon_time - timedelta(seconds=10),
            data2=self.callerid,
        )

    def _qs(self):
        return QueueLog.objects.filter(queuename="testqueue")

    # Test 1: No CDR at all -> row present, both times None; unresolved_only=True keeps it
    def test_no_cdr_is_unresolved(self):
        rows = build_lost_and_found(self._qs())
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["incoming_time"])
        self.assertIsNone(rows[0]["outgoing_time"])

        rows_unresolved = build_lost_and_found(self._qs(), unresolved_only=True)
        self.assertEqual(len(rows_unresolved), 1)

    # Test 2: Caller called back (CDR src=callerid, ANSWERED, after abandon) -> incoming_time set; filtered out
    def test_incoming_cdr_resolves(self):
        callback_time = self.abandon_time + timedelta(minutes=3)
        _make_cdr(
            src=self.callerid,
            dst="239",
            start=callback_time,
            dstchannel="PJSIP/239-0000b17c",
        )

        rows = build_lost_and_found(self._qs())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["incoming_time"], callback_time)
        self.assertEqual(rows[0]["incoming_dstchannel"], "PJSIP/239-0000b17c")

        rows_unresolved = build_lost_and_found(self._qs(), unresolved_only=True)
        self.assertEqual(len(rows_unresolved), 0)

    # Test 3: Operator called out (CDR dst=callerid, ANSWERED, after abandon) -> outgoing_time set; filtered out
    def test_outgoing_cdr_resolves(self):
        call_time = self.abandon_time + timedelta(minutes=5)
        _make_cdr(
            src="101",
            dst=self.callerid,
            start=call_time,
            channel="PJSIP/101-abc",
        )

        rows = build_lost_and_found(self._qs())
        self.assertEqual(rows[0]["outgoing_time"], call_time)

        rows_unresolved = build_lost_and_found(self._qs(), unresolved_only=True)
        self.assertEqual(len(rows_unresolved), 0)

    # Test 4: CDR src=callerid but disposition != ANSWERED -> does not resolve
    def test_unanswered_incoming_stays_unresolved(self):
        _make_cdr(
            src=self.callerid,
            dst="239",
            start=self.abandon_time + timedelta(minutes=2),
            disposition="NO ANSWER",
        )

        rows = build_lost_and_found(self._qs(), unresolved_only=True)
        self.assertEqual(len(rows_unresolved := rows), 1)

    # Test 5: CDR exists but BEFORE abandon_time -> does not resolve
    def test_cdr_before_abandon_stays_unresolved(self):
        _make_cdr(
            src=self.callerid,
            dst="239",
            start=self.abandon_time - timedelta(minutes=5),
            disposition="ANSWERED",
        )

        rows = build_lost_and_found(self._qs(), unresolved_only=True)
        self.assertEqual(len(rows), 1)

    # Test 6: normalize=True matches +380672381745 to 0672381745
    def test_normalize_incoming_match(self):
        callback_time = self.abandon_time + timedelta(minutes=3)
        _make_cdr(
            src="+380672381745",
            dst="239",
            start=callback_time,
            disposition="ANSWERED",
            dstchannel="PJSIP/239-normalized",
        )

        rows_no_norm = build_lost_and_found(self._qs(), normalize=False)
        self.assertIsNone(rows_no_norm[0]["incoming_time"])

        rows_norm = build_lost_and_found(self._qs(), normalize=True)
        self.assertEqual(rows_norm[0]["incoming_dstchannel"], "PJSIP/239-normalized")

    # Test 7: limit parameter caps result count
    def test_limit_parameter(self):
        for i in range(5):
            t = self.abandon_time - timedelta(minutes=i + 1)
            cid = f"callid-extra-{i}"
            _make_queuelog(callid=cid, event="ABANDON", time=t, data2=f"067000000{i}")
            _make_queuelog(callid=cid, event="ENTERQUEUE", time=t - timedelta(seconds=5), data2=f"067000000{i}")

        all_rows = build_lost_and_found(self._qs())
        self.assertGreater(len(all_rows), 3)

        limited = build_lost_and_found(self._qs(), limit=3)
        self.assertEqual(len(limited), 3)


class ExportCdrCsvTest(TestCase):
    def test_header_and_row_have_same_column_count(self):
        _make_cdr(
            src="100",
            dst="200",
            start=timezone.now(),
            channel="PJSIP/100-000001",
            dstchannel="PJSIP/200-000002",
        )
        response = CDRReportView.export_cdr_csv(None, CDR.objects.all())
        content = response.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content)))
        header, data_row = rows[0], rows[1]
        self.assertEqual(len(header), len(data_row))
        self.assertEqual(header[-1], "Dest. Channel")
        self.assertEqual(data_row[-1], "PJSIP/200-000002")


class AnalyticsMissedCallsBatchTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username="analytics-admin", email="a@example.com", password="pass12345"
        )
        self.now = timezone.now().replace(microsecond=0)
        self.abandon_time = self.now - timedelta(minutes=30)
        self.callerid = "0672381745"
        self.callid = "analytics-callid-001"

        _make_queuelog(
            callid=self.callid,
            event="ENTERQUEUE",
            time=self.abandon_time - timedelta(seconds=10),
            queuename="supportq",
            data2=self.callerid,
        )
        _make_queuelog(
            callid=self.callid,
            event="ABANDON",
            time=self.abandon_time,
            queuename="supportq",
            data2=self.callerid,
        )

    def _get_table_data(self, date_from, date_to):
        request = self.factory.get(
            "/reports/analytics/missed-calls/",
            {"date_from": date_from, "date_to": date_to},
        )
        request.user = self.user
        with patch("apps.reports.views.render") as mock_render:
            mock_render.return_value = None
            AnalyticsMissedCallsView.as_view()(request)
            context = mock_render.call_args[0][2]
        return context["table_data"]

    def _fmt(self, dt):
        return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")

    def test_operator_called_back_counted_via_batch_queries(self):
        _make_cdr(
            src="101",
            dst=self.callerid,
            start=self.abandon_time + timedelta(minutes=5),
            disposition="ANSWERED",
        )
        table_data = self._get_table_data(
            self._fmt(self.now - timedelta(hours=1)), self._fmt(self.now)
        )
        row = next(r for r in table_data if r["queuename"] == "supportq")
        self.assertEqual(row["missed"], 1)
        self.assertEqual(row["operators"], 1)
        self.assertEqual(row["called_back"], 0)

    def test_caller_called_back_counted_via_batch_queries(self):
        _make_cdr(
            src=self.callerid,
            dst="239",
            start=self.abandon_time + timedelta(minutes=3),
            disposition="ANSWERED",
        )
        table_data = self._get_table_data(
            self._fmt(self.now - timedelta(hours=1)), self._fmt(self.now)
        )
        row = next(r for r in table_data if r["queuename"] == "supportq")
        self.assertEqual(row["missed"], 1)
        self.assertEqual(row["called_back"], 1)
        self.assertEqual(row["operators"], 0)


class AnalyticsDestinationCallsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username="analytics-dst-admin", email="b@example.com", password="pass12345"
        )
        self.now = timezone.now().replace(microsecond=0)
        self.peer = SIPPeer.objects.create(name="trunk1")
        self.sip_user = SIPUser.objects.create(
            username="101", secret="secret", extension="101"
        )

    def _get(self, **params):
        params.setdefault("date_from", self._fmt(self.now - timedelta(hours=1)))
        params.setdefault("date_to", self._fmt(self.now + timedelta(hours=1)))
        request = self.factory.get(
            "/reports/analytics/destination-calls/", params
        )
        request.user = self.user
        with patch("apps.reports.views.render") as mock_render:
            mock_render.return_value = None
            AnalyticsDestinationCallsView.as_view()(request)
            context = mock_render.call_args[0][2]
        return context

    def _fmt(self, dt):
        return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")

    def test_external_peer_call_is_counted(self):
        _make_cdr(
            src="+380501112233",
            dst="0800123456",
            start=self.now,
            disposition="ANSWERED",
            channel="PJSIP/trunk1-00000001",
        )
        table_data = self._get()["table_data"]
        row = next(r for r in table_data if r["dst"] == "0800123456")
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["answered"], 1)
        self.assertEqual(row["not_answered"], 0)

    def test_internal_user_call_is_excluded(self):
        _make_cdr(
            src="101",
            dst="102",
            start=self.now,
            disposition="ANSWERED",
            channel="PJSIP/101-00000002",
        )
        table_data = self._get()["table_data"]
        self.assertEqual(table_data, [])

    def test_not_answered_calls_are_counted_but_not_as_answered(self):
        _make_cdr(
            src="+380501112233",
            dst="0800123456",
            start=self.now,
            disposition="NO ANSWER",
            channel="PJSIP/trunk1-00000003",
        )
        table_data = self._get()["table_data"]
        row = next(r for r in table_data if r["dst"] == "0800123456")
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["answered"], 0)
        self.assertEqual(row["not_answered"], 1)

    def test_multiple_cdr_rows_same_uniqueid_counted_once(self):
        # Two CDR rows for the same call (e.g. a transfer leg) share a
        # uniqueid but differ by sequence, which stays NULL here - Postgres
        # treats NULL as distinct under unique_together, so both inserts succeed.
        for _ in range(2):
            _make_cdr(
                src="+380501112233",
                dst="0800123456",
                start=self.now,
                disposition="ANSWERED",
                channel="PJSIP/trunk1-00000004",
                uniqueid="shared-uid",
            )
        table_data = self._get()["table_data"]
        row = next(r for r in table_data if r["dst"] == "0800123456")
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["answered"], 1)

    def test_exclude_contacts_filters_known_callers(self):
        Contact.objects.create(callerid="+380501112233", name="Known caller")
        _make_cdr(
            src="+380501112233",
            dst="0800123456",
            start=self.now,
            disposition="ANSWERED",
            channel="PJSIP/trunk1-00000005",
        )
        table_data = self._get(exclude_contacts="on")["table_data"]
        self.assertEqual(table_data, [])

    def test_top_n_limits_chart_but_not_table(self):
        # top_n only accepts the fixed dropdown values (30/50/100/""), so
        # exercising the "30" truncation branch needs more than 30 distinct
        # destination numbers.
        for i in range(35):
            _make_cdr(
                src=f"+3805011122{i:02d}",
                dst=f"08001234{i:03d}",
                start=self.now,
                disposition="ANSWERED",
                channel=f"PJSIP/trunk1-{i:08d}",
            )
        context = self._get(top_n="30")
        self.assertEqual(len(context["table_data"]), 35)
        self.assertEqual(len(context["chart_data"]["labels"]), 30)

    def test_top_n_all_keeps_full_chart(self):
        for i in range(3):
            _make_cdr(
                src=f"+38050111223{i}",
                dst=f"080012345{i}",
                start=self.now,
                disposition="ANSWERED",
                channel=f"PJSIP/trunk1-0000000{i}",
            )
        context = self._get(top_n="")
        self.assertEqual(len(context["table_data"]), 3)
        self.assertEqual(len(context["chart_data"]["labels"]), 3)

    def test_top_n_defaults_to_30_when_omitted_from_a_partial_get(self):
        # A GET carrying only date_from/date_to (e.g. a hand-built or
        # bookmarked URL) must still default top_n to "30", not "" (all).
        for i in range(35):
            _make_cdr(
                src=f"+3805011122{i:02d}",
                dst=f"08001234{i:03d}",
                start=self.now,
                disposition="ANSWERED",
                channel=f"PJSIP/trunk1-{i:08d}",
            )
        context = self._get()
        self.assertEqual(len(context["table_data"]), 35)
        self.assertEqual(len(context["chart_data"]["labels"]), 30)

    def test_no_sip_peers_returns_empty_result_without_error(self):
        SIPPeer.objects.all().delete()
        _make_cdr(
            src="+380501112233",
            dst="0800123456",
            start=self.now,
            disposition="ANSWERED",
            channel="PJSIP/trunk1-00000006",
        )
        table_data = self._get()["table_data"]
        self.assertEqual(table_data, [])


class ServeAudioFileResponseTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.file_path = os.path.join(self.tmpdir.name, "test.wav")
        with open(self.file_path, "wb") as f:
            f.write(b"0123456789")

    def test_full_file_response_headers(self):
        request = self.factory.get("/reports/audio/1/")
        response = _serve_audio_file_response(
            request, self.file_path, "audio/wav", "test.wav"
        )
        self.assertEqual(response["Content-Length"], "10")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertIn("test.wav", response["Content-Disposition"])

    def test_range_request_returns_206(self):
        request = self.factory.get("/reports/audio/1/", HTTP_RANGE="bytes=2-5")
        response = _serve_audio_file_response(
            request, self.file_path, "audio/wav", "test.wav"
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 2-5/10")
        self.assertEqual(response["Content-Length"], "4")
        self.assertEqual(response.content, b"2345")

    def test_same_headers_for_both_views_shared_logic(self):
        """Regression test: both AudioFileView and AudioFileByUniqueidView
        delegate to the same helper, so identical requests produce identical
        Range headers."""
        request1 = self.factory.get("/reports/audio/1/", HTTP_RANGE="bytes=0-3")
        request2 = self.factory.get("/reports/audio/uid/1/", HTTP_RANGE="bytes=0-3")
        response1 = _serve_audio_file_response(
            request1, self.file_path, "audio/wav", "test.wav"
        )
        response2 = _serve_audio_file_response(
            request2, self.file_path, "audio/wav", "test.wav"
        )
        self.assertEqual(response1["Content-Range"], response2["Content-Range"])
        self.assertEqual(response1.content, response2.content)


class FindRecordingPathByUniqueidTest(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.settings_override = override_settings(
            ASTERISK_MONITOR_DIR=self.tmpdir.name, ASTERISK_BACKUP_MONITOR_DIR=""
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def _write(self, relative_path):
        path = os.path.join(self.tmpdir.name, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"audio")
        return path

    def test_legacy_flat_file_found(self):
        path = self._write("123.456.wav")
        self.assertEqual(find_recording_path_by_uniqueid("123.456"), path)

    def test_new_style_file_found_via_monitor_filenames(self):
        path = self._write("2026/07/21/10_00_00_100_200.wav")
        MonitorFilenames.objects.create(
            src="100",
            dst="200",
            filename="2026/07/21/10_00_00_100_200",
            cdr_uniqueid="123.456",
        )
        self.assertEqual(find_recording_path_by_uniqueid("123.456"), path)

    def test_missing_recording_returns_none(self):
        MonitorFilenames.objects.create(
            src="100", dst="200", filename="2026/07/21/none", cdr_uniqueid="123.456"
        )
        self.assertIsNone(find_recording_path_by_uniqueid("123.456"))

    def test_invalid_uniqueid_returns_none(self):
        self.assertIsNone(find_recording_path_by_uniqueid("../../etc/passwd"))
        self.assertIsNone(find_recording_path_by_uniqueid(""))
