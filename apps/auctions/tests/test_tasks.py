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
    def test_finish_closed_creates_deal(self, broadcast_mock):
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

        deal = Deal.objects.get(auction_id=auc.id)
        self.assertEqual(deal.broker_id, self.broker1.id)
        self.assertEqual(deal.bid_id, bid.id)
        self.assertEqual(deal.real_property_id, self.prop1.id)
        self.assertEqual(deal.amount, self.prop1.price)
        self.assertEqual(deal.lot_bid_amount, Decimal("1500.00"))

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

    @patch("auctions.services.assignments.notify_closed_not_selected")
    @patch("auctions.tasks.broadcast_auction_status")
    def test_finish_closed_notifies_non_selected(self, broadcast_mock, notify_mock):
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
        self.create_bid(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("2000.00"),
            is_sealed=True,
        )

        finish_auction.run(auc.id)

        notify_mock.assert_called_once()
        _, kwargs = notify_mock.call_args
        self.assertEqual(kwargs["selected_broker_ids"], [self.broker2.id])
