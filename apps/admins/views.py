from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.users.serializers import TokenUserSerializer

from .filters import UserFilter
from .paginations import UserListPagination
from .schemas import broker_verify_schema, user_list_schema
from .serializers import BrokerVerificationSerializer

User = get_user_model()


class UserListView(generics.ListAPIView):
    pagination_class = UserListPagination
    permission_classes = [IsAdminUser]
    serializer_class = TokenUserSerializer

    filterset_class = UserFilter
    ordering_fields = ["date_joined", "email", "role", "is_active"]
    ordering = ["-date_joined"]

    def get_queryset(self):
        return (
            User.objects.all()
            .select_related("broker", "developer")
            .only(
                "id",
                "email",
                "first_name",
                "last_name",
                "role",
                "is_active",
                "is_staff",
                "date_joined",
                # broker safe fields
                "broker__id",
                "broker__user_id",
                "broker__is_verified",
                "broker__verification_status",
                "broker__verified_at",
                "broker__rejected_at",
                "broker__inn_number",
                # developer safe fields
                "developer__id",
                "developer__user_id",
                "developer__company_name",
            )
        )

    @user_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BrokerVerificationView(generics.GenericAPIView):
    queryset = (
        User.objects.select_related("broker")
        .only("id", "role", "broker__id", "broker__verification_status")
        .filter(role=User.Roles.BROKER)
    )
    serializer_class = BrokerVerificationSerializer
    permission_classes = [IsAdminUser]

    @broker_verify_schema
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["id"]
        action = serializer.validated_data["action"]

        user = get_object_or_404(self.get_queryset(), id=user_id)

        broker = getattr(user, "broker", None)
        if broker is None:
            # Broker profile missing even though role is broker
            raise ValidationError({"id": _("Broker profile not found for this user.")})

        if action == "accept":
            broker.verify_broker()
            msg = _("Broker has been successfully verified.")
        else:
            broker.set_as_rejected()
            msg = _("Broker has been rejected.")

        return Response({"message": msg}, status=status.HTTP_200_OK)
