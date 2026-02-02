from django.urls import path

from .views import LoginView, CustomTokenRefreshView


urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', CustomTokenRefreshView.as_view(), name='refresh'),
]
