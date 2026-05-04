from django.urls import path

from .views import (
    AdminDeveloperCreateView,
    AdminDeveloperUpdateView,
    AdminPropertiesListView,
    AdminUserUpdateView,
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
        "users/<int:pk>/",
        AdminUserUpdateView.as_view(),
        name="admin-user-update",
    ),
    path(
        "users/<int:pk>/block/",
        UserActiveUpdateView.as_view(),
        name="admin-user-block",
    ),
    path(
        "developers/",
        AdminDeveloperCreateView.as_view(),
        name="admin-developer-create",
    ),
    path(
        "developers/<int:pk>/",
        AdminDeveloperUpdateView.as_view(),
        name="admin-developer-update",
    ),
    # Brokers
    path(
        "broker/verify/",
        BrokerVerificationView.as_view(),
        name="broker-verification",
    ),
    # Properties
    path(
        "properties/",
        AdminPropertiesListView.as_view(),
        name="admin-properties-list",
    ),
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
