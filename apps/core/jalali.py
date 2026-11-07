from datetime import date, datetime

import jdatetime
from django.utils import timezone

from apps.core.digits import to_persian_digits

PERSIAN_MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)


def _tehran_datetime(value):
    if timezone.is_naive(value):
        raise ValueError("A timezone-aware datetime is required.")
    return timezone.localtime(value)


def to_jalali(value):
    if isinstance(value, datetime):
        gregorian_date = _tehran_datetime(value).date()
    elif isinstance(value, date):
        gregorian_date = value
    else:
        raise TypeError("Expected a date or datetime.")
    return jdatetime.date.fromgregorian(date=gregorian_date)


def format_jalali_date(value, style="numeric"):
    jalali_date = to_jalali(value)
    if style == "numeric":
        formatted = f"{jalali_date.year:04d}/{jalali_date.month:02d}/{jalali_date.day:02d}"
    elif style == "long":
        formatted = (
            f"{jalali_date.day} {PERSIAN_MONTHS[jalali_date.month - 1]} "
            f"{jalali_date.year}"
        )
    else:
        raise ValueError("style must be 'numeric' or 'long'.")
    return to_persian_digits(formatted)


def format_jalali_datetime(value):
    local_datetime = _tehran_datetime(value)
    time_text = f"{local_datetime.hour:02d}:{local_datetime.minute:02d}"
    return f"{format_jalali_date(local_datetime)} {to_persian_digits(time_text)}"
