from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker, Developer
from apps.users.tests.test_auth_flow import make_inn12

User = get_user_model()


def _url(pk: int) -> str:
    return f"/api/v1/admin/users/{pk}/"


class AdminUserUpdateTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-u@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.other_admin = User.objects.create_user(
            email="admin2@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_staff=True,
            is_active=True,
        )
        self.broker_user = User.objects.create_user(
            email="br@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            first_name="BrokerFirst",
            is_active=True,
            inn_number=make_inn12("7721581040"),
        )
        self.broker = Broker.objects.create(
            user=self.broker_user,
            phone_number="+70000000002",
            is_verified=True,
            verification_status=Broker.VerificationStatuses.ACCEPTED,
            verified_at=timezone.now(),
        )
        self.developer_user = User.objects.create_user(
            email="dv@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.developer = Developer.objects.create(
            user=self.developer_user, company_name="Old Co"
        )

    def test_requires_admin(self):
        self.client.force_authenticate(user=self.broker_user)
        resp = self.client.patch(
            _url(self.developer_user.id),
            {"first_name": "X"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_updates_broker_profile(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.broker_user.id),
            {
                "first_name": "AdminChanged",
                "phone_number": "+79999999999",
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.broker_user.refresh_from_db()
        self.broker.refresh_from_db()
        self.assertEqual(self.broker_user.first_name, "AdminChanged")
        self.assertFalse(self.broker_user.is_active)
        self.assertEqual(self.broker.phone_number, "+79999999999")

    def test_admin_updates_developer_company(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.developer_user.id),
            {"company_name": "New Company"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.developer.refresh_from_db()
        self.assertEqual(self.developer.company_name, "New Company")

    def test_admin_cannot_deactivate_self(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.admin.id),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_deactivate_other_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.other_admin.id),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.other_admin.refresh_from_db()
        self.assertFalse(self.other_admin.is_active)

    def test_empty_payload_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.broker_user.id),
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_user_returns_404(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(999999),
            {"first_name": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_email_rejected(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            _url(self.broker_user.id),
            {"email": self.developer_user.email},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
