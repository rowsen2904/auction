from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker

User = get_user_model()

VERIFY_URL = "/api/v1/admin/broker/verify/"


class TestBrokerVerificationEndpoint(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

        self.broker_user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
            inn_number="7707083893",
        )

        self.broker = Broker.objects.create(
            user=self.broker_user,
            verification_status=Broker.VerificationStatuses.PENDING,
            is_verified=False,
            verified_at=None,
            rejected_at=None,
        )

    def test_admin_can_accept_broker(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)

        self.broker.refresh_from_db()
        self.assertEqual(
            self.broker.verification_status,
            Broker.VerificationStatuses.ACCEPTED,
        )
        self.assertTrue(self.broker.is_verified)
        self.assertIsNotNone(self.broker.verified_at)
        self.assertIsNone(self.broker.rejected_at)

    def test_admin_can_reject_broker(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "reject"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)

        self.broker.refresh_from_db()
        self.assertEqual(
            self.broker.verification_status,
            Broker.VerificationStatuses.REJECTED,
        )
        self.assertFalse(self.broker.is_verified)
        self.assertIsNotNone(self.broker.rejected_at)
        self.assertIsNone(self.broker.verified_at)

    def test_non_admin_gets_403(self):
        self.client.force_authenticate(user=self.broker_user)

        resp = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_action_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_user_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(
            VERIFY_URL,
            data={"id": 999999, "action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_role_not_broker_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        dev = User.objects.create_user(
            email="dev@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )

        resp = self.client.post(
            VERIFY_URL,
            data={"id": dev.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_broker_role_but_profile_missing_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        user = User.objects.create_user(
            email="broker2@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
            inn_number="123456789012",
        )

        resp = self.client.post(
            VERIFY_URL,
            data={"id": user.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_is_idempotent(self):
        self.client.force_authenticate(user=self.admin)

        r1 = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        first_verified_at = self.broker.verified_at

        r2 = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "accept"},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(
            self.broker.verification_status,
            Broker.VerificationStatuses.ACCEPTED,
        )
        self.assertTrue(self.broker.is_verified)
        self.assertEqual(self.broker.verified_at, first_verified_at)
        self.assertIsNone(self.broker.rejected_at)

    def test_reject_is_idempotent(self):
        self.client.force_authenticate(user=self.admin)

        r1 = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "reject"},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        first_rejected_at = self.broker.rejected_at

        r2 = self.client.post(
            VERIFY_URL,
            data={"id": self.broker_user.id, "action": "reject"},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(
            self.broker.verification_status,
            Broker.VerificationStatuses.REJECTED,
        )
        self.assertFalse(self.broker.is_verified)
        self.assertEqual(self.broker.rejected_at, first_rejected_at)
        self.assertIsNone(self.broker.verified_at)
