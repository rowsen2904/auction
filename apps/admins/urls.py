from django.urls import path

from .views import (
    BrokerVerificationView,
    UserListView,
)

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path(
        "broker/verify/",
        BrokerVerificationView.as_view(),
        name="broker-verification",
    ),
]
