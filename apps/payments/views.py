from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Case, Q, Sum, Value, When
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment
from .serializers import (
    DeveloperPaymentSummarySerializer,
    PaymentListSerializer,
    PaymentSummarySerializer,
    ReceiptUploadSerializer,
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


class PaymentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
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

    def post(self, request, pk: int):
        ser = ReceiptUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            payment = get_object_or_404(
                Payment.objects.select_for_update(), pk=pk
            )

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
            payment.save(
                update_fields=["receipt_document", "status", "updated_at"]
            )

        return Response(
            {"detail": "Чек загружен. Выплата отмечена как оплаченная."},
            status=status.HTTP_200_OK,
        )
