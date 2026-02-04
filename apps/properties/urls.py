from django.urls import path

from .views import (
    MyPropertiesView,
    PropertyDetailView,
    PropertyImageListCreateView,
    PropertyListCreateView,
)

urlpatterns = [
    path("", PropertyListCreateView.as_view(), name="property-list-create"),
    path("<int:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path("my/", MyPropertiesView.as_view(), name="my-properties"),
    path(
        "<int:pk>/images/",
        PropertyImageListCreateView.as_view(),
        name="property-images",
    ),
]
