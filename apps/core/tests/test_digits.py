from django.test import SimpleTestCase

from apps.core.digits import normalize_digits, to_persian_digits


class DigitConversionTests(SimpleTestCase):
    def test_normalize_persian_and_arabic_indic_digits(self):
        self.assertEqual(normalize_digits("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"), "01234567890123456789")

    def test_normalize_leaves_other_characters_unchanged(self):
        self.assertEqual(normalize_digits("ریال - ۱۲٣/a"), "ریال - 123/a")

    def test_to_persian_digits_uses_string_value(self):
        self.assertEqual(to_persian_digits(123), "۱۲۳")
        self.assertEqual(to_persian_digits("A-09"), "A-۰۹")
