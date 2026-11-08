from itertools import count

from apps.catalog.models import Category, Product, ProductVariant

_counter = count(1)


def make_category(**overrides):
    number = next(_counter)
    values = {"name": f"دسته {number}", "slug": f"دسته-{number}"}
    values.update(overrides)
    return Category.objects.create(**values)


def make_product(**overrides):
    number = next(_counter)
    values = {
        "name": f"محصول {number}",
        "slug": f"محصول-{number}",
        "category": make_category(),
    }
    values.update(overrides)
    return Product.objects.create(**values)


def make_variant(**overrides):
    number = next(_counter)
    values = {
        "product": make_product(),
        "sku": f"SKU-{number}",
        "base_price": 1000,
    }
    values.update(overrides)
    return ProductVariant.objects.create(**values)
