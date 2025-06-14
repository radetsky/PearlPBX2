import json
import uuid
from django.test import TestCase, Client
from django.utils.timezone import now, timedelta

from apps.api.models import CustomListNames, CustomListEntries


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
        response = self.client.post("/api/v1/lists/add/",
                                    data=json.dumps({"name": "New List"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.json())

    def test_add_list_missing_name(self):
        response = self.client.post("/api/v1/lists/add/",
                                    data=json.dumps({}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'Missing "name"')

    def test_add_list_invalid_json(self):
        response = self.client.post("/api/v1/lists/add/",
                                    data="Invalid JSON",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'Invalid JSON')

    def test_update_list_success(self):
        response = self.client.post(f"/api/v1/lists/update/{self.list.id}/",
                                    data=json.dumps({"name": "Updated List"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Updated List")

    def test_update_list_not_found(self):
        fake_id = uuid.uuid4()
        response = self.client.post(f"/api/v1/lists/update/{fake_id}/",
                                    data=json.dumps({"name": "Name"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_update_list_missing_name(self):
        response = self.client.post(f"/api/v1/lists/update/{self.list.id}/",
                                    data=json.dumps({}),
                                    content_type="application/json")
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
        entry = CustomListEntries.objects.create(
            list_name=self.list,
            callerid="123",
            destination="456",
            reason="Test",
            expiration_date=now() + timedelta(days=1)
        )
        response = self.client.get(f"/api/v1/lists/{self.list.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["callerid"], "123")


class ListEntryAddViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.list_obj = CustomListNames.objects.create(name="Test List")
        self.base_url = f'/api/v1/lists/{self.list_obj.id}/add/'
        self.valid_payload = {
            "callerid": "123456789",
            "destination": "987654321",
            "reason": "Test reason",
            "expiration_date": (now() + timedelta(days=1)).isoformat()
        }

    def test_successful_entry_creation(self):
        response = self.client.post(
            self.base_url,
            data=json.dumps(self.valid_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['callerid'], self.valid_payload['callerid'])
        self.assertEqual(data['destination'],
                         self.valid_payload['destination'])
        self.assertEqual(data['reason'], self.valid_payload['reason'])
        self.assertTrue('id' in data)

    def test_missing_callerid_returns_400(self):
        payload = self.valid_payload.copy()
        payload['callerid'] = ''
        response = self.client.post(
            self.base_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Missing required fields')

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            self.base_url,
            data='not a valid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid JSON')

    def test_nonexistent_list_returns_404(self):
        fake_uuid = uuid.uuid4()
        url = f'/api/v1/lists/{fake_uuid}/add/'
        response = self.client.post(
            url,
            data=json.dumps(self.valid_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'List not found')

    def test_optional_fields_can_be_empty(self):
        payload = {
            "callerid": "999000",
            "destination": "",
            "reason": "",
            "expiration_date": None
        }
        response = self.client.post(
            self.base_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['callerid'], "999000")
        self.assertEqual(data['destination'], "")
        self.assertEqual(data['reason'], "")
        self.assertIsNone(data['expiration_date'])


class ListEntryRevokeViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.list_obj = CustomListNames.objects.create(name="Test List")
        self.entry_obj = CustomListEntries.objects.create(
            list_name=self.list_obj,
            callerid="12345",
            destination="54321",
            reason="Test Reason",
            expiration_date=None
        )
        self.revoke_url = f'/api/v1/lists/{self.list_obj.id}/revoke/{self.entry_obj.id}/'

    def test_successful_deletion(self):
        response = self.client.delete(self.revoke_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'status': 'deleted',
            'id': str(self.entry_obj.id)
        })
        self.assertFalse(CustomListEntries.objects.filter(
            id=self.entry_obj.id).exists())

    def test_entry_not_found_returns_404(self):
        fake_entry_id = uuid.uuid4()
        url = f'/api/v1/lists/{self.list_obj.id}/revoke/{fake_entry_id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'Entry not found'})

    def test_wrong_list_id_returns_404(self):
        other_list = CustomListNames.objects.create(name="Another List")
        url = f'/api/v1/lists/{other_list.id}/revoke/{self.entry_obj.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'Entry not found'})
