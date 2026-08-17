"""
Integration tests against a REAL Asterisk instance.

Unlike apps/api/tests.py's QueueMemberPauseApiTests / QueueMemberListApiTests
(which mock core.ami.AsteriskManagementInterface entirely), this module seeds
a real Queue + PJSIP QueueMember, applies the generated config to a live
Asterisk the same way the "Apply Changes" admin action does, and drives the
REST API against it — confirming AMI QueuePause/QueueStatus actually change
and reflect live agent state, not just that the right AMI kwargs were built.

Not part of the default test run: pytest.ini's `testpaths` does not include
this directory, and `python manage.py test` won't discover it either (it
isn't a Django app). Run explicitly via:

    make integration-test

or:

    docker compose -f docker-compose.integration.yml run --rm integration-test
"""

import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from asterisk.ami import SimpleAction
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from core.ami import AsteriskManagementInterface
from core.models import (
    MusicOnHold,
    Queue,
    QueueAnnouncements,
    QueueMember,
    RoutingTable,
    SIPTransport,
    SIPUser,
)
from pbx.admin import ApplyChangesView


def _wait_for_ami(timeout=30):
    """
    Retry AMI login until Asterisk is actually ready to accept connections.

    The `asterisk` service in docker-compose.integration.yml has no Docker
    healthcheck (same as docker-compose.yml's dev stack — the vendor image
    doesn't wire one in either), so `depends_on` only guarantees the
    container started, not that Asterisk finished booting and AMI is live.
    """
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with AsteriskManagementInterface(timeout=3):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"AMI never became ready within {timeout}s: {last_error}")


def _ensure_app_queue_loaded(ami):
    """
    Best-effort `module load app_queue.so`.

    docker/asterisk-bootstrap.sh only patches modules.conf for res_crypto.so
    (needed by the vendor image's own healthcheck.sh); app_queue.so isn't
    guaranteed to be in the vendor default autoload list. QueuePause/
    QueueStatus need it — an "already loaded" response here is harmless.
    """
    ami.client.send_action(
        SimpleAction(name="Command", Command="module load app_queue.so")
    )


class QueueMemberIntegrationTests(APITestCase):
    """
    End-to-end: DB -> queues.conf/pjsip.conf -> AMI reload -> real Asterisk
    -> REST API, for POST /queues/members/pause/ and GET /queues/members/.
    """

    QUEUE_NAME = "integration-queue"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = get_user_model().objects.create_user(
            username="integration-api", password="x"
        )
        cls.token = Token.objects.create(user=cls.user)

        cls.transport = SIPTransport.objects.create(
            name="integration-transport",
            protocol="udp",
            bind="0.0.0.0:5060",
        )
        cls.routing_table = RoutingTable.objects.get(
            name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )
        cls.sip_user = SIPUser.objects.create(
            name="Integration Agent",
            username="int1000",
            extension="1000",
            secret="integration-secret",
            transport=cls.transport,
            routing_table=cls.routing_table,
            auth_type="userpass",
        )
        cls.interface = cls.sip_user.standard_pjsip_user  # "PJSIP/int1000"

        moh = MusicOnHold.objects.create(name="integration-moh", mode="files")
        ann = QueueAnnouncements.objects.create(name="integration-ann")
        cls.queue = Queue.objects.create(
            name=cls.QUEUE_NAME,
            music_class=moh,
            queue_announcement=ann,
            strategy="ringall",
            timeout=30,
            retry=5,
        )
        QueueMember.objects.create(
            queue=cls.queue,
            interface=cls.interface,
            penalty=0,
            member_name=cls.sip_user.name,
            state_interface=cls.interface,
        )

        _wait_for_ami()
        with AsteriskManagementInterface() as ami:
            _ensure_app_queue_loaded(ami)

        # Same code path as the "Apply Changes" admin action: writes
        # queues.conf/pjsip.conf/etc. to the shared config volume, then a
        # soft reload (includes `module reload app_queue.so` and
        # `module reload res_pjsip.so`) picks them up.
        view = ApplyChangesView()
        view.apply_changes(view._build_cfgfiles())
        with AsteriskManagementInterface() as ami:
            ami.soft_reload()

        cls._wait_for_member_visible()

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    # --- helpers -------------------------------------------------------

    @classmethod
    def _get_members(cls, queue=None):
        client = cls.client_class()
        client.credentials(HTTP_AUTHORIZATION=f"Token {cls.token.key}")
        params = {"queue": queue} if queue else {}
        return client.get(reverse("queue_members"), params)

    @classmethod
    def _find_member(cls, response, interface):
        if response.status_code != 200:
            return None
        for member in response.data.get("members", []):
            if interface in (member.get("location"), member.get("name")):
                return member
        return None

    @classmethod
    def _wait_for_member_visible(cls, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cls._find_member(cls._get_members(cls.QUEUE_NAME), cls.interface):
                return
            time.sleep(0.5)
        raise RuntimeError(
            f"Seeded member {cls.interface!r} never appeared in queue "
            f"{cls.QUEUE_NAME!r} after applying config and reloading."
        )

    def _wait_for_paused_state(self, expected_paused, timeout=15):
        deadline = time.monotonic() + timeout
        last_seen = None
        while time.monotonic() < deadline:
            member = self._find_member(self._get_members(self.QUEUE_NAME), self.interface)
            if member is not None:
                last_seen = member.get("paused")
                if last_seen == expected_paused:
                    return member
            time.sleep(0.5)
        self.fail(
            f"paused never became {expected_paused!r} for {self.interface!r} "
            f"(last seen: {last_seen!r})"
        )

    def _pause(self, paused, queue=None):
        body = {"interface": self.interface, "paused": paused}
        if queue:
            body["queue"] = queue
        return self.client.post(reverse("queue_member_pause"), body, format="json")

    # --- tests -----------------------------------------------------------

    def test_pause_changes_state_visible_via_api(self):
        """The core scenario: pausing via the API is really seen by Asterisk."""
        self.addCleanup(self._pause, False)

        response = self._pause(True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "paused")
        self._wait_for_paused_state(True)

        response = self._pause(False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "unpaused")
        self._wait_for_paused_state(False)

    def test_pause_unknown_interface_returns_404(self):
        """Confirms the "not found" heuristic matches real Asterisk wording."""
        response = self.client.post(
            reverse("queue_member_pause"),
            {"interface": "PJSIP/does-not-exist", "paused": True},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_list_members_reflects_seeded_pjsip_endpoint(self):
        response = self._get_members(self.QUEUE_NAME)
        self.assertEqual(response.status_code, 200)
        member = self._find_member(response, self.interface)
        self.assertIsNotNone(member)
        self.assertEqual(member["queue"], self.QUEUE_NAME)
        self.assertEqual(member["penalty"], 0)

    def test_pause_scoped_to_queue_param(self):
        self.addCleanup(self._pause, False, self.QUEUE_NAME)

        response = self._pause(True, queue=self.QUEUE_NAME)
        self.assertEqual(response.status_code, 200)
        self._wait_for_paused_state(True)
