from django.urls import path

from .views import (
    ApprovePropertyView,
    BrokerVerificationView,
    PendingPropertiesListView,
    RejectPropertyView,
    UserActiveUpdateView,
    UserListView,
)

urlpatterns = [
    # User
    path("users/", UserListView.as_view(), name="user-list"),
    path(
        "users/<int:pk>/block/",
        UserActiveUpdateView.as_view(),
        name="admin-user-block",
    ),
    # Broker
    path(
        "broker/verify/",
        BrokerVerificationView.as_view(),
        name="broker-verification",
    ),
    # Property
    path("properties/pending/", PendingPropertiesListView.as_view()),
    path("properties/<int:pk>/approve/", ApprovePropertyView.as_view()),
    path("properties/<int:pk>/reject/", RejectPropertyView.as_view()),
]
