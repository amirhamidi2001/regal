from io import StringIO
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.catalog.inventory import verify_stock_log
from apps.catalog.models import Category, Product, ProductVariant, StockLog
from apps.catalog.pricing import quote
from apps.catalog.services import publish_product
from apps.catalog.tests.helpers import make_variant


class SeedDemoDataTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_creates_demo_categories_products_variants_and_quotes(self):
        output = StringIO()

        call_command("seed_demo_data", stdout=output)

        self.assertEqual(Category.objects.count(), 4)
        self.assertEqual(Product.objects.count(), 4)
        self.assertEqual(ProductVariant.objects.count(), 6)
        self.assertEqual(
            output.getvalue().strip(),
            "Created: 4 categories, 4 products, 6 variants. "
            "Skipped: 0 categories, 0 products, 0 variants.",
        )

        store_supplies = Category.objects.get(name="لوازم فروشگاهی", parent=None)
        self.assertSetEqual(
            set(store_supplies.children.values_list("name", flat=True)),
            {"جالباسی", "ویترین"},
        )
        self.assertTrue(Category.objects.filter(name="لوازم بسته‌بندی", parent=None).exists())

        rack_product = Product.objects.get(code="DEMO-RACK")
        self.assertEqual(rack_product.name, "جالباسی مدل ایکس")
        self.assertEqual(rack_product.status, Product.Status.PUBLISHED)
        rack_variants = {variant.sku: variant for variant in rack_product.variants.all()}
        black = rack_variants["DEMO-RACK-BLACK"]
        white = rack_variants["DEMO-RACK-WHITE"]
        gold = rack_variants["DEMO-RACK-GOLD"]
        self.assertEqual(quote(black, 5).line_total, 520000)
        self.assertEqual(quote(gold, 3).unit_price, 127200)
        self.assertEqual(quote(gold, 6).unit_price, 124800)
        self.assertEqual(quote(gold, 51).unit_price, 123600)
        self.assertEqual(black.attributes.get(name="رنگ").color_hex, "#000000")
        self.assertEqual(white.attributes.get(name="رنگ").color_hex, "#FFFFFF")
        self.assertEqual(gold.attributes.get(name="رنگ").color_hex, "#D4AF37")
        self.assertTrue(all(variant.is_active for variant in (black, white, gold)))

        paper = Product.objects.get(code="DEMO-PAPER-ROLL")
        self.assertEqual(paper.status, Product.Status.PUBLISHED)
        self.assertEqual(paper.variants.count(), 1)
        self.assertEqual(paper.variants.get().attributes.count(), 0)
        self.assertEqual(paper.variants.get().stock_quantity, 2000)

        out_of_stock = Product.objects.get(code="DEMO-OUT-OF-STOCK")
        self.assertEqual(out_of_stock.status, Product.Status.PUBLISHED)
        self.assertTrue(out_of_stock.variants.get().is_active)
        self.assertEqual(out_of_stock.variants.get().stock_quantity, 0)

        draft = Product.objects.get(code="DEMO-DRAFT")
        self.assertEqual(draft.status, Product.Status.DRAFT)
        self.assertFalse(draft.variants.get().is_active)

        for product in Product.objects.filter(status=Product.Status.PUBLISHED):
            # The published products have active, correctly priced variants and pass the service rule.
            publish_product(product)

    @override_settings(DEBUG=True)
    def test_second_run_creates_nothing_and_skips_existing_demo_objects(self):
        call_command("seed_demo_data", stdout=StringIO())
        before_counts = (
            Category.objects.count(),
            Product.objects.count(),
            ProductVariant.objects.count(),
            StockLog.objects.count(),
        )
        output = StringIO()

        call_command("seed_demo_data", stdout=output)

        self.assertEqual(
            output.getvalue().strip(),
            "Created: 0 categories, 0 products, 0 variants. "
            "Skipped: 4 categories, 4 products, 6 variants.",
        )
        self.assertEqual(
            (
                Category.objects.count(),
                Product.objects.count(),
                ProductVariant.objects.count(),
                StockLog.objects.count(),
            ),
            before_counts,
        )

    @override_settings(DEBUG=False)
    def test_refuses_outside_debug_without_creating_anything(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(Category.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(ProductVariant.objects.count(), 0)
        self.assertEqual(StockLog.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_all_demo_variants_have_consistent_stock_logs(self):
        call_command("seed_demo_data", stdout=StringIO())

        variants = ProductVariant.objects.filter(sku__startswith="DEMO-")
        self.assertEqual(variants.count(), 6)
        for variant in variants:
            with self.subTest(sku=variant.sku):
                self.assertTrue(verify_stock_log(variant.pk).ok)
                if variant.stock_quantity == 0:
                    self.assertFalse(StockLog.objects.filter(variant=variant).exists())

    @override_settings(DEBUG=True)
    def test_existing_products_and_skus_are_skipped_without_modification(self):
        existing_category = Category.objects.create(name="Existing", slug="existing")
        existing_product = Product.objects.create(
            name="جالباسی مدل ایکس",
            slug="existing-rack",
            category=existing_category,
            code="DEMO-RACK",
            status=Product.Status.ARCHIVED,
        )
        existing_sku_variant = make_variant(sku="DEMO-PAPER-ROLL", base_price=35000)
        initial_status = existing_product.status
        initial_price = existing_sku_variant.base_price
        initial_product_id = existing_sku_variant.product_id

        call_command("seed_demo_data", stdout=StringIO())

        existing_product.refresh_from_db()
        existing_sku_variant.refresh_from_db()
        self.assertEqual(existing_product.status, initial_status)
        self.assertEqual(existing_sku_variant.base_price, initial_price)
        self.assertEqual(existing_sku_variant.product_id, initial_product_id)
        self.assertFalse(Product.objects.filter(code="DEMO-PAPER-ROLL").exists())

