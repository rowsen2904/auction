from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import BytesIO
from PIL import Image
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

BASE = "/api/v1/properties/"


def make_png_file(name: str = "img.png") -> SimpleUploadedFile:
    buf = BytesIO()
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 0))
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(
        name=name,
        content=buf.read(),
        content_type="image/png",
    )


class BasePropertyTestCase(APITestCase):
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

    def _create_property(
        self,
        owner,
        *,
        p_type="apartment",
        address="Moscow, Tverskaya 1",
        area=Decimal("52.50"),
        p_class="comfort",
        price=Decimal("12000000.00"),
        status_val=Property.PropertyStatuses.PUBLISHED,
        moderation_status_val=Property.ModerationStatuses.APPROVED,
    ) -> Property:
        return Property.objects.create(
            owner=owner,
            type=p_type,
            address=address,
            area=area,
            property_class=p_class,
            price=price,
            status=status_val,
            moderation_status=moderation_status_val,
        )


class PropertyAPITests(BasePropertyTestCase):
    def test_create_property_requires_auth(self):
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Moscow, New Address 1",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_property_requires_developer(self):
        self.client.force_authenticate(user=self.broker)

        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Moscow, New Address 2",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_property_success_sets_owner(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Moscow, Created By Dev1"
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": address,
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        prop = Property.objects.get(address=address)
        self.assertEqual(prop.owner_id, self.dev1.id)

    def test_list_properties_paginated(self):
        for i in range(21):
            self._create_property(
                self.dev1,
                address=f"Moscow, Paginated {i}",
                price=Decimal("1000000.00") + i,
            )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 21)
        self.assertEqual(len(resp.data["results"]), 20)
        self.assertIsNotNone(resp.data["next"])

    def test_filters_work_type_and_price_range(self):
        self._create_property(
            self.dev1,
            p_type="house",
            address="House A",
            price=Decimal("9000000.00"),
        )
        self._create_property(
            self.dev1,
            p_type="house",
            address="House B",
            price=Decimal("15000000.00"),
        )
        self._create_property(
            self.dev1,
            p_type="apartment",
            address="Apt C",
            price=Decimal("7000000.00"),
        )

        resp = self.client.get(
            f"{BASE}?type=house&price_min=10000000&price_max=20000000",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["type"], "house")
        self.assertEqual(resp.data["results"][0]["address"], "House B")

    def test_list_excludes_not_approved_even_if_published(self):
        self._create_property(
            self.dev1,
            address="Approved Visible",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )
        self._create_property(
            self.dev1,
            address="Pending Hidden",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.PENDING,
        )
        self._create_property(
            self.dev1,
            address="Rejected Hidden",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.REJECTED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["address"], "Approved Visible")

    def test_list_includes_sold_if_approved(self):
        self._create_property(
            self.dev1,
            address="Sold Visible",
            status_val=Property.PropertyStatuses.SOLD,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["status"], "sold")

    def test_ordering_by_price_desc(self):
        self._create_property(self.dev1, address="Cheap", price=Decimal("100.00"))
        self._create_property(self.dev1, address="Expensive", price=Decimal("999.00"))

        resp = self.client.get(f"{BASE}?ordering=-price", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["results"][0]["address"], "Expensive")
        self.assertEqual(resp.data["results"][1]["address"], "Cheap")

    def test_patch_property_only_owner(self):
        prop = self._create_property(self.dev1, address="Only Owner Can Patch")

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_property_owner_can_update(self):
        prop = self._create_property(self.dev1, address="Owner Patch OK")

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("9999999.00"))

    def test_patch_property_resets_moderation_status_to_pending_on_change(self):
        prop = self._create_property(
            self.dev1,
            address="Moderation Reset On Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("9999999.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.PENDING)

    def test_patch_property_does_not_reset_moderation_status_when_value_not_changed(
        self,
    ):
        prop = self._create_property(
            self.dev1,
            address="Moderation Not Reset Without Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "12000000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("12000000.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.APPROVED)
