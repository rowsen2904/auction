from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction, Bid
from deals.models import Deal, DealLog
from django.utils import timezone
from notifications.models import Notification
from notifications.services import NotificationEvent
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class DeclineResultTestsBase(APITestCase, AuctionTestMixin):
    DECLINE_SUFFIX = "/decline-result/"

    def setUp(self):
        self.create_users()
        self.prop = self.create_property(self.dev1, address="Decline prop")

    def _make_open_auction_with_bids(
        self, amounts: list[Decimal]
    ) -> tuple[Auction, list[Bid]]:
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("100.00"),
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )
        brokers = [self.broker1, self.broker2]
        bids: list[Bid] = []
        for idx, amt in enumerate(amounts):
            if idx >= len(brokers):
                break
            bid = self.create_bid(
                auction=auc, broker=brokers[idx], amount=amt, is_sealed=False
            )
            bids.append(bid)
        top_bid = max(bids, key=lambda b: b.amount)
        auc.winner_bid_id = top_bid.id
        auc.highest_bid_id = top_bid.id
        auc.save(update_fields=["winner_bid_id", "highest_bid_id"])
        return auc, bids

    def _make_closed_auction_with_shortlist(self) -> tuple[Auction, Bid, Bid]:
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
            min_price=Decimal("1000.00"),
        )
        b1 = self.create_bid(
            auction=auc, broker=self.broker1, amount=Decimal("2000.00"), is_sealed=True
        )
        b2 = self.create_bid(
            auction=auc, broker=self.broker2, amount=Decimal("1500.00"), is_sealed=True
        )
        auc.winner_bid_id = b1.id
        auc.save(update_fields=["winner_bid_id"])
        auc.shortlisted_bids.set([b1.id, b2.id])
        return auc, b1, b2


class DeclineResultPermissionsTests(DeclineResultTestsBase):
    def test_requires_auth(self):
        auc, _ = self._make_open_auction_with_bids([Decimal("1000"), Decimal("2000")])
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
            {"reason": "late"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_forbidden(self):
        auc, _ = self._make_open_auction_with_bids([Decimal("1000"), Decimal("2000")])
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
            {"reason": "late"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_reason_required(self):
        auc, _ = self._make_open_auction_with_bids([Decimal("1000"), Decimal("2000")])
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class DeclineOpenAuctionTests(DeclineResultTestsBase):
    def test_promotes_next_highest(self):
        auc, bids = self._make_open_auction_with_bids(
            [Decimal("1000"), Decimal("2000")]
        )
        top, lower = sorted(bids, key=lambda b: b.amount, reverse=True)

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "no fit"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["auctionFailed"])
        self.assertEqual(resp.data["newWinnerBidId"], lower.id)

        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FINISHED)
        self.assertEqual(auc.winner_bid_id, lower.id)
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.PENDING)
        self.assertIn(top.id, auc.declined_bids.values_list("id", flat=True))

    def test_no_next_candidate_marks_failed(self):
        auc, bids = self._make_open_auction_with_bids([Decimal("1000")])

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "nope"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["auctionFailed"])
        self.assertIsNone(resp.data["newWinnerBidId"])

        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FAILED)
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.REJECTED)
        self.assertEqual(auc.owner_rejection_reason, "nope")

    def test_declined_broker_gets_notification(self):
        auc, bids = self._make_open_auction_with_bids(
            [Decimal("1000"), Decimal("2000")]
        )
        top = max(bids, key=lambda b: b.amount)

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "price too high"},
                format="json",
            )

        notif = Notification.objects.get(
            user=top.broker, event_type=NotificationEvent.AUCTION_WINNER_DECLINED
        )
        self.assertEqual(notif.data["auction_id"], auc.id)

    def test_new_winner_gets_promotion_notification(self):
        auc, bids = self._make_open_auction_with_bids(
            [Decimal("1000"), Decimal("2000")]
        )
        lower = min(bids, key=lambda b: b.amount)

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "promote"},
                format="json",
            )

        notif = Notification.objects.filter(
            user=lower.broker, event_type=NotificationEvent.AUCTION_WINNER_PROMOTED
        )
        self.assertEqual(notif.count(), 1)

    def test_cannot_decline_twice_without_candidates(self):
        auc, bids = self._make_open_auction_with_bids(
            [Decimal("1000"), Decimal("2000")]
        )
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "1"},
                format="json",
            )
        # 2nd decline exhausts pool -> FAILED
        with self.captureOnCommitCallbacks(execute=True):
            resp2 = self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "2"},
                format="json",
            )
        # 3rd decline -> auction already FAILED, no winner
        resp3 = self.client.post(
            f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
            {"reason": "3"},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertTrue(resp2.data["auctionFailed"])
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)


class DeclineClosedAuctionTests(DeclineResultTestsBase):
    def test_decline_picks_next_from_shortlist(self):
        auc, b1, b2 = self._make_closed_auction_with_shortlist()

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "switch"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["newWinnerBidId"], b2.id)

        auc.refresh_from_db()
        self.assertEqual(auc.winner_bid_id, b2.id)
        self.assertEqual(auc.status, Auction.Status.FINISHED)
        self.assertIn(b1.id, auc.declined_bids.values_list("id", flat=True))
        self.assertNotIn(b1.id, auc.shortlisted_bids.values_list("id", flat=True))
        self.assertIn(b2.id, auc.shortlisted_bids.values_list("id", flat=True))

    def test_shortlist_exhausted_marks_failed(self):
        auc, b1, b2 = self._make_closed_auction_with_shortlist()

        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "decline first"},
                format="json",
            )
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "decline second"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["auctionFailed"])
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FAILED)


class DeclineWithExistingDealTests(DeclineResultTestsBase):
    def _confirm_auction_and_get_deal(self, auc: Auction) -> Deal:
        # simulate deal creation via confirm-result
        self.client.force_authenticate(user=self.dev1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{self.BASE}{auc.id}/confirm-result/")
        deal = Deal.objects.get(auction_id=auc.id)
        return deal

    def test_decline_marks_deal_as_declined(self):
        auc, bids = self._make_open_auction_with_bids(
            [Decimal("1000"), Decimal("2000")]
        )
        deal = self._confirm_auction_and_get_deal(auc)
        self.assertEqual(deal.status, Deal.Status.PENDING_DOCUMENTS)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
                {"reason": "docs wrong"},
                format="json",
            )

        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.DECLINED)
        self.assertTrue(
            DealLog.objects.filter(
                deal=deal, action=DealLog.Action.MARKED_DECLINED
            ).exists()
        )

    def test_decline_blocked_when_deal_in_admin_review(self):
        auc, _ = self._make_open_auction_with_bids([Decimal("1000"), Decimal("2000")])
        deal = self._confirm_auction_and_get_deal(auc)
        deal.status = Deal.Status.ADMIN_REVIEW
        deal.save(update_fields=["status"])

        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.DECLINE_SUFFIX}",
            {"reason": "too late"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.ADMIN_REVIEW)
