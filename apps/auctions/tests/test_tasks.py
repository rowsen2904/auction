from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction
from auctions.tasks import activate_auction, finish_auction
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

    def test_finish_closed_does_not_autopick_winner(self):
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
