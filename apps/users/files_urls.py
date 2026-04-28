"""
Auth-gated, signed-URL download endpoints. All file links emitted in API
responses point here. Files are encrypted at rest; this is the only path
that can decrypt them. Direct /media/ access returns ciphertext.
"""

from django.urls import path

from .views import (
    DealDocumentDownloadView,
    DeveloperTemplateDownloadView,
    SettlementDocumentDownloadView,
    UserDocumentDownloadView,
)

urlpatterns = [
    path(
        "user-document/<int:document_id>/",
        UserDocumentDownloadView.as_view(),
        name="file-user-document",
    ),
    path(
        "deal/<int:deal_id>/<str:kind>/",
        DealDocumentDownloadView.as_view(),
        name="file-deal-document",
    ),
    path(
        "developer/<int:developer_user_id>/ddu-template/",
        DeveloperTemplateDownloadView.as_view(),
        name="file-developer-template",
    ),
    path(
        "settlement/<int:settlement_id>/<str:kind>/",
        SettlementDocumentDownloadView.as_view(),
        name="file-settlement-document",
    ),
]
