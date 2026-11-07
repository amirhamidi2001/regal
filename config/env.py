import os

from django.core.exceptions import ImproperlyConfigured


def _required_value(name, required):
    value = os.environ.get(name)
    if required and (value is None or value == ""):
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_str(name, default=None, required=False):
    value = _required_value(name, required)
    return default if value is None else value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ImproperlyConfigured(
        f"Environment variable {name} must be true, false, 1, 0, yes, or no."
    )


def env_int(name, default=None, required=False):
    value = _required_value(name, required)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {name} must be an integer."
        ) from exc


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]
