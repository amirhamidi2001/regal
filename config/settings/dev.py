from config.env import env_bool, env_list, env_str
from config.settings.base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env_str(
    "DJANGO_SECRET_KEY", default="dev-only-insecure-key-not-for-production"
)
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS", default=("localhost", "127.0.0.1", "[::1]")
)
