from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection
from django.test import TransactionTestCase

from apps.catalog.inventory import InsufficientStock, adjust_manual, deduct, verify_stock_log
from apps.catalog.models import StockLog
from apps.catalog.tests.helpers import make_variant


class InventoryConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def run_concurrently(self, workers):
        barrier = Barrier(len(workers))

        def run(worker):
            try:
                barrier.wait(timeout=60)
                return worker()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [executor.submit(run, worker) for worker in workers]
            return [future.result(timeout=60) for future in futures]

    def make_stock_variant(self, quantity):
        variant = make_variant()
        if quantity:
            adjust_manual(variant.pk, quantity)
            variant.refresh_from_db()
        return variant

    def test_ten_deductions_of_one_against_five_stock(self):
        variant = self.make_stock_variant(5)

        def try_deduct():
            try:
                deduct([(variant.pk, 1)])
                return "success"
            except InsufficientStock:
                return "insufficient"

        results = self.run_concurrently([try_deduct for _ in range(10)])

        self.assertEqual(results.count("success"), 5)
        self.assertEqual(results.count("insufficient"), 5)
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 0)
        logs = StockLog.objects.filter(variant=variant, reason=StockLog.Reason.ORDER_PAID)
        self.assertEqual(logs.count(), 5)
        self.assertEqual(sum(log.change for log in logs), -5)
        self.assertTrue(verify_stock_log(variant.pk).ok)

    def test_two_deductions_of_three_against_five_stock(self):
        variant = self.make_stock_variant(5)

        def try_deduct():
            try:
                deduct([(variant.pk, 3)])
                return "success"
            except InsufficientStock:
                return "insufficient"

        results = self.run_concurrently([try_deduct, try_deduct])

        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("insufficient"), 1)
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 2)

    def test_only_one_of_eight_threads_can_deduct_the_last_unit(self):
        variant = self.make_stock_variant(1)

        def try_deduct():
            try:
                deduct([(variant.pk, 1)])
                return "success"
            except InsufficientStock:
                return "insufficient"

        results = self.run_concurrently([try_deduct for _ in range(8)])

        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("insufficient"), 7)
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 0)
        self.assertGreaterEqual(variant.stock_quantity, 0)

    def test_opposite_input_orders_do_not_deadlock(self):
        first = self.make_stock_variant(100)
        second = self.make_stock_variant(100)

        def deduct_forward():
            for _ in range(50):
                deduct([(first.pk, 1), (second.pk, 1)])

        def deduct_reverse():
            for _ in range(50):
                deduct([(second.pk, 1), (first.pk, 1)])

        self.run_concurrently([deduct_forward, deduct_reverse])

        for variant in (first, second):
            variant.refresh_from_db()
            self.assertEqual(variant.stock_quantity, 0)
            logs = StockLog.objects.filter(variant=variant, reason=StockLog.Reason.ORDER_PAID)
            self.assertEqual(logs.count(), 100)
            self.assertTrue(verify_stock_log(variant.pk).ok)

    def test_deductions_and_absolute_adjustments_preserve_log_balance(self):
        variant = self.make_stock_variant(50)
        workers = [
            (lambda variant_id=variant.pk: deduct([(variant_id, 1)]))
            for _ in range(20)
        ]
        workers.extend(
            lambda quantity=quantity, variant_id=variant.pk: adjust_manual(variant_id, quantity)
            for quantity in (50, 51, 52, 53, 54)
        )

        self.run_concurrently(workers)

        self.assertTrue(verify_stock_log(variant.pk).ok)
