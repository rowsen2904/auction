from django.urls import path

from .views import (
    AllDocumentsView,
    CustomTokenRefreshView,
    GetVerificationCodeView,
    LoginView,
    MeView,
    RegisterBrokerView,
    RegisterDeveloperView,
    ResendCodeView,
    UserDocumentDeleteView,
    UserDocumentNameUpdateView,
    UserDocumentsUploadView,
    VerifyEmailView,
)

urlpatterns = [
    # JWT urls
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", CustomTokenRefreshView.as_view(), name="refresh"),
    # OTP email verification
    path("get-code/", GetVerificationCodeView.as_view(), name="get-code"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-code/", ResendCodeView.as_view(), name="resend-code"),
    # Register
    path(
        "register/developer/",
        RegisterDeveloperView.as_view(),
        name="register-developer",
    ),
    path(
        "register/broker/",
        RegisterBrokerView.as_view(),
        name="register-broker",
    ),
    # Current user
    path("me/", MeView.as_view(), name="me"),
    # User documents
    path(
        "documents/all/",
        AllDocumentsView.as_view(),
        name="documents-all",
    ),
    path(
        "documents/upload/",
        UserDocumentsUploadView.as_view(),
        name="documents-upload",
    ),
    path(
        "documents/update-name/",
        UserDocumentNameUpdateView.as_view(),
        name="documents-update-name",
    ),
    path(
        "documents/<int:document_id>/",
        UserDocumentDeleteView.as_view(),
        name="user-document-delete",
    ),
]
