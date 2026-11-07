from django.conf import settings
from django.db import connection
from django.test import TestCase


class DatabaseConnectivityTests(TestCase):
    def test_postgresql_connection_and_atomic_requests_setting(self):
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
        self.assertIs(settings.DATABASES["default"]["ATOMIC_REQUESTS"], False)
