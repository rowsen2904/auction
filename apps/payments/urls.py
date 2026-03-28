from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="payment-list"),
    path("summary/", views.PaymentSummaryView.as_view(), name="payment-summary"),
    path(
        "<int:pk>/upload-receipt/",
        views.UploadReceiptView.as_view(),
        name="payment-upload-receipt",
    ),
]
