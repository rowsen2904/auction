from django.urls import path

from .views.auctions import (
    AuctionDetailView,
    AuctionListCreateView,
    MyAuctionListView,
)
from .views.cancel import AuctionCancelView
from .views.closed_bids import (
    ClosedBidCreateView,
    ClosedBidsListForOwnerAdminView,
    MyClosedBidUpdateView,
)
from .views.closed_flow import ClosedSelectWinnerView, ClosedShortlistView
from .views.participants import AuctionJoinView, AuctionParticipantsView

app_name = "auctions"

urlpatterns = [
    path("", AuctionListCreateView.as_view(), name="auction-list-create"),
    path("my/", MyAuctionListView.as_view(), name="auction-my-list"),
    path("<int:pk>/", AuctionDetailView.as_view(), name="auction-detail"),
    path("<int:pk>/cancel/", AuctionCancelView.as_view(), name="auction-cancel"),
    path("<int:pk>/join/", AuctionJoinView.as_view(), name="auction-join"),
    path(
        "<int:pk>/participants/",
        AuctionParticipantsView.as_view(),
        name="auction-participants",
    ),
    path("<int:pk>/bid/", ClosedBidCreateView.as_view(), name="closed-bid-create"),
    path(
        "<int:pk>/bid/update/",
        MyClosedBidUpdateView.as_view(),
        name="closed-bid-update",
    ),
    path(
        "<int:pk>/sealed-bids/",
        ClosedBidsListForOwnerAdminView.as_view(),
        name="closed-bids-list",
    ),
    path("<int:pk>/shortlist/", ClosedShortlistView.as_view(), name="closed-shortlist"),
    path(
        "<int:pk>/select-winner/",
        ClosedSelectWinnerView.as_view(),
        name="closed-select-winner",
    ),
]
