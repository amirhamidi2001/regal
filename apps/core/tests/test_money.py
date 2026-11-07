from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.money import format_number, format_toman


class MoneyDisplayTests(SimpleTestCase):
    def test_format_number(self):
        self.assertEqual(format_number(104000), "۱۰۴٬۰۰۰")
        self.assertEqual(format_number(1234567), "۱٬۲۳۴٬۵۶۷")
        self.assertEqual(format_number(-5000), "-۵٬۰۰۰")

    def test_format_toman(self):
        self.assertEqual(format_toman(104000), "۱۰۴٬۰۰۰ تومان")
        self.assertEqual(format_toman(0), "۰ تومان")

    def test_non_ints_are_rejected(self):
        for value in (12.5, Decimal("12.5"), True, "12"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    format_number(value)
                with self.assertRaises(TypeError):
                    format_toman(value)
