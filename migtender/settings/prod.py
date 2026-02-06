from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = [
    "backend.migtender.app",
    "www.backend.migtender.app",
    "72.62.249.144",
    "127.0.0.1",
    "localhost",
]

CORS_ALLOWED_ORIGINS = ["https://migntender.app/", "https://admin.migntender.app/"]

CSRF_TRUSTED_ORIGINS = [
    "https://backend.migntender.app",
    "https://www.backend.migntender.app",
]

HTTPS_ONLY = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
