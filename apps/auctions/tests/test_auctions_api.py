from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction, Bid
from django.contrib.auth import get_user_model
from django.utils import timezone
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

BASE = "/api/v1/auctions/"
MY_BASE = "/api/v1/auctions/my/"


class AuctionAPITests(APITestCase):
    def setUp(self):
        self.dev1 = User.objects.create_user(
            email="dev1@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.dev2 = User.objects.create_user(
            email="dev2@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.broker = User.objects.create_user(
            email="broker@test.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
        )

        self.prop1 = self._create_property(self.dev1, address="Dev1 Property A")
        self.prop2 = self._create_property(self.dev2, address="Dev2 Property B")

    def _create_property(
        self,
        owner: User,
        *,
        address: str,
        p_type: str = "apartment",
        p_class: str = "comfort",
        area: Decimal = Decimal("50.00"),
        price: Decimal = Decimal("1000000.00"),
        status_val: str = "published",
    ) -> Property:
        return Property.objects.create(
            owner=owner,
            type=p_type,
            address=address,
            area=area,
            property_class=p_class,
            price=price,
            currency="RUB",
            status=status_val,
        )

    def _create_auction(
        self,
        *,
        owner: User,
        prop: Property,
        mode: str = Auction.Mode.OPEN,
        status_val: str = Auction.Status.DRAFT,
        start: timezone.datetime | None = None,
        end: timezone.datetime | None = None,
        min_price: Decimal = Decimal("1000.00"),
        current_price: Decimal = Decimal("0.00"),
    ) -> Auction:
        now = timezone.now()
        start_dt = start or (now + timedelta(hours=1))
        end_dt = end or (now + timedelta(days=1))

        auc = Auction.objects.create(
            owner=owner,
            real_property=prop,
            mode=mode,
            min_price=min_price,
            start_date=start_dt,
            end_date=end_dt,
            status=status_val,
            current_price=current_price,
        )
        return auc

    # -------------------------
    # CREATE (POST /auctions/)
    # -------------------------

    def test_create_auction_requires_auth(self):
        now = timezone.now()
        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=1)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_auction_requires_developer(self):
        self.client.force_authenticate(user=self.broker)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=1)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_auction_denies_creating_for_stranger_property(self):
        # dev2 tries to create auction on dev1 property -> should be 400 validation error
        self.client.force_authenticate(user=self.dev2)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,  # belongs to dev1
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=1)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_auction_validates_dates_end_must_be_after_start(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(days=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_auction_validates_end_must_be_in_future(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now - timedelta(days=2)).isoformat(),
                "end_date": (now - timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_auction_auto_sets_status_active_when_started(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now - timedelta(minutes=5)).isoformat(),
                "end_date": (now + timedelta(hours=3)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        auction_id = resp.data["id"]
        auc = Auction.objects.get(id=auction_id)
        self.assertEqual(auc.owner_id, self.dev1.id)
        self.assertEqual(auc.status, Auction.Status.ACTIVE)

    def test_create_auction_sets_status_draft_when_start_in_future(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        auc = Auction.objects.get(id=resp.data["id"])
        self.assertEqual(auc.status, Auction.Status.DRAFT)

    # -------------------------
    # LIST (GET /auctions/)
    # -------------------------

    def test_list_auctions_paginated(self):
        now = timezone.now()
        for i in range(21):
            self._create_auction(
                owner=self.dev1,
                prop=self.prop1,
                mode=Auction.Mode.OPEN,
                status_val=Auction.Status.DRAFT,
                start=now + timedelta(hours=1),
                end=now + timedelta(days=1),
                min_price=Decimal("1000.00"),
            )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 21)
        self.assertEqual(len(resp.data["results"]), 20)
        self.assertIsNotNone(resp.data["next"])

    def test_list_filters_by_mode_and_status(self):
        now = timezone.now()
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        resp = self.client.get(f"{BASE}?mode=open&status=active", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["mode"], Auction.Mode.OPEN)
        self.assertEqual(resp.data["results"][0]["status"], Auction.Status.ACTIVE)

    def test_list_filters_by_property_id_and_owner_id(self):
        now = timezone.now()
        a1 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )
        self._create_auction(
            owner=self.dev2,
            prop=self.prop2,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(
            f"{BASE}?property_id={self.prop1.id}&owner_id={self.dev1.id}", format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], a1.id)

    def test_list_filters_active_true_returns_only_active_now(self):
        now = timezone.now()

        active_auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=10),
        )
        # Not active: status draft
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            status_val=Auction.Status.DRAFT,
            start=now - timedelta(minutes=10),
            end=now + timedelta(minutes=10),
        )
        # Not active: time window passed
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(days=2),
            end=now - timedelta(days=1),
        )

        resp = self.client.get(f"{BASE}?active=true", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], active_auc.id)

    def test_list_ordering_works(self):
        now = timezone.now()
        a1 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            current_price=Decimal("5000.00"),
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )
        a2 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            current_price=Decimal("2000.00"),
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(f"{BASE}?ordering=-current_price", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        ids = [row["id"] for row in resp.data["results"]]
        # a1 should appear before a2 when ordering by -current_price
        self.assertTrue(ids.index(a1.id) < ids.index(a2.id))

    # -------------------------
    # DETAIL (GET /auctions/:id)
    # -------------------------

    def test_detail_open_auction_bids_are_public(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        Bid.objects.create(auction=auc, broker=self.broker, amount=Decimal("1500.00"))

        resp = self.client.get(f"{BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("bids", resp.data)
        self.assertEqual(len(resp.data["bids"]), 1)

    def test_detail_closed_auction_bids_hidden_for_non_owner(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        Bid.objects.create(auction=auc, broker=self.broker, amount=Decimal("1500.00"))

        # Anonymous request
        resp = self.client.get(f"{BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("bids", resp.data)
        self.assertEqual(len(resp.data["bids"]), 0)

        # Authenticated but not owner
        self.client.force_authenticate(user=self.dev2)
        resp2 = self.client.get(f"{BASE}{auc.id}/", format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.data["bids"]), 0)

    def test_detail_closed_auction_bids_visible_for_owner(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=5),
            end=now + timedelta(hours=1),
        )
        Bid.objects.create(auction=auc, broker=self.broker, amount=Decimal("1500.00"))

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(f"{BASE}{auc.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["bids"]), 1)

    # -------------------------
    # MY AUCTIONS (GET /auctions/my/)
    # -------------------------

    def test_my_auctions_requires_auth(self):
        resp = self.client.get(MY_BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_auctions_requires_developer(self):
        self.client.force_authenticate(user=self.broker)
        resp = self.client.get(MY_BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_auctions_returns_only_owner_auctions(self):
        now = timezone.now()
        a1 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )
        self._create_auction(
            owner=self.dev2,
            prop=self.prop2,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(MY_BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertIn(a1.id, ids)
        self.assertEqual(resp.data["count"], 1)

    def test_my_auctions_supports_filters(self):
        now = timezone.now()
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )
        closed = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            start=now + timedelta(hours=1),
            end=now + timedelta(days=1),
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(f"{MY_BASE}?mode=closed", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], closed.id)
