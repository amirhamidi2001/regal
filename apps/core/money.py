from apps.core.digits import to_persian_digits


def _require_int(value):
    if type(value) is not int:
        raise TypeError("Toman display values must be integers.")


def format_number(n):
    _require_int(n)
    sign = "-" if n < 0 else ""
    grouped = f"{abs(n):,}".replace(",", "٬")
    return sign + to_persian_digits(grouped)


def format_toman(amount):
    _require_int(amount)
    return f"{format_number(amount)} تومان"
