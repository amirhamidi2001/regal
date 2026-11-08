import posixpath
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
DERIVATIVES = {"card": 480, "detail": 960}
WEBP_QUALITY = 82
# ASSUMPTION: These upload limits, supported formats, derivative sizes, and quality are the catalog image policy.


class ImageError(Exception):
    """Raised when a stored image cannot be processed deterministically."""


def _validation_error(message, code):
    return ValidationError(message, code=code)


def validate_uploaded_image(file):
    """Validate the file contents and reset the file position to its beginning."""
    try:
        file.seek(0)
        size = 0
        while True:
            chunk = file.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                raise _validation_error("حجم تصویر بیش از حد مجاز است.", "image_too_large")

        file.seek(0)
        try:
            with Image.open(file) as image:
                image_format = image.format
                width, height = image.size
                if image_format not in ALLOWED_FORMATS:
                    raise _validation_error("قالب تصویر پشتیبانی نمی‌شود.", "image_unsupported_format")
                if width * height > MAX_IMAGE_PIXELS:
                    raise _validation_error("ابعاد تصویر بیش از حد مجاز است.", "image_too_many_pixels")
                image.verify()

            file.seek(0)
            with Image.open(file) as image:
                image.load()
        except ValidationError:
            raise
        except Image.DecompressionBombError as error:
            raise _validation_error("ابعاد تصویر بیش از حد مجاز است.", "image_too_many_pixels") from error
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise _validation_error("فایل تصویر معتبر نیست.", "invalid_image") from error
    except ValidationError:
        raise
    except Exception as error:
        raise _validation_error("فایل تصویر معتبر نیست.", "invalid_image") from error
    finally:
        try:
            file.seek(0)
        except Exception:
            pass


def derivative_name(name, variant):
    """Return the deterministic WebP derivative key for a storage name."""
    root, _extension = posixpath.splitext(name)
    return f"{root}.{variant}.webp"


def build_derivatives(name, *, storage=None):
    """Build card and detail WebP copies without modifying the stored original."""
    storage = storage or default_storage
    try:
        with storage.open(name, "rb") as original_file:
            with Image.open(original_file) as original:
                oriented = ImageOps.exif_transpose(original)
                oriented.load()
                has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info

                saved_names = {}
                for variant, longest_side in DERIVATIVES.items():
                    derivative = oriented.copy()
                    derivative.thumbnail(
                        (longest_side, longest_side),
                        resample=Image.Resampling.LANCZOS,
                    )
                    derivative = derivative.convert("RGBA" if has_alpha else "RGB")
                    output = BytesIO()
                    derivative.save(
                        output,
                        format="WEBP",
                        quality=WEBP_QUALITY,
                        exif=b"",
                    )

                    target_name = derivative_name(name, variant)
                    if storage.exists(target_name):
                        storage.delete(target_name)
                    stored_name = storage.save(target_name, ContentFile(output.getvalue()))
                    if stored_name != target_name:
                        if storage.exists(stored_name):
                            storage.delete(stored_name)
                        raise ImageError(
                            f"Storage changed the deterministic derivative name: {target_name}."
                        )
                    saved_names[variant] = stored_name
                    derivative.close()
                oriented.close()
                return saved_names
    except FileNotFoundError as error:
        raise ImageError(f"Original image does not exist: {name}.") from error
    except ImageError:
        raise
    except Exception as error:
        raise ImageError(f"Could not build derivatives for {name}.") from error


def delete_derivatives(name, *, storage=None):
    """Delete existing card and detail derivative objects for a storage name."""
    storage = storage or default_storage
    for variant in DERIVATIVES:
        derivative = derivative_name(name, variant)
        if storage.exists(derivative):
            storage.delete(derivative)
