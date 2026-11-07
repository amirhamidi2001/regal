from django import template

from apps.core.digits import to_persian_digits
from apps.core.jalali import format_jalali_date, format_jalali_datetime
from apps.core.money import format_toman

register = template.Library()


@register.filter
def persian_digits(value):
    return to_persian_digits(value)


@register.filter
def toman(value):
    if value is None:
        return ""
    return format_toman(value)


@register.filter
def jdate(value, style="numeric"):
    return format_jalali_date(value, style=style)


@register.filter
def jdatetime_fa(value):
    return format_jalali_datetime(value)
