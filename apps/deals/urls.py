from django.urls import path

from . import views

urlpatterns = [
    path("", views.DealListView.as_view(), name="deal-list"),
    path("<int:pk>/", views.DealDetailView.as_view(), name="deal-detail"),
    path("<int:pk>/upload-ddu/", views.UploadDDUView.as_view(), name="deal-upload-ddu"),
    path(
        "<int:pk>/upload-payment-proof/",
        views.UploadPaymentProofView.as_view(),
        name="deal-upload-payment-proof",
    ),
    path("<int:pk>/comment/", views.BrokerCommentView.as_view(), name="deal-comment"),
    path(
        "<int:pk>/submit-for-review/",
        views.SubmitForReviewView.as_view(),
        name="deal-submit-for-review",
    ),
    path(
        "<int:pk>/admin-approve/",
        views.AdminApproveView.as_view(),
        name="deal-admin-approve",
    ),
    path(
        "<int:pk>/admin-reject/",
        views.AdminRejectView.as_view(),
        name="deal-admin-reject",
    ),
    path(
        "<int:pk>/developer-confirm/",
        views.DeveloperConfirmView.as_view(),
        name="deal-developer-confirm",
    ),
    path(
        "<int:pk>/developer-reject/",
        views.DeveloperRejectView.as_view(),
        name="deal-developer-reject",
    ),
    path("<int:pk>/logs/", views.DealLogsView.as_view(), name="deal-logs"),
]
