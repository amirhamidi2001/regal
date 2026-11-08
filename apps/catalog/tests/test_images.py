import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from PIL import Image

from apps.catalog.images import (
    ImageError,
    build_derivatives,
    delete_derivatives,
    derivative_name,
    validate_uploaded_image,
)
from apps.catalog.models import Product, ProductImage
from apps.catalog.tests.helpers import make_category


def make_image_bytes(format_name, size=(20, 10), mode=None, *, exif=None, color=None):
    mode = mode or ("RGBA" if format_name == "PNG" else "RGB")
    color = color or ((255, 0, 0, 128) if mode == "RGBA" else (80, 120, 160))
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=format_name, exif=exif or b"")
    image.close()
    return output.getvalue()


class ImageTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_settings = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.storage = FileSystemStorage(location=self.media_directory.name)

    def uploaded(self, name, data, content_type="application/octet-stream"):
        return SimpleUploadedFile(name, data, content_type=content_type)

    def assert_validation_code(self, upload, code):
        with self.assertRaises(ValidationError) as caught:
            validate_uploaded_image(upload)
        self.assertEqual(caught.exception.code, code)


class ImageValidationTests(ImageTestCase):
    def test_accepts_jpeg_png_with_alpha_and_webp(self):
        for format_name in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format=format_name):
                upload = self.uploaded(
                    f"image.{format_name.lower()}",
                    make_image_bytes(format_name),
                    content_type="text/plain",
                )
                validate_uploaded_image(upload)
                self.assertEqual(upload.tell(), 0)

    def test_rejects_unsupported_formats(self):
        for format_name in ("GIF", "BMP"):
            with self.subTest(format=format_name):
                self.assert_validation_code(
                    self.uploaded("photo.jpg", make_image_bytes(format_name)),
                    "image_unsupported_format",
                )

    def test_rejects_text_named_as_jpeg_and_truncated_jpeg(self):
        self.assert_validation_code(
            self.uploaded("photo.jpg", b"this is plain text", "image/jpeg"),
            "invalid_image",
        )
        jpeg = make_image_bytes("JPEG", (80, 60))
        self.assert_validation_code(
            self.uploaded("truncated.jpg", jpeg[: len(jpeg) // 2], "image/jpeg"),
            "invalid_image",
        )

    def test_rejects_oversized_file(self):
        with patch("apps.catalog.images.MAX_IMAGE_BYTES", 16):
            self.assert_validation_code(
                self.uploaded("large.png", make_image_bytes("PNG", (20, 10))),
                "image_too_large",
            )

    def test_rejects_too_many_pixels_from_header_dimensions(self):
        with patch("apps.catalog.images.MAX_IMAGE_PIXELS", 100):
            self.assert_validation_code(
                self.uploaded("large.png", make_image_bytes("PNG", (11, 10))),
                "image_too_many_pixels",
            )


class DerivativeTests(ImageTestCase):
    def save_original(self, name, data):
        return self.storage.save(name, ContentFile(data))

    def dimensions_and_format(self, name):
        with self.storage.open(name, "rb") as file:
            with Image.open(file) as image:
                return image.size, image.format, image.mode, image.getexif()

    def test_builds_card_and_detail_at_expected_sizes(self):
        name = self.save_original("products/main/2026/11/large.jpg", make_image_bytes("JPEG", (2000, 1000)))

        derivatives = build_derivatives(name, storage=self.storage)

        self.assertEqual(derivatives["card"], "products/main/2026/11/large.card.webp")
        self.assertEqual(derivatives["detail"], "products/main/2026/11/large.detail.webp")
        self.assertEqual(self.dimensions_and_format(derivatives["card"])[0:2], ((480, 240), "WEBP"))
        self.assertEqual(self.dimensions_and_format(derivatives["detail"])[0:2], ((960, 480), "WEBP"))

    def test_never_upscales_and_preserves_aspect_ratio_within_one_pixel(self):
        small = self.save_original("products/main/small.jpg", make_image_bytes("JPEG", (200, 100)))
        small_derivatives = build_derivatives(small, storage=self.storage)
        for key in ("card", "detail"):
            self.assertEqual(self.dimensions_and_format(small_derivatives[key])[0], (200, 100))

        name = self.save_original("products/main/ratio.jpg", make_image_bytes("JPEG", (1000, 667)))
        derivatives = build_derivatives(name, storage=self.storage)
        for key in ("card", "detail"):
            width, height = self.dimensions_and_format(derivatives[key])[0]
            self.assertLessEqual(abs(width / height - 1000 / 667), 1 / min(width, height))

    def test_exif_orientation_is_applied_and_exif_is_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        name = self.save_original(
            "products/main/oriented.jpg",
            make_image_bytes("JPEG", (800, 400), exif=exif),
        )

        derivatives = build_derivatives(name, storage=self.storage)
        detail_size, detail_format, _mode, detail_exif = self.dimensions_and_format(derivatives["detail"])
        self.assertEqual(detail_size, (400, 800))
        self.assertEqual(detail_format, "WEBP")
        self.assertEqual(len(detail_exif), 0)

    def test_png_alpha_is_preserved(self):
        rgba = Image.new("RGBA", (20, 10), (255, 0, 0, 0))
        rgba.putpixel((0, 0), (255, 0, 0, 128))
        output = BytesIO()
        rgba.save(output, format="PNG")
        rgba.close()
        name = self.save_original("products/main/alpha.png", output.getvalue())

        derivative = build_derivatives(name, storage=self.storage)["detail"]
        _size, format_name, mode, _exif = self.dimensions_and_format(derivative)
        self.assertEqual(format_name, "WEBP")
        self.assertEqual(mode, "RGBA")
        with self.storage.open(derivative, "rb") as file:
            with Image.open(file) as image:
                self.assertGreater(image.getchannel("A").getpixel((0, 0)), 0)
                self.assertEqual(image.getchannel("A").getpixel((10, 5)), 0)

    def test_names_are_deterministic_and_existing_derivatives_are_overwritten(self):
        name = self.save_original("products/main/repeated.jpg", make_image_bytes("JPEG", color=(10, 20, 30)))
        first_names = build_derivatives(name, storage=self.storage)
        first_content = {}
        for variant, derivative in first_names.items():
            with self.storage.open(derivative, "rb") as file:
                first_content[variant] = file.read()

        self.storage.delete(name)
        self.save_original(name, make_image_bytes("JPEG", color=(230, 220, 210)))
        second_names = build_derivatives(name, storage=self.storage)

        self.assertEqual(second_names, first_names)
        for variant, derivative in second_names.items():
            with self.storage.open(derivative, "rb") as file:
                self.assertNotEqual(file.read(), first_content[variant])
        files = self.storage.listdir("products/main")[1]
        self.assertCountEqual(files, ["repeated.jpg", "repeated.card.webp", "repeated.detail.webp"])

        delete_derivatives(name, storage=self.storage)
        self.assertFalse(self.storage.exists(first_names["card"]))
        self.assertFalse(self.storage.exists(first_names["detail"]))

    def test_missing_original_raises_image_error(self):
        with self.assertRaises(ImageError):
            build_derivatives("products/main/missing.jpg", storage=self.storage)

    def test_derivative_name_replaces_extension(self):
        self.assertEqual(
            derivative_name("products/main/2026/11/abc.jpg", "card"),
            "products/main/2026/11/abc.card.webp",
        )


class ImageModelTests(ImageTestCase):
    def setUp(self):
        super().setUp()
        self.category = make_category()

    def test_image_fields_accept_valid_uploads_and_reject_invalid_ones(self):
        product = Product(
            name="تصویر",
            slug="image-product",
            category=self.category,
            main_image=self.uploaded("main.jpg", make_image_bytes("JPEG")),
        )
        product.full_clean()
        product.save()

        gallery = ProductImage(
            product=product,
            image=self.uploaded("gallery.png", make_image_bytes("PNG")),
        )
        gallery.full_clean()

        invalid_product = Product(
            name="تصویر نامعتبر",
            slug="invalid-image-product",
            category=self.category,
            main_image=self.uploaded("photo.jpg", b"not an image", "image/jpeg"),
        )
        with self.assertRaises(ValidationError):
            invalid_product.full_clean()

        invalid_gallery = ProductImage(
            product=product,
            image=self.uploaded("photo.jpg", b"not an image", "image/jpeg"),
        )
        with self.assertRaises(ValidationError):
            invalid_gallery.full_clean()

    def test_gallery_ordering_and_product_delete_leaves_files_in_storage(self):
        product = Product.objects.create(
            name="گالری",
            slug="gallery-product",
            category=self.category,
        )
        second = ProductImage.objects.create(
            product=product,
            image=self.uploaded("second.png", make_image_bytes("PNG")),
            sort_order=2,
        )
        first = ProductImage.objects.create(
            product=product,
            image=self.uploaded("first.png", make_image_bytes("PNG")),
            sort_order=1,
        )
        file_paths = [Path(second.image.path), Path(first.image.path)]

        self.assertEqual(list(product.gallery_images.all()), [first, second])
        self.assertTrue(all(path.exists() for path in file_paths))

        product.delete()
        self.assertFalse(ProductImage.objects.filter(product_id=product.pk).exists())
        self.assertTrue(all(path.exists() for path in file_paths))
