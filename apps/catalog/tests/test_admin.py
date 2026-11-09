from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.catalog.admin import ProductVariantAdmin
from apps.catalog.inventory import adjust_manual
from apps.catalog.models import (
    Category,
    PricingTier,
    Product,
    ProductImage,
    ProductVariant,
    StockLog,
    VariantAttribute,
)
from apps.catalog.pricing import replace_pricing_tiers
from apps.catalog.tests.helpers import make_category, make_product, make_variant


class CatalogAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            mobile="09123456789",
            password="A-strong-test-password-123",
            full_name="Catalog Inspector",
        )
        cls.category = make_category()
        cls.product = make_product(category=cls.category)
        cls.variant = make_variant(product=cls.product, base_price=100000)
        replace_pricing_tiers(cls.variant)
        VariantAttribute.objects.create(
            variant=cls.variant,
            name="رنگ",
            value="مشکی",
            sort_order=1,
        )
        cls.stock_log = adjust_manual(cls.variant.pk, 3)

    def setUp(self):
        self.client.force_login(self.user)

    def admin_url(self, model, action, object_id=None):
        route = f"admin:{model._meta.app_label}_{model._meta.model_name}_{action}"
        args = [] if object_id is None else [object_id]
        return reverse(route, args=args)

    def test_registered_models_are_viewable_but_never_mutable(self):
        model_objects = (
            (Category, self.category),
            (Product, self.product),
            (ProductVariant, self.variant),
            (StockLog, self.stock_log),
        )
        for model, obj in model_objects:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)
                self.assertEqual(self.client.get(self.admin_url(model, "changelist")).status_code, 200)
                self.assertEqual(
                    self.client.get(self.admin_url(model, "change", obj.pk)).status_code,
                    200,
                )
                self.assertEqual(self.client.get(self.admin_url(model, "add")).status_code, 403)
                self.assertEqual(
                    self.client.post(self.admin_url(model, "change", obj.pk), {}).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.get(self.admin_url(model, "delete", obj.pk)).status_code,
                    403,
                )

    def test_pricing_tiers_attributes_and_product_images_are_not_registered(self):
        for model in (PricingTier, VariantAttribute, ProductImage):
            with self.subTest(model=model.__name__):
                self.assertNotIn(model, admin.site._registry)

    def test_staff_with_view_permission_can_open_changelist_and_detail(self):
        staff_user = get_user_model().objects.create_user(
            mobile="09123456780",
            password="A-strong-test-password-456",
            full_name="Category Viewer",
            is_staff=True,
        )
        view_permission = Permission.objects.get(
            content_type__app_label="catalog",
            content_type__model="category",
            codename="view_category",
        )
        staff_user.user_permissions.add(view_permission)
        self.client.force_login(staff_user)

        self.assertEqual(self.client.get(self.admin_url(Category, "changelist")).status_code, 200)
        self.assertEqual(
            self.client.get(self.admin_url(Category, "change", self.category.pk)).status_code,
            200,
        )

    def test_variant_changelist_query_count_does_not_grow_with_row_count(self):
        product = make_product()
        for _ in range(5):
            make_variant(product=product)

        url = self.admin_url(ProductVariant, "changelist")
        with CaptureQueriesContext(connection) as five_variant_queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        five_query_count = len(five_variant_queries)

        for _ in range(20):
            make_variant(product=product)
        with CaptureQueriesContext(connection) as twenty_five_variant_queries:
            self.assertEqual(self.client.get(url).status_code, 200)

        self.assertEqual(len(twenty_five_variant_queries), five_query_count)

    def test_variant_summary_methods_render_ordered_values_and_tiers(self):
        model_admin = ProductVariantAdmin(ProductVariant, admin.site)

        self.assertEqual(model_admin.attributes_summary(self.variant), "مشکی")
        self.assertEqual(
            model_admin.tiers_summary(self.variant),
            "1-10: 4%, 11-100: 3%, 101-1000: 2%, 1001+: 2%",
        )
