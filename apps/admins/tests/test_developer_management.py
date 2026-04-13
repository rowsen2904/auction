from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Developer

User = get_user_model()

CREATE_URL = "/api/v1/admin/developers/"
UPDATE_URL_TEMPLATE = "/api/v1/admin/developers/{pk}/"


class TestAdminDeveloperManagement(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin-dev@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

        self.existing_developer_user = User.objects.create_user(
            email="existing-dev@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.existing_developer = Developer.objects.create(
            user=self.existing_developer_user,
            company_name="Existing Company",
        )

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
        )

    def _update_url(self, pk: int) -> str:
        return UPDATE_URL_TEMPLATE.format(pk=pk)

    def test_admin_can_create_developer(self):
        self.client.force_authenticate(user=self.admin)

        payload = {
            "email": "new-dev@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "first_name": "New",
            "last_name": "Developer",
            "company_name": "New Company",
        }
        resp = self.client.post(CREATE_URL, data=payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", resp.data)
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["email"], "new-dev@example.com")
        self.assertEqual(resp.data["user"]["role"], User.Roles.DEVELOPER)
        self.assertIsNotNone(resp.data["user"]["developer"])
        self.assertEqual(
            resp.data["user"]["developer"]["company_name"],
            "New Company",
        )
        self.assertIsNone(resp.data["user"]["broker"])

        created_user = User.objects.get(email="new-dev@example.com")
        self.assertEqual(created_user.role, User.Roles.DEVELOPER)
        self.assertTrue(Developer.objects.filter(user=created_user).exists())
        self.assertEqual(created_user.developer.company_name, "New Company")

    def test_non_admin_cannot_create_developer(self):
        self.client.force_authenticate(user=self.existing_developer_user)

        resp = self.client.post(
            CREATE_URL,
            data={
                "email": "forbidden-dev@example.com",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "company_name": "Forbidden Company",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_developer_duplicate_email_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(
            CREATE_URL,
            data={
                "email": self.existing_developer_user.email,
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "company_name": "Duplicate Company",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)

    def test_admin_can_update_developer(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self._update_url(self.existing_developer_user.id),
            data={
                "email": "updated-dev@example.com",
                "first_name": "Updated",
                "last_name": "Name",
                "company_name": "Updated Company",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["user"]["email"], "updated-dev@example.com")
        self.assertEqual(
            resp.data["user"]["developer"]["company_name"],
            "Updated Company",
        )

        self.existing_developer_user.refresh_from_db()
        self.existing_developer.refresh_from_db()
        self.assertEqual(
            self.existing_developer_user.email,
            "updated-dev@example.com",
        )
        self.assertEqual(self.existing_developer_user.first_name, "Updated")
        self.assertEqual(self.existing_developer_user.last_name, "Name")
        self.assertEqual(self.existing_developer.company_name, "Updated Company")

    def test_update_developer_without_fields_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self._update_url(self.existing_developer_user.id),
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", resp.data)

    def test_update_unknown_developer_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self._update_url(999999),
            data={"company_name": "Unknown"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_non_developer_user_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self._update_url(self.other_user.id),
            data={"company_name": "Should Not Work"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_cannot_update_developer(self):
        self.client.force_authenticate(user=self.existing_developer_user)

        resp = self.client.patch(
            self._update_url(self.existing_developer_user.id),
            data={"company_name": "Forbidden Update"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
