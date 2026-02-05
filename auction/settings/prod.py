from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = [
    "backend.migtender.app",
    "www.backend.migtender.app",
]

CORS_ALLOWED_ORIGINS = ["https://migtender.app/" "https://admin.migtender.app/"]

HTTPS_ONLY = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
