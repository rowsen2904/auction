from __future__ import annotations

from datetime import timedelta

from auctions.models import Auction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .mixins import AuctionTestMixin


class TestParticipantsAPI(APITestCase, AuctionTestMixin):
    def setUp(self):
        self.create_users()
        self.prop1 = self.create_property(self.dev1, address="Dev1 Property A")

    def test_join_endpoint_works(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.broker1)
        url = self.rev("auction-join", pk=auc.id)
        resp = self.client.post(url, format="json")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

    def test_participants_list_requires_auth(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        url = self.rev("auction-participants", pk=auc.id)
        resp = self.client.get(url, format="json")
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

        self.client.force_authenticate(user=self.broker1)
        resp2 = self.client.get(url, format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertIn("participants", resp2.data)
        self.assertIsInstance(resp2.data["participants"], list)

    def test_join_endpoint_is_idempotent_for_same_user(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.OPEN,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.broker1)
        url = self.rev("auction-join", pk=auc.id)

        r1 = self.client.post(url, format="json")
        r2 = self.client.post(url, format="json")

        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        resp = self.client.get(
            self.rev("auction-participants", pk=auc.id), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["participants"].count(self.broker1.id), 1)

    def test_closed_participants_list_forbidden_for_non_owner_non_admin(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.broker1)
        url = self.rev("auction-participants", pk=auc.id)
        resp = self.client.get(url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_closed_participants_list_allowed_for_owner(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.dev1)
        url = self.rev("auction-participants", pk=auc.id)
        resp = self.client.get(url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("participants", resp.data)

    def test_closed_participants_list_allowed_for_admin(self):
        now = timezone.now()
        auc = self.create_auction(
            owner=self.dev1,
            prop=self.prop1,
            mode=Auction.Mode.CLOSED,
            status_val=Auction.Status.ACTIVE,
            start=now - timedelta(minutes=1),
            end=now + timedelta(hours=1),
        )

        self.client.force_authenticate(user=self.admin)
        url = self.rev("auction-participants", pk=auc.id)
        resp = self.client.get(url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("participants", resp.data)
