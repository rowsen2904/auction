from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import LoginSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses=LoginSerializer,
        description=_("Obtain JWT token pair."),
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    @extend_schema(
        request=TokenRefreshSerializer,
        responses=TokenRefreshSerializer,
        description=_(
            "Takes a refresh type JSON web token and returns an access type JSON web token if the refresh token is valid."),
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
