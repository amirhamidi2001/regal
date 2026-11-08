"""Pure pricing calculations.

Unit prices are rounded half-up to a whole Toman, never the total, so
unit_price × quantity always equals the line total.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

from apps.catalog.constants import DEFAULT_TIER_TUPLES, MAX_QUANTITY


class PricingError(Exception):
    """Base class for pricing errors."""


class InvalidQuantity(PricingError, ValueError):
    """Raised when a requested quantity is outside the supported range."""


class InvalidTierSet(PricingError):
    """Raised when pricing tiers do not describe a valid quantity range."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(message for _code, message in self.problems))


@dataclass(frozen=True)
class TierSpec:
    min_quantity: int
    max_quantity: int | None
    markup_percent: Decimal


@dataclass(frozen=True)
class Quote:
    base_price: int
    quantity: int
    markup_percent: Decimal
    unit_price: int
    line_total: int


def validate_tier_specs(specs):
    """Validate a complete tier set and return it sorted by minimum quantity."""
    specs = tuple(specs)
    problems = []

    def add(code, message):
        problems.append((code, message))

    if not specs:
        raise InvalidTierSet([("empty_tier_set", "At least one pricing tier is required.")])

    usable_intervals = []
    unlimited_count = 0
    for index, spec in enumerate(specs):
        minimum = spec.min_quantity
        maximum = spec.max_quantity
        markup = spec.markup_percent

        min_valid = isinstance(minimum, int) and not isinstance(minimum, bool)
        max_valid = maximum is None or (isinstance(maximum, int) and not isinstance(maximum, bool))
        if not min_valid or not max_valid:
            add("not_integer", f"Tier {index + 1} bounds must be integers (except an unlimited maximum).")

        if min_valid and minimum < 1:
            add("min_below_one", f"Tier {index + 1} minimum quantity must be at least 1.")
        if max_valid and maximum is None:
            unlimited_count += 1
        if min_valid and max_valid and maximum is not None and maximum < minimum:
            add("max_below_min", f"Tier {index + 1} maximum quantity is below its minimum.")

        if not isinstance(markup, Decimal):
            add("markup_not_decimal", f"Tier {index + 1} markup must be a Decimal.")
        else:
            if markup < 0:
                add("markup_negative", f"Tier {index + 1} markup cannot be negative.")
            if markup > Decimal("999.99"):
                add("markup_too_large", f"Tier {index + 1} markup cannot exceed 999.99.")
            if markup.as_tuple().exponent < -2:
                add("markup_too_many_decimals", f"Tier {index + 1} markup cannot have more than two decimals.")

        if min_valid and max_valid and minimum >= 1 and (maximum is None or maximum >= minimum):
            usable_intervals.append((minimum, maximum, index))

    ordered = sorted(
        specs,
        key=lambda spec: (0, spec.min_quantity)
        if isinstance(spec.min_quantity, int) and not isinstance(spec.min_quantity, bool)
        else (1, 0),
    )
    ordered_intervals = sorted(usable_intervals, key=lambda interval: (interval[0], interval[2]))

    if ordered_intervals and ordered_intervals[0][0] != 1:
        add("first_tier_must_start_at_1", "The first pricing tier must start at quantity 1.")

    for previous, current in zip(ordered_intervals, ordered_intervals[1:]):
        previous_min, previous_max, _ = previous
        current_min, _current_max, _ = current
        if current_min == previous_min or (previous_max is not None and current_min <= previous_max):
            add("overlapping_tiers", f"Tier beginning at {current_min} overlaps the preceding tier.")
        elif previous_max is not None and current_min > previous_max + 1:
            add("gap_between_tiers", f"There is a gap between quantities {previous_max} and {current_min}.")

    if unlimited_count == 0:
        add("unlimited_tier_missing", "A complete pricing tier set must include an unlimited tier.")
    elif unlimited_count > 1:
        add("multiple_unlimited_tiers", "A pricing tier set cannot include multiple unlimited tiers.")

    unlimited_specs = [spec for spec in specs if spec.max_quantity is None]
    if unlimited_specs and all(
        isinstance(spec.min_quantity, int) and not isinstance(spec.min_quantity, bool)
        for spec in specs
    ):
        last_minimum = max(
            (spec.min_quantity for spec in specs if isinstance(spec.min_quantity, int) and not isinstance(spec.min_quantity, bool)),
            default=None,
        )
        if any(spec.min_quantity != last_minimum for spec in unlimited_specs):
            add("unlimited_tier_not_last", "The unlimited tier must be last.")

    if problems:
        raise InvalidTierSet(problems)
    return tuple(ordered)


def compute_unit_price(base_price, markup_percent):
    if not isinstance(base_price, int) or isinstance(base_price, bool):
        raise TypeError("base_price must be an integer.")
    if base_price < 1:
        raise ValueError("base_price must be at least 1.")
    if not isinstance(markup_percent, Decimal):
        raise TypeError("markup_percent must be a Decimal.")

    with localcontext() as context:
        context.prec = 40
        amount = Decimal(base_price) * (Decimal(100) + markup_percent) / Decimal(100)
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def quote_from_specs(base_price, specs, quantity):
    if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= MAX_QUANTITY:
        raise InvalidQuantity(f"Quantity must be an integer from 1 to {MAX_QUANTITY}.")

    tiers = validate_tier_specs(specs)
    for tier in tiers:
        if quantity >= tier.min_quantity and (tier.max_quantity is None or quantity <= tier.max_quantity):
            unit_price = compute_unit_price(base_price, tier.markup_percent)
            return Quote(
                base_price=base_price,
                quantity=quantity,
                markup_percent=tier.markup_percent,
                unit_price=unit_price,
                line_total=unit_price * quantity,
            )
    raise InvalidTierSet([("tier_not_found", "No pricing tier contains the requested quantity.")])


def default_tier_specs():
    return tuple(
        TierSpec(minimum, maximum, Decimal(markup))
        for minimum, maximum, markup in DEFAULT_TIER_TUPLES
    )
