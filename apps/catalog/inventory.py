from dataclasses import dataclass

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.constants import MAX_STOCK
from apps.catalog.models import ProductVariant, StockLog


class StockError(Exception):
    """Base class for inventory operation errors."""


class InvalidStockOperation(StockError):
    """Raised when a stock operation contains invalid input or a missing variant."""


class InsufficientStock(StockError):
    """Raised when a stock deduction cannot be satisfied."""

    def __init__(self, shortages):
        self.shortages = list(shortages)
        super().__init__("Insufficient stock for one or more variants.")


@dataclass(frozen=True)
class StockLogBalance:
    stock: int
    logged: int
    ok: bool


def adjust_manual(variant_id, new_quantity, *, actor=None, note=""):
    """Set a variant's stock to a manually specified quantity and log the change."""
    # ASSUMPTION: An omitted optional note is stored as an empty string.
    if (
        not isinstance(new_quantity, int)
        or isinstance(new_quantity, bool)
        or not 0 <= new_quantity <= MAX_STOCK
    ):
        raise InvalidStockOperation(f"Stock quantity must be an integer from 0 to {MAX_STOCK}.")

    with transaction.atomic():
        try:
            variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
        except ProductVariant.DoesNotExist as error:
            raise InvalidStockOperation(f"Unknown variant: {variant_id}.") from error

        previous_quantity = variant.stock_quantity
        change = new_quantity - previous_quantity
        if change == 0:
            return None

        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            stock_quantity=previous_quantity,
        ).update(stock_quantity=new_quantity, updated_at=timezone.now())
        if updated != 1:
            raise StockError("Stock changed while applying the adjustment.")

        return StockLog.objects.create(
            variant=variant,
            previous_quantity=previous_quantity,
            change=change,
            new_quantity=new_quantity,
            reason=StockLog.Reason.MANUAL_ADJUSTMENT,
            actor=actor,
            note=note,
        )


def verify_stock_log(variant_id):
    """Valid only for variants whose stock changed exclusively through inventory.py starting from 0."""
    variant = ProductVariant.objects.get(pk=variant_id)
    logged = StockLog.objects.filter(variant_id=variant_id).aggregate(total=Sum("change"))["total"] or 0
    return StockLogBalance(stock=variant.stock_quantity, logged=logged, ok=variant.stock_quantity == logged)
