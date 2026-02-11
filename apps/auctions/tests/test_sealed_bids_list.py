from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestSealedBidsList(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    def _len(self, resp) -> int:
        if isinstance(resp.data, list):
            return len(resp.data)
        return int(resp.data.get("count", 0))

    def test_sealed_bids_list_owner_or_admin_only(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )
        self.create_bid(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=True
        )

        self.client.force_authenticate(user=self.broker1)
        r1 = self.client.get(f"{self.BASE}{auc.id}/sealed-bids/", format="json")
        self.assertEqual(r1.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.dev1)
        r2 = self.client.get(f"{self.BASE}{auc.id}/sealed-bids/", format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(self._len(r2), 1)

        self.client.force_authenticate(user=self.admin)
        r3 = self.client.get(f"{self.BASE}{auc.id}/sealed-bids/", format="json")
        self.assertEqual(r3.status_code, status.HTTP_200_OK)
        self.assertEqual(self._len(r3), 1)
