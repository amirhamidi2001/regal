# Catalog pricing and inventory

This document describes the catalog rules implemented in `apps/catalog`. Application code must use the service APIs below so displayed prices and stock history stay consistent.

## Price calculation

Prices are integer Toman. A tier markup is a `Decimal` percentage. The engine calculates

```text
unit price = round half-up(base price × (100 + markup percent) ÷ 100)
line total = unit price × quantity
```

It rounds the unit price to a whole Toman, never the total. This ensures `unit price × quantity` is exactly the line total. For example, base price 10 Toman at 5% produces 10.5 Toman before rounding and **11 Toman** after half-up rounding (banker's rounding would produce 10).

With the default tiers and base price 100,000 Toman:

| Quantity | Markup | Unit price (Toman) | Line total (Toman) |
| ---: | ---: | ---: | ---: |
| 5 | 4% | 104,000 | 520,000 |
| 50 | 3% | 103,000 | 5,150,000 |
| 200 | 2% | 102,000 | 20,400,000 |
| 1,500 | 2% | 102,000 | 153,000,000 |

Tier ranges are inclusive. The default ranges are 1–10 at 4%, 11–100 at 3%, 101–1,000 at 2%, and 1,001 onward at 2%. A valid tier set begins at quantity 1, has consecutive ranges with no gaps or overlaps, and has exactly one unlimited final range. Markups are nonnegative `Decimal` values from 0 through 999.99 with at most two decimal places. The validator reports all detected problems. Database constraints enforce individual range bounds and uniqueness, but **the database cannot by itself forbid gaps or overlaps**; all tier writes must go through `pricing.replace_pricing_tiers`.

Call `pricing.quote(variant, quantity)` for the authoritative current price. Never accept a price supplied by the browser. When an order is created, copy every value from its returned immutable `Quote` into the order line snapshot: `base_price`, `quantity`, `markup_percent`, `unit_price`, and `line_total`. Later order code must use that snapshot for the order and payment amount rather than recalculate from a changed catalog price. Shipping is excluded from order totals and gateway amounts; REGAL does not add VAT.

## Inventory and StockLog

`inventory.adjust_manual(variant_id, new_quantity, ...)` sets stock to an absolute quantity. `inventory.deduct(lines, ...)` subtracts purchased units after confirmed payment, and `inventory.restore(lines, ...)` adds units during the order cancellation flow. Each line is a `(variant_id, quantity)` pair. Duplicate variant IDs are combined. `deduct` and `restore` validate every line before writing, lock variants in ascending ID order, update stock and append complete logs in one transaction, and either complete all lines or none. Restore rejects values above `MAX_STOCK`.

These functions do not reserve stock. `deduct` and `restore` do not check whether a variant is active or its product is published; an already-paid order must still deduct. Callers that combine inventory operations with other writes must wrap the whole operation in their own `transaction.atomic()`. `restore` is not idempotent by itself: the orders app must prevent duplicate restoration using `stock_restored_at` in Phase 6C. Manual adjustment permission checks belong to the Phase 8 dashboard.

Every `StockLog` records the variant, previous quantity, signed change, new quantity, reason, optional order ID, optional actor, note, and creation time. Database constraints require a nonzero change and `new_quantity = previous_quantity + change`; stock values are nonnegative. The log is append-only through the model's Python protections. Reasons are `order_paid`, `order_cancelled`, `manual_adjustment`, and `conflict_resolution` (the last is reserved for later reconciliation). `StockLog.order_id` is currently a plain integer and becomes a ForeignKey named `order` in Phase 6A.

`inventory.verify_stock_log(variant_id)` reports current stock, the sum of logged changes, and whether they match. It is valid only when that variant's stock started at zero and has been changed exclusively through `inventory.py`.

## Purchase availability

`services.get_purchase_problem(variant, quantity)` is the single soft availability check for cart and checkout. It reserves nothing and returns `None` when the variant can currently be bought. Otherwise it returns a `PurchaseProblem` with the first matching code, in this order:

| Code | Meaning | `available` value |
| --- | --- | --- |
| `invalid_quantity` | Not an integer from 1 through `MAX_QUANTITY` (booleans are invalid) | `None` |
| `variant_inactive` | Variant is inactive | `None` |
| `product_not_published` | Product is not published | `None` |
| `category_inactive` | Category or any ancestor is inactive | `None` |
| `invalid_pricing` | Base price is out of range or tiers are invalid | `None` |
| `out_of_stock` | Stock is zero | `0` |
| `insufficient_stock` | Stock is below requested quantity | Current stock |

## Limits and product images

`apps/catalog/constants.py` defines `MAX_BASE_PRICE = 100,000,000,000` Toman, `MAX_QUANTITY = 1,000,000`, `MAX_STOCK = 2,147,483,647`, and the default tier tuples. The price and quantity limits keep line totals inside a signed 64-bit integer.

Image uploads are limited to 5 MiB and 40,000,000 pixels. Accepted formats are JPEG, PNG, and WebP. `images.build_derivatives` creates `card` and `detail` WebP files with longest sides of 480 and 960 pixels, quality 82, applying EXIF orientation and preserving alpha where present. A source such as `products/main/2026/11/item.jpg` yields `products/main/2026/11/item.card.webp` and `products/main/2026/11/item.detail.webp`. Originals remain unchanged. Derivatives are built explicitly; there are no automatic hooks. Deleting product image rows does not delete stored files; cleanup is a later policy decision.

## Public catalog service functions

Private helpers (names beginning with `_`) are omitted.

| Module | Public function | Purpose |
| --- | --- | --- |
| `pricing.py` | `validate_tier_specs(specs)` | Validate and sort a complete set of tier specifications. |
| `pricing.py` | `compute_unit_price(base_price, markup_percent)` | Calculate a rounded integer-Toman unit price. |
| `pricing.py` | `quote_from_specs(base_price, specs, quantity)` | Quote using tier specifications without database access. |
| `pricing.py` | `default_tier_specs()` | Build the configured default tiers. |
| `pricing.py` | `tier_specs_for(variant)` | Load a variant's tiers, using a prefetch cache if present. |
| `pricing.py` | `quote(variant, quantity)` | Return the authoritative quote for a variant. |
| `pricing.py` | `has_valid_pricing(variant)` | Check whether the variant has a valid tier set. |
| `pricing.py` | `replace_pricing_tiers(variant, specs=None)` | Atomically replace all tiers through the sole write path. |
| `inventory.py` | `deduct(lines, *, order_id=None, actor=None, note="")` | Deduct stock and append `order_paid` logs. |
| `inventory.py` | `restore(lines, *, order_id=None, actor=None, note="")` | Restore stock and append `order_cancelled` logs. |
| `inventory.py` | `adjust_manual(variant_id, new_quantity, *, actor=None, note="")` | Apply an absolute manual adjustment and append a log. |
| `inventory.py` | `verify_stock_log(variant_id)` | Compare current stock with the logged balance. |
| `services.py` | `generate_unique_slug(model, name, *, instance_pk=None)` | Return an available Unicode slug. |
| `services.py` | `build_category_tree(include_inactive=False)` | Return ordered category trees. |
| `services.py` | `get_descendant_category_ids(category_id, include_self=True)` | Return descendant IDs in breadth-first order. |
| `services.py` | `set_category_parent(category, parent)` | Move a category while preventing cycles. |
| `services.py` | `variant_label(variant)` | Join ordered attribute values for display. |
| `services.py` | `is_simple_product(product)` | Derive whether a product has one attribute-free variant. |
| `services.py` | `create_variant(product, *, sku, base_price, attributes=(), stock_quantity=0, tier_specs=None, actor=None, sort_order=0)` | Create a variant with tiers and optional logged initial stock. |
| `services.py` | `activate_variant(variant)` | Activate a variant only when its price and tiers are valid. |
| `services.py` | `deactivate_variant(variant)` | Deactivate a variant. |
| `services.py` | `publish_product(product)` | Publish after checking category, variants, and pricing. |
| `services.py` | `unpublish_product(product)` | Return a product to draft status. |
| `services.py` | `archive_product(product)` | Archive a product. |
| `services.py` | `get_purchase_problem(variant, quantity)` | Return the first soft availability problem, or `None`. |
| `images.py` | `validate_uploaded_image(file)` | Validate an uploaded image's bytes, format, and dimensions. |
| `images.py` | `derivative_name(name, variant)` | Construct a deterministic derivative object name. |
| `images.py` | `build_derivatives(name, *, storage=None)` | Create deterministic card and detail WebP derivatives. |
| `images.py` | `delete_derivatives(name, *, storage=None)` | Delete existing derivatives for an original. |

`constants.py` exposes limits and default tier data rather than service functions. Model methods perform simple field handling and append-only protections; pricing and inventory business operations remain in their service modules.
