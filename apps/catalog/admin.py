from django.contrib import admin
from django.db.models import Count

from apps.catalog.models import Category, Product, ProductVariant, StockLog
from apps.catalog.pricing import tier_specs_for
from apps.core.money import format_toman


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """Allow authorized staff to inspect objects without editing catalog data."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(ReadOnlyModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "sort_order")
    search_fields = ("name", "slug")
    list_select_related = ("parent",)


@admin.register(Product)
class ProductAdmin(ReadOnlyModelAdmin):
    list_display = ("name", "slug", "category", "status", "code", "variants_count")
    list_filter = ("status", "category")
    search_fields = ("name", "slug", "code")
    list_select_related = ("category",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(variants_count=Count("variants"))

    @admin.display(description="تعداد گونه‌ها", ordering="variants_count")
    def variants_count(self, obj):
        return obj.variants_count


@admin.register(ProductVariant)
class ProductVariantAdmin(ReadOnlyModelAdmin):
    list_display = ("sku", "product", "base_price_display", "stock_quantity", "is_active")
    readonly_fields = ("attributes_summary", "tiers_summary")
    list_select_related = ("product",)
    search_fields = ("sku", "product__name")
    list_filter = ("is_active",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("product")
            .prefetch_related("attributes", "pricing_tiers")
        )

    @admin.display(description="قیمت پایه")
    def base_price_display(self, obj):
        return format_toman(obj.base_price)

    @admin.display(description="ویژگی‌ها")
    def attributes_summary(self, obj):
        attributes = sorted(obj.attributes.all(), key=lambda attribute: (attribute.sort_order, attribute.pk))
        return " / ".join(attribute.value for attribute in attributes)

    @admin.display(description="پله‌های قیمت")
    def tiers_summary(self, obj):
        summaries = []
        for tier in tier_specs_for(obj):
            quantity_range = (
                f"{tier.min_quantity}-{tier.max_quantity}"
                if tier.max_quantity is not None
                else f"{tier.min_quantity}+"
            )
            markup = format(tier.markup_percent.normalize(), "f")
            summaries.append(f"{quantity_range}: {markup}%")
        return ", ".join(summaries)


@admin.register(StockLog)
class StockLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "variant",
        "previous_quantity",
        "change",
        "new_quantity",
        "reason",
        "order_id",
        "actor",
        "created_at",
    )
    list_filter = ("reason",)
    date_hierarchy = "created_at"
    list_select_related = ("variant", "actor")
