from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction, DocumentRequest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from notifications.models import Notification
from notifications.services import NotificationEvent
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


def _make_file(
    name: str = "passport.pdf", content: bytes = b"%PDF-1.4 test"
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class DocumentRequestsTestsBase(APITestCase, AuctionTestMixin):
    REQUEST_SUFFIX = "/request-documents/"
    LIST_SUFFIX = "/document-requests/"
    UPLOAD_URL = "/api/v1/auctions/document-requests/{pk}/upload/"

    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")
        now = timezone.now()
        self.auction = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )
        self.bid1 = self.create_bid(
            auction=self.auction,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )
        self.bid2 = self.create_bid(
            auction=self.auction,
            broker=self.broker2,
            amount=Decimal("1200.00"),
            is_sealed=True,
        )


class CreateDocumentRequestTests(DocumentRequestsTestsBase):
    def test_requires_auth(self):
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": self.broker1.id, "description": "passport"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_forbidden(self):
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": self.broker1.id, "description": "passport"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_broker_cannot_request(self):
        self.client.force_authenticate(user=self.broker1)
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": self.broker2.id, "description": "passport"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_creates_request(self):
        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
                {"broker_id": self.broker1.id, "description": "Скан паспорта"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], DocumentRequest.Status.PENDING)
        self.assertEqual(resp.data["broker"], self.broker1.id)
        self.assertEqual(resp.data["requested_by"], self.dev1.id)
        self.assertEqual(DocumentRequest.objects.count(), 1)

    def test_admin_can_request(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": self.broker1.id, "description": "Скан паспорта"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_broker_must_be_participant(self):
        other_broker = self.admin  # not a participant
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": other_broker.id, "description": "scan"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("broker_id", resp.data)

    def test_empty_description_rejected(self):
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(
            f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
            {"broker_id": self.broker1.id, "description": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_broker_gets_notification(self):
        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{self.auction.id}{self.REQUEST_SUFFIX}",
                {"broker_id": self.broker1.id, "description": "Скан паспорта"},
                format="json",
            )

        notif = Notification.objects.get(
            user=self.broker1, event_type=NotificationEvent.DOCUMENTS_REQUESTED
        )
        self.assertEqual(notif.data["auction_id"], self.auction.id)


class ListDocumentRequestsTests(DocumentRequestsTestsBase):
    def _create_request(self, broker):
        return DocumentRequest.objects.create(
            auction=self.auction,
            broker=broker,
            requested_by=self.dev1,
            description=f"request for {broker.email}",
        )

    def test_owner_sees_all(self):
        self._create_request(self.broker1)
        self._create_request(self.broker2)
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(f"{self.BASE}{self.auction.id}{self.LIST_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_admin_sees_all(self):
        self._create_request(self.broker1)
        self._create_request(self.broker2)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"{self.BASE}{self.auction.id}{self.LIST_SUFFIX}")
        self.assertEqual(len(resp.data), 2)

    def test_broker_sees_only_own(self):
        self._create_request(self.broker1)
        self._create_request(self.broker2)
        self.client.force_authenticate(user=self.broker1)
        resp = self.client.get(f"{self.BASE}{self.auction.id}{self.LIST_SUFFIX}")
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["broker"], self.broker1.id)

    def test_other_developer_sees_nothing(self):
        self._create_request(self.broker1)
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.get(f"{self.BASE}{self.auction.id}{self.LIST_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)


class UploadDocumentRequestResponseTests(DocumentRequestsTestsBase):
    def _create_pending_request(self, broker=None):
        return DocumentRequest.objects.create(
            auction=self.auction,
            broker=broker or self.broker1,
            requested_by=self.dev1,
            description="scan of passport",
        )

    def test_requires_auth(self):
        req = self._create_pending_request()
        resp = self.client.post(
            self.UPLOAD_URL.format(pk=req.id),
            {"files": [_make_file()]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_target_broker_can_upload(self):
        req = self._create_pending_request(broker=self.broker1)
        self.client.force_authenticate(user=self.broker2)
        resp = self.client.post(
            self.UPLOAD_URL.format(pk=req.id),
            {"files": [_make_file()]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_developer_cannot_upload(self):
        req = self._create_pending_request()
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(
            self.UPLOAD_URL.format(pk=req.id),
            {"files": [_make_file()]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_sets_status_and_creates_files(self):
        req = self._create_pending_request()
        self.client.force_authenticate(user=self.broker1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                self.UPLOAD_URL.format(pk=req.id),
                {
                    "files": [_make_file("f1.pdf"), _make_file("f2.pdf")],
                    "broker_comment": "Вот мои документы",
                },
                format="multipart",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        req.refresh_from_db()
        self.assertEqual(req.status, DocumentRequest.Status.ANSWERED)
        self.assertIsNotNone(req.answered_at)
        self.assertEqual(req.broker_comment, "Вот мои документы")
        self.assertEqual(req.response_documents.count(), 2)
        self.assertEqual(len(resp.data["response_documents"]), 2)

    def test_cannot_upload_twice(self):
        req = self._create_pending_request()
        self.client.force_authenticate(user=self.broker1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                self.UPLOAD_URL.format(pk=req.id),
                {"files": [_make_file()]},
                format="multipart",
            )
        resp = self.client.post(
            self.UPLOAD_URL.format(pk=req.id),
            {"files": [_make_file()]},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_files_rejected(self):
        req = self._create_pending_request()
        self.client.force_authenticate(user=self.broker1)
        resp = self.client.post(
            self.UPLOAD_URL.format(pk=req.id),
            {"files": []},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requester_gets_notification(self):
        req = self._create_pending_request()
        self.client.force_authenticate(user=self.broker1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                self.UPLOAD_URL.format(pk=req.id),
                {"files": [_make_file()]},
                format="multipart",
            )

        notif = Notification.objects.get(
            user=self.dev1, event_type=NotificationEvent.DOCUMENTS_REQUEST_ANSWERED
        )
        self.assertEqual(notif.data["document_request_id"], req.id)
        self.assertEqual(notif.data["file_count"], 1)
