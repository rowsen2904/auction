from django.urls import path

from .views import (
    CustomTokenRefreshView,
    GetVerificationCodeView,
    LoginView,
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
]
