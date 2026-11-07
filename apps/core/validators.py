import re

from django.core.exceptions import ValidationError

from apps.core.digits import normalize_digits

MOBILE_PATTERN = r"^09[0-9]{9}$"
_MOBILE_RE = re.compile(MOBILE_PATTERN)
_FORMATTING_RE = re.compile(r"[\s()\-]+")


def _invalid_mobile():
    return ValidationError("شماره موبایل معتبر نیست.", code="invalid_mobile")


def normalize_mobile(value):
    if not isinstance(value, str):
        raise _invalid_mobile()

    mobile = _FORMATTING_RE.sub("", normalize_digits(value))
    if mobile.startswith("+989") and len(mobile) == 13:
        mobile = "0" + mobile[3:]
    elif mobile.startswith("00989") and len(mobile) == 14:
        mobile = "0" + mobile[4:]
    elif mobile.startswith("989") and len(mobile) == 12:
        mobile = "0" + mobile[2:]
    elif mobile.startswith("9") and len(mobile) == 10:
        mobile = "0" + mobile

    if not _MOBILE_RE.fullmatch(mobile):
        raise _invalid_mobile()
    return mobile


def validate_mobile(value):
    if not isinstance(value, str) or not _MOBILE_RE.fullmatch(value):
        raise _invalid_mobile()


def normalize_postal_code(value):
    if not isinstance(value, str):
        raise ValidationError("کد پستی معتبر نیست.", code="invalid_postal_code")
    return re.sub(r"[\s-]+", "", normalize_digits(value))


def validate_postal_code(value):
    postal_code = normalize_postal_code(value)
    if not re.fullmatch(r"[1-9][0-9]{9}", postal_code):
        raise ValidationError("کد پستی معتبر نیست.", code="invalid_postal_code")
