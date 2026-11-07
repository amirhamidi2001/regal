import importlib
import os
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured


BASE_ENV = {
    "POSTGRES_DB": "regal",
    "POSTGRES_USER": "regal",
    "POSTGRES_PASSWORD": "dummy",
    "POSTGRES_HOST": "localhost",
}
VALID_PROD_ENV = {
    **BASE_ENV,
    "DJANGO_SECRET_KEY": "s" * 64,
    "DJANGO_ALLOWED_HOSTS": "example.com",
    "S3_ENDPOINT_URL": "https://s3.example.com",
    "S3_ACCESS_KEY_ID": "placeholder-key",
    "S3_SECRET_ACCESS_KEY": "placeholder-secret",
    "S3_BUCKET_NAME": "regal-media",
    "S3_PUBLIC_BASE_URL": "https://media.example.com",
}


class SettingsTests(TestCase):
    def load_fresh(self, module_name, environment):
        with patch.dict(os.environ, environment, clear=True):
            sys.modules.pop(module_name, None)
            importlib.reload(importlib.import_module("config.settings.base"))
            return importlib.import_module(module_name)

    def test_prod_rejects_missing_secret_key(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            self.load_fresh("config.settings.prod", {**BASE_ENV, "DJANGO_ALLOWED_HOSTS": "example.com"})

    def test_prod_rejects_short_secret_key(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            self.load_fresh(
                "config.settings.prod",
                {**BASE_ENV, "DJANGO_SECRET_KEY": "short", "DJANGO_ALLOWED_HOSTS": "example.com"},
            )

    def test_prod_rejects_placeholder_secret_key(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            self.load_fresh(
                "config.settings.prod",
                {**BASE_ENV, "DJANGO_SECRET_KEY": "dev-only-" + "x" * 60, "DJANGO_ALLOWED_HOSTS": "example.com"},
            )

    def test_prod_rejects_missing_allowed_hosts(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS"):
            self.load_fresh(
                "config.settings.prod", {**BASE_ENV, "DJANGO_SECRET_KEY": "s" * 64}
            )

    def test_prod_defaults_and_ssl_override(self):
        settings = self.load_fresh("config.settings.prod", VALID_PROD_ENV)
        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        settings = self.load_fresh(
            "config.settings.prod", {**VALID_PROD_ENV, "DJANGO_SECURE_SSL": "false"}
        )
        self.assertFalse(settings.SECURE_SSL_REDIRECT)

    def test_dev_settings_import(self):
        settings = self.load_fresh("config.settings.dev", BASE_ENV)
        self.assertTrue(settings.DEBUG)
        self.assertEqual(settings.ALLOWED_HOSTS, ["localhost", "127.0.0.1", "[::1]"])
