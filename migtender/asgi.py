from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "migtender.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from auctions.routing import (  # noqa: E402
    websocket_urlpatterns as auction_ws_urlpatterns,
)
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from notifications.routing import (  # noqa: E402
    websocket_urlpatterns as notification_ws_urlpatterns,
)

from .middleware import JwtAuthMiddleware  # noqa: E402

websocket_urlpatterns = [
    *auction_ws_urlpatterns,
    *notification_ws_urlpatterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
