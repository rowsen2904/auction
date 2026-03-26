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
    # Users
    path("users/", UserListView.as_view(), name="user-list"),
    path(
        "users/<int:pk>/block/",
        UserActiveUpdateView.as_view(),
        name="admin-user-block",
    ),
    # Brokers
    path(
        "broker/verify/",
        BrokerVerificationView.as_view(),
        name="broker-verification",
    ),
    # Properties
    path(
        "properties/pending/",
        PendingPropertiesListView.as_view(),
        name="pending-properties-list",
    ),
    path(
        "properties/<int:pk>/approve/",
        ApprovePropertyView.as_view(),
        name="property-approve",
    ),
    path(
        "properties/<int:pk>/reject/",
        RejectPropertyView.as_view(),
        name="property-reject",
    ),
]
