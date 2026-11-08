from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import PricingTier
from apps.catalog.tests.helpers import make_variant


class PricingTierConstraintTests(TestCase):
    def test_duplicate_variant_minimum_is_rejected(self):
        variant = make_variant()
        PricingTier.objects.create(variant=variant, min_quantity=1, max_quantity=10, markup_percent=Decimal("4"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            PricingTier.objects.bulk_create(
                [PricingTier(variant=variant, min_quantity=1, max_quantity=None, markup_percent=Decimal("3"))]
            )

    def test_only_one_unlimited_tier_per_variant_but_each_variant_can_have_one(self):
        first_variant = make_variant()
        second_variant = make_variant()
        PricingTier.objects.bulk_create(
            [
                PricingTier(variant=first_variant, min_quantity=1, max_quantity=None, markup_percent=Decimal("4")),
                PricingTier(variant=second_variant, min_quantity=1, max_quantity=None, markup_percent=Decimal("3")),
            ]
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PricingTier.objects.bulk_create(
                [PricingTier(variant=first_variant, min_quantity=2, max_quantity=None, markup_percent=Decimal("2"))]
            )

    def test_minimum_must_be_at_least_one(self):
        variant = make_variant()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PricingTier.objects.bulk_create(
                [PricingTier(variant=variant, min_quantity=0, max_quantity=None, markup_percent=Decimal("4"))]
            )

    def test_maximum_must_not_be_below_minimum(self):
        variant = make_variant()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PricingTier.objects.bulk_create(
                [PricingTier(variant=variant, min_quantity=11, max_quantity=10, markup_percent=Decimal("4"))]
            )

    def test_markup_must_be_nonnegative(self):
        variant = make_variant()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PricingTier.objects.bulk_create(
                [PricingTier(variant=variant, min_quantity=1, max_quantity=None, markup_percent=Decimal("-0.01"))]
            )

    def test_variant_deletion_cascades_to_tiers(self):
        variant = make_variant()
        tier = PricingTier.objects.create(
            variant=variant,
            min_quantity=1,
            max_quantity=None,
            markup_percent=Decimal("4"),
        )
        tier_id, variant_id = tier.pk, variant.pk
        variant.delete()
        self.assertFalse(PricingTier.objects.filter(pk=tier_id).exists())
        self.assertFalse(PricingTier.objects.filter(variant_id=variant_id).exists())
