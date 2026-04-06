from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from properties.filters import PendingPropertyFilter
from properties.models import Property
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import UserDocument
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
    PropertyRejectSerializer,
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
            .prefetch_related(
                Prefetch(
                    "documents",
                    queryset=UserDocument.objects.only(
                        "id",
                        "user_id",
                        "doc_type",
                        "document",
                        "document_name",
                        "created_at",
                        "updated_at",
                    ).order_by("-created_at"),
                )
            )
            .only(
                "id",
                "email",
                "first_name",
                "last_name",
                "role",
                "inn_number",
                "is_active",
                "is_staff",
                "date_joined",
                # broker
                "broker__id",
                "broker__user_id",
                "broker__is_verified",
                "broker__verification_status",
                "broker__verified_at",
                "broker__rejected_at",
                # developer
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
        .only(
            "id",
            "role",
            "broker__id",
            "broker__verification_status",
            "broker__is_verified",
            "broker__verified_at",
            "broker__rejected_at",
        )
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
        reason = serializer.validated_data.get("reason")

        with transaction.atomic():
            user = get_object_or_404(
                self.get_queryset().select_for_update(),
                id=user_id,
            )

            broker = getattr(user, "broker", None)
            if broker is None:
                raise ValidationError(
                    {"id": _("Профиль брокера для этого пользователя не найден.")}
                )

            if action == "accept":
                broker.verify_broker()
                message = _("Брокер успешно верифицирован.")
            else:
                broker.set_as_rejected(reason=reason)
                message = _("Брокеру было отказано.")

        return Response(
            {
                "message": message,
                "broker_id": broker.id,
                "verification_status": broker.verification_status,
                "is_verified": broker.is_verified,
                "verified_at": broker.verified_at,
                "rejected_at": broker.rejected_at,
                "rejection_reason": broker.rejection_reason,
            },
            status=status.HTTP_200_OK,
        )


class UserActiveUpdateView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserActiveUpdateSerializer

    @user_active_update_schema
    def patch(self, request, pk: int, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)

        new_is_active: bool = serializer.validated_data["is_active"]

        if request.user.id == pk and new_is_active is False:
            raise ValidationError(
                {"detail": _("Вы не можете деактивировать свой аккаунт.")}
            )

        user = get_object_or_404(
            User.objects.only("id", "is_active"),
            pk=pk,
        )

        if user.is_active != new_is_active:
            user.is_active = new_is_active
            user.save(update_fields=["is_active"])

        return Response(
            {
                "id": user.id,
                "is_active": user.is_active,
                "message": _("Пользователь обновлён."),
            },
            status=status.HTTP_200_OK,
        )


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
        with transaction.atomic():
            prop = (
                Property.objects.select_for_update()
                .only("id", "moderation_status", "moderation_rejection_reason")
                .filter(pk=pk)
                .first()
            )
            if not prop:
                return Response(
                    {"detail": _("Не найдено.")},
                    status=status.HTTP_404_NOT_FOUND,
                )

            prop.approve_moderation()

        return Response(
            {
                "message": _("Объект успешно одобрен."),
                "property_id": prop.id,
                "moderation_status": prop.moderation_status,
                "moderation_rejection_reason": prop.moderation_rejection_reason,
            },
            status=status.HTTP_200_OK,
        )


class RejectPropertyView(APIView):
    permission_classes = [IsAdminUser]

    @reject_property_schema
    def patch(self, request, pk: int):
        serializer = PropertyRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data["reason"]

        with transaction.atomic():
            prop = (
                Property.objects.select_for_update()
                .only("id", "moderation_status", "moderation_rejection_reason")
                .filter(pk=pk)
                .first()
            )
            if not prop:
                return Response(
                    {"detail": _("Не найдено.")},
                    status=status.HTTP_404_NOT_FOUND,
                )

            prop.reject_moderation(reason=reason)

        return Response(
            {
                "message": _(
                    "Заявка на приобретение недвижимости была успешно отклонена."
                ),
                "property_id": prop.id,
                "moderation_status": prop.moderation_status,
                "moderation_rejection_reason": prop.moderation_rejection_reason,
            },
            status=status.HTTP_200_OK,
        )
