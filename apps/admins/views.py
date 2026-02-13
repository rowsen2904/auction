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
from .schemas import broker_verify_schema, user_active_update_schema, user_list_schema
from .serializers import BrokerVerificationSerializer, UserActiveUpdateSerializer

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
        print(request.user)
        return super().get(request, *args, **kwargs)


class BlockUserView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]


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


class UserActiveUpdateView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserActiveUpdateSerializer

    @user_active_update_schema
    def patch(self, request, pk: int, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        new_is_active: bool = serializer.validated_data["is_active"]

        # Prevent admin from disabling themselves (optional, but usually needed)
        if request.user.id == pk and new_is_active is False:
            raise ValidationError({"detail": "You cannot deactivate your own account."})

        user = get_object_or_404(User.objects.only("id", "is_active"), pk=pk)

        if user.is_active != new_is_active:
            user.is_active = new_is_active
            user.save(update_fields=["is_active"])

        return Response(
            {
                "id": user.id,
                "is_active": user.is_active,
                "message": "User updated.",
            },
            status=status.HTTP_200_OK,
        )
