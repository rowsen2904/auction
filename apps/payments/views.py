from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Case, Sum, Value, When
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from notifications.services import notify_payment_paid
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import models as _models
from django.db.models import Sum
from django.utils import timezone

from .models import DealSettlement, Payment
from .schemas import (
    payment_list_schema,
    payment_summary_schema,
    payment_upload_receipt_schema,
)
from .serializers import (
    ConfirmDeveloperReceiptSerializer,
    DealSettlementSerializer,
    DeveloperPaymentSummarySerializer,
    MarkPaidToBrokerSerializer,
    PaymentListSerializer,
    PaymentSummarySerializer,
    ReceiptUploadSerializer,
    SettlementSummarySerializer,
    UploadDeveloperReceiptSerializer,
)


class PaymentListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Payment.objects.select_related(
            "deal", "deal__real_property", "deal__broker", "deal__developer"
        )
        if user.is_staff or getattr(user, "is_admin", False):
            return qs
        if getattr(user, "is_developer", False):
            return qs.filter(
                deal__developer=user,
                type=Payment.Type.DEVELOPER_COMMISSION,
            )
        # Default: broker — sees both commission types
        return qs.filter(deal__broker=user)

    @payment_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PaymentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @payment_summary_schema
    def get(self, request, *args, **kwargs):
        user = request.user

        if getattr(user, "is_developer", False):
            return self._developer_summary(user)

        # Broker or Admin
        return self._broker_summary(user)

    def _broker_summary(self, user):
        qs = Payment.objects.all()
        if not (user.is_staff or getattr(user, "is_admin", False)):
            qs = qs.filter(deal__broker=user)

        agg = qs.aggregate(
            total=Sum("amount") or Decimal("0.00"),
            from_developers=Sum(
                Case(
                    When(type=Payment.Type.DEVELOPER_COMMISSION, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
            from_platform=Sum(
                Case(
                    When(type=Payment.Type.PLATFORM_COMMISSION, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
            pending=Sum(
                Case(
                    When(status=Payment.Status.PENDING, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
            paid=Sum(
                Case(
                    When(status=Payment.Status.PAID, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
        )

        # Replace None with 0
        for key in agg:
            if agg[key] is None:
                agg[key] = Decimal("0.00")

        ser = PaymentSummarySerializer(agg)
        return Response(ser.data, status=status.HTTP_200_OK)

    def _developer_summary(self, user):
        qs = Payment.objects.filter(
            deal__developer=user,
            type=Payment.Type.DEVELOPER_COMMISSION,
        )

        agg = qs.aggregate(
            total_to_pay=Sum("amount"),
            paid=Sum(
                Case(
                    When(status=Payment.Status.PAID, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
            pending=Sum(
                Case(
                    When(status=Payment.Status.PENDING, then="amount"),
                    default=Value(Decimal("0.00")),
                )
            ),
        )

        for key in agg:
            if agg[key] is None:
                agg[key] = Decimal("0.00")

        ser = DeveloperPaymentSummarySerializer(agg)
        return Response(ser.data, status=status.HTTP_200_OK)


class UploadReceiptView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    @payment_upload_receipt_schema
    def post(self, request, pk: int):
        ser = ReceiptUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            payment = get_object_or_404(Payment.objects.select_for_update(), pk=pk)

            if payment.type != Payment.Type.PLATFORM_COMMISSION:
                raise ValidationError(
                    {"detail": _("Чек загружается только для комиссии платформы.")}
                )

            if payment.status == Payment.Status.PAID:
                raise ValidationError(
                    {"detail": _("Выплата уже отмечена как оплаченная.")}
                )

            payment.receipt_document = ser.validated_data["receipt_document"]
            payment.status = Payment.Status.PAID
            payment.save(update_fields=["receipt_document", "status", "updated_at"])

        notify_payment_paid(payment=payment)

        return Response(
            {"detail": "Чек загружен. Выплата отмечена как оплаченная."},
            status=status.HTTP_200_OK,
        )


# =========================================================================
# Transit settlement endpoints
# =========================================================================


def _settlement_qs_for_user(user):
    qs = DealSettlement.objects.select_related(
        "deal",
        "deal__real_property",
        "deal__broker",
        "deal__developer",
        "deal__developer__developer",
    )
    if user.is_staff or getattr(user, "is_admin", False):
        return qs
    if getattr(user, "is_developer", False):
        return qs.filter(deal__developer=user)
    # broker
    return qs.filter(deal__broker=user)


class SettlementListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DealSettlementSerializer

    def get_queryset(self):
        return _settlement_qs_for_user(self.request.user).order_by("-created_at")


class SettlementSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _settlement_qs_for_user(request.user)
        total = qs.count()
        closed = qs.filter(
            paid_to_broker=True, received_from_developer=True
        ).count()
        awaiting_broker = qs.filter(paid_to_broker=False).count()
        awaiting_dev = qs.filter(received_from_developer=False).count()

        agg = qs.aggregate(
            owed=Sum("total_from_developer"),
            paid_to_b=Sum(
                "broker_amount", filter=_models.Q(paid_to_broker=True)
            ),
            received_from_d=Sum(
                "total_from_developer",
                filter=_models.Q(received_from_developer=True),
            ),
        )
        data = {
            "total_settlements": total,
            "closed": closed,
            "awaiting_broker_payout": awaiting_broker,
            "awaiting_developer_payment": awaiting_dev,
            "total_owed_by_developers": agg["owed"] or Decimal("0.00"),
            "total_paid_to_brokers": agg["paid_to_b"] or Decimal("0.00"),
            "total_received_from_developers": agg["received_from_d"]
            or Decimal("0.00"),
        }
        return Response(SettlementSummarySerializer(data).data)


class MarkPaidToBrokerView(APIView):
    """Admin marks that the platform has paid the broker (uploads receipt)."""

    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk: int):
        ser = MarkPaidToBrokerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            s = get_object_or_404(
                DealSettlement.objects.select_for_update(), pk=pk
            )
            if s.paid_to_broker:
                raise ValidationError(
                    {"detail": _("Уже отмечено как выплаченное брокеру.")}
                )

            s.broker_payout_receipt = ser.validated_data["broker_payout_receipt"]
            s.paid_to_broker = True
            s.paid_to_broker_at = timezone.now()
            s.save(
                update_fields=[
                    "broker_payout_receipt",
                    "paid_to_broker",
                    "paid_to_broker_at",
                    "updated_at",
                ]
            )

        try:
            from notifications.services import notify_broker_paid_out

            notify_broker_paid_out(settlement=s)
        except Exception:
            pass

        return Response(
            DealSettlementSerializer(s, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class UploadDeveloperReceiptView(APIView):
    """Developer uploads receipt that they paid the platform (3% + 0.4%)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk: int):
        ser = UploadDeveloperReceiptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            s = get_object_or_404(
                DealSettlement.objects.select_for_update(), pk=pk
            )
            if s.deal.developer_id != request.user.id and not (
                request.user.is_staff or getattr(request.user, "is_admin", False)
            ):
                raise ValidationError(
                    {"detail": _("Это расчёт не по вашей сделке.")}
                )
            if s.received_from_developer:
                raise ValidationError(
                    {"detail": _("Оплата уже подтверждена админом.")}
                )

            s.developer_receipt = ser.validated_data["developer_receipt"]
            s.developer_receipt_uploaded_at = timezone.now()
            s.save(
                update_fields=[
                    "developer_receipt",
                    "developer_receipt_uploaded_at",
                    "updated_at",
                ]
            )

        try:
            from notifications.services import notify_developer_receipt_uploaded

            notify_developer_receipt_uploaded(settlement=s)
        except Exception:
            pass

        return Response(
            DealSettlementSerializer(s, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class ConfirmDeveloperReceiptView(APIView):
    """Admin confirms they received the money from the developer."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        ConfirmDeveloperReceiptSerializer(data=request.data).is_valid(
            raise_exception=True
        )

        with transaction.atomic():
            s = get_object_or_404(
                DealSettlement.objects.select_for_update(), pk=pk
            )
            if s.received_from_developer:
                raise ValidationError(
                    {"detail": _("Уже подтверждено.")}
                )
            if not s.developer_receipt:
                raise ValidationError(
                    {"detail": _("Девелопер ещё не загрузил чек.")}
                )

            s.received_from_developer = True
            s.received_from_developer_at = timezone.now()
            s.save(
                update_fields=[
                    "received_from_developer",
                    "received_from_developer_at",
                    "updated_at",
                ]
            )

        try:
            from notifications.services import notify_developer_payment_received

            notify_developer_payment_received(settlement=s)
        except Exception:
            pass

        return Response(
            DealSettlementSerializer(s, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
