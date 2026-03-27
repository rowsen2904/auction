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

    @patch("auctions.views.closed_bids.broadcast_sealed_bid_changed")
    @patch(
        "auctions.views.closed_bids.auction_participants.list_participants",
        return_value=[1],
    )
    @patch(
        "auctions.views.closed_bids.auction_participants.add_participant_with_flag",
        return_value=(1, True),
    )
    def test_closed_bid_create_broadcasts_sealed_bid_changed(
        self,
        add_participant_mock,
        list_participants_mock,
        bid_changed_mock,
    ):
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

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}/bid/",
                data={"amount": "1500.00"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        bid_changed_mock.assert_called_once()

        _, kwargs = bid_changed_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["action"], "created")
        self.assertEqual(kwargs["auction_payload"]["id"], auc.id)
        self.assertEqual(kwargs["bid_payload"]["id"], resp.data["id"])

    @patch("auctions.views.closed_bids._broadcast_sealed_participants_changed")
    @patch(
        "auctions.views.closed_bids.auction_participants.list_participants",
        return_value=[123],
    )
    @patch(
        "auctions.views.closed_bids.auction_participants.add_participant_with_flag",
        return_value=(1, True),
    )
    def test_closed_bid_create_broadcasts_joined_when_user_was_added(
        self,
        add_participant_mock,
        list_participants_mock,
        participants_changed_mock,
    ):
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

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}/bid/",
                data={"amount": "1500.00"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        participants_changed_mock.assert_called_once()

        _, kwargs = participants_changed_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["action"], "joined")
        self.assertEqual(kwargs["user_id"], self.broker1.id)
        self.assertEqual(kwargs["participants"], [123])

    @patch("auctions.views.closed_bids._broadcast_sealed_participants_changed")
    @patch(
        "auctions.views.closed_bids.auction_participants.list_participants",
        return_value=[123],
    )
    @patch(
        "auctions.views.closed_bids.auction_participants.add_participant_with_flag",
        return_value=(1, False),
    )
    def test_closed_bid_create_does_not_broadcast_joined_if_already_participant(
        self,
        add_participant_mock,
        list_participants_mock,
        participants_changed_mock,
    ):
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

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}/bid/",
                data={"amount": "1500.00"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        participants_changed_mock.assert_not_called()

    @patch("auctions.views.closed_bids.broadcast_sealed_bid_changed")
    def test_closed_bid_update_broadcasts_sealed_bid_changed(self, bid_changed_mock):
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
        self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )

        self.client.force_authenticate(user=self.broker1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.patch(
                f"{self.BASE}{auc.id}/bid/update/",
                data={"amount": "2500.00"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        bid_changed_mock.assert_called_once()

        _, kwargs = bid_changed_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["action"], "updated")

    @patch("auctions.views.closed_bids.broadcast_sealed_bid_changed")
    @patch("auctions.views.closed_bids._broadcast_sealed_participants_changed")
    @patch(
        "auctions.views.closed_bids.auction_participants.list_participants",
        return_value=[],
    )
    @patch(
        "auctions.views.closed_bids.auction_participants.remove_participant",
        return_value=0,
    )
    @patch(
        "auctions.views.closed_bids.auction_participants.participants_count",
        return_value=1,
    )
    def test_closed_bid_delete_success(
        self,
        participants_count_mock,
        remove_participant_mock,
        list_participants_mock,
        participants_changed_mock,
        bid_changed_mock,
    ):
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
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )

        auc.bids_count = 1
        auc.current_price = Decimal("1500.00")
        auc.highest_bid_id = bid.id
        auc.save(
            update_fields=[
                "bids_count",
                "current_price",
                "highest_bid_id",
                "updated_at",
            ]
        )

        self.client.force_authenticate(user=self.broker1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"{self.BASE}{auc.id}/bid/update/", format="json")

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Bid.objects.filter(id=bid.id).exists())

        remove_participant_mock.assert_called_once()
        bid_changed_mock.assert_called_once()
        participants_changed_mock.assert_called_once()

    def test_closed_bid_delete_recalculates_auction_state(self):
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

        bid1 = self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )
        bid2 = self.create_bid(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("2000.00"),
            is_sealed=True,
        )

        auc.bids_count = 2
        auc.current_price = Decimal("2000.00")
        auc.highest_bid_id = bid2.id
        auc.save(
            update_fields=[
                "bids_count",
                "current_price",
                "highest_bid_id",
                "updated_at",
            ]
        )

        self.client.force_authenticate(user=self.broker2)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"{self.BASE}{auc.id}/bid/update/", format="json")

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        auc.refresh_from_db()
        self.assertEqual(auc.bids_count, 1)
        self.assertEqual(auc.current_price, Decimal("1500.00"))
        self.assertEqual(auc.highest_bid_id, bid1.id)
