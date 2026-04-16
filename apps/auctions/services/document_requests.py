from __future__ import annotations

from typing import Iterable

from auctions.models import Auction, Bid, DocumentRequest, DocumentRequestFile
from auctions.services.rules import is_admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from notifications.services import (
    notify_broker_documents_requested,
    notify_documents_request_answered,
)
from rest_framework.exceptions import PermissionDenied, ValidationError

User = get_user_model()


def _assert_can_request(auction: Auction, user) -> None:
    if not (is_admin(user) or user.id == auction.owner_id):
        raise PermissionDenied(
            "Запрашивать документы может только владелец аукциона или администратор."
        )


def create_document_request(
    *,
    auction: Auction,
    broker_id: int,
    description: str,
    requested_by,
) -> DocumentRequest:
    _assert_can_request(auction, requested_by)

    if not description.strip():
        raise ValidationError({"description": "Описание не может быть пустым."})

    broker_has_bid = Bid.objects.filter(
        auction_id=auction.id, broker_id=broker_id
    ).exists()
    if not broker_has_bid:
        raise ValidationError(
            {"broker_id": "Запросить документы можно только у участника аукциона."}
        )

    broker = User.objects.filter(id=broker_id).first()
    if broker is None:
        raise ValidationError({"broker_id": "Брокер не найден."})

    with transaction.atomic():
        document_request = DocumentRequest.objects.create(
            auction=auction,
            broker=broker,
            requested_by=requested_by,
            description=description.strip(),
            status=DocumentRequest.Status.PENDING,
        )

    notify_broker_documents_requested(document_request=document_request)
    return document_request


def upload_document_request_response(
    *,
    document_request: DocumentRequest,
    files: Iterable,
    broker_comment: str,
    broker,
) -> DocumentRequest:
    if document_request.broker_id != broker.id:
        raise PermissionDenied(
            "Ответить на запрос может только брокер, которому он адресован."
        )
    if document_request.status != DocumentRequest.Status.PENDING:
        raise ValidationError({"detail": "Запрос уже обработан или отменён."})

    files = list(files)
    if not files:
        raise ValidationError({"files": "Нужно загрузить хотя бы один файл."})

    with transaction.atomic():
        [
            DocumentRequestFile.objects.create(request=document_request, file=file)
            for file in files
        ]
        document_request.status = DocumentRequest.Status.ANSWERED
        document_request.answered_at = timezone.now()
        if broker_comment:
            document_request.broker_comment = broker_comment
        document_request.save(
            update_fields=[
                "status",
                "answered_at",
                "broker_comment",
                "updated_at",
            ]
        )

    notify_documents_request_answered(document_request=document_request)
    return document_request


def list_document_requests_for_user(*, auction: Auction, user):
    qs = (
        DocumentRequest.objects.filter(auction=auction)
        .select_related("broker", "requested_by")
        .prefetch_related("response_documents")
    )

    if is_admin(user) or user.id == auction.owner_id:
        return qs
    return qs.filter(broker_id=user.id)
