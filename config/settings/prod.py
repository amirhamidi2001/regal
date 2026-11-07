from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_list, env_str
from config.settings.base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env_str("DJANGO_SECRET_KEY", required=True)
if len(SECRET_KEY) < 50 or SECRET_KEY.lower().startswith(("change-me", "dev-only")):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be at least 50 characters and cannot be a placeholder."
    )
env_str("DJANGO_ALLOWED_HOSTS", required=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Environment variable DJANGO_ALLOWED_HOSTS is required.")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", default=())
SECURE_SSL = env_bool("DJANGO_SECURE_SSL", default=True)
if SECURE_SSL:
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
else:
    SECURE_SSL_REDIRECT = False

X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
# HSTS includeSubDomains and preload are deliberate owner decisions deferred to Phase 10.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
