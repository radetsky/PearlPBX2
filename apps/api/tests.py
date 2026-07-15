import uuid

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now, timedelta
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from unittest.mock import patch, MagicMock

from apps.api.models import CustomListNames, CustomListEntries
from core.models import Blacklist, Whitelist, Contact


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
