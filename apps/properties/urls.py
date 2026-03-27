from django.urls import path

from .views import (
    MyAvailablePropertiesView,
    MyPropertiesView,
    PropertyDeleteView,
    PropertyDetailView,
    PropertyImageListCreateView,
    PropertyImageUpdateView,
    PropertyListCreateView,
)

urlpatterns = [
    path("", PropertyListCreateView.as_view(), name="property-list-create"),
    path("<int:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path("<int:pk>/delete/", PropertyDeleteView.as_view(), name="property-delete"),
    path("my/", MyPropertiesView.as_view(), name="my-properties"),
    path(
        "my/available/",
        MyAvailablePropertiesView.as_view(),
        name="my-available-properties",
    ),
    path(
        "<int:pk>/images/",
        PropertyImageListCreateView.as_view(),
        name="property-images",
    ),
    path(
        "<int:pk>/images/<int:image_id>/",
        PropertyImageUpdateView.as_view(),
        name="property-image-update",
    ),
]
