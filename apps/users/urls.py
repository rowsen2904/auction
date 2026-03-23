from django.urls import path

from .views import (
    BrokerDocumentNamesUpdateView,
    BrokerDocumentsUploadView,
    CustomTokenRefreshView,
    GetVerificationCodeView,
    LoginView,
    MeView,
    RegisterBrokerView,
    RegisterDeveloperView,
    ResendCodeView,
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
    path("register/broker/", RegisterBrokerView.as_view(), name="register-broker"),
    # Get user profile (me)
    path("me/", MeView.as_view(), name="me"),
    # Broker documents
    path(
        "broker/upload-documents/",
        BrokerDocumentsUploadView.as_view(),
        name="broker-upload-documents",
    ),
    path(
        "broker/update-document-names/",
        BrokerDocumentNamesUpdateView.as_view(),
        name="broker-update-document-names",
    ),
]
