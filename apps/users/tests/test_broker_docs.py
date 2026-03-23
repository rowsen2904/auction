import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker, Developer

User = get_user_model()

BASE = "/api/v1/auth"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestBrokerDocumentsUpload(APITestCase):
    def setUp(self):
        self.url = f"{BASE}/broker/upload-documents/"

        self.broker_user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            first_name="Alice",
            last_name="Smith",
            role=User.Roles.BROKER,
        )
        self.broker = Broker.objects.create(
            user=self.broker_user,
            inn_number="7721581040",
        )

        self.developer_user = User.objects.create_user(
            email="developer@example.com",
            password="StrongPass123!",
            first_name="John",
            last_name="Doe",
            role=User.Roles.DEVELOPER,
        )
        self.developer = Developer.objects.create(
            user=self.developer_user,
            company_name="Acme Inc",
        )

    def _make_file(self, name: str, content: bytes = b"dummy file"):
        return SimpleUploadedFile(
            name=name,
            content=content,
            content_type="application/pdf",
        )

    def test_upload_both_documents_success(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn.pdf", b"dummy inn"),
                        "passport": self._make_file("passport.pdf", b"dummy passport"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertIn("broker", resp.data)

        self.broker.refresh_from_db()
        self.assertTrue(bool(self.broker.inn))
        self.assertTrue(bool(self.broker.passport))
        self.assertIn(f"brokers/{self.broker_user.id}/inns/", self.broker.inn.name)
        self.assertIn(
            f"brokers/{self.broker_user.id}/passports/",
            self.broker.passport.name,
        )

    def test_upload_only_inn_success(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn.pdf", b"dummy inn"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertTrue(bool(self.broker.inn))
        self.assertFalse(bool(self.broker.passport))

    def test_upload_only_passport_success(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "passport": self._make_file("passport.pdf", b"dummy passport"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertFalse(bool(self.broker.inn))
        self.assertTrue(bool(self.broker.passport))

    def test_upload_requires_authentication(self):
        resp = self.client.post(
            self.url,
            data={
                "inn": self._make_file("inn.pdf", b"dummy inn"),
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_forbidden_for_non_broker(self):
        self.client.force_authenticate(user=self.developer_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn.pdf", b"dummy inn"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", resp.data)

    def test_upload_without_files_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        resp = self.client.post(
            self.url,
            data={},
            format="multipart",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_inn_twice_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn.pdf", b"dummy inn"),
                    },
                    format="multipart",
                )
                self.assertEqual(first.status_code, status.HTTP_200_OK)

                second = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn2.pdf", b"dummy inn second"),
                    },
                    format="multipart",
                )

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inn", second.data)

        self.broker.refresh_from_db()
        self.assertTrue(bool(self.broker.inn))

    def test_upload_passport_twice_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "passport": self._make_file("passport.pdf", b"dummy passport"),
                    },
                    format="multipart",
                )
                self.assertEqual(first.status_code, status.HTTP_200_OK)

                second = self.client.post(
                    self.url,
                    data={
                        "passport": self._make_file(
                            "passport2.pdf", b"dummy passport second"
                        ),
                    },
                    format="multipart",
                )

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("passport", second.data)

        self.broker.refresh_from_db()
        self.assertTrue(bool(self.broker.passport))

    def test_upload_both_when_inn_already_exists_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn.pdf", b"dummy inn"),
                    },
                    format="multipart",
                )
                self.assertEqual(first.status_code, status.HTTP_200_OK)

                second = self.client.post(
                    self.url,
                    data={
                        "inn": self._make_file("inn2.pdf", b"dummy inn second"),
                        "passport": self._make_file("passport.pdf", b"dummy passport"),
                    },
                    format="multipart",
                )

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inn", second.data)

        self.broker.refresh_from_db()
        self.assertTrue(bool(self.broker.inn))
        self.assertFalse(bool(self.broker.passport))


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestBrokerDocumentNames(APITestCase):
    def setUp(self):
        self.upload_url = f"{BASE}/broker/upload-documents/"
        self.rename_url = f"{BASE}/broker/update-document-names/"

        self.user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
        )
        self.broker = Broker.objects.create(
            user=self.user,
            inn_number="7721581040",
        )

    def _make_file(self, name, content=b"dummy"):
        return SimpleUploadedFile(
            name=name,
            content=content,
            content_type="application/pdf",
        )

    def test_upload_document_with_custom_names_success(self):
        self.client.force_authenticate(user=self.user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.upload_url,
                    data={
                        "inn": self._make_file("inn.pdf", b"inn"),
                        "inn_name": "Мой ИНН",
                        "passport": self._make_file("passport.pdf", b"passport"),
                        "passport_name": "Мой паспорт",
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(self.broker.inn_name, "Мой ИНН")
        self.assertEqual(self.broker.passport_name, "Мой паспорт")

    def test_upload_document_without_custom_name_uses_filename(self):
        self.client.force_authenticate(user=self.user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.upload_url,
                    data={
                        "inn": self._make_file("company_inn.pdf", b"inn"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(self.broker.inn_name, "company_inn")

    def test_rename_document_names_success(self):
        self.client.force_authenticate(user=self.user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                upload = self.client.post(
                    self.upload_url,
                    data={
                        "inn": self._make_file("inn.pdf", b"inn"),
                        "passport": self._make_file("passport.pdf", b"passport"),
                    },
                    format="multipart",
                )
                self.assertEqual(upload.status_code, status.HTTP_200_OK)

                resp = self.client.patch(
                    self.rename_url,
                    data={
                        "inn_name": "Новый ИНН",
                        "passport_name": "Новый паспорт",
                    },
                    format="json",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(self.broker.inn_name, "Новый ИНН")
        self.assertEqual(self.broker.passport_name, "Новый паспорт")

    def test_rename_inn_name_only_success(self):
        self.client.force_authenticate(user=self.user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                upload = self.client.post(
                    self.upload_url,
                    data={
                        "inn": self._make_file("inn.pdf", b"inn"),
                    },
                    format="multipart",
                )
                self.assertEqual(upload.status_code, status.HTTP_200_OK)

                resp = self.client.patch(
                    self.rename_url,
                    data={"inn_name": "ИНН 2026"},
                    format="json",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.broker.refresh_from_db()
        self.assertEqual(self.broker.inn_name, "ИНН 2026")

    def test_rename_passport_name_without_uploaded_passport_returns_400(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.patch(
            self.rename_url,
            data={"passport_name": "Новый паспорт"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("passport_name", resp.data)

    def test_rename_requires_at_least_one_field(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.patch(
            self.rename_url,
            data={},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
