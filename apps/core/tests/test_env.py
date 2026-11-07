import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.env import env_bool, env_int, env_list, env_str


class EnvironmentHelpersTests(SimpleTestCase):
    def test_env_str(self):
        with patch.dict(os.environ, {"VALUE": "hello"}, clear=True):
            self.assertEqual(env_str("VALUE"), "hello")
            self.assertEqual(env_str("MISSING", default="fallback"), "fallback")

    def test_env_str_required_rejects_missing_and_empty(self):
        for environment in ({}, {"VALUE": ""}):
            with self.subTest(environment=environment), patch.dict(
                os.environ, environment, clear=True
            ):
                with self.assertRaisesRegex(ImproperlyConfigured, "VALUE"):
                    env_str("VALUE", required=True)

    def test_env_bool_values_and_default(self):
        for value in ("true", "TRUE", "1", "Yes"):
            with patch.dict(os.environ, {"VALUE": value}, clear=True):
                self.assertIs(env_bool("VALUE"), True)
        for value in ("false", "FALSE", "0", "No"):
            with patch.dict(os.environ, {"VALUE": value}, clear=True):
                self.assertIs(env_bool("VALUE", default=True), False)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(env_bool("VALUE", default=True), True)

    def test_env_bool_rejects_invalid_value(self):
        with patch.dict(os.environ, {"VALUE": "sometimes"}, clear=True):
            with self.assertRaisesRegex(ImproperlyConfigured, "VALUE"):
                env_bool("VALUE")

    def test_env_int(self):
        with patch.dict(os.environ, {"VALUE": "42"}, clear=True):
            self.assertEqual(env_int("VALUE"), 42)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(env_int("VALUE", default=9), 9)

    def test_env_int_rejects_invalid_value(self):
        with patch.dict(os.environ, {"VALUE": "four"}, clear=True):
            with self.assertRaisesRegex(ImproperlyConfigured, "VALUE"):
                env_int("VALUE")

    def test_env_list(self):
        with patch.dict(os.environ, {"VALUE": " a, ,b ,, c "}, clear=True):
            self.assertEqual(env_list("VALUE"), ["a", "b", "c"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(env_list("VALUE", default=("fallback",)), ["fallback"])
