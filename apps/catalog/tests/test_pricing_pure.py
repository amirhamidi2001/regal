from dataclasses import FrozenInstanceError
from decimal import Decimal

from django.test import SimpleTestCase

from apps.catalog.constants import MAX_BASE_PRICE, MAX_QUANTITY
from apps.catalog.pricing import (
    InvalidQuantity,
    InvalidTierSet,
    Quote,
    TierSpec,
    compute_unit_price,
    default_tier_specs,
    quote_from_specs,
    validate_tier_specs,
)


class PurePricingTests(SimpleTestCase):
    def test_default_tiers_and_literal_quotes(self):
        specs = default_tier_specs()
        expected = (
            (1, Decimal("4"), 104000, 104000),
            (10, Decimal("4"), 104000, 1040000),
            (11, Decimal("3"), 103000, 1133000),
            (100, Decimal("3"), 103000, 10300000),
            (101, Decimal("2"), 102000, 10302000),
            (1000, Decimal("2"), 102000, 102000000),
            (1001, Decimal("2"), 102000, 102102000),
            (1500, Decimal("2"), 102000, 153000000),
        )
        for quantity, markup, unit_price, line_total in expected:
            with self.subTest(quantity=quantity):
                quote = quote_from_specs(100000, specs, quantity)
                self.assertEqual(quote.base_price, 100000)
                self.assertEqual(quote.quantity, quantity)
                self.assertEqual(quote.markup_percent, markup)
                self.assertEqual(quote.unit_price, unit_price)
                self.assertEqual(quote.line_total, line_total)

    def test_default_quantity_totals(self):
        for quantity, expected_total in (
            (5, 520000),
            (50, 5150000),
            (200, 20400000),
            (1500, 153000000),
        ):
            with self.subTest(quantity=quantity):
                self.assertEqual(quote_from_specs(100000, default_tier_specs(), quantity).line_total, expected_total)

    def test_maximum_quantity_is_accepted(self):
        quote = quote_from_specs(100000, default_tier_specs(), MAX_QUANTITY)
        self.assertEqual(quote.quantity, 1_000_000)
        self.assertEqual(quote.unit_price, 102000)
        self.assertEqual(quote.line_total, 102000000000)

    def test_invalid_quantities(self):
        for quantity in (MAX_QUANTITY + 1, 0, -1, True, "5", 5.0):
            with self.subTest(quantity=quantity), self.assertRaises(InvalidQuantity):
                quote_from_specs(100000, default_tier_specs(), quantity)

    def test_rounding_examples(self):
        examples = (
            (99999, Decimal("4"), 103999),
            (12345, Decimal("3"), 12715),
            (10, Decimal("5"), 11),
            (50, Decimal("3"), 52),
            (1000, Decimal("2.5"), 1025),
            (1, Decimal("4"), 1),
            (12345, Decimal("0"), 12345),
            (MAX_BASE_PRICE, Decimal("4"), 104000000000),
        )
        for base_price, markup, expected in examples:
            with self.subTest(base_price=base_price, markup=markup):
                self.assertEqual(compute_unit_price(base_price, markup), expected)

    def test_float_markup_is_rejected_by_unit_price_calculation(self):
        with self.assertRaises(TypeError):
            compute_unit_price(100, 4.0)

    def test_unit_price_rejects_invalid_base_prices(self):
        for base_price in (True, 100.0):
            with self.subTest(base_price=base_price), self.assertRaises(TypeError):
                compute_unit_price(base_price, Decimal("4"))
        for base_price in (0, -1):
            with self.subTest(base_price=base_price), self.assertRaises(ValueError):
                compute_unit_price(base_price, Decimal("4"))

    def test_valid_tier_shapes_and_order_independence(self):
        defaults = default_tier_specs()
        self.assertEqual(validate_tier_specs(defaults), defaults)
        self.assertEqual(validate_tier_specs(tuple(reversed(defaults))), defaults)
        one = (TierSpec(1, None, Decimal("0")),)
        self.assertEqual(validate_tier_specs(one), one)

    def assert_invalid(self, specs, code):
        with self.assertRaises(InvalidTierSet) as caught:
            validate_tier_specs(specs)
        self.assertIn(code, [problem_code for problem_code, _message in caught.exception.problems])

    def test_invalid_tier_shapes(self):
        d = Decimal
        cases = (
            ([], "empty_tier_set"),
            ((TierSpec(True, None, d("4")),), "not_integer"),
            ((TierSpec(1, 10, d("4")), TierSpec(12, None, d("3"))), "gap_between_tiers"),
            ((TierSpec(1, 10, d("4")), TierSpec(10, 20, d("3")), TierSpec(21, None, d("2"))), "overlapping_tiers"),
            ((TierSpec(1, 10, d("4")), TierSpec(1, None, d("3"))), "overlapping_tiers"),
            ((TierSpec(1, None, d("4")), TierSpec(2, None, d("3"))), "multiple_unlimited_tiers"),
            ((TierSpec(1, 10, d("4")), TierSpec(11, None, d("3")), TierSpec(12, 20, d("2"))), "unlimited_tier_not_last"),
            ((TierSpec(1, 10, d("4")), TierSpec(11, 20, d("3"))), "unlimited_tier_missing"),
            ((TierSpec(1, 10, d("4")), TierSpec(11, 10, d("3"))), "max_below_min"),
            ((TierSpec(0, None, d("4")),), "min_below_one"),
            ((TierSpec(1, None, d("-0.01")),), "markup_negative"),
            ((TierSpec(1, None, d("1000")),), "markup_too_large"),
            ((TierSpec(1, None, d("1.001")),), "markup_too_many_decimals"),
            ((TierSpec(1, None, 4.0),), "markup_not_decimal"),
        )
        for specs, code in cases:
            with self.subTest(code=code, specs=specs):
                self.assert_invalid(specs, code)

    def test_first_tier_must_start_at_one(self):
        self.assert_invalid((TierSpec(2, None, Decimal("4")),), "first_tier_must_start_at_1")

    def test_tier_validation_reports_all_independent_problems(self):
        with self.assertRaises(InvalidTierSet) as caught:
            validate_tier_specs((TierSpec(2, 5, Decimal("4")), TierSpec(8, None, Decimal("3"))))
        codes = [code for code, _message in caught.exception.problems]
        self.assertIn("first_tier_must_start_at_1", codes)
        self.assertIn("gap_between_tiers", codes)
        self.assertIn("; ", str(caught.exception))

    def test_same_quantity_can_quote_different_variants_independently(self):
        first_specs = (TierSpec(1, None, Decimal("4")),)
        second_specs = (TierSpec(1, None, Decimal("3")),)
        self.assertEqual(quote_from_specs(100000, first_specs, 1).unit_price, 104000)
        self.assertEqual(quote_from_specs(100000, second_specs, 1).unit_price, 103000)

    def test_quote_is_immutable(self):
        quote = Quote(100, 1, Decimal("4"), 104, 104)
        with self.assertRaises(FrozenInstanceError):
            quote.unit_price = 103
