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
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
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
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
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
                "property_id": self.prop1.id,  # belongs to dev1
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

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

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_success_creates_draft_and_schedules(self, schedule_mock):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(days=1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                self.BASE,
                data={
                    "property_id": self.prop1.id,
                    "mode": Auction.Mode.OPEN,
                    "min_price": "1000.00",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        auc = Auction.objects.get(id=resp.data["id"])
        self.assertEqual(auc.status, Auction.Status.DRAFT)
        self.assertEqual(resp.data["property_id"], self.prop1.id)

        schedule_mock.assert_called_once()
        _, kwargs = schedule_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["start_date"], auc.start_date)
        self.assertEqual(kwargs["end_date"], auc.end_date)

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_denies_unapproved_property(self, schedule_mock):
        self.client.force_authenticate(user=self.dev1)
        self.prop1.moderation_status = Property.ModerationStatuses.IN_REVIEW
        self.prop1.save(update_fields=["moderation_status"])

        now = timezone.now()
        resp = self.client.post(
            self.BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("real_property", resp.data)
        self.assertIn("approved", resp.data["real_property"][0].lower())

        schedule_mock.assert_not_called()
