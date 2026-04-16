from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction
from deals.models import Deal
from django.utils import timezone
from notifications.models import Notification
from notifications.services import NotificationEvent
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class AuctionResultDecisionTestsBase(APITestCase, AuctionTestMixin):
    CONFIRM_SUFFIX = "/confirm-result/"
    REJECT_SUFFIX = "/reject-result/"

    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    def _make_finished_open_auction_with_winner(self) -> tuple[Auction, int]:
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )
        bid = self.create_bid(
            auction=auc,
            broker=self.broker1,
            amount=Decimal("2000.00"),
            is_sealed=False,
        )
        auc.winner_bid_id = bid.id
        auc.highest_bid_id = bid.id
        auc.save(update_fields=["winner_bid_id", "highest_bid_id"])
        return auc, bid.id

    def _make_finished_closed_auction_with_winner(self) -> tuple[Auction, int]:
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.FINISHED,
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
        self.create_bid(
            auction=auc,
            broker=self.broker2,
            amount=Decimal("1200.00"),
            is_sealed=True,
        )
        auc.winner_bid_id = bid.id
        auc.save(update_fields=["winner_bid_id"])
        auc.shortlisted_bids.set([bid.id])
        return auc, bid.id


class AuctionConfirmResultTests(AuctionResultDecisionTestsBase):
    def test_requires_auth(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_forbidden(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_broker_forbidden(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.broker1)
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_rejects_unfinished_auction(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_auction_without_winner(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_creates_deal_for_open(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["ownerDecision"], Auction.OwnerDecision.CONFIRMED)
        self.assertEqual(len(resp.data["createdDealIds"]), 1)

        auc.refresh_from_db()
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.CONFIRMED)
        self.assertIsNotNone(auc.owner_decided_at)

        deal = Deal.objects.get(auction_id=auc.id)
        self.assertEqual(deal.broker_id, self.broker1.id)
        self.assertEqual(deal.real_property_id, self.prop1.id)

    def test_confirm_creates_deal_for_closed(self):
        auc, bid_id = self._make_finished_closed_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        deals = Deal.objects.filter(auction_id=auc.id)
        self.assertEqual(deals.count(), 1)
        self.assertEqual(deals.first().bid_id, bid_id)

    def test_admin_can_confirm(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        auc.refresh_from_db()
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.CONFIRMED)

    def test_double_confirm_is_rejected(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AuctionRejectResultTests(AuctionResultDecisionTestsBase):
    def test_requires_auth(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
            {"reason": "no"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_forbidden(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
            {"reason": "no"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_reason_required(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}", {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_marks_auction_failed(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
                {"reason": "Not acceptable price"},
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.FAILED)
        self.assertEqual(auc.owner_decision, Auction.OwnerDecision.REJECTED)
        self.assertEqual(auc.owner_rejection_reason, "Not acceptable price")
        self.assertIsNotNone(auc.owner_decided_at)
        self.assertFalse(Deal.objects.filter(auction_id=auc.id).exists())

    def test_reject_notifies_broker_and_admins(self):
        auc, bid_id = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
                {"reason": "Price too low"},
                format="json",
            )

        notifs = Notification.objects.filter(
            auction=auc, event_type=NotificationEvent.AUCTION_RESULT_REJECTED
        )
        recipients = set(notifs.values_list("user_id", flat=True))
        self.assertIn(self.broker1.id, recipients)
        self.assertIn(self.admin.id, recipients)

    def test_cannot_confirm_after_reject(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
                {"reason": "nope"},
                format="json",
            )
        resp = self.client.post(f"{self.BASE}{auc.id}{self.CONFIRM_SUFFIX}")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_reject_cancelled_auction(self):
        auc, _ = self._make_finished_open_auction_with_winner()
        auc.status = Auction.Status.CANCELLED
        auc.save(update_fields=["status"])
        self.client.force_authenticate(user=self.dev1)

        resp = self.client.post(
            f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
            {"reason": "late"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("auctions.services.result_decision.notify_auction_result_rejected")
    def test_reject_calls_notify_with_reason_and_winner(self, notify_mock):
        auc, bid_id = self._make_finished_open_auction_with_winner()
        self.client.force_authenticate(user=self.dev1)

        self.client.post(
            f"{self.BASE}{auc.id}{self.REJECT_SUFFIX}",
            {"reason": "price low"},
            format="json",
        )

        notify_mock.assert_called_once()
        _, kwargs = notify_mock.call_args
        self.assertEqual(kwargs["reason"], "price low")
        self.assertEqual(kwargs["winner_bid"].id, bid_id)
