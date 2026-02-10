from __future__ import annotations

from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication


@sync_to_async
def _get_user_from_token(token: str):
    """
    Resolve DRF SimpleJWT token into Django user.
    """
    jwt_auth = JWTAuthentication()
    validated = jwt_auth.get_validated_token(token)
    return jwt_auth.get_user(validated)


class JwtAuthMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections using SimpleJWT access token passed via query string:
      ws://.../ws/auctions/<id>/?token=...
    """

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()

        query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        token = (query.get("token") or [None])[0]

        if token:
            try:
                scope["user"] = await _get_user_from_token(token)
            except Exception:
                scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
