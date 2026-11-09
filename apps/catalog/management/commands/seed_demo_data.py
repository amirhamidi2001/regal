from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog import services
from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.pricing import TierSpec


class Command(BaseCommand):
    help = "Create a small development-only demo catalog."

    # ASSUMPTION: Categories are identified by name/parent, products by demo code or name/category,
    # and variants by their normalized SKU when deciding whether an object already exists.

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo_data can only run when DEBUG=True.")

        summary = {
            "categories": {"created": 0, "skipped": 0},
            "products": {"created": 0, "skipped": 0},
            "variants": {"created": 0, "skipped": 0},
        }

        store_supplies = self._get_or_create_category("لوازم فروشگاهی", None, summary)
        rack_category = self._get_or_create_category("جالباسی", store_supplies, summary)
        self._get_or_create_category("ویترین", store_supplies, summary)
        packaging_category = self._get_or_create_category("لوازم بسته‌بندی", None, summary)

        # ASSUMPTION: These labels, product codes, and DEMO-prefixed SKU suffixes identify the demo fixtures.
        self._seed_product(
            name="جالباسی مدل ایکس",
            category=rack_category,
            code="DEMO-RACK",
            variants=(
                {
                    "sku": "DEMO-RACK-BLACK",
                    "base_price": 100000,
                    "stock_quantity": 500,
                    "attributes": ({"name": "رنگ", "value": "مشکی", "color_hex": "#000000"},),
                    "active": True,
                },
                {
                    "sku": "DEMO-RACK-WHITE",
                    "base_price": 105000,
                    "stock_quantity": 300,
                    "attributes": ({"name": "رنگ", "value": "سفید", "color_hex": "#FFFFFF"},),
                    "active": True,
                },
                {
                    "sku": "DEMO-RACK-GOLD",
                    "base_price": 120000,
                    "stock_quantity": 50,
                    "attributes": ({"name": "رنگ", "value": "طلایی", "color_hex": "#D4AF37"},),
                    "tier_specs": (
                        TierSpec(1, 5, Decimal("6")),
                        TierSpec(6, 50, Decimal("4")),
                        TierSpec(51, None, Decimal("3")),
                    ),
                    "active": True,
                },
            ),
            publish=True,
            summary=summary,
        )
        self._seed_product(
            name="رول کاغذ بسته‌بندی",
            category=packaging_category,
            code="DEMO-PAPER-ROLL",
            variants=(
                {
                    "sku": "DEMO-PAPER-ROLL",
                    "base_price": 25000,
                    "stock_quantity": 2000,
                    "attributes": (),
                    "active": True,
                },
            ),
            publish=True,
            summary=summary,
        )
        self._seed_product(
            name="محصول نمونه ناموجود",
            category=store_supplies,
            code="DEMO-OUT-OF-STOCK",
            variants=(
                {
                    "sku": "DEMO-OUT-OF-STOCK",
                    "base_price": 50000,
                    "stock_quantity": 0,
                    "attributes": (),
                    "active": True,
                },
            ),
            publish=True,
            summary=summary,
        )
        self._seed_product(
            name="محصول نمونه پیش‌نویس",
            category=store_supplies,
            code="DEMO-DRAFT",
            variants=(
                {
                    "sku": "DEMO-DRAFT",
                    "base_price": 75000,
                    "stock_quantity": 0,
                    "attributes": (),
                    "active": False,
                },
            ),
            publish=False,
            summary=summary,
        )

        self.stdout.write(
            "Created: {created_categories} categories, {created_products} products, "
            "{created_variants} variants. Skipped: {skipped_categories} categories, "
            "{skipped_products} products, {skipped_variants} variants.".format(
                created_categories=summary["categories"]["created"],
                created_products=summary["products"]["created"],
                created_variants=summary["variants"]["created"],
                skipped_categories=summary["categories"]["skipped"],
                skipped_products=summary["products"]["skipped"],
                skipped_variants=summary["variants"]["skipped"],
            )
        )

    def _get_or_create_category(self, name, parent, summary):
        category = (
            Category.objects.filter(name=name, parent=parent).order_by("pk").first()
        )
        if category is not None:
            summary["categories"]["skipped"] += 1
            return category

        category = Category.objects.create(
            name=name,
            parent=parent,
            slug=services.generate_unique_slug(Category, name),
        )
        summary["categories"]["created"] += 1
        return category

    def _seed_product(self, *, name, category, code, variants, publish, summary):
        existing_product = (
            Product.objects.filter(Q(code=code) | Q(name=name, category=category))
            .order_by("pk")
            .first()
        )
        if existing_product is not None:
            summary["products"]["skipped"] += 1
            summary["variants"]["skipped"] += len(variants)
            return existing_product

        existing_skus = {
            sku
            for sku in (spec["sku"] for spec in variants)
            if ProductVariant.objects.filter(sku=sku).exists()
        }
        if len(existing_skus) == len(variants):
            summary["products"]["skipped"] += 1
            summary["variants"]["skipped"] += len(variants)
            return None

        # Category/Product creation uses ORM only because no catalog creation service exists;
        # owner approval explicitly permits these two seed-only writes.
        product = Product.objects.create(
            name=name,
            slug=services.generate_unique_slug(Product, name),
            category=category,
            code=code,
        )
        summary["products"]["created"] += 1

        for spec in variants:
            if spec["sku"] in existing_skus:
                summary["variants"]["skipped"] += 1
                continue
            variant = services.create_variant(
                product,
                sku=spec["sku"],
                base_price=spec["base_price"],
                attributes=spec["attributes"],
                stock_quantity=spec["stock_quantity"],
                tier_specs=spec.get("tier_specs"),
                actor=None,
            )
            summary["variants"]["created"] += 1
            if spec["active"]:
                services.activate_variant(variant)

        if publish:
            services.publish_product(product)
        return product
