import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test.client import BytesIO
from PIL import Image
from properties.models import Property, PropertyImage
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


class PropertyAPITests(APITestCase):
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
        currency="RUB",
        status_val="published",
    ) -> Property:
        return Property.objects.create(
            owner=owner,
            type=p_type,
            address=address,
            area=area,
            property_class=p_class,
            price=price,
            currency=currency,
            status=status_val,
        )

    def test_create_property_requires_auth(self):
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Moscow, New Address 1",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "currency": "RUB",
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
                "currency": "RUB",
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
                "currency": "RUB",
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

    def test_property_detail_includes_images(self):
        prop = self._create_property(self.dev1, address="Prop With Images")

        PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/img.jpg",
            sort_order=0,
            is_primary=True,
        )

        resp = self.client.get(f"{BASE}{prop.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("images", resp.data)
        self.assertEqual(len(resp.data["images"]), 1)
        self.assertEqual(
            resp.data["images"][0]["url"], "https://cdn.example.com/img.jpg"
        )
        self.assertTrue(resp.data["images"][0]["is_primary"])

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

    def test_add_image_only_owner_returns_404(self):
        prop = self._create_property(self.dev1, address="Images Owner Only")

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.post(
            f"{BASE}{prop.id}/images/",
            data={"external_url": "https://cdn.example.com/a.jpg", "is_primary": True},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_image_external_url_success_and_primary_switch(self):
        prop = self._create_property(self.dev1, address="Primary Switch")

        self.client.force_authenticate(user=self.dev1)

        r1 = self.client.post(
            f"{BASE}{prop.id}/images/",
            data={
                "external_url": "https://cdn.example.com/1.jpg",
                "is_primary": True,
                "sort_order": 0,
            },
            format="multipart",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r1.data["is_primary"])

        r2 = self.client.post(
            f"{BASE}{prop.id}/images/",
            data={
                "external_url": "https://cdn.example.com/2.jpg",
                "is_primary": True,
                "sort_order": 1,
            },
            format="multipart",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r2.data["is_primary"])

        img1 = PropertyImage.objects.get(external_url="https://cdn.example.com/1.jpg")
        img2 = PropertyImage.objects.get(external_url="https://cdn.example.com/2.jpg")
        self.assertFalse(img1.is_primary)
        self.assertTrue(img2.is_primary)

    def test_add_image_file_upload_success_and_list_images(self):
        prop = self._create_property(self.dev1, address="Upload Image File")
        self.client.force_authenticate(user=self.dev1)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                img_file = make_png_file("img.png")

                r1 = self.client.post(
                    f"{BASE}{prop.id}/images/",
                    data={"image": img_file, "is_primary": True, "sort_order": 0},
                    format="multipart",
                )

                # English: print errors if validation fails
                if r1.status_code != status.HTTP_201_CREATED:
                    print(r1.data)

                self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
                self.assertIn("url", r1.data)
                self.assertTrue(r1.data["url"])
                self.assertIn("/media/", r1.data["url"])

                r2 = self.client.get(f"{BASE}{prop.id}/images/", format="json")
                self.assertEqual(r2.status_code, status.HTTP_200_OK)
                self.assertEqual(len(r2.data), 1)
                self.assertEqual(r2.data[0]["sort_order"], 0)
                self.assertTrue(r2.data[0]["is_primary"])
