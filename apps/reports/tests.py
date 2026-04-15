from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.reports.models import CDR, QueueLog
from apps.reports.services.lost_and_found import build_lost_and_found


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
