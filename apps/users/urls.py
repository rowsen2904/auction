from django.urls import path

from .views import (
    AllDocumentsView,
    ChangePasswordView,
    CustomTokenRefreshView,
    DeveloperDDUTemplateView,
    GetVerificationCodeView,
    LoginView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    RegisterBrokerView,
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
        "register/broker/",
        RegisterBrokerView.as_view(),
        name="register-broker",
    ),
    # Change password
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    # Password reset (forgot password)
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "password-reset/verify/",
        PasswordResetVerifyView.as_view(),
        name="password-reset-verify",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # Current user
    path("me/", MeView.as_view(), name="me"),
    # Developer DDU template (self-upload)
    path(
        "developer/ddu-template/",
        DeveloperDDUTemplateView.as_view(),
        name="developer-ddu-template",
    ),
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
