from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestAuctionsFilters(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")
        self.prop2 = self.create_property(self.dev2, address="Dev2 Property B")

    def make_property(self, owner, suffix: str):
        return self.create_property(owner, address=f"{owner.email} Property {suffix}")

    def test_list_paginated(self):
        now = timezone.now()
        for i in range(21):
            prop = self.make_property(self.dev1, f"paginated-{i}")
            self.create_auction(
                owner=self.dev1,
                prop=prop,
                mode=Auction.Mode.OPEN,
                min_bid_increment=Decimal("150000.00"),
                status_val=Auction.Status.SCHEDULED,
                start=now + timedelta(hours=2),
                end=now + timedelta(days=1),
            )

        resp = self.client.get(self.BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 21)
        self.assertEqual(len(resp.data["results"]), 20)

    def test_list_filters_mode_status(self):
        now = timezone.now()
        open_prop = self.make_property(self.dev1, "open-active")
        closed_prop = self.make_property(self.dev1, "closed-active")

        self.create_auction(
            owner=self.dev1,
            prop=open_prop,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )
        self.create_auction(
            owner=self.dev1,
            prop=closed_prop,
            mode=Auction.Mode.CLOSED,
            min_bid_increment=Decimal("150000.00"),
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        resp = self.client.get(f"{self.BASE}?mode=open&status=active", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["mode"], Auction.Mode.OPEN)

    def test_list_filters_property_and_owner(self):
        now = timezone.now()
        a1 = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        self.create_auction(
            owner=self.dev2,
            prop=self.prop2,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(
            f"{self.BASE}?property_id={self.prop1.id}&owner_id={self.dev1.id}",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], a1.id)

    def test_list_active_true(self):
        now = timezone.now()

        active_prop = self.make_property(self.dev1, "active-now")
        scheduled_prop = self.make_property(self.dev1, "scheduled-now")
        finished_window_prop = self.make_property(self.dev1, "active-old")

        active = self.create_auction(
            owner=self.dev1,
            prop=active_prop,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=10),
        )
        self.create_auction(
            owner=self.dev1,
            prop=scheduled_prop,
            status_val=Auction.Status.SCHEDULED,
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=10),
        )
        self.create_auction(
            owner=self.dev1,
            prop=finished_window_prop,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(days=2),
            end=now - timedelta(days=1),
        )

        resp = self.client.get(f"{self.BASE}?active=true", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], active.id)

    def test_list_starts_after_ends_before(self):
        now = timezone.now()

        prop1 = self.make_property(self.dev1, "ends-before-1")
        prop2 = self.make_property(self.dev1, "ends-before-2")

        a1 = self.create_auction(
            owner=self.dev1,
            prop=prop1,
            start=now + timedelta(hours=2),
            end=now + timedelta(hours=5),
        )
        self.create_auction(
            owner=self.dev1,
            prop=prop2,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=2),
        )

        resp = self.client.get(
            self.BASE,
            data={"ends_before": (now + timedelta(hours=6)).isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertIn(a1.id, ids)

        early_prop = self.make_property(self.dev1, "starts-after-early")
        late_prop = self.make_property(self.dev1, "starts-after-late")

        early = self.create_auction(
            owner=self.dev1,
            prop=early_prop,
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=10),
        )
        late = self.create_auction(
            owner=self.dev1,
            prop=late_prop,
            start=now + timedelta(hours=10),
            end=now + timedelta(hours=20),
        )

        resp2 = self.client.get(
            self.BASE,
            data={"starts_after": (now + timedelta(hours=2)).isoformat()},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        ids2 = [row["id"] for row in resp2.data["results"]]
        self.assertIn(late.id, ids2)
        self.assertNotIn(early.id, ids2)

    def test_list_ordering(self):
        now = timezone.now()

        prop1 = self.make_property(self.dev1, "ordering-1")
        prop2 = self.make_property(self.dev1, "ordering-2")

        a1 = self.create_auction(
            owner=self.dev1,
            prop=prop1,
            current_price=Decimal("5000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        a2 = self.create_auction(
            owner=self.dev1,
            prop=prop2,
            current_price=Decimal("2000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(f"{self.BASE}?ordering=-current_price", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertTrue(ids.index(a1.id) < ids.index(a2.id))
