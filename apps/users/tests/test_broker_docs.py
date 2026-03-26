import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker, Developer, UserDocument

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
class TestUserDocumentsUpload(APITestCase):
    def setUp(self):
        self.url = f"{BASE}/documents/upload/"

        self.broker_user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            first_name="Alice",
            last_name="Smith",
            role=User.Roles.BROKER,
            inn_number="772158104012",
        )
        self.broker = Broker.objects.create(user=self.broker_user)

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

        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            first_name="Admin",
            last_name="User",
            role=User.Roles.ADMIN,
            is_staff=True,
        )

    def _make_file(self, name: str, content: bytes = b"dummy file"):
        return SimpleUploadedFile(
            name=name,
            content=content,
            content_type="application/pdf",
        )

    def test_broker_can_upload_inn_success(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.INN,
                        "document": self._make_file("inn.pdf", b"dummy inn"),
                        "document_name": "Мой ИНН",
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertIn("document", resp.data)

        doc = UserDocument.objects.get(
            user=self.broker_user,
            doc_type=UserDocument.Types.INN,
        )
        self.assertEqual(doc.document_name, "Мой ИНН")
        self.assertTrue(bool(doc.document))
        self.assertIn(f"users/{self.broker_user.id}/documents/", doc.document.name)

    def test_developer_can_upload_other_document_success(self):
        self.client.force_authenticate(user=self.developer_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("license.pdf", b"dummy license"),
                        "document_name": "Лицензия",
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        doc = UserDocument.objects.get(
            user=self.developer_user,
            doc_type=UserDocument.Types.OTHERS,
        )
        self.assertEqual(doc.document_name, "Лицензия")
        self.assertTrue(bool(doc.document))

    def test_upload_without_custom_name_uses_filename(self):
        self.client.force_authenticate(user=self.developer_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("company_license.pdf", b"dummy"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        doc = UserDocument.objects.get(user=self.developer_user)
        self.assertEqual(doc.document_name, "company_license")

    def test_upload_requires_authentication(self):
        resp = self.client.post(
            self.url,
            data={
                "doc_type": UserDocument.Types.OTHERS,
                "document": self._make_file("doc.pdf", b"dummy"),
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_cannot_upload_documents(self):
        self.client.force_authenticate(user=self.admin_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                resp = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("admin_doc.pdf", b"dummy"),
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)
        self.assertEqual(UserDocument.objects.filter(user=self.admin_user).count(), 0)

    def test_upload_without_file_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        resp = self.client.post(
            self.url,
            data={"doc_type": UserDocument.Types.INN},
            format="multipart",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_duplicate_inn_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.INN,
                        "document": self._make_file("inn.pdf", b"dummy inn"),
                    },
                    format="multipart",
                )
                self.assertEqual(first.status_code, status.HTTP_200_OK)

                second = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.INN,
                        "document": self._make_file("inn2.pdf", b"dummy inn second"),
                    },
                    format="multipart",
                )

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doc_type", second.data)
        self.assertEqual(
            UserDocument.objects.filter(
                user=self.broker_user,
                doc_type=UserDocument.Types.INN,
            ).count(),
            1,
        )

    def test_upload_duplicate_passport_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.PASSPORT,
                        "document": self._make_file("passport.pdf", b"dummy passport"),
                    },
                    format="multipart",
                )
                self.assertEqual(first.status_code, status.HTTP_200_OK)

                second = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.PASSPORT,
                        "document": self._make_file(
                            "passport2.pdf",
                            b"dummy passport second",
                        ),
                    },
                    format="multipart",
                )

        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doc_type", second.data)
        self.assertEqual(
            UserDocument.objects.filter(
                user=self.broker_user,
                doc_type=UserDocument.Types.PASSPORT,
            ).count(),
            1,
        )

    def test_upload_other_documents_can_repeat(self):
        self.client.force_authenticate(user=self.developer_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                first = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("doc1.pdf", b"dummy 1"),
                    },
                    format="multipart",
                )
                second = self.client.post(
                    self.url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("doc2.pdf", b"dummy 2"),
                    },
                    format="multipart",
                )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            UserDocument.objects.filter(
                user=self.developer_user,
                doc_type=UserDocument.Types.OTHERS,
            ).count(),
            2,
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestUserDocumentNames(APITestCase):
    def setUp(self):
        self.upload_url = f"{BASE}/documents/upload/"
        self.rename_url = f"{BASE}/documents/update-name/"

        self.broker_user = User.objects.create_user(
            email="broker@example.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            inn_number="772158104012",
        )
        self.broker = Broker.objects.create(user=self.broker_user)

        self.developer_user = User.objects.create_user(
            email="developer@example.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
        )
        self.developer = Developer.objects.create(
            user=self.developer_user,
            company_name="Acme Inc",
        )

        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=User.Roles.ADMIN,
            is_staff=True,
        )

    def _make_file(self, name, content=b"dummy"):
        return SimpleUploadedFile(
            name=name,
            content=content,
            content_type="application/pdf",
        )

    def test_rename_document_name_success(self):
        self.client.force_authenticate(user=self.broker_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                upload = self.client.post(
                    self.upload_url,
                    data={
                        "doc_type": UserDocument.Types.INN,
                        "document": self._make_file("inn.pdf", b"inn"),
                    },
                    format="multipart",
                )
                self.assertEqual(upload.status_code, status.HTTP_200_OK)

                doc = UserDocument.objects.get(
                    user=self.broker_user,
                    doc_type=UserDocument.Types.INN,
                )

                resp = self.client.patch(
                    self.rename_url,
                    data={
                        "document_id": doc.id,
                        "document_name": "Новый ИНН",
                    },
                    format="json",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        doc.refresh_from_db()
        self.assertEqual(doc.document_name, "Новый ИНН")

    def test_developer_can_rename_document_success(self):
        self.client.force_authenticate(user=self.developer_user)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                upload = self.client.post(
                    self.upload_url,
                    data={
                        "doc_type": UserDocument.Types.OTHERS,
                        "document": self._make_file("license.pdf", b"license"),
                    },
                    format="multipart",
                )
                self.assertEqual(upload.status_code, status.HTTP_200_OK)

                doc = UserDocument.objects.get(user=self.developer_user)

                resp = self.client.patch(
                    self.rename_url,
                    data={
                        "document_id": doc.id,
                        "document_name": "Новая лицензия",
                    },
                    format="json",
                )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        doc.refresh_from_db()
        self.assertEqual(doc.document_name, "Новая лицензия")

    def test_rename_requires_authentication(self):
        resp = self.client.patch(
            self.rename_url,
            data={
                "document_id": 1,
                "document_name": "Новое имя",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rename_document_not_found_returns_400(self):
        self.client.force_authenticate(user=self.broker_user)

        resp = self.client.patch(
            self.rename_url,
            data={
                "document_id": 999999,
                "document_name": "Новый ИНН",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("document_id", resp.data)

    def test_admin_cannot_rename_documents(self):
        self.client.force_authenticate(user=self.admin_user)

        resp = self.client.patch(
            self.rename_url,
            data={
                "document_id": 1,
                "document_name": "Admin Doc",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)
