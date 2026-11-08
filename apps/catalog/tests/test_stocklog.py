from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import ImmutableLogError, StockLog
from apps.catalog.tests.helpers import make_variant


class StockLogTests(TestCase):
    def setUp(self):
        self.variant = make_variant()

    def make_log(self, **overrides):
        values = {
            "variant": self.variant,
            "previous_quantity": 1,
            "change": 2,
            "new_quantity": 3,
            "reason": StockLog.Reason.MANUAL_ADJUSTMENT,
        }
        values.update(overrides)
        return StockLog.objects.create(**values)

    def test_first_time_save_and_bulk_create_are_allowed(self):
        first = self.make_log()
        second = StockLog.objects.bulk_create(
            [
                StockLog(
                    variant=self.variant,
                    previous_quantity=3,
                    change=-1,
                    new_quantity=2,
                    reason=StockLog.Reason.MANUAL_ADJUSTMENT,
                )
            ]
        )[0]
        self.assertIsNotNone(first.pk)
        self.assertIsNotNone(second.pk)

    def test_saving_an_existing_row_is_rejected(self):
        log = self.make_log()
        log.note = "edited"
        with self.assertRaises(ImmutableLogError):
            log.save()

    def test_instance_delete_is_rejected(self):
        log = self.make_log()
        with self.assertRaises(ImmutableLogError):
            log.delete()

    def test_queryset_update_delete_and_bulk_update_are_rejected(self):
        log = self.make_log()
        queryset = StockLog.objects.filter(pk=log.pk)
        with self.assertRaises(ImmutableLogError):
            queryset.update(note="edited")
        with self.assertRaises(ImmutableLogError):
            queryset.delete()
        with self.assertRaises(ImmutableLogError):
            StockLog.objects.bulk_update([log], ["note"])

    def test_database_rejects_invalid_changes_and_negative_quantities(self):
        invalid_rows = (
            {"previous_quantity": 2, "change": 0, "new_quantity": 2},
            {"previous_quantity": 2, "change": 1, "new_quantity": 4},
            {"previous_quantity": -1, "change": 2, "new_quantity": 1},
            {"previous_quantity": 0, "change": -1, "new_quantity": -1},
        )
        for values in invalid_rows:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                StockLog.objects.bulk_create(
                    [
                        StockLog(
                            variant=self.variant,
                            reason=StockLog.Reason.MANUAL_ADJUSTMENT,
                            **values,
                        )
                    ]
                )
