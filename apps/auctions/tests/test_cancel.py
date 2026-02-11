from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from auctions.models import Auction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestAuctionsCancel(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    def test_cancel_requires_auth(self):
        auc = self.create_auction(owner=self.dev1, prop=self.prop1)
        resp = self.client.delete(
            f"{self.BASE}{auc.id}{self.CANCEL_SUFFIX}", format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cancel_requires_owner_or_admin(self):
        auc = self.create_auction(owner=self.dev1, prop=self.prop1)
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.delete(
            f"{self.BASE}{auc.id}{self.CANCEL_SUFFIX}", format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch("auctions.views.cancel.cancel_auction_status_tasks")
    def test_cancel_owner_success_far_from_start(self, cancel_tasks_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=5),
            end=now + timedelta(days=1),
            status_val=Auction.Status.DRAFT,
        )

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(
                f"{self.BASE}{auc.id}{self.CANCEL_SUFFIX}", format="json"
            )

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.CANCELLED)
        cancel_tasks_mock.assert_called_once_with(auction_id=auc.id)
