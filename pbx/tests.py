from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class ApplyChangesViewAccessTest(TestCase):
    """Test that /admin/apply is only accessible to superusers."""

    def setUp(self):
        self.client = Client()
        self.apply_url = reverse("apply_changes")

        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )

        self.staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="staffpass123",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="regularpass123",
        )

    def test_anonymous_user_cannot_access_apply(self):
        response = self.client.get(self.apply_url)
        self.assertIn(response.status_code, [302, 403])

    def test_regular_user_cannot_access_apply(self):
        self.client.login(username="regular", password="regularpass123")
        response = self.client.get(self.apply_url)
        self.assertEqual(response.status_code, 403)

    def test_staff_user_cannot_access_apply(self):
        self.client.login(username="staff", password="staffpass123")
        response = self.client.get(self.apply_url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_apply(self):
        self.client.login(username="admin", password="adminpass123")
        response = self.client.get(self.apply_url)
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_post_apply(self):
        self.client.login(username="regular", password="regularpass123")
        response = self.client.post(self.apply_url, {"commit_changes": True})
        self.assertEqual(response.status_code, 403)

    def test_staff_user_cannot_post_apply(self):
        self.client.login(username="staff", password="staffpass123")
        response = self.client.post(self.apply_url, {"commit_changes": True})
        self.assertEqual(response.status_code, 403)
