from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.consumers import _place_open_bid_atomic_sync
from auctions.models import Auction, Bid
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .mixins import AuctionTestMixin


class TestOpenBidPlacement(TestCase, AuctionTestMixin):
    """Tests for the open-auction single-bid-per-broker logic."""

    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")
        now = timezone.now()
        self.auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
            min_price=Decimal("1000.00"),
            min_bid_increment=Decimal("100.00"),
        )

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_first_bid_creates_new(self, _add_mock):
        auction_patch, bid_data, participant_event, is_new = (
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker1,
                requested_amount=Decimal("1000.00"),
            )
        )

        self.assertTrue(is_new)
        self.assertEqual(
            Bid.objects.filter(auction=self.auc, is_sealed=False).count(), 1
        )

        bid = Bid.objects.get(id=bid_data["id"])
        self.assertEqual(bid.broker_id, self.broker1.id)
        self.assertEqual(bid.amount, Decimal("1000.00"))
        self.assertFalse(bid.is_sealed)

        self.auc.refresh_from_db()
        self.assertEqual(self.auc.bids_count, 1)
        self.assertEqual(self.auc.current_price, Decimal("1000.00"))
        self.assertEqual(self.auc.highest_bid_id, bid.id)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(2, True))
    def test_second_broker_creates_own_bid(self, _add_mock):
        # broker1 places first bid
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )

        # broker2 places a higher bid
        auction_patch, bid_data, _, is_new = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker2,
            requested_amount=Decimal("1100.00"),
        )

        self.assertTrue(is_new)
        self.assertEqual(
            Bid.objects.filter(auction=self.auc, is_sealed=False).count(), 2
        )

        self.auc.refresh_from_db()
        self.assertEqual(self.auc.bids_count, 2)
        self.assertEqual(self.auc.current_price, Decimal("1100.00"))

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, False))
    def test_same_broker_updates_existing_bid(self, _add_mock):
        # broker1 places first bid (first bid always = min_price)
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )
        bid = Bid.objects.get(auction=self.auc, broker=self.broker1, is_sealed=False)
        original_bid_id = bid.id
        original_created_at = bid.created_at

        # broker2 places a bid so broker1 is no longer leader
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(2, True)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker2,
                requested_amount=Decimal("1100.00"),
            )

        # broker1 updates their bid
        auction_patch, bid_data, _, is_new = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1200.00"),
        )

        self.assertFalse(is_new)
        # same bid object, not a new one
        self.assertEqual(bid_data["id"], original_bid_id)
        # still only 2 bids total
        self.assertEqual(
            Bid.objects.filter(auction=self.auc, is_sealed=False).count(), 2
        )

        bid.refresh_from_db()
        self.assertEqual(bid.amount, Decimal("1200.00"))
        self.assertEqual(bid.created_at, original_created_at)

        self.auc.refresh_from_db()
        self.assertEqual(self.auc.bids_count, 2)
        self.assertEqual(self.auc.current_price, Decimal("1200.00"))
        self.assertEqual(self.auc.highest_bid_id, original_bid_id)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_bids_count_reflects_unique_participants(self, _add_mock):
        # broker1 first bid
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )
        self.auc.refresh_from_db()
        self.assertEqual(self.auc.bids_count, 1)

        # broker2 bids
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker2,
            requested_amount=Decimal("1100.00"),
        )
        self.auc.refresh_from_db()
        self.assertEqual(self.auc.bids_count, 2)

        # broker1 updates (outbid by broker2, so not leader)
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(2, False)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker1,
                requested_amount=Decimal("1200.00"),
            )
        self.auc.refresh_from_db()
        # still 2, not 3
        self.assertEqual(self.auc.bids_count, 2)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_participant_event_on_first_bid_only(self, _add_mock):
        _, _, participant_event, _ = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )
        self.assertIsNotNone(participant_event)
        self.assertEqual(participant_event["user_id"], self.broker1.id)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, False))
    def test_no_participant_event_on_update(self, _add_mock):
        # create first bid
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(1, True)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker1,
                requested_amount=Decimal("1000.00"),
            )

        # broker2 bids to make broker1 no longer leader
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(2, True)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker2,
                requested_amount=Decimal("1100.00"),
            )

        # broker1 updates
        _, _, participant_event, _ = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1200.00"),
        )
        self.assertIsNone(participant_event)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_bid_updated_at_changes_on_update(self, _add_mock):
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )
        bid = Bid.objects.get(auction=self.auc, broker=self.broker1, is_sealed=False)
        original_updated_at = bid.updated_at

        # broker2 bids
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(2, True)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker2,
                requested_amount=Decimal("1100.00"),
            )

        # broker1 updates
        with patch(
            "auctions.consumers.add_participant_with_flag", return_value=(2, False)
        ):
            _place_open_bid_atomic_sync(
                auction_id=self.auc.id,
                user=self.broker1,
                requested_amount=Decimal("1200.00"),
            )

        bid.refresh_from_db()
        self.assertGreaterEqual(bid.updated_at, original_updated_at)

    def test_unique_constraint_open_bid_per_broker(self):
        Bid.objects.create(
            auction=self.auc,
            broker=self.broker1,
            amount=Decimal("1000.00"),
            is_sealed=False,
        )

        with self.assertRaises(IntegrityError):
            Bid.objects.create(
                auction=self.auc,
                broker=self.broker1,
                amount=Decimal("1500.00"),
                is_sealed=False,
            )

    def test_different_brokers_can_have_open_bids(self):
        Bid.objects.create(
            auction=self.auc,
            broker=self.broker1,
            amount=Decimal("1000.00"),
            is_sealed=False,
        )
        Bid.objects.create(
            auction=self.auc,
            broker=self.broker2,
            amount=Decimal("1500.00"),
            is_sealed=False,
        )
        self.assertEqual(
            Bid.objects.filter(auction=self.auc, is_sealed=False).count(), 2
        )

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_bid_response_contains_updated_at(self, _add_mock):
        _, bid_data, _, _ = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )
        self.assertIn("updated_at", bid_data)

    @patch("auctions.consumers.add_participant_with_flag", return_value=(1, True))
    def test_leader_can_raise_own_bid(self, _add_mock):
        _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1000.00"),
        )

        auction_patch, bid_data, _, is_new = _place_open_bid_atomic_sync(
            auction_id=self.auc.id,
            user=self.broker1,
            requested_amount=Decimal("1100.00"),
        )
        self.assertFalse(is_new)
        self.assertEqual(auction_patch["current_price"], "1100.00")
        self.assertEqual(bid_data["amount"], "1100.00")
