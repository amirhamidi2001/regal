from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.constants import MAX_STOCK
from apps.catalog.inventory import (
    InvalidStockOperation,
    adjust_manual,
    verify_stock_log,
)
from apps.catalog.models import ProductVariant, StockLog
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
