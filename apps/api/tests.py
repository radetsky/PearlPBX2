from django.contrib.auth import get_user_model
from django.utils.timezone import now, timedelta
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

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
        import uuid

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
        import uuid

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
        import uuid

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
