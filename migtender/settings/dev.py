from datetime import timedelta

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE

# daphne must be first — enables Channels/WebSocket in runserver
INSTALLED_APPS = ["daphne", *INSTALLED_APPS]

DEBUG = True

ALLOWED_HOSTS = ["*"]

CORS_ALLOW_ALL_ORIGINS = True


# Simple JWT Settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}


MIDDLEWARE += ["whitenoise.middleware.WhiteNoiseMiddleware"]


# Email
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Debug toolbar
try:
    __import__("debug_toolbar")
except ImportError:
    pass
else:
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
    INTERNAL_IPS = ["127.0.0.1"]
    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: True}
