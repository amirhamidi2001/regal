import os
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User


class UserModelTests(TestCase):
    def test_save_normalizes_mobile_and_sets_timestamps(self):
        user = User.objects.create_user("9123456789")
        self.assertEqual(user.mobile, "09123456789")
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)
        self.assertEqual(str(user), "09123456789")
        self.assertEqual(user.get_full_name(), "09123456789")
        self.assertEqual(user.get_short_name(), "09123456789")

        international_user = User.objects.create_user("+989123456780", full_name="Amir")
        self.assertEqual(international_user.mobile, "09123456780")
        self.assertEqual(international_user.get_full_name(), "Amir")
        self.assertEqual(international_user.get_short_name(), "Amir")

    def test_manager_password_and_authentication_behavior(self):
        passwordless = User.objects.create_user("09123456789")
        self.assertFalse(passwordless.has_usable_password())
        self.assertIsNone(authenticate(mobile=passwordless.mobile, password="any-password"))

        user = User.objects.create_user("09123456780", password="A-strong-test-password-123")
        self.assertTrue(user.has_usable_password())
        self.assertEqual(
            authenticate(mobile=user.mobile, password="A-strong-test-password-123"), user
        )

    def test_create_superuser_flags_and_requires_password(self):
        superuser = User.objects.create_superuser(
            "09123456789",
            password="A-strong-test-password-123",
            is_staff=False,
            is_superuser=False,
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        with self.assertRaises(ValueError):
            User.objects.create_superuser("09123456780")

    def test_duplicate_normalized_mobile_raises_integrity_error(self):
        User.objects.create_user("09123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user("+989123456789")

    def test_database_constraint_rejects_bulk_created_non_mobile(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.bulk_create([User(mobile=123)])

    def test_createsuperuser_command_uses_environment_password(self):
        with patch.dict(os.environ, {"DJANGO_SUPERUSER_PASSWORD": "A-strong-test-password-123"}):
            call_command(
                "createsuperuser",
                interactive=False,
                mobile="09123456789",
                full_name="Admin",
                verbosity=0,
            )
        user = User.objects.get(mobile="09123456789")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("A-strong-test-password-123"))
