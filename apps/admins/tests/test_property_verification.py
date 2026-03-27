from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

APPROVE_URL_TEMPLATE = "/api/v1/admin/properties/{pk}/approve/"
REJECT_URL_TEMPLATE = "/api/v1/admin/properties/{pk}/reject/"


class TestPropertyModerationEndpoint(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

        self.developer = User.objects.create_user(
            email="developer@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )

        self.property = Property.objects.create(
            owner=self.developer,
            type=Property.PropertyTypes.APARTMENT,
            address="Ashgabat, Mir 10",
            area=Decimal("85.50"),
            property_class=Property.PropertyClasses.COMFORT,
            price=Decimal("1500000.00"),
            deadline=date(2026, 12, 31),
            status=Property.PropertyStatuses.PUBLISHED,
            moderation_status=Property.ModerationStatuses.PENDING,
            moderation_rejection_reason=None,
        )

    def approve_url(self, pk=None):
        return APPROVE_URL_TEMPLATE.format(pk=pk or self.property.pk)

    def reject_url(self, pk=None):
        return REJECT_URL_TEMPLATE.format(pk=pk or self.property.pk)

    def test_admin_can_approve_property(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(self.approve_url(), data={}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["property_id"], self.property.id)
        self.assertEqual(
            resp.data["moderation_status"],
            Property.ModerationStatuses.APPROVED,
        )
        self.assertIsNone(resp.data["moderation_rejection_reason"])

        self.property.refresh_from_db()
        self.assertEqual(
            self.property.moderation_status,
            Property.ModerationStatuses.APPROVED,
        )
        self.assertIsNone(self.property.moderation_rejection_reason)

    def test_admin_can_reject_property_with_reason(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self.reject_url(),
            data={"reason": "Not enough documents for moderation."},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["property_id"], self.property.id)
        self.assertEqual(
            resp.data["moderation_status"],
            Property.ModerationStatuses.REJECTED,
        )
        self.assertEqual(
            resp.data["moderation_rejection_reason"],
            "Not enough documents for moderation.",
        )

        self.property.refresh_from_db()
        self.assertEqual(
            self.property.moderation_status,
            Property.ModerationStatuses.REJECTED,
        )
        self.assertEqual(
            self.property.moderation_rejection_reason,
            "Not enough documents for moderation.",
        )

    def test_reject_without_reason_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self.reject_url(),
            data={},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", resp.data)

    def test_reject_with_blank_reason_returns_400(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self.reject_url(),
            data={"reason": ""},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", resp.data)

    def test_approve_clears_old_rejection_reason(self):
        self.property.moderation_status = Property.ModerationStatuses.REJECTED
        self.property.moderation_rejection_reason = "Old rejection reason"
        self.property.save(
            update_fields=[
                "moderation_status",
                "moderation_rejection_reason",
                "updated_at",
            ]
        )

        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(self.approve_url(), data={}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.data["moderation_status"],
            Property.ModerationStatuses.APPROVED,
        )
        self.assertIsNone(resp.data["moderation_rejection_reason"])

        self.property.refresh_from_db()
        self.assertEqual(
            self.property.moderation_status,
            Property.ModerationStatuses.APPROVED,
        )
        self.assertIsNone(self.property.moderation_rejection_reason)

    def test_non_admin_cannot_approve_property(self):
        self.client.force_authenticate(user=self.developer)

        resp = self.client.patch(self.approve_url(), data={}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_reject_property(self):
        self.client.force_authenticate(user=self.developer)

        resp = self.client.patch(
            self.reject_url(),
            data={"reason": "Reason"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_unknown_property_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self.approve_url(pk=999999),
            data={},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_reject_unknown_property_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(
            self.reject_url(pk=999999),
            data={"reason": "Reason"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_keeps_approved_state_on_repeat(self):
        self.client.force_authenticate(user=self.admin)

        r1 = self.client.patch(self.approve_url(), data={}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.patch(self.approve_url(), data={}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        self.property.refresh_from_db()
        self.assertEqual(
            self.property.moderation_status,
            Property.ModerationStatuses.APPROVED,
        )
        self.assertIsNone(self.property.moderation_rejection_reason)

    def test_reject_keeps_rejected_state_on_repeat(self):
        self.client.force_authenticate(user=self.admin)

        r1 = self.client.patch(
            self.reject_url(),
            data={"reason": "Duplicate content."},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.patch(
            self.reject_url(),
            data={"reason": "Duplicate content."},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        self.property.refresh_from_db()
        self.assertEqual(
            self.property.moderation_status,
            Property.ModerationStatuses.REJECTED,
        )
        self.assertEqual(
            self.property.moderation_rejection_reason,
            "Duplicate content.",
        )
