from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import SimpleTestCase

from apps.core.geo import (
    canonical_location,
    get_cities,
    get_provinces,
    load_geo,
    normalize_location_text,
)

CAPITALS = (
    ("آذربایجان شرقی", "تبریز"),
    ("آذربایجان غربی", "ارومیه"),
    ("اردبیل", "اردبیل"),
    ("اصفهان", "اصفهان"),
    ("البرز", "کرج"),
    ("ایلام", "ایلام"),
    ("بوشهر", "بوشهر"),
    ("تهران", "تهران"),
    ("چهارمحال و بختیاری", "شهرکرد"),
    ("خراسان جنوبی", "بیرجند"),
    ("خراسان رضوی", "مشهد"),
    ("خراسان شمالی", "بجنورد"),
    ("خوزستان", "اهواز"),
    ("زنجان", "زنجان"),
    ("سمنان", "سمنان"),
    ("سیستان و بلوچستان", "زاهدان"),
    ("فارس", "شیراز"),
    ("قزوین", "قزوین"),
    ("قم", "قم"),
    ("کردستان", "سنندج"),
    ("کرمان", "کرمان"),
    ("کرمانشاه", "کرمانشاه"),
    ("کهگیلویه و بویراحمد", "یاسوج"),
    ("گلستان", "گرگان"),
    ("گیلان", "رشت"),
    ("لرستان", "خرم‌آباد"),
    ("مازندران", "ساری"),
    ("مرکزی", "اراک"),
    ("هرمزگان", "بندرعباس"),
    ("همدان", "همدان"),
    ("یزد", "یزد"),
)


class IranGeoTests(SimpleTestCase):
    def test_dataset_has_31_provinces_and_non_empty_city_lists(self):
        data = load_geo()
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(get_provinces()), 31)
        self.assertTrue(all(get_cities(province) for province in get_provinces()))
        self.assertEqual(sum(len(entry["cities"]) for entry in data["provinces"]), 31)

    def test_all_province_capital_pairs_are_canonical(self):
        for province, capital in CAPITALS:
            with self.subTest(province=province):
                self.assertEqual(canonical_location(province, capital), (province, capital))

    def test_text_variants_resolve_to_canonical_pairs(self):
        self.assertEqual(normalize_location_text("  آذربايجان   شرقي  "), "آذربایجان شرقی")
        self.assertEqual(canonical_location("آذربايجان شرقي", "تبریز"), ("آذربایجان شرقی", "تبریز"))
        self.assertEqual(canonical_location("كرمان", "كرمان"), ("کرمان", "کرمان"))
        self.assertEqual(canonical_location(" اصفهان ", "  اصفهان  "), ("اصفهان", "اصفهان"))
        self.assertEqual(canonical_location("لرستان", "خرم آباد"), ("لرستان", "خرم‌آباد"))
        self.assertEqual(canonical_location("لرستان", "خرم‌آباد"), ("لرستان", "خرم‌آباد"))

    def test_invalid_province_and_city_errors_have_codes(self):
        cases = (
            (("استان ناشناخته", "تهران"), "invalid_province"),
            (("تهران", "شهر ناشناخته"), "invalid_city"),
            (("تهران", "شیراز"), "invalid_city"),
        )
        for args, expected_code in cases:
            with self.subTest(args=args), self.assertRaises(ValidationError) as caught:
                canonical_location(*args)
            self.assertEqual(caught.exception.code, expected_code)

        with self.assertRaises(ValidationError) as caught:
            get_cities("استان ناشناخته")
        self.assertEqual(caught.exception.code, "invalid_province")

    def test_broken_in_memory_datasets_raise_improperly_configured(self):
        broken_datasets = (
            {
                "version": 1,
                "provinces": [
                    {"name": "تهران", "cities": ["تهران"]},
                    {"name": "تهران", "cities": ["شهر دیگر"]},
                ],
            },
            {"version": 1, "provinces": [{"name": "تهران", "cities": []}]},
        )
        for broken_data in broken_datasets:
            with self.subTest(broken_data=broken_data), patch(
                "apps.core.geo._read_geo_data", return_value=broken_data
            ):
                load_geo.cache_clear()
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        load_geo()
                finally:
                    load_geo.cache_clear()
