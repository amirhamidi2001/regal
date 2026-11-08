MAX_BASE_PRICE = 100_000_000_000
MAX_QUANTITY = 1_000_000
MAX_STOCK = 2_147_483_647

# ASSUMPTION: These limits keep line totals inside a signed 64-bit integer.
DEFAULT_TIER_TUPLES = ((1, 10, "4"), (11, 100, "3"), (101, 1000, "2"), (1001, None, "2"))
