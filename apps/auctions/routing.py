from django.urls import re_path

from .consumers import (
    AuctionLiveBidConsumer,
    AuctionsGlobalConsumer,
    ClosedAuctionBidsConsumer,
)

websocket_urlpatterns = [
    re_path(r"^ws/auctions/$", AuctionsGlobalConsumer.as_asgi()),
    re_path(r"^ws/auctions/(?P<auction_id>\d+)/$", AuctionLiveBidConsumer.as_asgi()),
    re_path(
        r"^ws/auctions/(?P<auction_id>\d+)/sealed-bids/$",
        ClosedAuctionBidsConsumer.as_asgi(),
    ),
]
