from datetime import date, datetime, timezone as datetime_timezone

from django.test import SimpleTestCase

from apps.core.jalali import format_jalali_date, format_jalali_datetime, to_jalali


class JalaliDisplayTests(SimpleTestCase):
    def test_numeric_and_long_date_formats(self):
        value = date(2026, 11, 4)
        self.assertEqual(format_jalali_date(value), "۱۴۰۵/۰۸/۱۳")
        self.assertEqual(format_jalali_date(value, style="long"), "۱۳ آبان ۱۴۰۵")

    def test_datetime_is_converted_to_tehran_before_formatting(self):
        value = datetime(2026, 3, 20, 20, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(format_jalali_date(value), "۱۴۰۵/۰۱/۰۱")
        self.assertEqual(format_jalali_datetime(value), "۱۴۰۵/۰۱/۰۱ ۰۰:۰۰")
        self.assertEqual(str(to_jalali(value)), "1405-01-01")

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            to_jalali(datetime(2026, 3, 20, 20, 30))

    def test_unknown_style_is_rejected(self):
        with self.assertRaises(ValueError):
            format_jalali_date(date(2026, 11, 4), style="short")
