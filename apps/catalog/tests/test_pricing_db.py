from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import PricingTier, ProductVariant
from apps.catalog.pricing import (
    InvalidTierSet,
    TierSpec,
    has_valid_pricing,
    quote,
    replace_pricing_tiers,
)
from apps.catalog.tests.helpers import make_product, make_variant


class DatabasePricingTests(TestCase):
    def test_defaults_create_four_tiers_and_quote_each_boundary(self):
        variant = make_variant(base_price=100000)
        tiers = replace_pricing_tiers(variant)
        self.assertEqual(len(tiers), 4)

        expected = (
            (1, Decimal("4"), 104000, 104000),
            (10, Decimal("4"), 104000, 1040000),
            (11, Decimal("3"), 103000, 1133000),
            (100, Decimal("3"), 103000, 10300000),
            (101, Decimal("2"), 102000, 10302000),
            (1000, Decimal("2"), 102000, 102000000),
            (1001, Decimal("2"), 102000, 102102000),
        )
        for quantity, markup, unit_price, line_total in expected:
            with self.subTest(quantity=quantity):
                result = quote(variant, quantity)
                self.assertEqual(result.markup_percent, markup)
                self.assertEqual(result.unit_price, unit_price)
                self.assertEqual(result.line_total, line_total)

    def test_variants_of_one_product_use_independent_prices_and_tiers(self):
        product = make_product()
        first = make_variant(product=product, base_price=100000)
        second = make_variant(product=product, base_price=200000)
        replace_pricing_tiers(
            first,
            (TierSpec(1, 10, Decimal("4")), TierSpec(11, None, Decimal("3"))),
        )
        replace_pricing_tiers(
            second,
            (TierSpec(1, 20, Decimal("5")), TierSpec(21, None, Decimal("2"))),
        )

        first_at_twelve = quote(first, 12)
        second_at_twelve = quote(second, 12)
        self.assertEqual((first_at_twelve.markup_percent, first_at_twelve.unit_price), (Decimal("3"), 103000))
        self.assertEqual((second_at_twelve.markup_percent, second_at_twelve.unit_price), (Decimal("5"), 210000))

        cart_quotes = [quote(variant, 6) for variant in (first, second)]
        self.assertEqual(
            [(result.markup_percent, result.unit_price) for result in cart_quotes],
            [(Decimal("4"), 104000), (Decimal("5"), 210000)],
        )

    def test_quote_uses_one_query_and_prefetched_tiers_use_none(self):
        variant = make_variant(base_price=100000)
        replace_pricing_tiers(variant)

        fresh = ProductVariant.objects.get(pk=variant.pk)
        with self.assertNumQueries(1):
            quote(fresh, 1)

        prefetched = ProductVariant.objects.prefetch_related("pricing_tiers").get(pk=variant.pk)
        list(prefetched.pricing_tiers.all())
        with self.assertNumQueries(0):
            quote(prefetched, 1)

    def test_invalid_replacements_do_not_query_or_change_existing_rows(self):
        variant = make_variant()
        replace_pricing_tiers(
            variant,
            (TierSpec(1, 10, Decimal("4")), TierSpec(11, None, Decimal("3"))),
        )
        before = list(
            PricingTier.objects.filter(variant=variant)
            .order_by("min_quantity")
            .values_list("id", "min_quantity", "max_quantity", "markup_percent")
        )
        invalid_sets = (
            (TierSpec(1, 10, Decimal("4")), TierSpec(12, None, Decimal("3"))),
            (TierSpec(1, 10, Decimal("4")), TierSpec(10, None, Decimal("3"))),
        )

        for specs in invalid_sets:
            with self.subTest(specs=specs), self.assertNumQueries(0):
                with self.assertRaises(InvalidTierSet):
                    replace_pricing_tiers(variant, specs)

        after = list(
            PricingTier.objects.filter(variant=variant)
            .order_by("min_quantity")
            .values_list("id", "min_quantity", "max_quantity", "markup_percent")
        )
        self.assertEqual(after, before)

    def test_valid_replacement_swaps_the_complete_set(self):
        variant = make_variant()
        old = replace_pricing_tiers(variant)
        replacement = (
            TierSpec(1, 5, Decimal("7")),
            TierSpec(6, None, Decimal("1")),
        )
        created = replace_pricing_tiers(variant, replacement)

        self.assertEqual(len(created), 2)
        self.assertFalse(PricingTier.objects.filter(pk__in=[tier.pk for tier in old]).exists())
        self.assertEqual(
            list(
                PricingTier.objects.filter(variant=variant)
                .order_by("min_quantity")
                .values_list("min_quantity", "max_quantity", "markup_percent")
            ),
            [(1, 5, Decimal("7.00")), (6, None, Decimal("1.00"))],
        )

    def test_failed_bulk_create_rolls_back_deletion(self):
        variant = make_variant()
        replace_pricing_tiers(
            variant,
            (TierSpec(1, 10, Decimal("4")), TierSpec(11, None, Decimal("3"))),
        )
        before = list(
            PricingTier.objects.filter(variant=variant)
            .order_by("min_quantity")
            .values_list("id", "min_quantity", "max_quantity", "markup_percent")
        )
        replacement = (TierSpec(1, None, Decimal("2")),)

        with patch.object(PricingTier.objects, "bulk_create", side_effect=RuntimeError("injected failure")):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                replace_pricing_tiers(variant, replacement)

        after = list(
            PricingTier.objects.filter(variant=variant)
            .order_by("min_quantity")
            .values_list("id", "min_quantity", "max_quantity", "markup_percent")
        )
        self.assertEqual(after, before)

    def test_missing_or_corrupted_tiers_are_invalid(self):
        variant = make_variant(base_price=100000)
        with self.assertRaises(InvalidTierSet):
            quote(variant, 1)
        self.assertFalse(has_valid_pricing(variant))

        PricingTier.objects.bulk_create(
            [
                PricingTier(variant=variant, min_quantity=1, max_quantity=5, markup_percent=Decimal("4")),
                PricingTier(variant=variant, min_quantity=7, max_quantity=None, markup_percent=Decimal("3")),
            ]
        )
        with self.assertRaises(InvalidTierSet):
            quote(variant, 6)
        self.assertFalse(has_valid_pricing(variant))

    def test_quote_ignores_variant_and_product_availability(self):
        variant = make_variant(base_price=100000, is_active=False)
        self.assertEqual(variant.product.status, "draft")
        replace_pricing_tiers(variant)
        self.assertEqual(quote(variant, 1).unit_price, 104000)
