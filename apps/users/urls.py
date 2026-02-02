from django.urls import path

from .views import (
    LoginView,
    CustomTokenRefreshView,
    VerifyEmailView,
    ResendCodeView,
    GetVerificationCodeView,
)


urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='refresh'),
    path('get-code/', GetVerificationCodeView.as_view(), name='get-code'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('resend-code/', ResendCodeView.as_view(), name='resend-code'),
]
