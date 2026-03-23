import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test.client import BytesIO
from PIL import Image
from properties.models import PropertyImage
from rest_framework import status

from .test_properties_api import BasePropertyTestCase

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


class PropertyImageAPITests(BasePropertyTestCase):
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

                self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
                self.assertIn("url", r1.data)
                self.assertTrue(r1.data["url"])
                self.assertIn("/media/", r1.data["url"])

                r2 = self.client.get(f"{BASE}{prop.id}/images/", format="json")
                self.assertEqual(r2.status_code, status.HTTP_200_OK)
                self.assertEqual(len(r2.data), 1)
                self.assertEqual(r2.data[0]["sort_order"], 0)
                self.assertTrue(r2.data[0]["is_primary"])

    def test_patch_image_requires_auth(self):
        prop = self._create_property(self.dev1, address="Patch Image Auth")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/auth.jpg",
            sort_order=0,
            is_primary=True,
        )

        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img.id}/",
            data={"is_primary": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_image_only_owner_returns_404(self):
        prop = self._create_property(self.dev1, address="Patch Image Owner Only")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/owner-only.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img.id}/",
            data={"is_primary": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_image_requires_developer(self):
        prop = self._create_property(self.dev1, address="Patch Image Developer Only")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/broker.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.broker)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img.id}/",
            data={"is_primary": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_image_is_primary_switch_success(self):
        prop = self._create_property(self.dev1, address="Patch Primary Switch")

        img1 = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/primary-1.jpg",
            sort_order=0,
            is_primary=True,
        )
        img2 = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/primary-2.jpg",
            sort_order=1,
            is_primary=False,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img2.id}/",
            data={"is_primary": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["is_primary"])

        img1.refresh_from_db()
        img2.refresh_from_db()
        self.assertFalse(img1.is_primary)
        self.assertTrue(img2.is_primary)

    def test_patch_image_sort_order_success(self):
        prop = self._create_property(self.dev1, address="Patch Sort Order")

        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/sort.jpg",
            sort_order=0,
            is_primary=False,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img.id}/",
            data={"sort_order": 7},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["sort_order"], 7)

        img.refresh_from_db()
        self.assertEqual(img.sort_order, 7)

    def test_patch_image_is_primary_and_sort_order_success(self):
        prop = self._create_property(self.dev1, address="Patch Both Fields")

        img1 = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/both-1.jpg",
            sort_order=0,
            is_primary=True,
        )
        img2 = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/both-2.jpg",
            sort_order=1,
            is_primary=False,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img2.id}/",
            data={"is_primary": True, "sort_order": 5},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["is_primary"])
        self.assertEqual(resp.data["sort_order"], 5)

        img1.refresh_from_db()
        img2.refresh_from_db()
        self.assertFalse(img1.is_primary)
        self.assertTrue(img2.is_primary)
        self.assertEqual(img2.sort_order, 5)

    def test_patch_image_duplicate_sort_order_returns_400(self):
        prop = self._create_property(self.dev1, address="Patch Duplicate Sort")

        PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/dup-1.jpg",
            sort_order=0,
            is_primary=True,
        )
        img2 = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/dup-2.jpg",
            sort_order=1,
            is_primary=False,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img2.id}/",
            data={"sort_order": 0},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)

    def test_patch_image_empty_payload_returns_400(self):
        prop = self._create_property(self.dev1, address="Patch Empty Payload")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/empty.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/{img.id}/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_image_not_found_returns_404(self):
        prop = self._create_property(self.dev1, address="Patch Image Not Found")

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/images/999999/",
            data={"is_primary": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_image_requires_auth(self):
        prop = self._create_property(self.dev1, address="Delete Image Auth")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/delete-auth.jpg",
            sort_order=0,
            is_primary=True,
        )

        resp = self.client.delete(f"{BASE}{prop.id}/images/{img.id}/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_image_only_owner_returns_404(self):
        prop = self._create_property(self.dev1, address="Delete Image Owner Only")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/delete-owner.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.delete(f"{BASE}{prop.id}/images/{img.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_image_requires_developer(self):
        prop = self._create_property(self.dev1, address="Delete Image Developer Only")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/delete-broker.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.broker)
        resp = self.client.delete(f"{BASE}{prop.id}/images/{img.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_image_success(self):
        prop = self._create_property(self.dev1, address="Delete Image Success")
        img = PropertyImage.objects.create(
            property=prop,
            external_url="https://cdn.example.com/delete-success.jpg",
            sort_order=0,
            is_primary=True,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.delete(f"{BASE}{prop.id}/images/{img.id}/")

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PropertyImage.objects.filter(id=img.id).exists())

    def test_delete_image_not_found(self):
        prop = self._create_property(self.dev1, address="Delete Image Not Found")

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.delete(f"{BASE}{prop.id}/images/999999/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
