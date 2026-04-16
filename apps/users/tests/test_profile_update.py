from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker, Developer

from .test_auth_flow import make_inn12

User = get_user_model()

ME_URL = "/api/v1/auth/me/"


class MePatchTests(APITestCase):
    def setUp(self):
        self.broker_user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            first_name="Old",
            last_name="Name",
            is_active=True,
            inn_number=make_inn12("7721581040"),
        )
        self.broker = Broker.objects.create(
            user=self.broker_user,
            phone_number="+70000000001",
            is_verified=True,
            verification_status=Broker.VerificationStatuses.ACCEPTED,
            verified_at=timezone.now(),
        )

        self.developer_user = User.objects.create_user(
            email="dev@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.developer = Developer.objects.create(
            user=self.developer_user, company_name="Old Co"
        )

        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

    def test_requires_auth(self):
        resp = self.client.patch(ME_URL, {"first_name": "X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_payload_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(ME_URL, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_broker_can_update_name_and_phone(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(
            ME_URL,
            {"first_name": "New", "last_name": "Name", "phone_number": "+70000000009"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker_user.refresh_from_db()
        self.broker.refresh_from_db()
        self.assertEqual(self.broker_user.first_name, "New")
        self.assertEqual(self.broker.phone_number, "+70000000009")

    def test_broker_can_update_inn(self):
        self.client.force_authenticate(user=self.broker_user)
        new_inn = make_inn12("7721581041")
        resp = self.client.patch(
            ME_URL,
            {"inn_number": new_inn},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.broker_user.refresh_from_db()
        self.assertEqual(self.broker_user.inn_number, new_inn)

    def test_broker_invalid_inn_rejected(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(ME_URL, {"inn_number": "123"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_uniqueness(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(
            ME_URL, {"email": self.developer_user.email}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_developer_can_update_company(self):
        self.client.force_authenticate(user=self.developer_user)
        resp = self.client.patch(ME_URL, {"company_name": "New Co"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.developer.refresh_from_db()
        self.assertEqual(self.developer.company_name, "New Co")

    def test_developer_phone_is_ignored(self):
        self.client.force_authenticate(user=self.developer_user)
        resp = self.client.patch(
            ME_URL,
            {"first_name": "Bob", "phone_number": "+1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.developer_user.refresh_from_db()
        self.assertEqual(self.developer_user.first_name, "Bob")

    def test_admin_can_update_name(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.patch(ME_URL, {"first_name": "Root"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.first_name, "Root")

    def test_me_patch_cannot_change_is_active(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(ME_URL, {"is_active": False}, format="json")
        # field is not in UserProfileUpdateSerializer for self-update -> ignored;
        # since it's the only field, validator requires at least one valid field
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.broker_user.refresh_from_db()
        self.assertTrue(self.broker_user.is_active)

    def test_inactive_user_forbidden(self):
        self.broker_user.is_active = False
        self.broker_user.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(ME_URL, {"first_name": "x"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
