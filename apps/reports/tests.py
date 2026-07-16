import csv
import io
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.reports.models import CDR, QueueLog
from apps.reports.services.lost_and_found import build_lost_and_found
from apps.reports.views import (
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
