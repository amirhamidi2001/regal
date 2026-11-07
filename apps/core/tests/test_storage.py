import importlib
import os
import sys
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from storages.backends.s3 import S3Storage

DATABASE_ENV = {
    "POSTGRES_DB": "regal",
    "POSTGRES_USER": "regal",
    "POSTGRES_PASSWORD": "dummy",
    "POSTGRES_HOST": "localhost",
}
VALID_PROD_ENV = {
    **DATABASE_ENV,
    "DJANGO_SECRET_KEY": "s" * 64,
    "DJANGO_ALLOWED_HOSTS": "example.com",
    "DJANGO_SECURE_SSL": "false",
    "S3_ENDPOINT_URL": "https://s3.example.com",
    "S3_ACCESS_KEY_ID": "placeholder-key",
    "S3_SECRET_ACCESS_KEY": "placeholder-secret",
    "S3_BUCKET_NAME": "regal-media",
    "S3_PUBLIC_BASE_URL": "https://media.example.com",
    "S3_REGION_NAME": "",
    "S3_ADDRESSING_STYLE": "auto",
}
REQUIRED_S3_ENV = (
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_BUCKET_NAME",
    "S3_PUBLIC_BASE_URL",
)


class MediaStorageSettingsTests(SimpleTestCase):
    def import_fresh_settings(self, module_name, environment):
        with patch.dict(os.environ, environment, clear=True):
            sys.modules.pop(module_name, None)
            base = importlib.import_module("config.settings.base")
            importlib.reload(base)
            return importlib.import_module(module_name)

    def test_prod_storage_uses_public_unsigned_s3_urls(self):
        prod_settings = self.import_fresh_settings("config.settings.prod", VALID_PROD_ENV)
        self.assertEqual(
            prod_settings.STORAGES["default"]["BACKEND"], "storages.backends.s3.S3Storage"
        )
        self.assertTrue(prod_settings.MEDIA_URL.endswith("/"))
        options = prod_settings.STORAGES["default"]["OPTIONS"]
        self.assertNotIn("region_name", options)
        self.assertFalse(options["querystring_auth"])
        storage = S3Storage(**options)
        self.assertEqual(
            storage.url("folder/image.jpg"),
            "https://media.example.com/folder/image.jpg",
        )

    def test_each_required_s3_environment_variable_is_enforced(self):
        for name in REQUIRED_S3_ENV:
            environment = {key: value for key, value in VALID_PROD_ENV.items() if key != name}
            with self.subTest(name=name), self.assertRaisesRegex(
                ImproperlyConfigured, name
            ):
                self.import_fresh_settings("config.settings.prod", environment)

    def test_dev_uses_filesystem_storage(self):
        dev_settings = self.import_fresh_settings("config.settings.dev", DATABASE_ENV)
        self.assertEqual(
            dev_settings.STORAGES["default"]["BACKEND"],
            "django.core.files.storage.FileSystemStorage",
        )
