from django.urls import path

from .views import BrokerVerificationView, UserActiveUpdateView, UserListView

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path(
        "users/<int:pk>/block/",
        UserActiveUpdateView.as_view(),
        name="admin-user-block",
    ),
    path(
        "broker/verify/",
        BrokerVerificationView.as_view(),
        name="broker-verification",
    ),
]
