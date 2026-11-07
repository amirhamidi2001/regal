from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlsplit

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

S3_ENDPOINT_URL = env_str("S3_ENDPOINT_URL", required=True)
S3_ACCESS_KEY_ID = env_str("S3_ACCESS_KEY_ID", required=True)
S3_SECRET_ACCESS_KEY = env_str("S3_SECRET_ACCESS_KEY", required=True)
S3_BUCKET_NAME = env_str("S3_BUCKET_NAME", required=True)
S3_PUBLIC_BASE_URL = env_str("S3_PUBLIC_BASE_URL", required=True)
S3_REGION_NAME = env_str("S3_REGION_NAME", default=None)
S3_ADDRESSING_STYLE = env_str("S3_ADDRESSING_STYLE", default="auto")

_public_url = urlsplit(S3_PUBLIC_BASE_URL)
_s3_storage_options = {
    "bucket_name": S3_BUCKET_NAME,
    "endpoint_url": S3_ENDPOINT_URL,
    "access_key": S3_ACCESS_KEY_ID,
    "secret_key": S3_SECRET_ACCESS_KEY,
    "addressing_style": S3_ADDRESSING_STYLE,
    "querystring_auth": False,
    "default_acl": None,
    "file_overwrite": False,
    "custom_domain": _public_url.netloc + _public_url.path,
    "url_protocol": f"{_public_url.scheme}:",
}
if S3_REGION_NAME:
    _s3_storage_options["region_name"] = S3_REGION_NAME

STORAGES["default"] = {
    "BACKEND": "storages.backends.s3.S3Storage",
    "OPTIONS": _s3_storage_options,
}
MEDIA_URL = S3_PUBLIC_BASE_URL + "/"
