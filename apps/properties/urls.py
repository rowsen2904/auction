from django.urls import path

from .views import (
    PropertyDetailView,
    PropertyImageListCreateView,
    PropertyListCreateView,
)

urlpatterns = [
    path("", PropertyListCreateView.as_view(), name="property-list-create"),
    path("<int:pk>/", PropertyDetailView.as_view(), name="property-detail"),
    path(
        "<int:pk>/images/",
        PropertyImageListCreateView.as_view(),
        name="property-images",
    ),
]
