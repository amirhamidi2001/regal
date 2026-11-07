from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.validators import (
    MOBILE_PATTERN,
    normalize_mobile,
    normalize_postal_code,
    validate_mobile,
    validate_postal_code,
)


class MobileValidationTests(SimpleTestCase):
    def test_mobile_normalization(self):
        accepted = (
            "09123456789",
            "9123456789",
            "+989123456789",
            "00989123456789",
            "989123456789",
            "۰۹۱۲۳۴۵۶۷۸۹",
            "٠٩١٢٣٤٥٦٧٨٩",
            "0912 345 6789",
            "0912-345-6789",
        )
        for value in accepted:
            with self.subTest(value=value):
                self.assertEqual(normalize_mobile(value), "09123456789")

    def test_mobile_normalization_rejects_invalid_values(self):
        rejected = ("", "0912345678", "091234567890", "02112345678", "08123456789", "abc", None)
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as caught:
                    normalize_mobile(value)
                self.assertEqual(caught.exception.code, "invalid_mobile")

    def test_validator_requires_canonical_mobile(self):
        self.assertEqual(MOBILE_PATTERN, r"^09[0-9]{9}$")
        validate_mobile("09123456789")
        with self.assertRaises(ValidationError):
            validate_mobile("۰۹۱۲۳۴۵۶۷۸۹")


class PostalCodeValidationTests(SimpleTestCase):
    def test_postal_code_normalization_and_validation(self):
        for value in ("1234567890", "۱۲۳۴۵۶۷۸۹۰", "12345-67890"):
            with self.subTest(value=value):
                self.assertEqual(normalize_postal_code(value), "1234567890")
                validate_postal_code(value)

    def test_postal_code_rejects_invalid_values(self):
        for value in ("0123456789", "123456789"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as caught:
                    validate_postal_code(value)
                self.assertEqual(caught.exception.code, "invalid_postal_code")
