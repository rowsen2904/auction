from __future__ import annotations

from auctions.document_request_serializers import (
    CreateDocumentRequestSerializer,
    DocumentRequestSerializer,
    UploadDocumentRequestSerializer,
)
from auctions.models import Auction, DocumentRequest
from auctions.services.document_requests import (
    create_document_request,
    list_document_requests_for_user,
    upload_document_request_response,
)
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class RequestDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        ser = CreateDocumentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            auction = get_object_or_404(
                Auction.objects.select_for_update().select_related("owner"),
                pk=pk,
            )
            document_request = create_document_request(
                auction=auction,
                broker_id=ser.validated_data["broker_id"],
                description=ser.validated_data["description"],
                requested_by=request.user,
            )

        return Response(
            DocumentRequestSerializer(
                document_request, context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentRequestListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentRequestSerializer
    pagination_class = None

    def get_queryset(self):
        auction = get_object_or_404(Auction, pk=self.kwargs["pk"])
        return list_document_requests_for_user(auction=auction, user=self.request.user)


class UploadDocumentRequestResponseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk: int):
        ser = UploadDocumentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            document_request = get_object_or_404(
                DocumentRequest.objects.select_for_update().select_related(
                    "auction", "broker", "requested_by"
                ),
                pk=pk,
            )
            upload_document_request_response(
                document_request=document_request,
                files=ser.validated_data["files"],
                broker_comment=ser.validated_data.get("broker_comment", ""),
                broker=request.user,
            )

        document_request.refresh_from_db()
        return Response(
            DocumentRequestSerializer(
                document_request, context={"request": request}
            ).data,
            status=status.HTTP_200_OK,
        )
