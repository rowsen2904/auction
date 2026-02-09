from django.urls import path

from .views import (
    AuctionCancelView,
    AuctionDetailView,
    AuctionListCreateView,
    MyAuctionListView,
)

urlpatterns = [
    path("", AuctionListCreateView.as_view(), name="auction-list-create"),
    path("my/", MyAuctionListView.as_view(), name="auction-my-list"),
    path("<int:pk>/", AuctionDetailView.as_view(), name="auction-detail"),
    path("<int:pk>/cancel/", AuctionCancelView.as_view(), name="auction-cancel"),
]
