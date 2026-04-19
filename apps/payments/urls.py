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
    # Transit settlements
    path(
        "settlements/",
        views.SettlementListView.as_view(),
        name="settlement-list",
    ),
    path(
        "settlements/summary/",
        views.SettlementSummaryView.as_view(),
        name="settlement-summary",
    ),
    path(
        "settlements/<int:pk>/mark-paid-to-broker/",
        views.MarkPaidToBrokerView.as_view(),
        name="settlement-mark-paid-to-broker",
    ),
    path(
        "settlements/<int:pk>/upload-developer-receipt/",
        views.UploadDeveloperReceiptView.as_view(),
        name="settlement-upload-developer-receipt",
    ),
    path(
        "settlements/<int:pk>/confirm-developer-receipt/",
        views.ConfirmDeveloperReceiptView.as_view(),
        name="settlement-confirm-developer-receipt",
    ),
]
