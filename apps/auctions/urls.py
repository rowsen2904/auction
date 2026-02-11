from django.urls import path

from .views import (
    AuctionCancelView,
    AuctionDetailView,
    AuctionJoinView,
    AuctionListCreateView,
    AuctionParticipantsView,
    ClosedBidCreateView,
    ClosedBidsListForOwnerAdminView,
    ClosedSelectWinnerView,
    ClosedShortlistView,
    MyAuctionListView,
    MyClosedBidUpdateView,
)

app_name = "auctions"

urlpatterns = [
    # Auctions
    path("", AuctionListCreateView.as_view(), name="auction-list-create"),
    path("my/", MyAuctionListView.as_view(), name="auction-my-list"),
    path("<int:pk>/", AuctionDetailView.as_view(), name="auction-detail"),
    path("<int:pk>/cancel/", AuctionCancelView.as_view(), name="auction-cancel"),
    # Participants (Redis)
    path("<int:pk>/join/", AuctionJoinView.as_view(), name="auction-join"),
    path(
        "<int:pk>/participants/",
        AuctionParticipantsView.as_view(),
        name="auction-participants",
    ),
    # CLOSED bids (HTTP)
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
    # CLOSED flow (after finish)
    path("<int:pk>/shortlist/", ClosedShortlistView.as_view(), name="closed-shortlist"),
    path(
        "<int:pk>/select-winner/",
        ClosedSelectWinnerView.as_view(),
        name="closed-select-winner",
    ),
]
