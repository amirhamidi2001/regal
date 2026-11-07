_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
_PERSIAN_DIGIT_TRANSLATION = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def normalize_digits(value: str) -> str:
    """Convert Persian and Arabic-Indic digits in a string to ASCII digits."""
    return value.translate(_DIGIT_TRANSLATION)


def to_persian_digits(value) -> str:
    """Convert ASCII digits in the string form of a value to Persian digits."""
    return str(value).translate(_PERSIAN_DIGIT_TRANSLATION)
