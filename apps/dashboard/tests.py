import json
from unittest.mock import patch, MagicMock

import redis
from django.contrib.auth.models import User
from django.test import TestCase, Client


class TestOperatorPanel(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testop", password="pass")

    def test_redirects_anonymous(self):
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 302)

    def test_returns_200_for_authenticated(self):
        self.client.login(username="testop", password="pass")
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)


class DashboardAPITestBase(TestCase):
    """Base class — creates user, logs in, sets up Redis mock."""

    def setUp(self):
        self.user = User.objects.create_user(username="testop", password="pass")
        self.client = Client()
        self.client.login(username="testop", password="pass")
        self.mock_redis = MagicMock()

    def _patch_redis(self):
        return patch("apps.dashboard.views._get_redis", return_value=self.mock_redis)

    def _patch_redis_down(self):
        return patch(
            "apps.dashboard.views._get_redis",
            side_effect=redis.exceptions.ConnectionError,
        )


class TestGetQueueState(DashboardAPITestBase):
    def test_returns_queue_data(self):
        data = {"members": {"SIP/100": {}}, "calls": {}, "stats": {"waiting": 2}}
        self.mock_redis.get.return_value = json.dumps(data)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/queues/support/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), data)
        self.mock_redis.get.assert_called_once_with("asterisk:queue:support")

    def test_returns_empty_when_no_data(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/queues/support/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["members"], {})
        self.assertEqual(body["calls"], {})
        self.assertEqual(body["stats"]["waiting"], 0)

    def test_invalid_queue_name_returns_400(self):
        resp = self.client.get("/dashboard/api/queues/; DROP TABLE/")
        self.assertEqual(resp.status_code, 400)

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/queues/support/")
        self.assertEqual(resp.status_code, 503)

    def test_post_not_allowed(self):
        resp = self.client.post("/dashboard/api/queues/support/")
        self.assertEqual(resp.status_code, 405)


class TestGetAllQueues(DashboardAPITestBase):
    def test_returns_multiple_queues(self):
        q1 = {"members": {}, "calls": {}, "stats": {"waiting": 0}}
        q2 = {"members": {"SIP/200": {}}, "calls": {}, "stats": {"waiting": 1}}
        self.mock_redis.keys.return_value = [
            "asterisk:queue:support",
            "asterisk:queue:sales",
        ]
        self.mock_redis.get.side_effect = [json.dumps(q1), json.dumps(q2)]
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/queues/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("support", data)
        self.assertIn("sales", data)
        self.assertEqual(data["sales"]["stats"]["waiting"], 1)

    def test_returns_empty_when_no_queues(self):
        self.mock_redis.keys.return_value = []
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/queues/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {})

    def test_skips_queue_with_none_data(self):
        self.mock_redis.keys.return_value = ["asterisk:queue:ghost"]
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/queues/")
        self.assertEqual(resp.json(), {})

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/queues/")
        self.assertEqual(resp.status_code, 503)

    def test_post_not_allowed(self):
        resp = self.client.post("/dashboard/api/queues/")
        self.assertEqual(resp.status_code, 405)


class TestGetAllChannels(DashboardAPITestBase):
    def test_returns_channels(self):
        channels = {"PJSIP/100": {"state": "Up"}, "PJSIP/200": {"state": "Ring"}}
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("PJSIP/100", data)
        self.assertEqual(data["PJSIP/200"]["state"], "Ring")

    def test_returns_empty_when_no_channels(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {})

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/channels/")
        self.assertEqual(resp.status_code, 503)


class TestGetChannel(DashboardAPITestBase):
    def test_returns_channel_data(self):
        ch = {"state": "Up", "caller_id": "100"}
        self.mock_redis.get.return_value = json.dumps(ch)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/PJSIP/100-00000001/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), ch)

    def test_channel_not_found_returns_404(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/PJSIP/999/")
        self.assertEqual(resp.status_code, 404)

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/channels/PJSIP/100/")
        self.assertEqual(resp.status_code, 503)


class TestGetActiveCalls(DashboardAPITestBase):
    def test_returns_bridged_calls(self):
        channels = {
            "PJSIP/100-0001": {
                "bridge_id": "br-1",
                "state": "Up",
                "duration": 42,
            },
            "PJSIP/200-0002": {
                "bridge_id": "br-1",
                "state": "Up",
                "duration": 42,
            },
            "PJSIP/300-0003": {"state": "Ring"},
        }
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/calls/active/")
        data = resp.json()
        self.assertEqual(len(data["calls"]), 1)
        self.assertEqual(data["calls"][0]["bridge_id"], "br-1")
        self.assertEqual(len(data["calls"][0]["channels"]), 2)

    def test_single_channel_in_bridge_not_returned(self):
        channels = {
            "PJSIP/100-0001": {"bridge_id": "br-lonely", "state": "Up"},
        }
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/calls/active/")
        self.assertEqual(resp.json()["calls"], [])

    def test_multiple_bridges(self):
        channels = {
            "PJSIP/100-0001": {"bridge_id": "br-1", "state": "Up", "duration": 10},
            "PJSIP/200-0002": {"bridge_id": "br-1", "state": "Up", "duration": 10},
            "PJSIP/300-0003": {"bridge_id": "br-2", "state": "Up", "duration": 5},
            "PJSIP/400-0004": {"bridge_id": "br-2", "state": "Up", "duration": 5},
        }
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/calls/active/")
        data = resp.json()
        self.assertEqual(len(data["calls"]), 2)
        bridge_ids = {c["bridge_id"] for c in data["calls"]}
        self.assertEqual(bridge_ids, {"br-1", "br-2"})

    def test_no_data_returns_empty(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/calls/active/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"calls": []})

    def test_no_bridges_returns_empty_calls(self):
        channels = {
            "PJSIP/100-0001": {"state": "Ring"},
            "PJSIP/200-0002": {"state": "Up"},
        }
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/calls/active/")
        self.assertEqual(resp.json()["calls"], [])

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/calls/active/")
        self.assertEqual(resp.status_code, 503)


class TestGetChannelsByType(DashboardAPITestBase):
    def test_filters_by_type(self):
        channels = {
            "PJSIP/100": {"state": "Up"},
            "PJSIP/200": {"state": "Ring"},
            "DAHDI/1": {"state": "Up"},
        }
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/type/PJSIP/")
        data = resp.json()
        self.assertEqual(len(data), 2)
        self.assertIn("PJSIP/100", data)
        self.assertIn("PJSIP/200", data)
        self.assertNotIn("DAHDI/1", data)

    def test_no_match_returns_empty(self):
        channels = {"PJSIP/100": {"state": "Up"}}
        self.mock_redis.get.return_value = json.dumps(channels)
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/type/DAHDI/")
        self.assertEqual(resp.json(), {})

    def test_no_data_returns_empty(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            resp = self.client.get("/dashboard/api/channels/type/PJSIP/")
        self.assertEqual(resp.json(), {})

    def test_redis_down_returns_503(self):
        with self._patch_redis_down():
            resp = self.client.get("/dashboard/api/channels/type/PJSIP/")
        self.assertEqual(resp.status_code, 503)


class TestInputValidation(DashboardAPITestBase):
    def test_valid_queue_names_accepted(self):
        self.mock_redis.get.return_value = None
        with self._patch_redis():
            for name in ["support", "my-queue_1", "Queue.test"]:
                resp = self.client.get(f"/dashboard/api/queues/{name}/")
                self.assertNotEqual(
                    resp.status_code, 400, f"Rejected valid name: {name}"
                )

    def test_invalid_queue_names_rejected(self):
        for name in ["queue name", "q;DROP", "q<script>"]:
            resp = self.client.get(f"/dashboard/api/queues/{name}/")
            self.assertEqual(resp.status_code, 400, f"Accepted invalid name: {name}")


class TestAuthRequired(TestCase):
    def test_all_api_endpoints_redirect_anonymous(self):
        c = Client()
        urls = [
            "/dashboard/",
            "/dashboard/api/queues/",
            "/dashboard/api/queues/test/",
            "/dashboard/api/channels/",
            "/dashboard/api/calls/active/",
            "/dashboard/api/channels/type/PJSIP/",
        ]
        for url in urls:
            resp = c.get(url)
            self.assertEqual(
                resp.status_code, 302, f"{url} didn't redirect anonymous user"
            )


class TestUlineMonitorAccess(DashboardAPITestBase):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(username="admin", password="pass")

    def _mock_redis_for_uline(self):
        m = MagicMock()
        m.exists.return_value = True
        m.scan_iter.return_value = iter([])
        m.pipeline.return_value.__enter__ = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=[])))
        m.pipeline.return_value.__exit__ = MagicMock(return_value=False)
        m.pipeline.return_value.execute.return_value = []
        return m

    def test_anonymous_redirected(self):
        c = Client()
        resp = c.get("/dashboard/ulines/")
        self.assertEqual(resp.status_code, 302)

    def test_regular_user_redirected(self):
        resp = self.client.get("/dashboard/ulines/")
        self.assertEqual(resp.status_code, 302)

    def test_superuser_allowed(self):
        self.client.login(username="admin", password="pass")
        mock_r = self._mock_redis_for_uline()
        with patch("apps.dashboard.views._get_redis", return_value=mock_r):
            resp = self.client.get("/dashboard/ulines/")
        self.assertEqual(resp.status_code, 200)
