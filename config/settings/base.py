import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import env_int, env_str

BASE_DIR = Path(__file__).resolve().parents[2]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
    "apps.payments",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", required=True),
        "USER": env_str("POSTGRES_USER", required=True),
        "PASSWORD": env_str("POSTGRES_PASSWORD", required=True),
        "HOST": env_str("POSTGRES_HOST", required=True),
        "PORT": env_int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        # Services open explicit transaction.atomic() blocks.
        "ATOMIC_REQUESTS": False,
    }
}

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# ASSUMPTION: The guest cart in Phase 5C relies on a 30-day session.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

ADMIN_URL = env_str("DJANGO_ADMIN_URL", default="internal-admin/")
if ADMIN_URL.startswith("/") or not ADMIN_URL.endswith("/"):
    raise ImproperlyConfigured(
        "DJANGO_ADMIN_URL must not start with '/' and must end with '/'."
    )

STATIC_URL = "static/"
STATIC_ROOT = env_str("STATIC_ROOT", default=BASE_DIR / "staticfiles")
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = env_str("MEDIA_URL", default="/media/")
MEDIA_ROOT = env_str("MEDIA_ROOT", default=BASE_DIR / "media")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # ASSUMPTION: Static asset URLs remain unhashed for Nginx's shared static volume.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

_log_level = env_str("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": _log_level},
    "loggers": {
        "django": {"handlers": ["console"], "level": _log_level, "propagate": False},
    },
}
