from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import DealFilter
from .models import Deal, DealLog
from .paginations import DealPagination
from .schemas import (
    deal_admin_approve_schema,
    deal_admin_reject_schema,
    deal_broker_comment_schema,
    deal_detail_schema,
    deal_developer_confirm_schema,
    deal_developer_reject_schema,
    deal_list_schema,
    deal_logs_schema,
    deal_upload_ddu_schema,
    deal_upload_payment_proof_schema,
)
from .serializers import (
    BrokerCommentSerializer,
    DDUUploadSerializer,
    DealDetailSerializer,
    DealListSerializer,
    DealLogSerializer,
    PaymentProofUploadSerializer,
    RejectReasonSerializer,
)
from .services import check_and_transition_to_review, create_payments_for_deal


def _get_deal_for_broker(pk: int, user) -> Deal:
    deal = get_object_or_404(Deal.objects.select_for_update(), pk=pk)
    if deal.broker_id != user.id:
        raise PermissionDenied(_("Вы не являетесь брокером этой сделки."))
    return deal


def _get_deal_for_developer(pk: int, user) -> Deal:
    deal = get_object_or_404(
        Deal.objects.select_for_update().select_related("real_property"),
        pk=pk,
    )
    if deal.developer_id != user.id:
        raise PermissionDenied(_("Вы не являетесь девелопером этой сделки."))
    return deal


class DealListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DealListSerializer
    pagination_class = DealPagination
    filterset_class = DealFilter

    def get_queryset(self):
        user = self.request.user
        qs = Deal.objects.select_related(
            "broker",
            "developer",
            "developer__developer",
            "real_property",
            "auction",
        )
        if user.is_staff or getattr(user, "is_admin", False):
            return qs
        if getattr(user, "is_developer", False):
            return qs.filter(developer=user)
        # Default: broker
        return qs.filter(broker=user)

    @deal_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DealDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DealDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Deal.objects.select_related(
            "broker",
            "developer",
            "developer__developer",
            "real_property",
            "auction",
        ).prefetch_related("logs", "logs__actor")
        if user.is_staff or getattr(user, "is_admin", False):
            return qs
        if getattr(user, "is_developer", False):
            return qs.filter(developer=user)
        return qs.filter(broker=user)

    @deal_detail_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UploadDDUView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @deal_upload_ddu_schema
    def post(self, request, pk: int):
        ser = DDUUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            deal = _get_deal_for_broker(pk, request.user)

            if deal.status != Deal.Status.PENDING_DOCUMENTS:
                raise ValidationError(
                    {
                        "detail": _(
                            "Загрузка документов доступна только в статусе «Ожидание документов»."
                        )
                    }
                )

            deal.ddu_document = ser.validated_data["ddu_document"]
            deal.save(update_fields=["ddu_document", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.DDU_UPLOADED,
                actor=request.user,
                detail="ДДУ загружен.",
            )

            check_and_transition_to_review(deal, actor=request.user)

        return Response({"detail": "ДДУ загружен."}, status=status.HTTP_200_OK)


class UploadPaymentProofView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @deal_upload_payment_proof_schema
    def post(self, request, pk: int):
        ser = PaymentProofUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            deal = _get_deal_for_broker(pk, request.user)

            if deal.status != Deal.Status.PENDING_DOCUMENTS:
                raise ValidationError(
                    {
                        "detail": _(
                            "Загрузка документов доступна только в статусе «Ожидание документов»."
                        )
                    }
                )

            deal.payment_proof_document = ser.validated_data["payment_proof_document"]
            deal.save(update_fields=["payment_proof_document", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.PAYMENT_PROOF_UPLOADED,
                actor=request.user,
                detail="Подтверждение оплаты загружено.",
            )

            check_and_transition_to_review(deal, actor=request.user)

        return Response(
            {"detail": "Подтверждение оплаты загружено."},
            status=status.HTTP_200_OK,
        )


class BrokerCommentView(APIView):
    permission_classes = [IsAuthenticated]

    @deal_broker_comment_schema
    def patch(self, request, pk: int):
        ser = BrokerCommentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            deal = _get_deal_for_broker(pk, request.user)

            if deal.status != Deal.Status.PENDING_DOCUMENTS:
                raise ValidationError(
                    {
                        "detail": _(
                            "Комментарий можно добавить только в статусе «Ожидание документов»."
                        )
                    }
                )

            deal.broker_comment = ser.validated_data["comment"]
            deal.save(update_fields=["broker_comment", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.COMMENT_ADDED,
                actor=request.user,
                detail="Комментарий добавлен.",
            )

            check_and_transition_to_review(deal, actor=request.user)

        return Response({"detail": "Комментарий сохранён."}, status=status.HTTP_200_OK)


class AdminApproveView(APIView):
    permission_classes = [IsAdminUser]

    @deal_admin_approve_schema
    def post(self, request, pk: int):
        with transaction.atomic():
            deal = get_object_or_404(Deal.objects.select_for_update(), pk=pk)

            if deal.status != Deal.Status.ADMIN_REVIEW:
                raise ValidationError(
                    {"detail": _("Одобрение возможно только в статусе «На проверке».")}
                )

            deal.status = Deal.Status.DEVELOPER_CONFIRM
            deal.save(update_fields=["status", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.ADMIN_APPROVED,
                actor=request.user,
                detail="Документы одобрены администратором.",
            )

        # Notify developer + broker
        from .tasks import send_deal_status_email

        deal_obj = Deal.objects.select_related(
            "developer",
            "broker",
            "real_property",
        ).get(id=deal.id)
        send_deal_status_email.delay(
            deal.id,
            deal_obj.developer.email,
            f"MIG Tender — Сделка #{deal.id} одобрена администратором",
            (
                f"Документы по сделке #{deal.id} "
                f"(объект «{deal_obj.real_property.address}») "
                f"одобрены администратором.\nПожалуйста, подтвердите сделку."
            ),
        )
        send_deal_status_email.delay(
            deal.id,
            deal_obj.broker.email,
            f"MIG Tender — Сделка #{deal.id} одобрена администратором",
            (
                f"Ваши документы по сделке #{deal.id} одобрены. "
                f"Ожидаем подтверждения от девелопера."
            ),
        )

        return Response(
            {"detail": "Документы одобрены. Сделка передана девелоперу."},
            status=status.HTTP_200_OK,
        )


class AdminRejectView(APIView):
    permission_classes = [IsAdminUser]

    @deal_admin_reject_schema
    def post(self, request, pk: int):
        ser = RejectReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data["reason"]

        with transaction.atomic():
            deal = get_object_or_404(Deal.objects.select_for_update(), pk=pk)

            if deal.status != Deal.Status.ADMIN_REVIEW:
                raise ValidationError(
                    {"detail": _("Отклонение возможно только в статусе «На проверке».")}
                )

            deal.status = Deal.Status.PENDING_DOCUMENTS
            deal.admin_rejection_reason = reason
            deal.save(update_fields=["status", "admin_rejection_reason", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.ADMIN_REJECTED,
                actor=request.user,
                detail=f"Отклонено администратором. Причина: {reason}",
            )

        from .tasks import send_deal_status_email

        deal_obj = Deal.objects.select_related("broker", "real_property").get(
            id=deal.id
        )
        send_deal_status_email.delay(
            deal.id,
            deal_obj.broker.email,
            f"MIG Tender — Сделка #{deal.id} отклонена администратором",
            (
                f"Документы по сделке #{deal.id} "
                f"(объект «{deal_obj.real_property.address}») "
                f"отклонены.\nПричина: {reason}\n"
                f"Пожалуйста, перезагрузите документы."
            ),
        )

        return Response(
            {"detail": "Сделка отклонена. Брокер уведомлён."},
            status=status.HTTP_200_OK,
        )


class DeveloperConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @deal_developer_confirm_schema
    def post(self, request, pk: int):
        with transaction.atomic():
            deal = _get_deal_for_developer(pk, request.user)

            if deal.status != Deal.Status.DEVELOPER_CONFIRM:
                raise ValidationError(
                    {
                        "detail": _(
                            "Подтверждение возможно только в статусе "
                            "«Ожидает подтверждения девелопера»."
                        )
                    }
                )

            deal.status = Deal.Status.CONFIRMED
            deal.obligation_status = Deal.ObligationStatus.FULFILLED
            deal.save(update_fields=["status", "obligation_status", "updated_at"])

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.DEVELOPER_CONFIRMED,
                actor=request.user,
                detail="Сделка подтверждена девелопером.",
            )

            create_payments_for_deal(deal)

        from .tasks import send_deal_status_email

        deal_obj = Deal.objects.select_related("broker", "real_property").get(
            id=deal.id
        )
        send_deal_status_email.delay(
            deal.id,
            deal_obj.broker.email,
            f"MIG Tender — Сделка #{deal.id} подтверждена",
            (
                f"Сделка #{deal.id} по объекту "
                f"«{deal_obj.real_property.address}» "
                f"подтверждена девелопером. Выплата комиссии будет оформлена."
            ),
        )

        return Response(
            {"detail": "Сделка подтверждена. Выплаты созданы."},
            status=status.HTTP_200_OK,
        )


class DeveloperRejectView(APIView):
    permission_classes = [IsAuthenticated]

    @deal_developer_reject_schema
    def post(self, request, pk: int):
        ser = RejectReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data["reason"]

        with transaction.atomic():
            deal = _get_deal_for_developer(pk, request.user)

            if deal.status != Deal.Status.DEVELOPER_CONFIRM:
                raise ValidationError(
                    {
                        "detail": _(
                            "Отклонение возможно только в статусе "
                            "«Ожидает подтверждения девелопера»."
                        )
                    }
                )

            deal.status = Deal.Status.PENDING_DOCUMENTS
            deal.developer_rejection_reason = reason
            deal.save(
                update_fields=["status", "developer_rejection_reason", "updated_at"]
            )

            DealLog.objects.create(
                deal=deal,
                action=DealLog.Action.DEVELOPER_REJECTED,
                actor=request.user,
                detail=f"Отклонено девелопером. Причина: {reason}",
            )

        from .tasks import send_deal_status_email

        deal_obj = Deal.objects.select_related("broker", "real_property").get(
            id=deal.id
        )
        send_deal_status_email.delay(
            deal.id,
            deal_obj.broker.email,
            f"MIG Tender — Сделка #{deal.id} отклонена девелопером",
            (
                f"Сделка #{deal.id} "
                f"(объект «{deal_obj.real_property.address}») отклонена.\n"
                f"Причина: {reason}\n"
                f"Пожалуйста, перезагрузите документы."
            ),
        )

        return Response(
            {"detail": "Сделка отклонена. Брокер уведомлён."},
            status=status.HTTP_200_OK,
        )


class DealLogsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DealLogSerializer

    def get_queryset(self):
        user = self.request.user
        deal = get_object_or_404(Deal, pk=self.kwargs["pk"])

        # Role-based access check
        if not (
            user.is_staff
            or getattr(user, "is_admin", False)
            or deal.broker_id == user.id
            or deal.developer_id == user.id
        ):
            raise PermissionDenied(_("Нет доступа к логам этой сделки."))

        return DealLog.objects.filter(deal=deal).select_related("actor")

    @deal_logs_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
