from dataclasses import dataclass

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.catalog.constants import MAX_QUANTITY, MAX_STOCK
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


def _normalize_lines(lines):
    try:
        raw_lines = tuple(lines)
    except Exception as error:
        raise InvalidStockOperation("Lines must be a non-empty iterable of (variant_id, quantity) pairs.") from error
    if not raw_lines:
        raise InvalidStockOperation("At least one stock line is required.")

    combined = {}
    for line in raw_lines:
        if isinstance(line, (str, bytes)):
            raise InvalidStockOperation("Each stock line must be a (variant_id, quantity) pair.")
        try:
            pair = tuple(line)
        except Exception as error:
            raise InvalidStockOperation("Each stock line must be a (variant_id, quantity) pair.") from error
        if len(pair) != 2:
            raise InvalidStockOperation("Each stock line must be a (variant_id, quantity) pair.")

        variant_id, quantity = pair
        if not isinstance(variant_id, int) or isinstance(variant_id, bool):
            raise InvalidStockOperation("Variant ids must be integers.")
        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or not 1 <= quantity <= MAX_QUANTITY
        ):
            raise InvalidStockOperation(f"Each quantity must be an integer from 1 to {MAX_QUANTITY}.")
        combined[variant_id] = combined.get(variant_id, 0) + quantity

    return tuple(sorted(combined.items()))


def _validate_order_id(order_id):
    if order_id is not None and (
        not isinstance(order_id, int) or isinstance(order_id, bool) or order_id < 1
    ):
        raise InvalidStockOperation("order_id must be a positive integer when supplied.")


def _locked_variants(lines):
    variant_ids = [variant_id for variant_id, _quantity in lines]
    variants = list(
        ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_ids)
        .order_by("pk")
    )
    variants_by_id = {variant.pk: variant for variant in variants}
    missing_ids = [variant_id for variant_id in variant_ids if variant_id not in variants_by_id]
    if missing_ids:
        raise InvalidStockOperation(f"Unknown variant ids: {missing_ids}.")
    return variants_by_id


def _update_logged_lines(lines, variants_by_id, *, restoring, order_id, actor, note):
    shortages = []
    for variant_id, quantity in lines:
        available = variants_by_id[variant_id].stock_quantity
        if restoring and available + quantity > MAX_STOCK:
            raise InvalidStockOperation(
                f"Restoring {quantity} units to variant {variant_id} would exceed {MAX_STOCK}."
            )
        if not restoring and available < quantity:
            shortages.append((variant_id, quantity, available))
    if shortages:
        raise InsufficientStock(shortages)

    now = timezone.now()
    logs = []
    for variant_id, quantity in lines:
        variant = variants_by_id[variant_id]
        previous_quantity = variant.stock_quantity
        if restoring:
            new_quantity = previous_quantity + quantity
            change = quantity
            predicate = {"stock_quantity__lte": MAX_STOCK - quantity}
            stock_expression = F("stock_quantity") + quantity
            reason = StockLog.Reason.ORDER_CANCELLED
        else:
            new_quantity = previous_quantity - quantity
            change = -quantity
            predicate = {"stock_quantity__gte": quantity}
            stock_expression = F("stock_quantity") - quantity
            reason = StockLog.Reason.ORDER_PAID

        updated = ProductVariant.objects.filter(
            pk=variant_id,
            **predicate,
        ).update(stock_quantity=stock_expression, updated_at=now)
        if updated != 1:
            raise StockError(f"Stock changed while updating variant {variant_id}.")

        logs.append(
            StockLog(
                variant=variant,
                previous_quantity=previous_quantity,
                change=change,
                new_quantity=new_quantity,
                reason=reason,
                order_id=order_id,
                actor=actor,
                note=note,
            )
        )

    created_logs = StockLog.objects.bulk_create(logs)
    return sorted(created_logs, key=lambda log: log.variant_id)


def deduct(lines, *, order_id=None, actor=None, note=""):
    """Deduct paid stock without checking is_active or product status; already-paid orders must still deduct.

    When combined with other writes, callers must invoke this inside their own transaction.atomic().
    """
    normalized = _normalize_lines(lines)
    _validate_order_id(order_id)

    with transaction.atomic():
        variants_by_id = _locked_variants(normalized)
        return _update_logged_lines(
            normalized,
            variants_by_id,
            restoring=False,
            order_id=order_id,
            actor=actor,
            note=note,
        )


def restore(lines, *, order_id=None, actor=None, note=""):
    """Restore stock without checking is_active or product status.

    This does NOT prevent being called twice for one order; orders must enforce that with
    stock_restored_at in Phase 6C. When combined with other writes, callers must invoke this
    inside their own transaction.atomic().
    """
    normalized = _normalize_lines(lines)
    _validate_order_id(order_id)

    with transaction.atomic():
        variants_by_id = _locked_variants(normalized)
        return _update_logged_lines(
            normalized,
            variants_by_id,
            restoring=True,
            order_id=order_id,
            actor=actor,
            note=note,
        )


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
