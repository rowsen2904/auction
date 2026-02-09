from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from auctions.models import Auction, Bid
from django.contrib.auth import get_user_model
from django.utils import timezone
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

BASE = "/api/v1/auctions/"
MY_BASE = "/api/v1/auctions/my/"
CANCEL_SUFFIX = "/cancel/"


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
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
            is_staff=True,
            is_superuser=True,
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
        start_dt = start or (now + timedelta(hours=2))
        end_dt = end or (now + timedelta(days=1))

        return Auction.objects.create(
            owner=owner,
            real_property=prop,
            mode=mode,
            min_price=min_price,
            start_date=start_dt,
            end_date=end_dt,
            status=status_val,
            current_price=current_price,
        )

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
                "start_date": (now + timedelta(hours=2)).isoformat(),
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
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_auction_denies_creating_for_stranger_property(self):
        self.client.force_authenticate(user=self.dev2)
        now = timezone.now()

        resp = self.client.post(
            BASE,
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

    def test_create_auction_validates_start_must_be_at_least_1_hour_from_now(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        # 30 minutes from now -> should fail
        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(minutes=30)).isoformat(),
                "end_date": (now + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_auction_validates_end_must_be_after_start(self):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()

        resp = self.client.post(
            BASE,
            data={
                "property_id": self.prop1.id,
                "mode": Auction.Mode.OPEN,
                "min_price": "1000.00",
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now + timedelta(hours=1)).isoformat(),
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
                "start_date": (now + timedelta(hours=2)).isoformat(),
                "end_date": (now - timedelta(minutes=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("auctions.serializers.schedule_auction_status_tasks")
    def test_create_auction_success_creates_draft_and_schedules_tasks(
        self, schedule_mock
    ):
        self.client.force_authenticate(user=self.dev1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(days=1)

        # In TestCase/APITestCase, on_commit callbacks won't run unless captured.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                BASE,
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
        self.assertEqual(auc.owner_id, self.dev1.id)
        self.assertEqual(auc.status, Auction.Status.DRAFT)

        # Ensure serializer output uses "property_id" alias
        self.assertEqual(resp.data["property_id"], self.prop1.id)

        # Ensure scheduling called after commit
        schedule_mock.assert_called_once()
        _, kwargs = schedule_mock.call_args
        self.assertEqual(kwargs["auction_id"], auc.id)
        self.assertEqual(kwargs["start_date"], auc.start_date)
        self.assertEqual(kwargs["end_date"], auc.end_date)

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
                start=now + timedelta(hours=2),
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
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        self._create_auction(
            owner=self.dev2,
            prop=self.prop2,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(
            f"{BASE}?property_id={self.prop1.id}&owner_id={self.dev1.id}",
            format="json",
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

    def test_list_filters_by_ends_before_and_starts_after(self):
        now = timezone.now()

        # Should match ends_before
        a1 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=2),
            end=now + timedelta(hours=5),
        )
        # Should NOT match ends_before (ends too late)
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=2),
        )

        ends_before = (now + timedelta(hours=6)).isoformat()
        resp = self.client.get(BASE, data={"ends_before": ends_before}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertIn(a1.id, ids)

        # starts_after should return only those starting after threshold
        early = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=10),
        )
        late = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=10),
            end=now + timedelta(hours=20),
        )

        starts_after = (now + timedelta(hours=2)).isoformat()
        resp2 = self.client.get(
            BASE, data={"starts_after": starts_after}, format="json"
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        ids2 = [row["id"] for row in resp2.data["results"]]
        self.assertIn(late.id, ids2)
        self.assertNotIn(early.id, ids2)

    def test_list_ordering_works(self):
        now = timezone.now()
        a1 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            current_price=Decimal("5000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        a2 = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            current_price=Decimal("2000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        resp = self.client.get(f"{BASE}?ordering=-current_price", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        ids = [row["id"] for row in resp.data["results"]]
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
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        self._create_auction(
            owner=self.dev2,
            prop=self.prop2,
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(MY_BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in resp.data["results"]]
        self.assertIn(a1.id, ids)
        self.assertEqual(resp.data["count"], 1)

    def test_my_auctions_supports_filters_and_ordering(self):
        now = timezone.now()

        # dev1 owns both, but filter should return only CLOSED
        self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            current_price=Decimal("1000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )
        closed = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            current_price=Decimal("5000.00"),
            start=now + timedelta(hours=2),
            end=now + timedelta(days=1),
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.get(
            f"{MY_BASE}?mode=closed&ordering=-current_price", format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], closed.id)

    # -------------------------
    # CANCEL (DELETE /auctions/:id/cancel/)
    # -------------------------

    def test_cancel_requires_auth(self):
        auc = self._create_auction(owner=self.dev1, prop=self.prop1)
        resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cancel_requires_owner_or_admin(self):
        auc = self._create_auction(owner=self.dev1, prop=self.prop1)

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch("auctions.views.cancel_auction_status_tasks")
    def test_cancel_owner_success_far_from_start(self, cancel_tasks_mock):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=5),
            end=now + timedelta(days=1),
            status_val=Auction.Status.DRAFT,
        )

        self.client.force_authenticate(user=self.dev1)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.CANCELLED)

        cancel_tasks_mock.assert_called_once_with(auction_id=auc.id)

    def test_cancel_within_10_minutes_only_admin_can_cancel(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(minutes=5),
            end=now + timedelta(hours=2),
            status_val=Auction.Status.DRAFT,
        )

        # Owner is NOT admin -> forbidden
        self.client.force_authenticate(user=self.dev1)
        resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Admin can cancel
        self.client.force_authenticate(user=self.admin)
        resp2 = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp2.status_code, status.HTTP_204_NO_CONTENT)

        auc.refresh_from_db()
        self.assertEqual(auc.status, Auction.Status.CANCELLED)

    def test_cancel_after_start_is_forbidden_for_everyone(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=2),
            status_val=Auction.Status.ACTIVE,
        )

        # Even admin cannot cancel after start
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_already_cancelled_returns_404(self):
        now = timezone.now()
        auc = self._create_auction(
            owner=self.dev1,
            prop=self.prop1,
            start=now + timedelta(hours=5),
            end=now + timedelta(days=1),
            status_val=Auction.Status.CANCELLED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.delete(f"{BASE}{auc.id}{CANCEL_SUFFIX}", format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
