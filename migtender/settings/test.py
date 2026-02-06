import os
from datetime import timedelta

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE

# -----------------------------
# Core
# -----------------------------
DEBUG = False

# Django test client uses "testserver" host by default
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]


# -----------------------------
# Database
# -----------------------------
# Fastest and most stable for unit/API tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# -----------------------------
# Cache
# -----------------------------
# No Redis in tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "migtender-test-cache",
    }
}


# -----------------------------
# Email
# -----------------------------
# Emails are stored in django.core.mail.outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@test.local"


# -----------------------------
# Password hashing (speed)
# -----------------------------
# Much faster than PBKDF2 for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# -----------------------------
# JWT (optional, but nice for predictable tests)
# -----------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


# -----------------------------
# Static / Media (avoid touching prod dirs)
# -----------------------------
MEDIA_ROOT = os.path.join(BASE_DIR, "test_media")
STATIC_ROOT = os.path.join(BASE_DIR, "test_staticfiles")


# -----------------------------
# Debug toolbar MUST NOT be installed in tests
# -----------------------------
# If dev/prod accidentally add it, remove it explicitly.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    mw for mw in MIDDLEWARE if mw != "debug_toolbar.middleware.DebugToolbarMiddleware"
]
