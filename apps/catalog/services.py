from collections import defaultdict, deque
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.constants import MAX_BASE_PRICE, MAX_QUANTITY, MAX_STOCK
from apps.catalog.inventory import adjust_manual
from apps.catalog.models import Category, Product, ProductVariant, VariantAttribute
from apps.catalog.pricing import InvalidTierSet, has_valid_pricing, replace_pricing_tiers


class CatalogError(Exception):
    """Base class for catalog lifecycle errors."""


class ActivationError(CatalogError):
    """Raised when a product variant cannot be activated."""


class PublishError(CatalogError):
    """Raised when a product does not meet the publication requirements."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


class CategoryCycleError(CatalogError):
    """Raised when a category move would create a parent cycle."""


@dataclass(frozen=True)
class CategoryNode:
    category: Category
    children: tuple["CategoryNode", ...]


@dataclass(frozen=True)
class PurchaseProblem:
    code: str
    available: int | None


def generate_unique_slug(model, name, *, instance_pk=None):
    """Return the first available slug, keeping any numeric suffix within the field limit."""
    slug_field = model._meta.get_field("slug")
    max_length = slug_field.max_length
    base = slugify(name, allow_unicode=True) or "item"
    base = base[:max_length].rstrip("-") or "item"[:max_length]

    # A one-character base prefix also covers candidates whose root was shortened for a suffix.
    prefix = base[:1]
    queryset = model._default_manager.filter(slug__startswith=prefix)
    if instance_pk is not None:
        queryset = queryset.exclude(pk=instance_pk)
    existing = set(queryset.values_list("slug", flat=True))

    number = 1
    while True:
        suffix = "" if number == 1 else f"-{number}"
        if len(suffix) > max_length:
            raise ValidationError({"slug": "No unique slug fits the field length."})
        stem = base[: max_length - len(suffix)].rstrip("-")
        candidate = f"{stem}{suffix}"
        if candidate not in existing:
            return candidate
        number += 1


def build_category_tree(include_inactive=False):
    """Return category trees ordered by sort_order and name using a single query."""
    categories = list(Category.objects.all().order_by("sort_order", "name"))
    categories_by_id = {category.pk: category for category in categories}

    visible_ids = set()
    for category in categories:
        if include_inactive:
            visible_ids.add(category.pk)
            continue
        current = category
        visited = set()
        visible = True
        while current is not None:
            if current.pk in visited:
                visible = False
                break
            visited.add(current.pk)
            if not current.is_active:
                visible = False
                break
            current = categories_by_id.get(current.parent_id)
        if visible:
            visible_ids.add(category.pk)

    child_ids = defaultdict(list)
    root_ids = []
    for category in categories:
        if category.pk not in visible_ids:
            continue
        if category.parent_id is None:
            root_ids.append(category.pk)
        elif category.parent_id in visible_ids:
            child_ids[category.parent_id].append(category.pk)

    def make_node(category_id, ancestors=frozenset()):
        if category_id in ancestors:
            return None
        next_ancestors = ancestors | {category_id}
        children = tuple(
            node
            for child_id in child_ids[category_id]
            if (node := make_node(child_id, next_ancestors)) is not None
        )
        return CategoryNode(categories_by_id[category_id], children)

    return [make_node(category_id) for category_id in root_ids]


def get_descendant_category_ids(category_id, include_self=True):
    """Return a category's ids in breadth-first order with one category-table query."""
    rows = list(Category.objects.order_by("id").values_list("id", "parent_id"))
    known_ids = {row_id for row_id, _parent_id in rows}
    if category_id not in known_ids:
        return []

    children = defaultdict(list)
    for row_id, parent_id in rows:
        if parent_id is not None:
            children[parent_id].append(row_id)

    result = [category_id] if include_self else []
    queue = deque([category_id])
    while queue:
        parent_id = queue.popleft()
        for child_id in children[parent_id]:
            result.append(child_id)
            queue.append(child_id)
    return result


def set_category_parent(category, parent):
    """Move a category under a parent without allowing concurrent cyclic moves."""
    with transaction.atomic():
        categories = list(Category.objects.select_for_update().order_by("id"))
        categories_by_id = {item.pk: item for item in categories}
        locked_category = categories_by_id.get(category.pk)
        if locked_category is None:
            raise ValidationError({"category": "The category must already exist."})

        parent_id = None if parent is None else parent.pk
        if parent_id is not None and parent_id not in categories_by_id:
            raise ValidationError({"parent": "The parent category must already exist."})

        if parent_id is not None:
            children = defaultdict(list)
            for item in categories:
                if item.parent_id is not None:
                    children[item.parent_id].append(item.pk)
            descendants = set()
            queue = deque([category.pk])
            while queue:
                current_id = queue.popleft()
                for child_id in children[current_id]:
                    if child_id not in descendants:
                        descendants.add(child_id)
                        queue.append(child_id)
            if parent_id == category.pk or parent_id in descendants:
                raise CategoryCycleError("A category cannot be placed under itself or one of its descendants.")

        locked_category.parent_id = parent_id
        locked_category.save(update_fields=["parent", "updated_at"])
        category.parent_id = parent_id
        category.updated_at = locked_category.updated_at
        return category


def variant_label(variant):
    """Return attribute values joined in their display order."""
    attributes = sorted(variant.attributes.all(), key=lambda attribute: (attribute.sort_order, attribute.pk))
    return " / ".join(attribute.value for attribute in attributes)


def is_simple_product(product):
    """Return whether a product has exactly one variant with no attributes."""
    variants = list(product.variants.all())
    return len(variants) == 1 and not list(variants[0].attributes.all())


def create_variant(
    product,
    *,
    sku,
    base_price,
    attributes=(),
    stock_quantity=0,
    tier_specs=None,
    actor=None,
    sort_order=0,
):
    """Create an inactive variant, its attributes and pricing tiers, and optional initial stock."""
    if (
        not isinstance(stock_quantity, int)
        or isinstance(stock_quantity, bool)
        or not 0 <= stock_quantity <= MAX_STOCK
    ):
        raise ValidationError({"stock_quantity": f"Must be an integer from 0 to {MAX_STOCK}."})
    if not isinstance(sku, str):
        raise ValidationError({"sku": "Must be text."})
    if not isinstance(base_price, int) or isinstance(base_price, bool):
        raise ValidationError({"base_price": "Must be an integer Toman amount."})

    with transaction.atomic():
        variant = ProductVariant(
            product=product,
            sku=sku.strip().upper(),
            base_price=base_price,
            is_active=False,
            sort_order=sort_order,
        )
        variant.full_clean()
        variant.save()

        for values in attributes:
            if not isinstance(values, dict):
                raise ValidationError({"attributes": "Each attribute must be a mapping."})
            unexpected = set(values) - {"name", "value", "color_hex", "sort_order"}
            if unexpected:
                raise ValidationError({"attributes": f"Unexpected attribute fields: {sorted(unexpected)}."})
            attribute = VariantAttribute(
                variant=variant,
                name=values.get("name"),
                value=values.get("value"),
                color_hex=values.get("color_hex", ""),
                sort_order=values.get("sort_order", 0),
            )
            attribute.full_clean()
            attribute.save()

        replace_pricing_tiers(variant, tier_specs)
        if stock_quantity > 0:
            adjust_manual(variant.pk, stock_quantity, actor=actor, note="initial stock")

        variant.refresh_from_db()
        return variant


def activate_variant(variant):
    """Activate a variant only when its price and tier set are valid."""
    base_price = variant.base_price
    if (
        not isinstance(base_price, int)
        or isinstance(base_price, bool)
        or not 1 <= base_price <= MAX_BASE_PRICE
    ):
        raise ActivationError("The variant base price is outside the allowed range.")
    if not has_valid_pricing(variant):
        raise ActivationError("The variant has no valid pricing tiers.")
    if not variant.is_active:
        variant.is_active = True
        variant.save(update_fields=["is_active", "updated_at"])
    return variant


def deactivate_variant(variant):
    """Deactivate a variant without changing its pricing or stock."""
    if variant.is_active:
        variant.is_active = False
        variant.save(update_fields=["is_active", "updated_at"])
    return variant


def publish_product(product):
    """Publish a product after validating its category and every active variant."""
    problems = []
    if product.category_id is None:
        problems.append("category_missing")
    elif not product.category.is_active:
        problems.append("category_inactive")

    active_variants = list(product.variants.filter(is_active=True).prefetch_related("pricing_tiers"))
    if not active_variants:
        problems.append("no_active_variants")
    for variant in active_variants:
        if not has_valid_pricing(variant):
            problems.append(f"invalid_pricing:{variant.pk}")

    if problems:
        raise PublishError(problems)
    _set_product_status(product, Product.Status.PUBLISHED)
    return product


def unpublish_product(product):
    """Return a product to draft without changing its variants."""
    _set_product_status(product, Product.Status.DRAFT)
    return product


def archive_product(product):
    """Archive a product without changing its variants."""
    _set_product_status(product, Product.Status.ARCHIVED)
    return product


def _set_product_status(product, status):
    if product.status != status:
        product.status = status
        product.save(update_fields=["status", "updated_at"])


def get_purchase_problem(variant, quantity):
    """Return the first soft availability problem; this function never reserves stock."""
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= MAX_QUANTITY
    ):
        # ASSUMPTION: `available` is None for problems unrelated to stock quantity.
        return PurchaseProblem("invalid_quantity", None)
    if not variant.is_active:
        return PurchaseProblem("variant_inactive", None)

    product = variant.product
    if product.status != Product.Status.PUBLISHED:
        return PurchaseProblem("product_not_published", None)

    category = product.category
    while category is not None:
        if not category.is_active:
            return PurchaseProblem("category_inactive", None)
        category = category.parent

    base_price = variant.base_price
    if (
        not isinstance(base_price, int)
        or isinstance(base_price, bool)
        or not 1 <= base_price <= MAX_BASE_PRICE
        or not has_valid_pricing(variant)
    ):
        return PurchaseProblem("invalid_pricing", None)
    if variant.stock_quantity == 0:
        return PurchaseProblem("out_of_stock", 0)
    if variant.stock_quantity < quantity:
        return PurchaseProblem("insufficient_stock", variant.stock_quantity)
    return None
