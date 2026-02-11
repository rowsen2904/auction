from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction, Bid
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestClosedBids(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    def test_closed_bid_create_requires_broker(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
            min_price=Decimal("1000.00"),
        )

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(
            f"{self.BASE}{auc.id}/bid/", data={"amount": "1500.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch("auctions.participants.add_participant_with_flag")
    def test_closed_bid_create_success_autojoin(self, add_participant_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
            min_price=Decimal("1000.00"),
        )

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.post(
            f"{self.BASE}{auc.id}/bid/", data={"amount": "1500.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        bid = Bid.objects.get(id=resp.data["id"])
        self.assertTrue(bid.is_sealed)
        self.assertEqual(bid.auction_id, auc.id)

        add_participant_mock.assert_called_once()
        _, kwargs = add_participant_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["user_id"], self.broker1.id)

    def test_closed_bid_create_only_one_bid_per_broker(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.broker1)
        r1 = self.client.post(
            f"{self.BASE}{auc.id}/bid/", data={"amount": "1500.00"}, format="json"
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        r2 = self.client.post(
            f"{self.BASE}{auc.id}/bid/", data={"amount": "1600.00"}, format="json"
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_closed_bid_update_success(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
            min_price=Decimal("1000.00"),
        )
        bid = self.create_bid(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=True
        )

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.patch(
            f"{self.BASE}{auc.id}/bid/update/",
            data={"amount": "2500.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        bid.refresh_from_db()
        self.assertEqual(bid.amount, Decimal("2500.00"))

    def test_closed_bid_update_forbidden_if_not_active(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(hours=1),
        )
        self.create_bid(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=True
        )

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.patch(
            f"{self.BASE}{auc.id}/bid/update/",
            data={"amount": "2500.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
