from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.catalog.constants import MAX_BASE_PRICE
from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name="دسته‌بندی والد",
    )
    name = models.CharField(max_length=120, verbose_name="نام")
    slug = models.SlugField(max_length=140, unique=True, allow_unicode=True, verbose_name="نامک")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ("sort_order", "name")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("pk")),
                name="catalog_category_parent_not_self",
            ),
        ]
        indexes = [models.Index(fields=("parent", "sort_order"))]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"
        ARCHIVED = "archived", "بایگانی‌شده"

    name = models.CharField(max_length=200, verbose_name="نام")
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True, verbose_name="نامک")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="دسته‌بندی",
    )
    short_description = models.CharField(max_length=300, blank=True, verbose_name="توضیح کوتاه")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    status = models.CharField(
        max_length=12,
        choices=Status,
        default=Status.DRAFT,
        verbose_name="وضعیت",
    )
    code = models.CharField(max_length=64, blank=True, verbose_name="کد محصول")

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        indexes = [models.Index(fields=("category", "status"))]

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name="محصول",
    )
    sku = models.CharField(max_length=64, unique=True, verbose_name="شناسه انبار")
    base_price = models.PositiveBigIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_BASE_PRICE)],
        verbose_name="قیمت پایه (تومان)",
    )
    # This field is written only by catalog/inventory.py.
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="موجودی")
    is_active = models.BooleanField(default=False, verbose_name="فعال")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "گونه محصول"
        verbose_name_plural = "گونه‌های محصول"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_price__gte=1, base_price__lte=MAX_BASE_PRICE),
                name="catalog_variant_base_price_range",
            ),
        ]
        indexes = [models.Index(fields=("product", "is_active"))]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.sku


class VariantAttribute(TimeStampedModel):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="attributes",
        verbose_name="گونه محصول",
    )
    name = models.CharField(max_length=60, verbose_name="ویژگی")
    value = models.CharField(max_length=100, verbose_name="مقدار")
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "کد رنگ باید به شکل #RRGGBB باشد.")],
        verbose_name="کد رنگ",
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "ویژگی گونه محصول"
        verbose_name_plural = "ویژگی‌های گونه محصول"
        constraints = [
            models.UniqueConstraint(
                fields=("variant", "name"),
                name="catalog_variantattribute_unique_name",
            ),
        ]

    def __str__(self):
        return f"{self.name}: {self.value}"


class PricingTier(TimeStampedModel):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="pricing_tiers",
        verbose_name="گونه محصول",
    )
    min_quantity = models.PositiveIntegerField(verbose_name="حداقل تعداد")
    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="حداکثر تعداد",
    )
    markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="درصد افزایش قیمت",
    )

    class Meta:
        verbose_name = "پله قیمت‌گذاری"
        verbose_name_plural = "پله‌های قیمت‌گذاری"
        ordering = ("variant", "min_quantity")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_quantity__gte=1),
                name="catalog_pricingtier_min_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(max_quantity__isnull=True)
                | models.Q(max_quantity__gte=models.F("min_quantity")),
                name="catalog_pricingtier_max_gte_min",
            ),
            models.CheckConstraint(
                condition=models.Q(markup_percent__gte=0),
                name="catalog_pricingtier_markup_gte_0",
            ),
            models.UniqueConstraint(
                fields=("variant", "min_quantity"),
                name="catalog_pricingtier_unique_variant_min",
            ),
            models.UniqueConstraint(
                fields=("variant",),
                condition=models.Q(max_quantity__isnull=True),
                name="catalog_pricingtier_one_unlimited_per_variant",
            ),
        ]

    def __str__(self):
        return f"{self.variant}: {self.min_quantity}–{self.max_quantity or '∞'}"


class ImmutableLogError(RuntimeError):
    """Raised when application code attempts to change an existing stock log."""


class StockLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableLogError("Stock log rows are append-only.")

    def delete(self):
        raise ImmutableLogError("Stock log rows are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableLogError("Stock log rows are append-only.")


class StockLog(models.Model):
    class Reason(models.TextChoices):
        ORDER_PAID = "order_paid", "پرداخت سفارش"
        ORDER_CANCELLED = "order_cancelled", "لغو سفارش"
        MANUAL_ADJUSTMENT = "manual_adjustment", "اصلاح دستی موجودی"
        CONFLICT_RESOLUTION = "conflict_resolution", "رفع مغایرت"

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="stock_logs",
        verbose_name="گونه محصول",
    )
    previous_quantity = models.PositiveIntegerField(verbose_name="موجودی پیشین")
    change = models.IntegerField(verbose_name="تغییر موجودی")
    new_quantity = models.PositiveIntegerField(verbose_name="موجودی جدید")
    reason = models.CharField(max_length=32, choices=Reason, verbose_name="دلیل")
    # ASSUMPTION: This stays an integer until Phase 6A converts it to a ForeignKey named order; orders has no model yet.
    order_id = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="شناسه سفارش")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_logs",
        verbose_name="کاربر انجام‌دهنده",
    )
    note = models.CharField(max_length=255, blank=True, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    objects = StockLogQuerySet.as_manager()

    class Meta:
        verbose_name = "گزارش تغییر موجودی"
        verbose_name_plural = "گزارش‌های تغییر موجودی"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(change=0),
                name="catalog_stocklog_change_nonzero",
            ),
            models.CheckConstraint(
                condition=models.Q(new_quantity=models.F("previous_quantity") + models.F("change")),
                name="catalog_stocklog_arithmetic",
            ),
        ]
        indexes = [
            models.Index(fields=("variant", "created_at")),
            models.Index(fields=("order_id",)),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ImmutableLogError("Stock log rows are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableLogError("Stock log rows are append-only.")

    def __str__(self):
        return f"{self.variant_id}: {self.previous_quantity} → {self.new_quantity}"
