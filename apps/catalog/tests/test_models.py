from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.catalog.constants import MAX_BASE_PRICE
from apps.catalog.models import Category, Product, ProductVariant, VariantAttribute
from apps.catalog.tests.helpers import make_category, make_product, make_variant


class CategoryModelTests(TestCase):
    def test_database_rejects_self_parent(self):
        category = make_category()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.filter(pk=category.pk).update(parent_id=category.pk)

    def test_unicode_slug_round_trips_and_duplicate_is_rejected(self):
        category = make_category(slug="کالای-فارسی")
        self.assertEqual(Category.objects.get(pk=category.pk).slug, "کالای-فارسی")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_category(slug="کالای-فارسی")

    def test_category_with_products_is_protected(self):
        product = make_product()
        with self.assertRaises(ProtectedError):
            product.category.delete()


class ProductModelTests(TestCase):
    def test_product_defaults_to_draft(self):
        self.assertEqual(make_product().status, Product.Status.DRAFT)


class ProductVariantModelTests(TestCase):
    def test_sku_is_trimmed_and_uppercased_and_duplicate_case_is_rejected(self):
        first = make_variant(sku="  ab-12  ")
        self.assertEqual(first.sku, "AB-12")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_variant(sku="ab-12")

    def test_base_price_database_range(self):
        product = make_product()
        for sku, price in (("ZERO", 0), ("TOO-HIGH", MAX_BASE_PRICE + 1)):
            with self.subTest(price=price), self.assertRaises(IntegrityError), transaction.atomic():
                ProductVariant.objects.bulk_create(
                    [ProductVariant(product=product, sku=sku, base_price=price)]
                )

    def test_stock_cannot_be_negative_through_queryset_update(self):
        variant = make_variant()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductVariant.objects.filter(pk=variant.pk).update(stock_quantity=-1)

    def test_defaults_to_zero_stock_and_inactive(self):
        variant = make_variant()
        self.assertEqual(variant.stock_quantity, 0)
        self.assertFalse(variant.is_active)

    def test_product_deletion_cascades_to_variants_and_attributes(self):
        variant = make_variant()
        attribute = VariantAttribute.objects.create(variant=variant, name="رنگ", value="آبی")
        product_id, variant_id, attribute_id = variant.product_id, variant.pk, attribute.pk
        Product.objects.get(pk=product_id).delete()
        self.assertFalse(ProductVariant.objects.filter(pk=variant_id).exists())
        self.assertFalse(VariantAttribute.objects.filter(pk=attribute_id).exists())

    def test_timestamps_are_set(self):
        variant = make_variant()
        self.assertIsNotNone(variant.created_at)
        self.assertIsNotNone(variant.updated_at)

class VariantAttributeModelTests(TestCase):
    def test_unique_per_variant_and_name(self):
        variant = make_variant()
        VariantAttribute.objects.create(variant=variant, name="رنگ", value="آبی")
        with self.assertRaises(IntegrityError), transaction.atomic():
            VariantAttribute.objects.create(variant=variant, name="رنگ", value="قرمز")

    def test_color_hex_validator_rejects_bad_value(self):
        attribute = VariantAttribute(variant=make_variant(), name="رنگ", value="آبی", color_hex="blue")
        with self.assertRaises(ValidationError):
            attribute.full_clean()

