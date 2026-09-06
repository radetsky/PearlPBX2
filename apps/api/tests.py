import os
import tempfile
import uuid

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now, timedelta
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from unittest.mock import patch, MagicMock

from django.conf import settings as django_settings

from apps.api.models import CustomListNames, CustomListEntries
from core.models import (
    Blacklist,
    Whitelist,
    Contact,
    MonitorFilenames,
    SIPUser,
    SIPTransport,
    SIPPeer,
    TrunkGroup,
    RoutingTable,
    RoutingRecord,
    DialplanContext,
    DialplanExtension,
)
from apps.provision.models import PhoneDevice


class BaseAPITestCase(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="apitester", password="x")
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")


class AuthTests(APITestCase):
    def test_no_token_returns_401(self):
        response = self.client.get("/api/v1/blacklist/")
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalidtoken")
        response = self.client.get("/api/v1/blacklist/")
        self.assertEqual(response.status_code, 401)


class BlacklistTests(BaseAPITestCase):
    def test_get_empty(self):
        response = self.client.get("/api/v1/blacklist/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_get_list(self):
        Blacklist.objects.create(callerid="111", destination="222", reason="spam")
        response = self.client.get("/api/v1/blacklist/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["callerid"], "111")

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/blacklist/",
            {"callerid": "111", "destination": "222", "reason": "spam"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["callerid"], "111")

    def test_upsert_200_on_existing(self):
        entry = Blacklist.objects.create(
            callerid="111", destination="222", reason="old"
        )
        response = self.client.post(
            "/api/v1/blacklist/",
            {"callerid": "111", "destination": "222", "reason": "updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.reason, "updated")

    def test_same_callerid_different_destination_201(self):
        Blacklist.objects.create(callerid="111", destination="222", reason="a")
        response = self.client.post(
            "/api/v1/blacklist/",
            {"callerid": "111", "destination": "333", "reason": "b"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Blacklist.objects.filter(callerid="111").count(), 2)

    def test_patch_collision_returns_409(self):
        Blacklist.objects.create(callerid="111", destination="222")
        other = Blacklist.objects.create(callerid="111", destination="333")
        response = self.client.patch(
            f"/api/v1/blacklist/{other.id}/",
            {"destination": "222"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_create_missing_callerid_400(self):
        response = self.client.post(
            "/api/v1/blacklist/", {"destination": "222"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("callerid", response.data)

    def test_delete_204(self):
        entry = Blacklist.objects.create(callerid="111")
        response = self.client.delete(f"/api/v1/blacklist/{entry.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Blacklist.objects.filter(pk=entry.id).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete(f"/api/v1/blacklist/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)

    def test_audit_created_by(self):
        self.client.post(
            "/api/v1/blacklist/",
            {"callerid": "111", "reason": "test"},
            format="json",
        )
        entry = Blacklist.objects.get(callerid="111")
        self.assertEqual(entry.created_by, self.user)


class WhitelistTests(BaseAPITestCase):
    def test_get_empty(self):
        response = self.client.get("/api/v1/whitelist/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/whitelist/",
            {"callerid": "111", "destination": "222", "reason": "trusted"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["callerid"], "111")

    def test_upsert_200_on_existing(self):
        entry = Whitelist.objects.create(
            callerid="111", destination="222", reason="old"
        )
        response = self.client.post(
            "/api/v1/whitelist/",
            {"callerid": "111", "destination": "222", "reason": "updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.reason, "updated")

    def test_create_missing_callerid_400(self):
        response = self.client.post(
            "/api/v1/whitelist/", {"destination": "222"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("callerid", response.data)

    def test_delete_204(self):
        entry = Whitelist.objects.create(callerid="111")
        response = self.client.delete(f"/api/v1/whitelist/{entry.id}/")
        self.assertEqual(response.status_code, 204)

    def test_delete_not_found_404(self):
        response = self.client.delete(f"/api/v1/whitelist/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)


class ContactTests(BaseAPITestCase):
    def test_get_empty(self):
        response = self.client.get("/api/v1/contacts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/contacts/", {"callerid": "111", "name": "John"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "John")

    def test_upsert_200_on_existing(self):
        Contact.objects.create(callerid="111", name="Old")
        response = self.client.post(
            "/api/v1/contacts/", {"callerid": "111", "name": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Contact.objects.get(callerid="111").name, "Updated")

    def test_create_missing_fields_400(self):
        response = self.client.post(
            "/api/v1/contacts/", {"name": "No CID"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("callerid", response.data)

    def test_delete_204(self):
        entry = Contact.objects.create(callerid="111", name="John")
        response = self.client.delete(f"/api/v1/contacts/{entry.id}/")
        self.assertEqual(response.status_code, 204)

    def test_delete_not_found_404(self):
        response = self.client.delete(f"/api/v1/contacts/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)


class CustomListTests(BaseAPITestCase):
    def test_create_list_201(self):
        response = self.client.post(
            "/api/v1/lists/", {"name": "VIP"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "VIP")

    def test_rename_list_200(self):
        lst = CustomListNames.objects.create(name="Old")
        response = self.client.patch(
            f"/api/v1/lists/{lst.id}/", {"name": "New"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "New")

    def test_rename_list_empty_body_400(self):
        lst = CustomListNames.objects.create(name="Old")
        response = self.client.patch(
            f"/api/v1/lists/{lst.id}/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], 'Missing "name"')

    def test_delete_list_204(self):
        lst = CustomListNames.objects.create(name="Del")
        response = self.client.delete(f"/api/v1/lists/{lst.id}/")
        self.assertEqual(response.status_code, 204)

    def test_list_entries_empty(self):
        lst = CustomListNames.objects.create(name="Empty")
        response = self.client.get(f"/api/v1/lists/{lst.id}/entries/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_list_entries_with_data(self):
        lst = CustomListNames.objects.create(name="Test")
        CustomListEntries.objects.create(
            list_name=lst, callerid="111", destination="222", reason="VIP"
        )
        response = self.client.get(f"/api/v1/lists/{lst.id}/entries/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["callerid"], "111")

    def test_add_entry_201(self):
        lst = CustomListNames.objects.create(name="Test")
        response = self.client.post(
            f"/api/v1/lists/{lst.id}/entries/",
            {
                "callerid": "111",
                "destination": "222",
                "reason": "VIP",
                "expiration_date": (now() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["callerid"], "111")

    def test_add_entry_optional_fields_empty(self):
        lst = CustomListNames.objects.create(name="Test")
        response = self.client.post(
            f"/api/v1/lists/{lst.id}/entries/",
            {"callerid": "999", "destination": "", "reason": "", "expiration_date": None},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["callerid"], "999")
        self.assertEqual(response.data["destination"], "")
        self.assertEqual(response.data["reason"], "")
        self.assertIsNone(response.data["expiration_date"])

    def test_delete_entry_204(self):
        lst = CustomListNames.objects.create(name="Test")
        entry = CustomListEntries.objects.create(list_name=lst, callerid="111")
        response = self.client.delete(
            f"/api/v1/lists/{lst.id}/entries/{entry.id}/"
        )
        self.assertEqual(response.status_code, 204)

    def test_delete_entry_wrong_list_404(self):
        lst = CustomListNames.objects.create(name="Test")
        other = CustomListNames.objects.create(name="Other")
        entry = CustomListEntries.objects.create(list_name=lst, callerid="111")
        response = self.client.delete(
            f"/api/v1/lists/{other.id}/entries/{entry.id}/"
        )
        self.assertEqual(response.status_code, 404)


class SIPUserApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="sipuser_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="sipuser_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

        self.transport = SIPTransport.objects.create(
            name="test-api-transport",
            protocol="udp",
            bind="0.0.0.0:5061",
            description="Test transport",
        )
        self.wss_transport = SIPTransport.objects.create(
            name="test-api-wss-transport",
            protocol="wss",
            bind="0.0.0.0:8089",
            description="Test WSS transport",
        )
        self.routing_table = RoutingTable.objects.get(
            name=django_settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )

    def _payload(self, **overrides):
        payload = {
            "name": "Test User",
            "username": "apiuser900",
            "secret": "s3cret123",
            "extension": "900",
            "transport": self.transport.id,
            "routing_table": self.routing_table.id,
            "auth_type": "userpass",
        }
        payload.update(overrides)
        return payload

    def test_get_empty(self):
        # core.migrations.0016_first_users seeds ppbxuser201..210, so the
        # table is never truly empty — filter to a username that can't exist.
        response = self.client.get("/api/v1/sip-users/?username=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/sip-users/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/sip-users/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["username"], "apiuser900")
        self.assertEqual(response.data["secret"], "s3cret123")

    def test_created_row_lands_in_generated_pjsip_conf(self):
        from core.conf import make_pjsip_conf_users

        self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        result = make_pjsip_conf_users()
        self.assertIn("[apiuser900](user-template)", result)

    def test_create_without_transport_400(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(transport=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("transport", response.data)

    def test_create_without_routing_table_400(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(routing_table=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("routing_table", response.data)

    def test_create_short_username_400(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(username="ab"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_create_non_alnum_username_400(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(username="bad.user"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_create_non_alnum_extension_400(self):
        response = self.client.post(
            "/api/v1/sip-users/", self._payload(extension="9-00"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("extension", response.data)

    def test_duplicate_username_400(self):
        self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        response = self.client.post(
            "/api/v1/sip-users/",
            self._payload(extension="901"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_duplicate_extension_400(self):
        self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        response = self.client.post(
            "/api/v1/sip-users/",
            self._payload(username="apiuser901"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("extension", response.data)

    def test_list_filter_by_username(self):
        SIPUser.objects.create(
            name="Other",
            username="other900",
            extension="800",
            secret="x",
            transport=self.transport,
            routing_table=self.routing_table,
        )
        self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        response = self.client.get("/api/v1/sip-users/?username=apiuser900")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["username"], "apiuser900")

    def test_search(self):
        self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        response = self.client.get("/api/v1/sip-users/?search=Test User")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_secret_and_md5_cred_hidden_in_list(self):
        create = self.client.post(
            "/api/v1/sip-users/",
            self._payload(transport=self.wss_transport.id, extension="903"),
            format="json",
        )
        self.assertIsNotNone(create.data["secret"])
        self.assertIsNotNone(create.data["md5_cred"])

        response = self.client.get("/api/v1/sip-users/?username=apiuser900")
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertIsNone(row["secret"])
        self.assertIsNone(row["md5_cred"])

    def test_secret_and_md5_cred_visible_on_retrieve(self):
        create = self.client.post(
            "/api/v1/sip-users/",
            self._payload(transport=self.wss_transport.id, extension="904"),
            format="json",
        )
        pk = create.data["id"]
        response = self.client.get(f"/api/v1/sip-users/{pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["secret"], "s3cret123")
        self.assertIsNotNone(response.data["md5_cred"])

    def test_patch_200(self):
        create = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/sip-users/{pk}/", {"name": "Updated Name"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Updated Name")

    def test_delete_204(self):
        create = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/sip-users/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SIPUser.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/sip-users/999999/")
        self.assertEqual(response.status_code, 404)

    def test_delete_cascades_phone_device(self):
        create = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        pk = create.data["id"]
        device = PhoneDevice.objects.create(
            mac_address="00:11:22:33:44:55",
            sip_user_id=pk,
            sip_server="pbx.example.com",
        )
        self.client.delete(f"/api/v1/sip-users/{pk}/")
        self.assertFalse(PhoneDevice.objects.filter(pk=device.pk).exists())

    def test_delete_removes_queue_members(self):
        from core.models import MusicOnHold, Queue, QueueAnnouncements, QueueMember

        create = self.client.post("/api/v1/sip-users/", self._payload(), format="json")
        pk = create.data["id"]
        moh = MusicOnHold.objects.create(name="test-sipuser-del-moh")
        ann = QueueAnnouncements.objects.create(name="test-sipuser-del-ann")
        queue = Queue.objects.create(
            name="TestSipUserDelQueue", music_class=moh, queue_announcement=ann
        )
        member = QueueMember.objects.create(queue=queue, interface="PJSIP/apiuser900")
        self.client.delete(f"/api/v1/sip-users/{pk}/")
        self.assertFalse(QueueMember.objects.filter(pk=member.pk).exists())
        queue.delete()
        ann.delete()
        moh.delete()

    def test_md5_cred_matches_model(self):
        create = self.client.post(
            "/api/v1/sip-users/",
            self._payload(transport=self.wss_transport.id, extension="901"),
            format="json",
        )
        user = SIPUser.objects.get(pk=create.data["id"])
        self.assertEqual(create.data["md5_cred"], user.md5_cred)

    def test_realm_for_wss_transport(self):
        create = self.client.post(
            "/api/v1/sip-users/",
            self._payload(transport=self.wss_transport.id, extension="901"),
            format="json",
        )
        self.assertEqual(create.data["realm"], "wss-apiuser900")
        self.assertTrue(create.data["is_webrtc"])

    def test_realm_null_when_transport_missing(self):
        SIPUser.objects.create(
            name="No Transport",
            username="notransport900",
            extension="902",
            secret="x",
            transport=None,
            routing_table=self.routing_table,
        )
        response = self.client.get("/api/v1/sip-users/?username=notransport900")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["results"][0]["realm"])
        self.assertIsNone(response.data["results"][0]["md5_cred"])
        self.assertIsNone(response.data["results"][0]["is_webrtc"])

    def test_audit_created_by(self):
        create = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        user = SIPUser.objects.get(pk=create.data["id"])
        self.assertEqual(user.created_by, self.staff_user)

    def test_audit_modified_by_not_overwritten_created_by_on_patch(self):
        create = self.client.post(
            "/api/v1/sip-users/", self._payload(), format="json"
        )
        pk = create.data["id"]

        other_staff = get_user_model().objects.create_user(
            username="sipuser_staff2", password="x", is_staff=True
        )
        other_token = Token.objects.create(user=other_staff)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {other_token.key}")
        self.client.patch(f"/api/v1/sip-users/{pk}/", {"name": "Renamed"}, format="json")

        user = SIPUser.objects.get(pk=pk)
        self.assertEqual(user.created_by, self.staff_user)
        self.assertEqual(user.modified_by, other_staff)


class SIPTransportApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="transport_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="transport_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

    def _payload(self, **overrides):
        payload = {
            "name": "api-transport-udp",
            "protocol": "udp",
            "bind": "0.0.0.0:5063",
            "description": "Created via API",
        }
        payload.update(overrides)
        return payload

    def test_get_empty(self):
        # core.migrations.0016_first_users seeds transport-udp/transport-tcp,
        # so the table is never truly empty — filter to a name that can't exist.
        response = self.client.get("/api/v1/sip-transports/?name=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/sip-transports/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/sip-transports/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "api-transport-udp")
        self.assertEqual(response.data["sip_users_count"], 0)
        self.assertEqual(response.data["sip_peers_count"], 0)
        self.assertFalse(response.data["has_tls_material"])

    def test_created_row_lands_in_generated_pjsip_conf(self):
        from core.conf import make_pjsip_conf_transports

        self.client.post("/api/v1/sip-transports/", self._payload(), format="json")
        result = make_pjsip_conf_transports()
        self.assertIn("[api-transport-udp]", result)
        self.assertIn("bind = 0.0.0.0:5063", result)

    def test_delete_in_use_returns_409(self):
        create = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        transport_id = create.data["id"]
        routing_table = RoutingTable.objects.get(
            name=django_settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )
        SIPUser.objects.create(
            name="Blocker",
            username="blocker900",
            extension="900",
            secret="x",
            transport_id=transport_id,
            routing_table=routing_table,
        )
        response = self.client.delete(f"/api/v1/sip-transports/{transport_id}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(SIPTransport.objects.filter(pk=transport_id).exists())

    def test_invalid_bind_400(self):
        response = self.client.post(
            "/api/v1/sip-transports/", self._payload(bind="not-an-ip"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("bind", response.data)

    def test_invalid_name_400(self):
        response = self.client.post(
            "/api/v1/sip-transports/", self._payload(name="1-bad name"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_duplicate_name_400(self):
        self.client.post("/api/v1/sip-transports/", self._payload(), format="json")
        response = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(bind="0.0.0.0:5064"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_description_with_newline_400(self):
        response = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(description="line1\nline2"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("description", response.data)

    def test_blank_local_nets_stored_as_null(self):
        create = self.client.post(
            "/api/v1/sip-transports/", self._payload(local_nets=""), format="json"
        )
        self.assertEqual(create.status_code, 201)
        self.assertIsNone(create.data["local_nets"])
        transport = SIPTransport.objects.get(pk=create.data["id"])
        self.assertIsNone(transport.local_nets)

    def test_invalid_local_net_400(self):
        response = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(local_nets="10.0.0.0/16, not-a-network"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("local_nets", response.data)

    def test_tls_material_roundtrip(self):
        create = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(
                protocol="tls",
                cert_file="-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n",
            ),
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        self.assertIn("BEGIN CERTIFICATE", create.data["cert_file"])
        self.assertTrue(create.data["has_tls_material"])

    def test_priv_key_file_hidden_in_list(self):
        create = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(protocol="tls", priv_key_file="-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n"),
            format="json",
        )
        self.assertIn("BEGIN PRIVATE KEY", create.data["priv_key_file"])

        response = self.client.get("/api/v1/sip-transports/?name=api-transport-udp")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["results"][0]["priv_key_file"])

    def test_priv_key_file_visible_on_retrieve(self):
        create = self.client.post(
            "/api/v1/sip-transports/",
            self._payload(protocol="tls", priv_key_file="-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n"),
            format="json",
        )
        pk = create.data["id"]
        response = self.client.get(f"/api/v1/sip-transports/{pk}/")
        self.assertIn("BEGIN PRIVATE KEY", response.data["priv_key_file"])

    def test_patch_200(self):
        create = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/sip-transports/{pk}/",
            {"description": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "Updated")

    def test_delete_204(self):
        create = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/sip-transports/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SIPTransport.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/sip-transports/999999/")
        self.assertEqual(response.status_code, 404)

    def test_audit_created_by(self):
        create = self.client.post(
            "/api/v1/sip-transports/", self._payload(), format="json"
        )
        transport = SIPTransport.objects.get(pk=create.data["id"])
        self.assertEqual(transport.created_by, self.staff_user)


class SIPPeerApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="peer_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="peer_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

        self.transport = SIPTransport.objects.create(
            name="test-peer-transport",
            protocol="udp",
            bind="0.0.0.0:5065",
            description="Test transport",
        )
        self.routing_table = RoutingTable.objects.get(
            name=django_settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )

    def _payload(self, **overrides):
        payload = {
            "name": "apipeer900",
            "description": "Test peer",
            "username": "peeruser",
            "secret": "s3cret123",
            "auth_type": "userpass",
            "transport": self.transport.id,
            "routing_table": self.routing_table.id,
        }
        payload.update(overrides)
        return payload

    def test_get_empty(self):
        response = self.client.get("/api/v1/sip-peers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/sip-peers/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/sip-peers/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "apipeer900")
        self.assertEqual(response.data["secret"], "s3cret123")
        self.assertEqual(response.data["registration_here"], False)
        self.assertEqual(response.data["registration_there"], False)

    def test_created_row_lands_in_generated_pjsip_conf(self):
        from core.conf import make_pjsip_conf_uplinks

        self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        result = make_pjsip_conf_uplinks()
        self.assertIn("[apipeer900]", result)
        self.assertIn("type=endpoint", result)

    def test_create_without_transport_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/", self._payload(transport=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("transport", response.data)

    def test_create_without_routing_table_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/", self._payload(routing_table=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("routing_table", response.data)

    def test_registration_there_without_uri_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/",
            self._payload(registration_there=True, username="provideruser"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("registration_uri", response.data)

    def test_registration_there_without_username_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/",
            self._payload(
                registration_there=True,
                registration_uri="reg.provider.com:5060",
                username="",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_non_alnum_name_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/", self._payload(name="bad.peer"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_short_name_400(self):
        response = self.client.post(
            "/api/v1/sip-peers/", self._payload(name="ab"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_duplicate_name_400(self):
        self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        response = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_md5_cred_matches_model(self):
        create = self.client.post(
            "/api/v1/sip-peers/",
            self._payload(auth_type="md5"),
            format="json",
        )
        peer = SIPPeer.objects.get(pk=create.data["id"])
        self.assertEqual(create.data["md5_cred"], peer.md5_cred)

    def test_secret_and_md5_cred_hidden_in_list(self):
        create = self.client.post(
            "/api/v1/sip-peers/", self._payload(auth_type="md5"), format="json"
        )
        self.assertIsNotNone(create.data["secret"])
        self.assertIsNotNone(create.data["md5_cred"])

        response = self.client.get("/api/v1/sip-peers/?name=apipeer900")
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertIsNone(row["secret"])
        self.assertIsNone(row["md5_cred"])

    def test_secret_and_md5_cred_visible_on_retrieve(self):
        create = self.client.post(
            "/api/v1/sip-peers/", self._payload(auth_type="md5"), format="json"
        )
        pk = create.data["id"]
        response = self.client.get(f"/api/v1/sip-peers/{pk}/")
        self.assertEqual(response.data["secret"], "s3cret123")
        self.assertIsNotNone(response.data["md5_cred"])

    def test_auth_realm_from_registration_uri(self):
        create = self.client.post(
            "/api/v1/sip-peers/",
            self._payload(registration_uri="reg.provider.com:5060"),
            format="json",
        )
        self.assertEqual(create.data["auth_realm"], "reg.provider.com")

    def test_registration_flags_are_snake_case(self):
        response = self.client.post(
            "/api/v1/sip-peers/",
            self._payload(registration_here=True),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["registration_here"])
        self.assertNotIn("registrationHere", response.data)

    def test_patch_200(self):
        create = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/sip-peers/{pk}/", {"description": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "Updated")

    def test_delete_204(self):
        create = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/sip-peers/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SIPPeer.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/sip-peers/999999/")
        self.assertEqual(response.status_code, 404)

    def test_delete_in_trunk_group_returns_409(self):
        create = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        pk = create.data["id"]
        group = TrunkGroup.objects.create(name="test-trunk-group")
        group.sip_peers.add(pk)

        response = self.client.delete(f"/api/v1/sip-peers/{pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(SIPPeer.objects.filter(pk=pk).exists())

    def test_audit_created_by(self):
        create = self.client.post("/api/v1/sip-peers/", self._payload(), format="json")
        peer = SIPPeer.objects.get(pk=create.data["id"])
        self.assertEqual(peer.created_by, self.staff_user)


class RoutingTableApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="rt_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="rt_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

    def _payload(self, **overrides):
        payload = {"name": "api-routing-table"}
        payload.update(overrides)
        return payload

    def test_get_empty(self):
        response = self.client.get("/api/v1/routing-tables/?name=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/routing-tables/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/routing-tables/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "api-routing-table")
        self.assertEqual(response.data["routing_records_count"], 0)

    def test_create_name_colliding_with_dialplan_context_400(self):
        ctx = DialplanContext.objects.create(name="api-rt-collision")
        response = self.client.post(
            "/api/v1/routing-tables/",
            self._payload(name="api-rt-collision"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        ctx.delete()

    def test_duplicate_name_400(self):
        self.client.post("/api/v1/routing-tables/", self._payload(), format="json")
        response = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_patch_200(self):
        create = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/routing-tables/{pk}/", {"name": "api-routing-table-renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "api-routing-table-renamed")

    def test_delete_204(self):
        create = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/routing-tables/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(RoutingTable.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/routing-tables/999999/")
        self.assertEqual(response.status_code, 404)

    def test_delete_in_use_returns_409(self):
        create = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        pk = create.data["id"]
        transport = SIPTransport.objects.create(
            name="test-rt-api-transport", protocol="udp", bind="0.0.0.0:5071"
        )
        SIPUser.objects.create(
            name="RT Blocker",
            username="rtblocker900",
            extension="900",
            secret="x",
            transport=transport,
            routing_table_id=pk,
        )
        response = self.client.delete(f"/api/v1/routing-tables/{pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(RoutingTable.objects.filter(pk=pk).exists())

    def test_delete_referenced_by_webhook_returns_409(self):
        from apps.webhooks.models import Webhook

        create = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        pk = create.data["id"]
        webhook = Webhook.objects.create(name="test-rt-webhook", url="https://example.com/hook")
        webhook.routing_tables.add(pk)

        response = self.client.delete(f"/api/v1/routing-tables/{pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(RoutingTable.objects.filter(pk=pk).exists())
        webhook.delete()

    def test_audit_created_by(self):
        create = self.client.post(
            "/api/v1/routing-tables/", self._payload(), format="json"
        )
        rt = RoutingTable.objects.get(pk=create.data["id"])
        self.assertEqual(rt.created_by, self.staff_user)


class RoutingRecordApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="rr_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="rr_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

        self.context = DialplanContext.objects.create(name="test-rr-context")
        self.routing_table = RoutingTable.objects.create(name="test-rr-table")

    def tearDown(self):
        RoutingRecord.objects.filter(routing_table=self.routing_table).delete()
        self.routing_table.delete()
        self.context.delete()

    def _payload(self, **overrides):
        payload = {
            "name": "Kyiv landline",
            "prefix": "044",
            "context": self.context.id,
            "routing_table": self.routing_table.id,
        }
        payload.update(overrides)
        return payload

    def test_get_empty(self):
        response = self.client.get("/api/v1/routing-records/?name=does-not-exist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/routing-records/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post(
            "/api/v1/routing-records/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/routing-records/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/routing-records/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["prefix"], "044")
        self.assertEqual(response.data["context_name"], "test-rr-context")
        self.assertEqual(response.data["routing_table_name"], "test-rr-table")

    def test_created_row_lands_in_generated_routing_tables(self):
        from core.conf import make_routing_tables

        self.client.post("/api/v1/routing-records/", self._payload(), format="json")
        result = make_routing_tables()
        self.assertIn("context test-rr-table {", result)
        self.assertIn("044 => { goto test-rr-context,${EXTEN},1; }", result)

    def test_create_without_context_400(self):
        response = self.client.post(
            "/api/v1/routing-records/", self._payload(context=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("context", response.data)

    def test_create_without_routing_table_400(self):
        response = self.client.post(
            "/api/v1/routing-records/", self._payload(routing_table=None), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("routing_table", response.data)

    def test_create_invalid_prefix_400(self):
        response = self.client.post(
            "/api/v1/routing-records/", self._payload(prefix="not-a-pattern"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("prefix", response.data)

    def test_list_filter_by_routing_table(self):
        self.client.post("/api/v1/routing-records/", self._payload(), format="json")
        response = self.client.get(
            f"/api/v1/routing-records/?routing_table={self.routing_table.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_search(self):
        self.client.post("/api/v1/routing-records/", self._payload(), format="json")
        response = self.client.get("/api/v1/routing-records/?search=Kyiv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_patch_200(self):
        create = self.client.post(
            "/api/v1/routing-records/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/routing-records/{pk}/", {"prefix": "050"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["prefix"], "050")

    def test_delete_204(self):
        create = self.client.post(
            "/api/v1/routing-records/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/routing-records/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(RoutingRecord.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/routing-records/999999/")
        self.assertEqual(response.status_code, 404)

    def test_audit_created_by(self):
        create = self.client.post(
            "/api/v1/routing-records/", self._payload(), format="json"
        )
        record = RoutingRecord.objects.get(pk=create.data["id"])
        self.assertEqual(record.created_by, self.staff_user)


class TrunkGroupApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="tg_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="tg_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")
        self.context = DialplanContext.objects.create(name="test-tg-api-context")

    def tearDown(self):
        DialplanExtension.objects.filter(context=self.context).delete()
        self.context.delete()

    def _payload(self, **overrides):
        payload = {"name": "api-trunk-group"}
        payload.update(overrides)
        return payload

    def _make_referencing_extension(self, group_name):
        return DialplanExtension.objects.create(
            context=self.context,
            ext="100",
            dialplan=f"AGI(agi://127.0.0.1:4573/dial-trunk-group,{group_name},${{EXTEN}});",
        )

    def test_get_empty(self):
        response = self.client.get("/api/v1/trunk-groups/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_non_staff_forbidden_on_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/trunk-groups/")
        self.assertEqual(response.status_code, 403)

    def test_non_staff_forbidden_on_post(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_token_returns_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/trunk-groups/")
        self.assertEqual(response.status_code, 401)

    def test_create_201(self):
        response = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "api-trunk-group")
        self.assertEqual(response.data["sip_peers_count"], 0)

    def test_sip_peers_writable_via_api(self):
        transport = SIPTransport.objects.create(
            name="test-tg-api-transport", protocol="udp", bind="0.0.0.0:5072"
        )
        peer = SIPPeer.objects.create(name="test-tg-api-peer", transport=transport)
        response = self.client.post(
            "/api/v1/trunk-groups/", self._payload(sip_peers=[peer.pk]), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["sip_peers"], [peer.pk])
        self.assertEqual(response.data["sip_peer_names"], ["test-tg-api-peer"])
        self.assertEqual(response.data["sip_peers_count"], 1)
        peer.delete()
        transport.delete()

    def test_duplicate_name_400(self):
        self.client.post("/api/v1/trunk-groups/", self._payload(), format="json")
        response = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_patch_200(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.patch(
            f"/api/v1/trunk-groups/{pk}/", {"name": "api-trunk-group-renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "api-trunk-group-renamed")

    def test_delete_204(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        pk = create.data["id"]
        response = self.client.delete(f"/api/v1/trunk-groups/{pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TrunkGroup.objects.filter(pk=pk).exists())

    def test_delete_not_found_404(self):
        response = self.client.delete("/api/v1/trunk-groups/999999/")
        self.assertEqual(response.status_code, 404)

    def test_rename_blocked_while_dialplan_references_old_name(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(name="test-tg-api-old"), format="json"
        )
        pk = create.data["id"]
        self._make_referencing_extension("test-tg-api-old")
        response = self.client.patch(
            f"/api/v1/trunk-groups/{pk}/", {"name": "test-tg-api-new"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_rename_allowed_after_dialplan_updated(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(name="test-tg-api-old2"), format="json"
        )
        pk = create.data["id"]
        ext = self._make_referencing_extension("test-tg-api-old2")
        ext.delete()
        response = self.client.patch(
            f"/api/v1/trunk-groups/{pk}/", {"name": "test-tg-api-new2"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_blocked_while_dialplan_references_returns_409(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(name="test-tg-api-del"), format="json"
        )
        pk = create.data["id"]
        self._make_referencing_extension("test-tg-api-del")
        response = self.client.delete(f"/api/v1/trunk-groups/{pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(TrunkGroup.objects.filter(pk=pk).exists())

    def test_delete_allowed_after_dialplan_updated(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(name="test-tg-api-del2"), format="json"
        )
        pk = create.data["id"]
        ext = self._make_referencing_extension("test-tg-api-del2")
        ext.delete()
        response = self.client.delete(f"/api/v1/trunk-groups/{pk}/")
        self.assertEqual(response.status_code, 204)

    def test_audit_created_by(self):
        create = self.client.post(
            "/api/v1/trunk-groups/", self._payload(), format="json"
        )
        group = TrunkGroup.objects.get(pk=create.data["id"])
        self.assertEqual(group.created_by, self.staff_user)


class ApplyChangesApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="apply_super", password="x", email="super@example.com"
        )
        self.superuser_token = Token.objects.create(user=self.superuser)
        self.staff_user = User.objects.create_user(
            username="apply_staff", password="x", is_staff=True
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.plain_user = User.objects.create_user(username="apply_plain", password="x")
        self.plain_token = Token.objects.create(user=self.plain_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.superuser_token.key}")
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_preview_forbidden_for_staff(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")
        response = self.client.get("/api/v1/config/preview/")
        self.assertEqual(response.status_code, 403)

    def test_preview_forbidden_for_plain_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.plain_token.key}")
        response = self.client.get("/api/v1/config/preview/")
        self.assertEqual(response.status_code, 403)

    def test_preview_no_token_401(self):
        self.client.credentials()
        response = self.client.get("/api/v1/config/preview/")
        self.assertEqual(response.status_code, 401)

    def test_preview_returns_generated_files(self):
        response = self.client.get("/api/v1/config/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("pjsip.conf", response.data["files"])
        self.assertIn("; ==== Transports section ====", response.data["files"]["pjsip.conf"])
        self.assertIn("skipped_sip_users", response.data)

    def test_apply_forbidden_for_staff(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")
        response = self.client.post("/api/v1/config/apply/", {"mode": "soft"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_apply_missing_mode_400(self):
        response = self.client.post("/api/v1/config/apply/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_apply_invalid_mode_400(self):
        response = self.client.post(
            "/api/v1/config/apply/", {"mode": "medium"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.api.views.config.redis.Redis")
    @override_settings(DEVMODE="without_asterisk_on_localhost")
    def test_apply_devmode_without_asterisk_skips_ami(self, mock_redis_cls):
        mock_redis_cls.from_url.return_value.set.return_value = True
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "soft"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["reloaded"])

    @patch("apps.api.views.config.AsteriskManagementInterface")
    @patch("apps.api.views.config.redis.Redis")
    @override_settings(DEVMODE="Development")
    def test_apply_soft_calls_soft_reload(self, mock_redis_cls, mock_ami_cls):
        mock_redis_cls.from_url.return_value.set.return_value = True
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "soft"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["reloaded"])
        mock_ami.soft_reload.assert_called_once()
        mock_ami.restart.assert_not_called()

    @patch("apps.api.views.config.AsteriskManagementInterface")
    @patch("apps.api.views.config.redis.Redis")
    @override_settings(DEVMODE="Development")
    def test_apply_hard_calls_restart(self, mock_redis_cls, mock_ami_cls):
        mock_redis_cls.from_url.return_value.set.return_value = True
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "hard"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        mock_ami.restart.assert_called_once()
        mock_ami.soft_reload.assert_not_called()

    @patch("apps.api.views.config.AsteriskManagementInterface")
    @patch("apps.api.views.config.redis.Redis")
    @override_settings(DEVMODE="Development")
    def test_apply_ami_failure_returns_500(self, mock_redis_cls, mock_ami_cls):
        # The AMI reload call must be covered by the same try/except as
        # apply_changes() — a failed reload must not escape as an unhandled
        # exception.
        mock_redis_cls.from_url.return_value.set.return_value = True
        mock_ami_cls.return_value.__enter__.side_effect = Exception("AMI down")
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "soft"}, format="json"
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("detail", response.data)

    @patch("apps.api.views.config.redis.Redis")
    def test_apply_returns_409_when_lock_held(self, mock_redis_cls):
        mock_redis_cls.from_url.return_value.set.return_value = False
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir, DEVMODE="without_asterisk_on_localhost"):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "soft"}, format="json"
            )
        self.assertEqual(response.status_code, 409)

    @patch("apps.api.views.config.redis.Redis", side_effect=Exception("redis down"))
    def test_apply_proceeds_when_redis_unavailable(self, mock_redis_cls):
        with self.settings(ASTERISK_ROOT_DIR=self.tmpdir, DEVMODE="without_asterisk_on_localhost"):
            response = self.client.post(
                "/api/v1/config/apply/", {"mode": "soft"}, format="json"
            )
        self.assertEqual(response.status_code, 200)


class OriginateApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="apitester", password="x"
        )
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("calls_originate")
        self.body = {
            "channel": "Local/0503856087@default",
            "exten": "0675653380",
            "context": "default",
            "callerid": "380443333333<0675653380>",
            "variable": {"userId": "0"},
        }

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_requires_auth(self):
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_validation_error(self):
        self._auth()
        resp = self.client.post(self.url, {"exten": "0675653380"}, format="json")
        self.assertEqual(resp.status_code, 400)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_originate_success(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = False
        ami_response.keys = {"Message": "Originate successfully queued"}
        mock_ami.originate.return_value = ami_response

        resp = self.client.post(self.url, self.body, format="json")

        self.assertEqual(resp.status_code, 200)
        mock_ami.originate.assert_called_once()
        called_kwargs = mock_ami.originate.call_args.kwargs
        self.assertEqual(called_kwargs["channel"], "Local/0503856087@default")
        self.assertEqual(called_kwargs["exten"], "0675653380")
        self.assertEqual(called_kwargs["variables"], {"userId": "0"})
        self.assertEqual(called_kwargs["callerid"], "380443333333<0675653380>")
        mock_ami_cls.return_value.__exit__.assert_called_once()

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_originate_ami_error(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = True
        ami_response.keys = {"Message": "Extension does not exist"}
        mock_ami.originate.return_value = ami_response

        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_originate_timeout_none_502(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        mock_ami.originate.return_value = None

        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface", side_effect=Exception("no ami"))
    def test_ami_unavailable(self, _mock):
        self._auth()
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)


class ConferenceApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="conftester", password="x"
        )
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("calls_conference")
        self.body = {
            "parties": [
                "PJSIP/101",
                "PJSIP/0504139380@mega-provider",
                "Local/2222@internal",
            ],
        }

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_requires_auth(self):
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_validation_error_needs_at_least_two_parties(self):
        self._auth()
        resp = self.client.post(
            self.url, {"parties": ["PJSIP/101"]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_conference_success_originates_each_party_async(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = False
        ami_response.keys = {"Message": "Originate successfully queued"}
        mock_ami.send_originate.return_value = MagicMock(response=ami_response)

        resp = self.client.post(self.url, self.body, format="json")

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(mock_ami.send_originate.call_count, 3)
        room = resp.data["room"]
        self.assertTrue(room)
        self.assertEqual(len(resp.data["results"]), 3)
        for result in resp.data["results"]:
            self.assertTrue(result["queued"])

        called_exten = {
            c.kwargs["exten"] for c in mock_ami.send_originate.call_args_list
        }
        self.assertEqual(called_exten, {room})
        for call in mock_ami.send_originate.call_args_list:
            self.assertTrue(call.kwargs["async_originate"])
        mock_ami_cls.return_value.__exit__.assert_called_once()

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_conference_uses_provided_room(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = False
        ami_response.keys = {"Message": ""}
        mock_ami.send_originate.return_value = MagicMock(response=ami_response)

        body = dict(self.body, room="8842")
        resp = self.client.post(self.url, body, format="json")

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data["room"], "8842")
        for call in mock_ami.send_originate.call_args_list:
            self.assertEqual(call.kwargs["exten"], "8842")

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface")
    def test_conference_partial_failure_reported_per_party(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ok_response = MagicMock()
        ok_response.is_error.return_value = False
        ok_response.keys = {"Message": "queued"}
        error_response = MagicMock()
        error_response.is_error.return_value = True
        error_response.keys = {"Message": "Extension does not exist"}
        mock_ami.send_originate.side_effect = [
            MagicMock(response=ok_response),
            MagicMock(response=error_response),
            MagicMock(response=None),
        ]

        resp = self.client.post(self.url, self.body, format="json")

        self.assertEqual(resp.status_code, 202)
        results = resp.data["results"]
        self.assertTrue(results[0]["queued"])
        self.assertFalse(results[1]["queued"])
        self.assertEqual(results[1]["detail"], "Extension does not exist")
        self.assertFalse(results[2]["queued"])
        self.assertEqual(results[2]["detail"], "AMI originate timed out.")

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.calls.AsteriskManagementInterface", side_effect=Exception("no ami"))
    def test_ami_unavailable(self, _mock):
        self._auth()
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)


class RecordingsApiTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.settings_override = override_settings(
            ASTERISK_MONITOR_DIR=self.tmpdir.name, ASTERISK_BACKUP_MONITOR_DIR=""
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def _write_recording(self, relative_path, content=b"RIFFaudio"):
        path = os.path.join(self.tmpdir.name, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_requires_auth(self):
        self.client.credentials()
        resp = self.client.get("/api/v1/recordings/123.456/")
        self.assertEqual(resp.status_code, 401)

    def test_legacy_recording_served_with_token(self):
        self._write_recording("123.456.wav")
        resp = self.client.get("/api/v1/recordings/123.456/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"RIFFaudio")

    def test_new_style_recording_served_via_monitor_filenames(self):
        self._write_recording("2026/07/21/10_00_00_100_200.wav")
        MonitorFilenames.objects.create(
            src="100",
            dst="200",
            filename="2026/07/21/10_00_00_100_200",
            cdr_uniqueid="123.456",
        )
        resp = self.client.get("/api/v1/recordings/123.456/")
        self.assertEqual(resp.status_code, 200)

    def test_missing_recording_404(self):
        resp = self.client.get("/api/v1/recordings/123.456/")
        self.assertEqual(resp.status_code, 404)

    def test_invalid_uniqueid_404(self):
        resp = self.client.get("/api/v1/recordings/not-a-uniqueid/")
        self.assertEqual(resp.status_code, 404)


class QueueMemberPauseApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="queuetester", password="x"
        )
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("queue_member_pause")
        self.body = {"interface": "PJSIP/101", "paused": True}

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_requires_auth(self):
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_invalid_interface_rejected(self):
        self._auth()
        resp = self.client.post(
            self.url, {"interface": "PJSIP/101\r\nBAD", "paused": True}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_paused_rejected(self):
        self._auth()
        resp = self.client.post(self.url, {"interface": "PJSIP/101"}, format="json")
        self.assertEqual(resp.status_code, 400)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_pause_success(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = False
        mock_ami.queue_pause.return_value = ami_response

        resp = self.client.post(self.url, self.body, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "paused")
        mock_ami.queue_pause.assert_called_once_with(
            interface="PJSIP/101", paused=True, queue=None
        )
        mock_ami_cls.return_value.__exit__.assert_called_once()

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_unpause_passes_queue_when_given(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = False
        mock_ami.queue_pause.return_value = ami_response

        body = {"interface": "PJSIP/101", "paused": False, "queue": "support"}
        resp = self.client.post(self.url, body, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "unpaused")
        mock_ami.queue_pause.assert_called_once_with(
            interface="PJSIP/101", paused=False, queue="support"
        )

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_interface_not_found_404(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = True
        ami_response.keys = {"Message": "Interface not found"}
        mock_ami.queue_pause.return_value = ami_response

        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 404)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_ami_error_502(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        ami_response = MagicMock()
        ami_response.is_error.return_value = True
        ami_response.keys = {"Message": "Some other AMI failure"}
        mock_ami.queue_pause.return_value = ami_response

        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_timeout_none_502(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        mock_ami.queue_pause.return_value = None

        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface", side_effect=Exception("no ami"))
    def test_ami_unavailable(self, _mock):
        self._auth()
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="without_asterisk_on_localhost")
    def test_asterisk_disabled_503(self):
        self._auth()
        resp = self.client.post(self.url, self.body, format="json")
        self.assertEqual(resp.status_code, 503)


class QueueMemberListApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="queuelisttester", password="x"
        )
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("queue_members")

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_requires_auth(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_list_maps_ami_events(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        event = MagicMock()
        event.keys = {
            "Queue": "support",
            "Name": "PJSIP/101",
            "Location": "PJSIP/101",
            "StateInterface": "PJSIP/101",
            "Membership": "static",
            "Penalty": "0",
            "CallsTaken": "3",
            "LastCall": "0",
            "InCall": "0",
            "Status": "1",
            "Paused": "1",
        }
        mock_ami.queue_members.return_value = [event]

        resp = self.client.get(self.url, {"queue": "support"})

        self.assertEqual(resp.status_code, 200)
        mock_ami.queue_members.assert_called_once_with(queue="support")
        member = resp.data["members"][0]
        self.assertEqual(member["queue"], "support")
        self.assertEqual(member["calls_taken"], 3)
        self.assertTrue(member["paused"])
        self.assertFalse(member["in_call"])

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_list_without_queue_param(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        mock_ami.queue_members.return_value = []

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["members"], [])
        mock_ami.queue_members.assert_called_once_with(queue=None)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface", side_effect=Exception("no ami"))
    def test_ami_unavailable(self, _mock):
        self._auth()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 502)

    @override_settings(DEVMODE="Development")
    @patch("apps.api.views.queues.AsteriskManagementInterface")
    def test_blank_queue_param_collapses_to_none(self, mock_ami_cls):
        self._auth()
        mock_ami = mock_ami_cls.return_value.__enter__.return_value
        mock_ami.queue_members.return_value = []

        resp = self.client.get(self.url, {"queue": ""})

        self.assertEqual(resp.status_code, 200)
        mock_ami.queue_members.assert_called_once_with(queue=None)

    @override_settings(DEVMODE="without_asterisk_on_localhost")
    def test_asterisk_disabled_503(self):
        self._auth()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 503)
