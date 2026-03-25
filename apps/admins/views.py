from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from properties.filters import PendingPropertyFilter
from properties.models import Property
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers import TokenUserSerializer

from .filters import UserFilter
from .paginations import UserListPagination
from .schemas import (
    approve_property_schema,
    broker_verify_schema,
    pending_properties_list_schema,
    reject_property_schema,
    user_active_update_schema,
    user_list_schema,
)
from .serializers import (
    BrokerVerificationSerializer,
    PendingPropertySerializer,
    UserActiveUpdateSerializer,
)

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


# TODO: Must to do general list of properties with filtering
class PendingPropertiesListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PendingPropertySerializer
    filterset_class = PendingPropertyFilter

    def get_queryset(self):
        return (
            Property.objects.select_related("owner")
            .filter(moderation_status=Property.ModerationStatuses.PENDING)
            .exclude(status=Property.PropertyStatuses.DRAFT)
            .order_by("-created_at")
        )

    @pending_properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ApprovePropertyView(APIView):
    permission_classes = [IsAdminUser]

    @approve_property_schema
    def patch(self, request, pk: int):
        prop = Property.objects.only("id", "moderation_status").filter(pk=pk).first()
        if not prop:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if prop.moderation_status == Property.ModerationStatuses.PENDING:
            prop.moderation_status = Property.ModerationStatuses.APPROVED
            prop.save(update_fields=["moderation_status", "updated_at"])
            return Response(
                {"message": _("Property has been successfully approved.")},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"message": _(f"Property has already {prop.moderation_status}.")},
            status=status.HTTP_200_OK,
        )


class RejectPropertyView(APIView):
    permission_classes = [IsAdminUser]

    @reject_property_schema
    def patch(self, request, pk: int):
        prop: Property = (
            Property.objects.only("id", "moderation_status").filter(pk=pk).first()
        )
        if not prop:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if prop.moderation_status == Property.ModerationStatuses.PENDING:
            prop.moderation_status = Property.ModerationStatuses.REJECTED
            prop.save(update_fields=["moderation_status", "updated_at"])
            return Response(
                {"message": _("Property has been successfully rejected.")},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"message": _(f"Property has already {prop.moderation_status}.")},
            status=status.HTTP_200_OK,
        )
