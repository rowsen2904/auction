from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.tests.mixins import AuctionTestMixin
from deals.models import Deal, DealLog
from deals.tasks import mark_failed_pending_deals
from django.test import TestCase, override_settings
from django.utils import timezone
from notifications.models import Notification
from notifications.services import NotificationEvent


class MarkFailedPendingDealsTests(TestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop = self.create_property(self.dev1, address="Mark-failed prop")
        self.auction = self.create_auction(
            owner=self.dev1,
            prop=self.prop,
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() - timedelta(days=8),
            min_bid_increment=Decimal("150000.00"),
        )
        self.bid = self.create_bid(
            auction=self.auction,
            broker=self.broker1,
            amount=Decimal("2000.00"),
            is_sealed=False,
        )

    def _create_deal(
        self,
        *,
        created_days_ago: int,
        status=Deal.Status.PENDING_DOCUMENTS,
        auction=None,
        bid=None,
        prop=None,
        broker=None,
    ) -> Deal:
        deal = Deal.objects.create(
            auction=auction or self.auction,
            bid=bid or self.bid,
            broker=broker or self.broker1,
            developer=self.dev1,
            real_property=prop or self.prop,
            amount=Decimal("2000.00"),
            lot_bid_amount=Decimal("2000.00"),
            status=status,
            obligation_status=Deal.ObligationStatus.ACTIVE,
            document_deadline=timezone.now() - timedelta(days=1),
        )
        Deal.objects.filter(id=deal.id).update(
            created_at=timezone.now() - timedelta(days=created_days_ago)
        )
        deal.refresh_from_db()
        return deal

    def _make_aux_auction(self, address: str, broker):
        prop = self.create_property(self.dev1, address=address)
        auction = self.create_auction(
            owner=self.dev1,
            prop=prop,
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() - timedelta(days=8),
            min_bid_increment=Decimal("150000.00"),
        )
        bid = self.create_bid(
            auction=auction,
            broker=broker,
            amount=Decimal("2000.00"),
            is_sealed=False,
        )
        return auction, bid, prop

    def test_marks_stale_pending_deal_as_failed(self):
        deal = self._create_deal(created_days_ago=6)

        result = mark_failed_pending_deals.run()

        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.FAILED)
        self.assertEqual(deal.obligation_status, Deal.ObligationStatus.OVERDUE)
        self.assertEqual(result["marked_failed"], 1)
        self.assertEqual(result["threshold_days"], 5)

    def test_does_not_touch_fresh_pending_deal(self):
        deal = self._create_deal(created_days_ago=2)

        result = mark_failed_pending_deals.run()

        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.PENDING_DOCUMENTS)
        self.assertEqual(result["marked_failed"], 0)

    def test_does_not_touch_non_pending_deal(self):
        deal = self._create_deal(created_days_ago=30, status=Deal.Status.ADMIN_REVIEW)

        mark_failed_pending_deals.run()

        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.ADMIN_REVIEW)

    def test_creates_marked_failed_deal_log(self):
        deal = self._create_deal(created_days_ago=10)

        mark_failed_pending_deals.run()

        log = DealLog.objects.get(deal=deal, action=DealLog.Action.MARKED_FAILED)
        self.assertIn("5", log.detail)

    def test_sends_deal_failed_notifications(self):
        deal = self._create_deal(created_days_ago=10)

        with self.captureOnCommitCallbacks(execute=True):
            mark_failed_pending_deals.run()

        notifs = Notification.objects.filter(
            deal=deal, event_type=NotificationEvent.DEAL_FAILED
        )
        recipients = set(notifs.values_list("user_id", flat=True))
        self.assertIn(self.broker1.id, recipients)
        self.assertIn(self.dev1.id, recipients)
        self.assertIn(self.admin.id, recipients)

    def test_is_idempotent_second_run_does_nothing(self):
        self._create_deal(created_days_ago=10)

        first = mark_failed_pending_deals.run()
        second = mark_failed_pending_deals.run()

        self.assertEqual(first["marked_failed"], 1)
        self.assertEqual(second["marked_failed"], 0)
        self.assertEqual(
            DealLog.objects.filter(action=DealLog.Action.MARKED_FAILED).count(), 1
        )

    @override_settings(DEAL_PENDING_DOCUMENTS_FAIL_DAYS=2)
    def test_threshold_is_configurable(self):
        deal = self._create_deal(created_days_ago=3)

        result = mark_failed_pending_deals.run()

        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.FAILED)
        self.assertEqual(result["threshold_days"], 2)

    def test_handles_mixed_deals_correctly(self):
        stale = self._create_deal(created_days_ago=10)

        fresh_auc, fresh_bid, fresh_prop = self._make_aux_auction(
            "Fresh prop", self.broker2
        )
        fresh = self._create_deal(
            created_days_ago=1,
            auction=fresh_auc,
            bid=fresh_bid,
            prop=fresh_prop,
            broker=self.broker2,
        )

        conf_auc, conf_bid, conf_prop = self._make_aux_auction(
            "Conf prop", self.broker2
        )
        confirmed = self._create_deal(
            created_days_ago=30,
            status=Deal.Status.CONFIRMED,
            auction=conf_auc,
            bid=conf_bid,
            prop=conf_prop,
            broker=self.broker2,
        )

        result = mark_failed_pending_deals.run()

        stale.refresh_from_db()
        fresh.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(stale.status, Deal.Status.FAILED)
        self.assertEqual(fresh.status, Deal.Status.PENDING_DOCUMENTS)
        self.assertEqual(confirmed.status, Deal.Status.CONFIRMED)
        self.assertEqual(result["marked_failed"], 1)

    @patch("notifications.services.notify_deal_failed")
    def test_notify_called_with_correct_kwargs(self, notify_mock):
        deal = self._create_deal(created_days_ago=10)

        with self.captureOnCommitCallbacks(execute=True):
            mark_failed_pending_deals.run()

        notify_mock.assert_called_once()
        _, kwargs = notify_mock.call_args
        self.assertEqual(kwargs["deal"].id, deal.id)
        self.assertGreaterEqual(kwargs["days_in_pending"], 5)
