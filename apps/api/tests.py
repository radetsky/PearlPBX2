import json
import uuid
from django.test import TestCase, Client
from django.utils.timezone import now, timedelta

from apps.api.models import CustomListNames, CustomListEntries

from core.models import Blacklist, Whitelist, Contact


class CustomListViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.list = CustomListNames.objects.create(name="Test List")
        self.entries_url = f"/api/v1/lists/entries/{self.list.id}/"

    def test_get_lists(self):
        response = self.client.get("/api/v1/lists/")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(isinstance(data, list))
        self.assertIn("name", data[0])

    def test_add_list_success(self):
        response = self.client.post(
            "/api/v1/lists/add/",
            data=json.dumps({"name": "New List"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.json())

    def test_add_list_missing_name(self):
        response = self.client.post(
            "/api/v1/lists/add/", data=json.dumps({}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'Missing "name"')

    def test_add_list_invalid_json(self):
        response = self.client.post(
            "/api/v1/lists/add/", data="Invalid JSON", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON")

    def test_update_list_success(self):
        response = self.client.post(
            f"/api/v1/lists/update/{self.list.id}/",
            data=json.dumps({"name": "Updated List"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Updated List")

    def test_update_list_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.post(
            f"/api/v1/lists/update/{fake_id}/",
            data=json.dumps({"name": "Name"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_update_list_missing_name(self):
        response = self.client.post(
            f"/api/v1/lists/update/{self.list.id}/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_revoke_list_success(self):
        response = self.client.delete(f"/api/v1/lists/revoke/{self.list.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")

    def test_revoke_list_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.delete(f"/api/v1/lists/revoke/{fake_id}/")
        self.assertEqual(response.status_code, 404)

    def test_get_list_entries_empty(self):
        response = self.client.get(f"/api/v1/lists/{self.list.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_list_entries_with_data(self):
        CustomListEntries.objects.create(
            list_name=self.list,
            callerid="123",
            destination="456",
            reason="Test",
            expiration_date=now() + timedelta(days=1),
        )
        response = self.client.get(f"/api/v1/lists/{self.list.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["callerid"], "123")


class ListEntryAddViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.list_obj = CustomListNames.objects.create(name="Test List")
        self.base_url = f"/api/v1/lists/{self.list_obj.id}/add/"
        self.valid_payload = {
            "callerid": "123456789",
            "destination": "987654321",
            "reason": "Test reason",
            "expiration_date": (now() + timedelta(days=1)).isoformat(),
        }

    def test_successful_entry_creation(self):
        response = self.client.post(
            self.base_url,
            data=json.dumps(self.valid_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["callerid"], self.valid_payload["callerid"])
        self.assertEqual(data["destination"], self.valid_payload["destination"])
        self.assertEqual(data["reason"], self.valid_payload["reason"])
        self.assertTrue("id" in data)

    def test_missing_callerid_returns_400(self):
        payload = self.valid_payload.copy()
        payload["callerid"] = ""
        response = self.client.post(
            self.base_url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Missing required fields")

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            self.base_url, data="not a valid json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON")

    def test_nonexistent_list_returns_404(self):
        fake_uuid = uuid.uuid4()
        url = f"/api/v1/lists/{fake_uuid}/add/"
        response = self.client.post(
            url, data=json.dumps(self.valid_payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "List not found")

    def test_optional_fields_can_be_empty(self):
        payload = {
            "callerid": "999000",
            "destination": "",
            "reason": "",
            "expiration_date": None,
        }
        response = self.client.post(
            self.base_url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["callerid"], "999000")
        self.assertEqual(data["destination"], "")
        self.assertEqual(data["reason"], "")
        self.assertIsNone(data["expiration_date"])


class ListEntryRevokeViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.list_obj = CustomListNames.objects.create(name="Test List")
        self.entry_obj = CustomListEntries.objects.create(
            list_name=self.list_obj,
            callerid="12345",
            destination="54321",
            reason="Test Reason",
            expiration_date=None,
        )
        self.revoke_url = (
            f"/api/v1/lists/{self.list_obj.id}/revoke/{self.entry_obj.id}/"
        )

    def test_successful_deletion(self):
        response = self.client.delete(self.revoke_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "deleted", "id": str(self.entry_obj.id)}
        )
        self.assertFalse(
            CustomListEntries.objects.filter(id=self.entry_obj.id).exists()
        )

    def test_entry_not_found_returns_404(self):
        fake_entry_id = uuid.uuid4()
        url = f"/api/v1/lists/{self.list_obj.id}/revoke/{fake_entry_id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Entry not found"})

    def test_wrong_list_id_returns_404(self):
        other_list = CustomListNames.objects.create(name="Another List")
        url = f"/api/v1/lists/{other_list.id}/revoke/{self.entry_obj.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Entry not found"})


class BlackListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url_list = "/api/v1/blacklist/"
        self.sample_data = {
            "callerid": "123456789",
            "destination": "987654321",
            "reason": "Spam",
            "expiration_date": (now() + timedelta(days=7)).isoformat(),
        }
        self.blacklist_entry = Blacklist.objects.create(**self.sample_data)
        self.url_detail = f"/api/v1/blacklist/{self.blacklist_entry.id}/"

    def test_get_blacklist(self):
        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertTrue(
            any(item["id"] == str(self.blacklist_entry.id) for item in response.json())
        )

    def test_create_blacklist_entry_success(self):
        new_data = {
            "callerid": "555",
            "destination": "666",
            "reason": "Test block",
            "expiration_date": None,
        }
        response = self.client.post(
            self.url_list, data=json.dumps(new_data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["callerid"], new_data["callerid"])
        self.assertTrue(Blacklist.objects.filter(callerid="555").exists())

    def test_create_blacklist_entry_missing_callerid(self):
        invalid_data = {"destination": "555", "reason": "Test"}
        response = self.client.post(
            self.url_list,
            data=json.dumps(invalid_data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing required fields"})

    def test_create_blacklist_invalid_json(self):
        response = self.client.post(
            self.url_list, data="not a json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON"})

    def test_delete_blacklist_entry_success(self):
        response = self.client.delete(self.url_detail)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")
        self.assertFalse(Blacklist.objects.filter(pk=self.blacklist_entry.id).exists())

    def test_delete_blacklist_entry_not_found(self):
        non_existing_id = uuid.uuid4()
        response = self.client.delete(f"/api/v1/blacklist/{non_existing_id}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Blacklist entry not found"})


class WhiteListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url_list = "/api/v1/whitelist/"
        self.sample_data = {
            "callerid": "111222333",
            "destination": "444555666",
            "reason": "Trusted contact",
            "expiration_date": (now() + timedelta(days=5)).isoformat(),
        }
        self.whitelist_entry = Whitelist.objects.create(**self.sample_data)
        self.url_detail = f"/api/v1/whitelist/{self.whitelist_entry.id}/"

    def test_get_whitelist(self):
        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertTrue(
            any(item["id"] == str(self.whitelist_entry.id) for item in response.json())
        )

    def test_create_whitelist_entry_success(self):
        new_data = {
            "callerid": "777888999",
            "destination": "000111222",
            "reason": "Allowlist test",
            "expiration_date": None,
        }
        response = self.client.post(
            self.url_list, data=json.dumps(new_data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["callerid"], new_data["callerid"])
        self.assertTrue(Whitelist.objects.filter(callerid="777888999").exists())

    def test_create_whitelist_entry_missing_callerid(self):
        invalid_data = {"destination": "123", "reason": "Missing callerid"}
        response = self.client.post(
            self.url_list,
            data=json.dumps(invalid_data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing required fields"})

    def test_create_whitelist_invalid_json(self):
        response = self.client.post(
            self.url_list, data="not a json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON"})

    def test_delete_whitelist_entry_success(self):
        response = self.client.delete(self.url_detail)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")
        self.assertFalse(Whitelist.objects.filter(pk=self.whitelist_entry.id).exists())

    def test_delete_whitelist_entry_not_found(self):
        non_existing_id = uuid.uuid4()
        response = self.client.delete(f"/api/v1/whitelist/{non_existing_id}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Whitelist entry not found"})


class ContactsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url_list = "/api/v1/contacts/"
        self.contact = Contact.objects.create(
            callerid="123456789", name="John Doe", allow_monitor=True
        )
        self.url_detail = f"/api/v1/contacts/{self.contact.id}/"
        self.new_contact_data = {
            "callerid": "987654321",
            "name": "Jane Smith",
            "allow_monitor": False,
        }

    def test_get_contacts_list(self):
        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertTrue(
            any(item["callerid"] == self.contact.callerid for item in response.json())
        )

    def test_create_new_contact_success(self):
        response = self.client.post(
            self.url_list,
            data=json.dumps(self.new_contact_data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["callerid"], self.new_contact_data["callerid"])
        self.assertTrue(
            Contact.objects.filter(callerid=self.new_contact_data["callerid"]).exists()
        )

    def test_update_existing_contact_success(self):
        update_data = {
            "callerid": self.contact.callerid,
            "name": "Updated Name",
            "allow_monitor": False,
        }
        response = self.client.post(
            self.url_list, data=json.dumps(update_data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Updated Name")
        self.assertFalse(data["allow_monitor"])
        self.assertEqual(data["callerid"], self.contact.callerid)

    def test_create_contact_missing_fields(self):
        bad_data = {"name": "No Caller ID"}
        response = self.client.post(
            self.url_list, data=json.dumps(bad_data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing required fields"})

    def test_create_contact_invalid_json(self):
        response = self.client.post(
            self.url_list, data="not a valid json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON"})

    def test_delete_contact_success(self):
        response = self.client.delete(self.url_detail)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")
        self.assertFalse(Contact.objects.filter(pk=self.contact.id).exists())

    def test_delete_contact_not_found(self):
        non_existing_id = uuid.uuid4()
        response = self.client.delete(f"/api/v1/contacts/{non_existing_id}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Contact not found"})
