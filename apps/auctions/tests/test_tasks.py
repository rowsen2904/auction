from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction, Bid
from auctions.tasks import activate_auction, finish_auction
from deals.models import Deal
from django.test import TestCase
from django.utils import timezone

from .mixins import AuctionTestMixin


class TestAuctionTasks(TestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    @patch("auctions.tasks.broadcast_auction_status")
    def test_activate_auction_sets_active(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.SCHEDULED,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        activate_auction.run(auc.id)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.ACTIVE)
        broadcast_mock.assert_called()

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_open_sets_winner_highest(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )

        self.create_bid(
            auction=auc, broker=self.broker1, amount=Decimal("1000.00"), is_sealed=False
        )
        b2 = self.create_bid(
            auction=auc, broker=self.broker2, amount=Decimal("2000.00"), is_sealed=False
        )

        auc.highest_bid_id = b2.id
        auc.save(update_fields=["highest_bid_id"])

        finish_auction.run(auc.id)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FINISHED)
        self.assertEqual(auc.winner_bid_id, b2.id)
        broadcast_mock.assert_called()

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_no_bids_no_winner(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )

        finish_auction.run(auc.id)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FINISHED)
        self.assertIsNone(auc.winner_bid_id)

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_autopicks_highest_bid(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )

        self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )
        b2 = self.create_bid(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("2000.00"),
            is_sealed=True,
        )

        finish_auction.run(auc.id)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FINISHED)
        self.assertEqual(auc.winner_bid_id, b2.id)

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_does_not_create_deal_until_confirm(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )

        bid = self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )

        finish_auction.run(auc.id)

        auc.refresh_from_db()
        self.assertEqual(auc.winner_bid_id, bid.id)
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.PENDING)
        self.assertFalse(Deal.objects.filter(auction_id=auc.id).exists())

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_tie_earliest_bid_wins(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )

        b1 = Bid.objects.create(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("2000.00"),
            is_sealed=True,
            created_at=now - timedelta(hours=1, minutes=30),
        )
        Bid.objects.create(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("2000.00"),
            is_sealed=True,
            created_at=now - timedelta(hours=1),
        )

        finish_auction.run(auc.id)
        auc.refresh_from_db()
        self.assertEqual(auc.winner_bid_id, b1.id)

    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_shortlists_winner(self, broadcast_mock):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )

        bid = self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )

        finish_auction.run(auc.id)
        auc.refresh_from_db()
        shortlisted = list(auc.shortlisted_bids.values_list("id", flat=True))
        self.assertEqual(shortlisted, [bid.id])

    @patch("auctions.tasks.notify_auction_result_awaiting_owner")
    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_notifies_owner_awaiting_decision(
        self, broadcast_mock, awaiting_mock
    ):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )

        self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("1500.00"),
            is_sealed=True,
        )
        b2 = self.create_bid(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("2000.00"),
            is_sealed=True,
        )

        finish_auction.run(auc.id)

        awaiting_mock.assert_called_once()
        _, kwargs = awaiting_mock.call_args
        self.assertEqual(kwargs["winner_bid"].id, b2.id)
