from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            "09123456789", password="A-strong-test-password-123", full_name="Admin"
        )

    def test_superuser_can_open_admin_pages(self):
        self.client.force_login(self.admin_user)
        for url in (
            reverse("admin:index"),
            reverse("admin:accounts_user_changelist"),
            reverse("admin:accounts_user_add"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_admin_client_is_redirected_to_login(self):
        response = self.client.get(f"/{settings.ADMIN_URL}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
