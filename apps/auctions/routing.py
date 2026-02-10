from __future__ import annotations

from django.urls import re_path

from .consumers import AuctionLiveBidConsumer

websocket_urlpatterns = [
    re_path(r"^ws/auctions/(?P<auction_id>\d+)/$", AuctionLiveBidConsumer.as_asgi()),
]
