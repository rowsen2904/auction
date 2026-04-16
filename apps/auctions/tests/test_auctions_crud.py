from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction
from django.utils import timezone
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestAuctionsCRUD(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")
        self.prop2 = self.create_property(self.dev2, address="Dev2 Property B")

        self.prop1.moderation_status = Property.ModerationStatuses.APPROVED
        self.prop1.save(update_fields=["moderation_status"])

    def test_create_requires_auth(self):
        now = timezone.now()
        resp = self.client.post(
            self.BASE,
            data={
                "propertyId": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "min_bid_increment": "150000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_developer(self):
        self.client.force_authenticate(user=self.broker1)
        now = timezone.now()
        resp = self.client.post(
            self.BASE,
            data={
                "propertyId": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "min_bid_increment": "150000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_denies_stranger_property(self):
        self.client.force_authenticate(user=self.dev2)
        now = timezone.now()
        resp = self.client.post(
            self.BASE,
            data={
                "propertyId": self.prop1.id,  # belongs to dev1
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "min_bid_increment": "150000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propertyIds", resp.data)

    def test_detail_open_bids_public(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        from auctions.models import Bid

        Bid.objects.create(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=False
        )

        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["bids"]), 1)

    def test_detail_exposes_owner_decision_fields(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.FINISHED,
            start=now - timedelta(hours=2),
            end=now - timedelta(minutes=1),
        )

        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("owner_decision", resp.data)
        self.assertIn("owner_rejection_reason", resp.data)
        self.assertIn("owner_decided_at", resp.data)
        self.assertEqual(resp.data["owner_decision"], Auction.OwnerDecision.PENDING)
        self.assertEqual(resp.data["owner_rejection_reason"], "")
        self.assertIsNone(resp.data["owner_decided_at"])

    def test_detail_closed_bids_hidden_for_non_owner(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        from auctions.models import Bid

        Bid.objects.create(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=True
        )

        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["bids"]), 0)

        self.client.force_authenticate(user=self.dev2)
        resp2 = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.data["bids"]), 0)

    def test_detail_closed_bids_visible_for_owner(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        from auctions.models import Bid

        Bid.objects.create(
            auction=auc, broker=self.broker1, amount=Decimal("1500.00"), is_sealed=True
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["bids"]), 1)

    def test_detail_closed_properties_hide_price_for_broker_when_disabled(self):
        self.prop1.show_price_to_brokers = False
        self.prop1.save(update_fields=["show_price_to_brokers"])

        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["properties"][0]["id"], self.prop1.id)
        self.assertIsNone(resp.data["properties"][0]["price"])

    def test_detail_closed_properties_price_visible_for_developer_when_disabled(self):
        self.prop1.show_price_to_brokers = False
        self.prop1.save(update_fields=["show_price_to_brokers"])

        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["properties"][0]["id"], self.prop1.id)
        self.assertEqual(resp.data["properties"][0]["price"], "1000000.00")

    def test_detail_closed_hides_summary_for_broker_but_keeps_my_bid(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
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
        auc.save(update_fields=["bids_count", "current_price", "updated_at"])

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.get(f"{self.BASE}{auc.id}/", format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["min_price"])
        self.assertIsNone(resp.data["current_price"])
        self.assertIsNone(resp.data["bids_count"])
        self.assertIsNotNone(resp.data["myBid"])
        self.assertEqual(resp.data["myBid"]["id"], bid.id)
        self.assertEqual(resp.data["myBid"]["amount"], "1500.00")

    def test_list_closed_hides_summary_for_broker(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
            min_price=Decimal("2000.00"),
        )
        auc.bids_count = 3
        auc.current_price = Decimal("2750.00")
        auc.save(update_fields=["bids_count", "current_price", "updated_at"])

        self.client.force_authenticate(user=self.broker1)
        resp = self.client.get(self.BASE, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item = next(x for x in resp.data["results"] if x["id"] == auc.id)
        self.assertIsNone(item["min_price"])
        self.assertIsNone(item["current_price"])
        self.assertIsNone(item["bids_count"])

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_success_creates_scheduled_and_schedules(self, schedule_mock):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(days=1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                self.BASE,
                data={
                    "propertyId": self.prop1.id,
                    "mode": Auction.Mode.OPEN,
                    "min_price": "1000.00",
                    "min_bid_increment": "150000.00",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        auc = Auction.objects.get(id=resp.data["id"])
        self.assertEqual(auc.status, Auction.Status.SCHEDULED)
        self.assertEqual(resp.data["real_property"]["id"], self.prop1.id)
        self.assertEqual(resp.data["real_property"]["address"], self.prop1.address)

        schedule_mock.assert_called_once()
        _, kwargs = schedule_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["start_date"], auc.start_date)
        self.assertEqual(kwargs["end_date"], auc.end_date)

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_denies_unapproved_property(self, schedule_mock):
        self.client.force_authenticate(user=self.dev1)
        self.prop1.moderation_status = Property.ModerationStatuses.PENDING
        self.prop1.save(update_fields=["moderation_status"])

        now = timezone.now()
        resp = self.client.post(
            self.BASE,
            data={
                "propertyId": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "min_bid_increment": "150000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propertyIds", resp.data)
        self.assertIn("не одобрена", resp.data["propertyIds"][0].lower())

        schedule_mock.assert_not_called()

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_denies_second_auction_for_same_property(self, schedule_mock):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        with self.captureOnCommitCallbacks(execute=True):
            first_resp = self.client.post(
                self.BASE,
                data={
                    "propertyId": self.prop1.id,
                    "mode": Auction.Mode.OPEN,
                    "min_price": "1000.00",
                    "min_bid_increment": "150000.00",
                    "start_date": (now + timedelta(hours=2)).isoformat(),
                    "end_date": (now + timedelta(days=1)).isoformat(),
                },
                format="json",
            )

        self.assertEqual(first_resp.status_code, status.HTTP_201_CREATED)

        second_resp = self.client.post(
            self.BASE,
            data={
                "propertyId": self.prop1.id,
                "mode": Auction.Mode.CLOSED,
                "min_price": "2000.00",
                "start_date": (now + timedelta(days=2)).isoformat(),
                "end_date": (now + timedelta(days=3)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(second_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propertyIds", second_resp.data)
        self.assertIn("связаны с аукционом", second_resp.data["propertyIds"][0].lower())
        self.assertEqual(
            Auction.objects.filter(real_property_id=self.prop1.id).count(),
            1,
        )
        self.assertEqual(schedule_mock.call_count, 1)
