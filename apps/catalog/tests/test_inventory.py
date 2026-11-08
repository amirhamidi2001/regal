from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.constants import MAX_QUANTITY, MAX_STOCK
from apps.catalog.inventory import (
    InsufficientStock,
    InvalidStockOperation,
    adjust_manual,
    deduct,
    restore,
    verify_stock_log,
)
from apps.catalog.models import Product, ProductVariant, StockLog
from apps.catalog.tests.helpers import make_variant


class ManualInventoryTests(TestCase):
    def setUp(self):
        self.variant = make_variant()

    def test_adjust_manual_from_three_to_ten_creates_complete_log(self):
        old_updated_at = timezone.now() - timedelta(days=1)
        ProductVariant.objects.filter(pk=self.variant.pk).update(
            stock_quantity=3,
            updated_at=old_updated_at,
        )
        actor = get_user_model().objects.create_user("09123456789", full_name="انباردار")

        log = adjust_manual(self.variant.pk, 10, actor=actor, note="شمارش دستی")

        self.assertEqual(log.variant_id, self.variant.pk)
        self.assertEqual(log.previous_quantity, 3)
        self.assertEqual(log.change, 7)
        self.assertEqual(log.new_quantity, 10)
        self.assertEqual(log.reason, StockLog.Reason.MANUAL_ADJUSTMENT)
        self.assertEqual(log.actor, actor)
        self.assertEqual(log.note, "شمارش دستی")
        self.assertEqual(StockLog.objects.filter(variant=self.variant).count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertGreater(self.variant.updated_at, old_updated_at)

    def test_same_value_returns_none_without_writing_a_log(self):
        adjust_manual(self.variant.pk, 4)
        self.assertIsNone(adjust_manual(self.variant.pk, 4))
        self.assertEqual(StockLog.objects.filter(variant=self.variant).count(), 1)

    def test_setting_stock_to_zero_works(self):
        adjust_manual(self.variant.pk, 5)
        log = adjust_manual(self.variant.pk, 0)
        self.assertEqual(log.previous_quantity, 5)
        self.assertEqual(log.change, -5)
        self.assertEqual(log.new_quantity, 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 0)

    def test_invalid_quantities_are_rejected(self):
        for new_quantity in (-1, True, 1.5, "5", MAX_STOCK + 1):
            with self.subTest(new_quantity=new_quantity), self.assertRaises(InvalidStockOperation):
                adjust_manual(self.variant.pk, new_quantity)

    def test_unknown_variant_is_rejected(self):
        with self.assertRaises(InvalidStockOperation):
            adjust_manual(987654321, 1)

    def test_none_actor_is_recorded_as_system(self):
        log = adjust_manual(self.variant.pk, 2)
        self.assertIsNone(log.actor_id)

    def test_verify_stock_log_matches_multiple_adjustments(self):
        adjust_manual(self.variant.pk, 5)
        adjust_manual(self.variant.pk, 2)
        adjust_manual(self.variant.pk, 9)

        balance = verify_stock_log(self.variant.pk)
        self.assertEqual(balance.stock, 9)
        self.assertEqual(balance.logged, 9)
        self.assertTrue(balance.ok)

    def test_verify_stock_log_detects_a_raw_stock_change(self):
        adjust_manual(self.variant.pk, 5)
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=8)

        balance = verify_stock_log(self.variant.pk)
        self.assertEqual(balance.stock, 8)
        self.assertEqual(balance.logged, 5)
        self.assertFalse(balance.ok)


class DeductRestoreTests(TestCase):
    def setUp(self):
        self.variant = make_variant()

    def make_stock_variant(self, quantity, **overrides):
        variant = make_variant(**overrides)
        if quantity:
            adjust_manual(variant.pk, quantity)
            variant.refresh_from_db()
        return variant

    def test_deduct_single_line_and_stores_order_actor_and_note(self):
        variant = self.make_stock_variant(5)
        actor = get_user_model().objects.create_user("09123456789", full_name="مسئول انبار")

        logs = deduct([(variant.pk, 2)], order_id=37, actor=actor, note="پرداخت تأیید شد")

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].previous_quantity, 5)
        self.assertEqual(logs[0].change, -2)
        self.assertEqual(logs[0].new_quantity, 3)
        self.assertEqual(logs[0].reason, StockLog.Reason.ORDER_PAID)
        self.assertEqual(logs[0].order_id, 37)
        self.assertEqual(logs[0].actor, actor)
        self.assertEqual(logs[0].note, "پرداخت تأیید شد")
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 3)

    def test_deduct_multiple_lines(self):
        first = self.make_stock_variant(5)
        second = self.make_stock_variant(8)

        logs = deduct([(second.pk, 3), (first.pk, 2)])

        self.assertEqual([log.variant_id for log in logs], [first.pk, second.pk])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.stock_quantity, second.stock_quantity), (3, 5))

    def test_duplicate_lines_merge_into_one_log(self):
        variant = self.make_stock_variant(10)

        logs = deduct([(variant.pk, 2), (variant.pk, 3)])

        self.assertEqual(len(logs), 1)
        self.assertEqual((logs[0].previous_quantity, logs[0].change, logs[0].new_quantity), (10, -5, 5))
        self.assertEqual(StockLog.objects.filter(variant=variant, reason=StockLog.Reason.ORDER_PAID).count(), 1)

    def test_exact_stock_deducts_to_zero(self):
        variant = self.make_stock_variant(4)
        logs = deduct([(variant.pk, 4)])
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 0)
        self.assertEqual(logs[0].new_quantity, 0)

    def test_one_unit_above_stock_fails(self):
        variant = self.make_stock_variant(4)
        logs_before = StockLog.objects.filter(variant=variant).count()
        with self.assertRaises(InsufficientStock) as caught:
            deduct([(variant.pk, 5)])
        self.assertEqual(caught.exception.shortages, [(variant.pk, 5, 4)])
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 4)
        self.assertEqual(StockLog.objects.filter(variant=variant).count(), logs_before)

    def test_insufficient_stock_reports_every_shortage_without_writing(self):
        first = self.make_stock_variant(2)
        second = self.make_stock_variant(4)
        sufficient = self.make_stock_variant(10)
        variants = (first, second, sufficient)
        before_stock = {variant.pk: variant.stock_quantity for variant in variants}
        before_logs = StockLog.objects.count()

        with self.assertRaises(InsufficientStock) as caught:
            deduct([(first.pk, 3), (second.pk, 5), (sufficient.pk, 4)])

        self.assertEqual(
            caught.exception.shortages,
            [(first.pk, 3, 2), (second.pk, 5, 4)],
        )
        for variant in variants:
            variant.refresh_from_db()
            self.assertEqual(variant.stock_quantity, before_stock[variant.pk])
        self.assertEqual(StockLog.objects.count(), before_logs)

    def test_deduct_works_for_inactive_variant_and_draft_product(self):
        variant = self.make_stock_variant(2, is_active=False)
        self.assertEqual(Product.objects.get(pk=variant.product_id).status, Product.Status.DRAFT)
        self.assertEqual(deduct([(variant.pk, 1)])[0].new_quantity, 1)

    def test_invalid_inputs_are_rejected(self):
        for lines in (
            [],
            [(self.variant_id_missing(), 1)],
            [(self.variant_id_missing(), 0)],
            [(self.variant_id_missing(), -1)],
            [(self.variant_id_missing(), True)],
            [(self.variant_id_missing(), 1.5)],
            [(self.variant_id_missing(), MAX_QUANTITY + 1)],
            [(True, 1)],
            [(self.variant_id_missing(), 1), (self.variant_id_missing(), 1.5)],
        ):
            with self.subTest(lines=lines), self.assertRaises(InvalidStockOperation):
                deduct(lines)

        for order_id in (0, True, 1.5, "7"):
            with self.subTest(order_id=order_id), self.assertRaises(InvalidStockOperation):
                deduct([(self.variant.pk, 1)], order_id=order_id)

    def variant_id_missing(self):
        return 987654321

    def test_restore_adds_stock_and_logs_order_cancellation(self):
        variant = self.make_stock_variant(3)

        logs = restore([(variant.pk, 4)], order_id=28, note="سفارش لغو شد")

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].previous_quantity, 3)
        self.assertEqual(logs[0].change, 4)
        self.assertEqual(logs[0].new_quantity, 7)
        self.assertEqual(logs[0].reason, StockLog.Reason.ORDER_CANCELLED)
        self.assertEqual(logs[0].order_id, 28)
        variant.refresh_from_db()
        self.assertEqual(variant.stock_quantity, 7)

    def test_restore_overflow_is_rejected_without_any_changes(self):
        first = make_variant()
        second = self.make_stock_variant(MAX_STOCK)
        before = StockLog.objects.count()

        with self.assertRaises(InvalidStockOperation):
            restore([(first.pk, 1), (second.pk, 1)])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.stock_quantity, second.stock_quantity), (0, MAX_STOCK))
        self.assertEqual(StockLog.objects.count(), before)

    def test_stock_updates_roll_back_when_bulk_log_creation_fails(self):
        first = self.make_stock_variant(5)
        second = self.make_stock_variant(7)
        before_logs = StockLog.objects.count()

        with patch.object(StockLog.objects, "bulk_create", side_effect=RuntimeError("injected log failure")):
            with self.assertRaisesRegex(RuntimeError, "injected log failure"):
                deduct([(first.pk, 2), (second.pk, 3)])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.stock_quantity, second.stock_quantity), (5, 7))
        self.assertEqual(StockLog.objects.count(), before_logs)

    def test_adjust_deduct_restore_deduct_logs_form_a_continuous_chain(self):
        variant = make_variant()
        adjust_manual(variant.pk, 10)
        deduct([(variant.pk, 4)])
        restore([(variant.pk, 2)])
        deduct([(variant.pk, 3)])

        logs = list(StockLog.objects.filter(variant=variant).order_by("pk"))
        self.assertTrue(verify_stock_log(variant.pk).ok)
        self.assertEqual(logs[0].previous_quantity, 0)
        for previous, current in zip(logs, logs[1:]):
            self.assertEqual(current.previous_quantity, previous.new_quantity)
        variant.refresh_from_db()
        self.assertEqual(logs[-1].new_quantity, variant.stock_quantity)
