from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.constants import MAX_QUANTITY
from apps.catalog.inventory import adjust_manual, verify_stock_log
from apps.catalog.models import Category, Product, ProductVariant, PricingTier, StockLog, VariantAttribute
from apps.catalog.pricing import InvalidTierSet, TierSpec, replace_pricing_tiers
from apps.catalog.services import (
    ActivationError,
    CategoryCycleError,
    PurchaseProblem,
    PublishError,
    activate_variant,
    archive_product,
    build_category_tree,
    create_variant,
    deactivate_variant,
    generate_unique_slug,
    get_descendant_category_ids,
    get_purchase_problem,
    is_simple_product,
    publish_product,
    set_category_parent,
    unpublish_product,
    variant_label,
)
from apps.catalog.tests.helpers import make_category, make_product, make_variant


class CatalogSlugTests(TestCase):
    def test_persian_names_keep_letters_and_join_words_with_hyphens(self):
        self.assertEqual(generate_unique_slug(Category, "کالای تازه"), "کالای-تازه")

    def test_collisions_use_incrementing_numeric_suffixes(self):
        make_category(slug="کالای-تازه")
        make_category(slug="کالای-تازه-2")
        self.assertEqual(generate_unique_slug(Category, "کالای تازه"), "کالای-تازه-3")

    def test_empty_slug_falls_back_to_item(self):
        self.assertEqual(generate_unique_slug(Category, "!!!"), "item")
        make_category(slug="item")
        self.assertEqual(generate_unique_slug(Category, "!!!"), "item-2")

    def test_instance_does_not_collide_with_its_own_slug(self):
        category = make_category(slug="موجود")
        self.assertEqual(
            generate_unique_slug(Category, "موجود", instance_pk=category.pk),
            "موجود",
        )

    def test_overlong_slug_is_truncated_and_stays_unique(self):
        name = "نام" * 100
        first_slug = generate_unique_slug(Category, name)
        self.assertLessEqual(len(first_slug), Category._meta.get_field("slug").max_length)
        make_category(slug=first_slug)
        second_slug = generate_unique_slug(Category, name)
        self.assertLessEqual(len(second_slug), Category._meta.get_field("slug").max_length)
        self.assertNotEqual(first_slug, second_slug)
        self.assertTrue(second_slug.endswith("-2"))


class CategoryServiceTests(TestCase):
    def test_tree_nesting_ordering_inactive_handling_and_single_query(self):
        root_b = make_category(name="ریشه ب", slug="root-b", sort_order=2)
        root_a = make_category(name="ریشه الف", slug="root-a", sort_order=1)
        child_b = make_category(name="فرزند ب", slug="child-b", parent=root_a, sort_order=2)
        child_a = make_category(name="فرزند الف", slug="child-a", parent=root_a, sort_order=1)
        make_category(name="ریشه پنهان", slug="hidden-root", is_active=False)
        make_category(name="فرزند پنهان", slug="hidden-child", parent=root_b, is_active=False)
        nested_under_inactive = make_category(
            name="فرزند فعال پنهان",
            slug="active-hidden-child",
            parent=Category.objects.get(slug="hidden-root"),
        )

        with self.assertNumQueries(1):
            visible = build_category_tree()
        self.assertEqual([node.category for node in visible], [root_a, root_b])
        self.assertEqual(
            [node.category for node in visible[0].children],
            [child_a, child_b],
        )
        self.assertFalse(any(node.category == nested_under_inactive for node in visible))

        with self.assertNumQueries(1):
            all_nodes = build_category_tree(include_inactive=True)
        self.assertEqual(len(all_nodes), 3)
        self.assertEqual(
            [node.category.slug for node in all_nodes[-1].children],
            ["hidden-child"],
        )

    def test_descendant_ids_are_breadth_first_with_optional_self(self):
        root = make_category()
        child_a = make_category(parent=root)
        child_b = make_category(parent=root)
        grandchild = make_category(parent=child_a)
        with self.assertNumQueries(1):
            with_self = get_descendant_category_ids(root.pk)
        with self.assertNumQueries(1):
            without_self = get_descendant_category_ids(root.pk, include_self=False)
        self.assertEqual(with_self, [root.pk, child_a.pk, child_b.pk, grandchild.pk])
        self.assertEqual(without_self, [child_a.pk, child_b.pk, grandchild.pk])

    def test_set_category_parent_moves_and_accepts_none(self):
        old_parent = make_category()
        new_parent = make_category()
        category = make_category(parent=old_parent)

        set_category_parent(category, new_parent)
        self.assertEqual(Category.objects.get(pk=category.pk).parent_id, new_parent.pk)
        self.assertEqual(category.parent_id, new_parent.pk)
        set_category_parent(category, None)
        self.assertIsNone(Category.objects.get(pk=category.pk).parent_id)

    def test_set_category_parent_rejects_self_child_and_grandchild_without_changes(self):
        root = make_category()
        child = make_category(parent=root)
        grandchild = make_category(parent=child)
        original = {
            row.pk: row.parent_id
            for row in Category.objects.filter(pk__in=(root.pk, child.pk, grandchild.pk))
        }

        for category, parent in ((root, root), (root, child), (root, grandchild)):
            with self.subTest(parent=parent.pk), self.assertRaises(CategoryCycleError):
                set_category_parent(category, parent)
            self.assertEqual(
                {
                    row.pk: row.parent_id
                    for row in Category.objects.filter(pk__in=(root.pk, child.pk, grandchild.pk))
                },
                original,
            )


class VariantServiceTests(TestCase):
    def test_create_variant_creates_defaults_attributes_and_initial_stock_log(self):
        product = make_product()
        actor = get_user_model().objects.create_user("09123456789", full_name="کاربر")

        variant = create_variant(
            product,
            sku=" blue-shirt ",
            base_price=100000,
            attributes=[{"name": "رنگ", "value": "آبی", "color_hex": "#123ABC"}],
            stock_quantity=5,
            actor=actor,
        )

        self.assertFalse(variant.is_active)
        self.assertEqual(variant.sku, "BLUE-SHIRT")
        self.assertEqual(variant.stock_quantity, 5)
        self.assertEqual(variant.pricing_tiers.count(), 4)
        self.assertEqual(variant.attributes.get().value, "آبی")
        logs = StockLog.objects.filter(variant=variant)
        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(log.reason, StockLog.Reason.MANUAL_ADJUSTMENT)
        self.assertEqual(log.actor, actor)
        self.assertEqual(log.note, "initial stock")
        self.assertTrue(verify_stock_log(variant.pk).ok)

    def test_zero_initial_stock_writes_no_log(self):
        variant = create_variant(make_product(), sku="ZERO", base_price=1000, stock_quantity=0)
        self.assertEqual(variant.stock_quantity, 0)
        self.assertFalse(StockLog.objects.filter(variant=variant).exists())

    def test_case_insensitive_duplicate_sku_leaves_nothing_created(self):
        product = make_product()
        make_variant(product=product, sku="DUPLICATE")
        counts_before = (
            ProductVariant.objects.count(),
            PricingTier.objects.count(),
            StockLog.objects.count(),
        )

        with self.assertRaises(ValidationError):
            create_variant(product, sku=" duplicate ", base_price=1000, stock_quantity=3)

        self.assertEqual(
            (
                ProductVariant.objects.count(),
                PricingTier.objects.count(),
                StockLog.objects.count(),
            ),
            counts_before,
        )

    def test_custom_tiers_are_used(self):
        custom = (TierSpec(1, 4, Decimal("8")), TierSpec(5, None, Decimal("2")))
        variant = create_variant(
            make_product(),
            sku="CUSTOM-TIERS",
            base_price=10000,
            tier_specs=custom,
        )
        self.assertEqual(
            list(variant.pricing_tiers.order_by("min_quantity").values_list("min_quantity", "max_quantity", "markup_percent")),
            [(1, 4, Decimal("8.00")), (5, None, Decimal("2.00"))],
        )

    def test_invalid_tiers_leave_no_variant_attributes_tiers_or_logs(self):
        product = make_product()
        counts_before = (
            ProductVariant.objects.count(),
            VariantAttribute.objects.count(),
            PricingTier.objects.count(),
            StockLog.objects.count(),
        )
        with self.assertRaises(InvalidTierSet):
            create_variant(
                product,
                sku="INVALID-TIERS",
                base_price=1000,
                attributes=[{"name": "رنگ", "value": "قرمز"}],
                stock_quantity=3,
                tier_specs=(TierSpec(1, 3, Decimal("2")), TierSpec(5, None, Decimal("1"))),
            )
        self.assertEqual(
            (
                ProductVariant.objects.count(),
                VariantAttribute.objects.count(),
                PricingTier.objects.count(),
                StockLog.objects.count(),
            ),
            counts_before,
        )

    def test_variant_label_for_empty_single_and_sorted_values(self):
        empty = make_variant()
        one = make_variant()
        VariantAttribute.objects.create(variant=one, name="رنگ", value="آبی")
        two = make_variant()
        VariantAttribute.objects.create(variant=two, name="سایز", value="بزرگ", sort_order=2)
        VariantAttribute.objects.create(variant=two, name="رنگ", value="قرمز", sort_order=1)

        self.assertEqual(variant_label(empty), "")
        self.assertEqual(variant_label(one), "آبی")
        self.assertEqual(variant_label(two), "قرمز / بزرگ")

    def test_is_simple_product(self):
        no_variants = make_product()
        bare = make_product()
        bare_variant = make_variant(product=bare)
        with_attribute = make_product()
        attr_variant = make_variant(product=with_attribute)
        VariantAttribute.objects.create(variant=attr_variant, name="رنگ", value="آبی")
        multiple = make_product()
        make_variant(product=multiple)
        make_variant(product=multiple)

        self.assertFalse(is_simple_product(no_variants))
        self.assertTrue(is_simple_product(bare))
        self.assertFalse(is_simple_product(with_attribute))
        self.assertFalse(is_simple_product(multiple))
        self.assertIsNotNone(bare_variant.pk)

    def test_activate_valid_variant_is_idempotent_and_invalid_pricing_fails(self):
        variant = create_variant(make_product(), sku="ACTIVATE", base_price=1000)
        self.assertFalse(variant.is_active)
        activate_variant(variant)
        self.assertTrue(variant.is_active)
        activate_variant(variant)
        self.assertTrue(ProductVariant.objects.get(pk=variant.pk).is_active)

        PricingTier.objects.filter(variant=variant).delete()
        variant.refresh_from_db()
        with self.assertRaises(ActivationError):
            activate_variant(variant)
        self.assertTrue(variant.is_active)

    def test_deactivate_variant_sets_inactive(self):
        variant = make_variant(is_active=True)
        deactivate_variant(variant)
        self.assertFalse(ProductVariant.objects.get(pk=variant.pk).is_active)


class ProductLifecycleTests(TestCase):
    def test_publish_lists_inactive_category_problem(self):
        category = make_category(is_active=False)
        product = make_product(category=category)
        with self.assertRaises(PublishError) as caught:
            publish_product(product)
        self.assertIn("category_inactive", caught.exception.problems)
        self.assertIn("category_inactive", str(caught.exception))

    def test_publish_lists_missing_active_variant_problem(self):
        product = make_product()
        with self.assertRaises(PublishError) as caught:
            publish_product(product)
        self.assertIn("no_active_variants", caught.exception.problems)

    def test_publish_lists_invalid_pricing_for_active_variant(self):
        product = make_product()
        variant = create_variant(product, sku="BAD-PRICING", base_price=1000)
        activate_variant(variant)
        PricingTier.objects.filter(variant=variant).delete()

        with self.assertRaises(PublishError) as caught:
            publish_product(product)
        self.assertIn(f"invalid_pricing:{variant.pk}", caught.exception.problems)

    def test_publish_unpublish_and_archive_change_product_status_only(self):
        product = make_product()
        variant = create_variant(product, sku="PUBLISHED", base_price=1000)
        activate_variant(variant)

        publish_product(product)
        self.assertEqual(Product.objects.get(pk=product.pk).status, Product.Status.PUBLISHED)
        self.assertTrue(ProductVariant.objects.get(pk=variant.pk).is_active)
        unpublish_product(product)
        self.assertEqual(Product.objects.get(pk=product.pk).status, Product.Status.DRAFT)
        self.assertTrue(ProductVariant.objects.get(pk=variant.pk).is_active)
        archive_product(product)
        self.assertEqual(Product.objects.get(pk=product.pk).status, Product.Status.ARCHIVED)
        self.assertTrue(ProductVariant.objects.get(pk=variant.pk).is_active)


class PurchaseProblemTests(TestCase):
    def setUp(self):
        self.category = make_category()
        self.product = make_product(category=self.category, status=Product.Status.PUBLISHED)
        self.variant = make_variant(product=self.product, base_price=1000, is_active=True)
        replace_pricing_tiers(self.variant)
        adjust_manual(self.variant.pk, 3)
        self.variant.refresh_from_db()

    def test_valid_purchase_and_each_soft_problem(self):
        self.assertIsNone(get_purchase_problem(self.variant, 2))

        cases = (
            ("variant_inactive", lambda: self.variant, self.deactivate_variant),
            ("product_not_published", lambda: self.variant, self.unpublish_product),
            ("category_inactive", lambda: self.variant, self.deactivate_ancestor),
            ("invalid_pricing", lambda: self.variant, self.remove_pricing),
            ("out_of_stock", lambda: self.out_of_stock_variant(), None),
            ("insufficient_stock", lambda: self.variant, None),
        )
        for code, get_variant, prepare in cases:
            with self.subTest(code=code):
                self.restore_valid_state()
                if prepare is not None:
                    prepare()
                variant = get_variant()
                quantity = 5 if code == "insufficient_stock" else 1
                problem = get_purchase_problem(variant, quantity)
                self.assertEqual(problem.code, code)
                if code == "insufficient_stock":
                    self.assertEqual(problem.available, 3)
                if code == "out_of_stock":
                    self.assertEqual(problem.available, 0)

    def test_invalid_quantity_values_are_reported_first(self):
        for quantity in (0, MAX_QUANTITY + 1, True, "2"):
            with self.subTest(quantity=quantity):
                problem = get_purchase_problem(self.variant, quantity)
                self.assertEqual(problem, PurchaseProblem("invalid_quantity", None))

    def deactivate_variant(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(is_active=False)
        self.variant.refresh_from_db()

    def unpublish_product(self):
        Product.objects.filter(pk=self.product.pk).update(status=Product.Status.DRAFT)
        self.product.refresh_from_db()

    def deactivate_ancestor(self):
        parent = make_category(is_active=False)
        set_category_parent(self.category, parent)
        self.category.refresh_from_db()

    def remove_pricing(self):
        PricingTier.objects.filter(variant=self.variant).delete()

    def out_of_stock_variant(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(stock_quantity=0)
        self.variant.refresh_from_db()
        return self.variant

    def restore_valid_state(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(is_active=True, stock_quantity=3)
        Product.objects.filter(pk=self.product.pk).update(status=Product.Status.PUBLISHED)
        Category.objects.filter(pk=self.category.pk).update(is_active=True, parent=None)
        if not PricingTier.objects.filter(variant=self.variant).exists():
            replace_pricing_tiers(self.variant)
        self.variant.refresh_from_db()
        self.product.refresh_from_db()
        self.category.refresh_from_db()
