import importlib
import os
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import TestCase

import config.settings.base as base_settings


class AccountsSettingsTests(TestCase):
    def test_custom_user_is_configured_and_migrations_are_current(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        output = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=output, verbosity=1)
        self.assertIn("No changes detected", output.getvalue())

    def test_admin_url_validation(self):
        for value in ("/internal-admin/", "internal-admin"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"DJANGO_ADMIN_URL": value}
            ):
                with self.assertRaises(ImproperlyConfigured):
                    importlib.reload(base_settings)
        importlib.reload(base_settings)
