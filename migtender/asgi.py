from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "migtender.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from auctions.middleware import JwtAuthMiddleware  # noqa: E402
from auctions.routing import websocket_urlpatterns  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
