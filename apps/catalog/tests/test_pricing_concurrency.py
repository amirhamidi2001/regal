from decimal import Decimal
from threading import Barrier, Thread

from django.db import connection
from django.test import TransactionTestCase

from apps.catalog.models import ProductVariant
from apps.catalog.pricing import (
    TierSpec,
    has_valid_pricing,
    quote,
    replace_pricing_tiers,
    tier_specs_for,
)
from apps.catalog.tests.helpers import make_variant


SPECS_A = (TierSpec(1, 5, Decimal("4")), TierSpec(6, None, Decimal("3")))
SPECS_B = (TierSpec(1, 10, Decimal("2")), TierSpec(11, None, Decimal("4")))


class PricingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.variant = make_variant(base_price=100000)
        replace_pricing_tiers(self.variant, SPECS_A)

    def run_threads(self, barrier, *workers):
        errors = []

        def run(worker):
            try:
                barrier.wait(timeout=20)
                worker()
            except BaseException as error:
                errors.append(error)
            finally:
                connection.close()

        threads = [Thread(target=run, args=(worker,)) for worker in workers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertFalse(any(thread.is_alive() for thread in threads), "Pricing worker thread did not finish.")
        self.assertEqual(errors, [])

    def test_concurrent_replacements_leave_one_complete_valid_set(self):
        variant_id = self.variant.pk
        start = Barrier(2)

        def replace_repeatedly(specs):
            variant = ProductVariant.objects.get(pk=variant_id)
            for _ in range(20):
                replace_pricing_tiers(variant, specs)

        self.run_threads(start, lambda: replace_repeatedly(SPECS_A), lambda: replace_repeatedly(SPECS_B))

        stored_specs = tier_specs_for(self.variant)
        self.assertIn(stored_specs, (SPECS_A, SPECS_B))
        self.assertTrue(has_valid_pricing(self.variant))

    def test_quotes_never_observe_a_mixed_set_during_replacement(self):
        variant_id = self.variant.pk
        start = Barrier(2)
        iteration_barrier = Barrier(2)
        quotes = []

        def replace_repeatedly():
            variant = ProductVariant.objects.get(pk=variant_id)
            for index in range(20):
                replace_pricing_tiers(variant, SPECS_B if index % 2 == 0 else SPECS_A)
                iteration_barrier.wait(timeout=20)

        def quote_repeatedly():
            variant = ProductVariant.objects.get(pk=variant_id)
            for _ in range(20):
                quotes.extend(
                    (result.markup_percent, result.unit_price, result.line_total)
                    for result in (quote(variant, 6) for _ in range(10))
                )
                iteration_barrier.wait(timeout=20)

        self.run_threads(start, replace_repeatedly, quote_repeatedly)

        self.assertEqual(len(quotes), 200)
        self.assertTrue(
            all(
                result in (
                    (Decimal("3"), 103000, 618000),
                    (Decimal("2"), 102000, 612000),
                )
                for result in quotes
            )
        )
