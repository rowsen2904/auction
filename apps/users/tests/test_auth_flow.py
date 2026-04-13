import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Broker, Developer, UserDocument
from apps.users.utils import (
    get_registration_verified_key,
    get_verification_key,
)

User = get_user_model()

BASE = "/api/v1/auth"


def _checksum(digits: list[int], weights: list[int]) -> int:
    return (sum(d * w for d, w in zip(digits, weights)) % 11) % 10


def make_inn10(prefix9: str = "770000000") -> str:
    if len(prefix9) != 9 or not prefix9.isdigit():
        raise ValueError("prefix9 must be exactly 9 digits")
    digits = list(map(int, prefix9))
    weights_10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    control = _checksum(digits[:9], weights_10)
    return prefix9 + str(control)


def make_inn12(prefix10: str = "7700000000") -> str:
    if len(prefix10) != 10 or not prefix10.isdigit():
        raise ValueError("prefix10 must be exactly 10 digits")

    digits10 = list(map(int, prefix10))
    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

    c11 = _checksum(digits10, weights_11)
    digits11 = digits10 + [c11]
    c12 = _checksum(digits11, weights_12)

    return prefix10 + str(c11) + str(c12)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestAuthOTPFlow(APITestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.users.views.get_client_ip", return_value="1.2.3.4")
    def test_get_code_success_sets_cache(self, _mock_ip):
        email = "user@example.com"

        resp = self.client.post(
            f"{BASE}/get-code/",
            data={"email": email},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["email"], email)

        otp = cache.get(get_verification_key(email))
        self.assertTrue(otp)
        self.assertEqual(len(otp), 6)

    @patch("apps.users.views.get_client_ip", return_value="1.2.3.4")
    def test_get_code_existing_user_returns_409(self, _mock_ip):
        User.objects.create_user(email="exists@example.com", password="StrongPass123!")

        resp = self.client.post(
            f"{BASE}/get-code/",
            data={"email": "exists@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("error", resp.data)

    @patch("apps.users.views.get_client_ip", return_value="1.2.3.4")
    def test_get_code_rate_limited_second_call(self, _mock_ip):
        email = "limit@example.com"

        r1 = self.client.post(f"{BASE}/get-code/", data={"email": email}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.post(f"{BASE}/get-code/", data={"email": email}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("code", r2.data)
        self.assertEqual(r2.data["code"], "rate_limit_exceeded")

    def test_verify_email_success_marks_registration_verified(self):
        email = "verify@example.com"

        with patch("apps.users.views.get_client_ip", return_value="1.2.3.4"):
            r1 = self.client.post(
                f"{BASE}/get-code/",
                data={"email": email},
                format="json",
            )
            self.assertEqual(r1.status_code, status.HTTP_200_OK)

        otp = cache.get(get_verification_key(email))
        self.assertTrue(otp)

        r2 = self.client.post(
            f"{BASE}/verify-email/",
            data={"email": email, "code": otp},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        self.assertIsNone(cache.get(get_verification_key(email)))
        self.assertTrue(cache.get(get_registration_verified_key(email)))

    def test_verify_email_invalid_code_returns_400(self):
        email = "badcode@example.com"

        with patch("apps.users.views.get_client_ip", return_value="1.2.3.4"):
            self.client.post(f"{BASE}/get-code/", data={"email": email}, format="json")

        r = self.client.post(
            f"{BASE}/verify-email/",
            data={"email": email, "code": "000000"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", r.data)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestRegistrationFlow(APITestCase):
    def setUp(self):
        cache.clear()

    def _verify_email_for_registration(self, email: str):
        with patch("apps.users.views.get_client_ip", return_value="1.2.3.4"):
            r1 = self.client.post(
                f"{BASE}/get-code/",
                data={"email": email},
                format="json",
            )
            self.assertEqual(r1.status_code, status.HTTP_200_OK)

        otp = cache.get(get_verification_key(email))
        self.assertTrue(otp)

        r2 = self.client.post(
            f"{BASE}/verify-email/",
            data={"email": email, "code": otp},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(cache.get(get_registration_verified_key(email)))

    def test_register_broker_requires_file(self):
        email = "broker1@example.com"
        self._verify_email_for_registration(email)

        resp = self.client.post(
            f"{BASE}/register/broker/",
            data={
                "email": email,
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "first_name": "Alice",
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inn", resp.data)
        self.assertIn("inn_number", resp.data)
        self.assertIn("passport", resp.data)

    def test_register_broker_success_creates_broker_profile_and_documents(self):
        email = "broker2@example.com"
        self._verify_email_for_registration(email)
        inn_number = make_inn12("7721581040")

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                passport_file = SimpleUploadedFile(
                    name="passport.pdf",
                    content=b"dummy passport",
                    content_type="application/pdf",
                )
                inn_file = SimpleUploadedFile(
                    name="inn.pdf",
                    content=b"dummy inn",
                    content_type="application/pdf",
                )

                resp = self.client.post(
                    f"{BASE}/register/broker/",
                    data={
                        "email": email,
                        "password": "StrongPass123!",
                        "password_confirm": "StrongPass123!",
                        "first_name": "Alice",
                        "last_name": "Smith",
                        "inn_number": inn_number,
                        "inn": inn_file,
                        "passport": passport_file,
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("refresh", resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["email"], email)
        self.assertEqual(resp.data["user"]["role"], User.Roles.BROKER)

        self.assertIsNotNone(resp.data["user"]["broker"])
        self.assertEqual(resp.data["user"]["broker"]["is_verified"], False)
        self.assertEqual(
            resp.data["user"]["broker"]["verification_status"],
            Broker.VerificationStatuses.PENDING,
        )
        self.assertEqual(resp.data["user"]["broker"]["inn_number"], inn_number)
        self.assertIsNone(resp.data["user"]["developer"])

        self.assertIn("documents", resp.data["user"])
        self.assertEqual(len(resp.data["user"]["documents"]), 2)
        self.assertSetEqual(
            {doc["doc_type"] for doc in resp.data["user"]["documents"]},
            {UserDocument.Types.INN, UserDocument.Types.PASSPORT},
        )
        self.assertIn("rejection_reason", resp.data["user"]["broker"])
        self.assertIsNone(resp.data["user"]["broker"]["rejection_reason"])

        user = User.objects.get(email=email)
        broker = Broker.objects.get(user=user)

        self.assertIsNone(broker.rejection_reason)
        self.assertFalse(broker.is_verified)
        self.assertEqual(
            broker.verification_status,
            Broker.VerificationStatuses.PENDING,
        )

        self.assertEqual(user.inn_number, inn_number)
        self.assertEqual(
            user.documents.filter(doc_type=UserDocument.Types.INN).count(),
            1,
        )
        self.assertEqual(
            user.documents.filter(doc_type=UserDocument.Types.PASSPORT).count(),
            1,
        )

        inn_doc = user.documents.get(doc_type=UserDocument.Types.INN)
        passport_doc = user.documents.get(doc_type=UserDocument.Types.PASSPORT)

        self.assertTrue(bool(inn_doc.document.name))
        self.assertTrue(bool(passport_doc.document.name))
        self.assertEqual(inn_doc.document_name, "inn")
        self.assertEqual(passport_doc.document_name, "passport")

        self.assertFalse(cache.get(get_registration_verified_key(email)))

    def test_register_broker_invalid_inn_returns_400(self):
        email = "broker_bad_inn@example.com"
        self._verify_email_for_registration(email)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                passport_file = SimpleUploadedFile(
                    name="passport.pdf",
                    content=b"dummy passport",
                    content_type="application/pdf",
                )
                inn_file = SimpleUploadedFile(
                    name="inn.pdf",
                    content=b"dummy inn",
                    content_type="application/pdf",
                )

                valid_inn = make_inn12("7721581040")
                invalid_inn = valid_inn[:-1] + ("0" if valid_inn[-1] != "0" else "1")

                resp = self.client.post(
                    f"{BASE}/register/broker/",
                    data={
                        "email": email,
                        "password": "StrongPass123!",
                        "password_confirm": "StrongPass123!",
                        "first_name": "Alice",
                        "last_name": "Smith",
                        "inn_number": invalid_inn,
                        "inn": inn_file,
                        "passport": passport_file,
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inn_number", resp.data)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestLoginAndRefresh(APITestCase):
    def setUp(self):
        cache.clear()

    def test_login_success_returns_tokens_and_user(self):
        email = "login@example.com"
        password = "StrongPass123!"

        user = User.objects.create_user(
            email=email,
            password=password,
            role=User.Roles.DEVELOPER,
        )
        Developer.objects.create(user=user, company_name="Acme Inc")

        resp = self.client.post(
            f"{BASE}/login/",
            data={"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("refresh", resp.data)
        self.assertIn("access", resp.data)
        self.assertEqual(resp.data["user"]["id"], user.id)
        self.assertEqual(resp.data["user"]["email"], email)
        self.assertEqual(resp.data["user"]["role"], User.Roles.DEVELOPER)
        self.assertIn("documents", resp.data["user"])
        self.assertEqual(resp.data["user"]["documents"], [])
        self.assertIsNotNone(resp.data["user"]["developer"])
        self.assertIsNone(resp.data["user"]["broker"])

    def test_login_invalid_password(self):
        email = "login2@example.com"
        user = User.objects.create_user(
            email=email,
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
        )
        Developer.objects.create(user=user, company_name="Acme Inc")

        resp = self.client.post(
            f"{BASE}/login/",
            data={"email": email, "password": "wrongpass"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_new_access(self):
        email = "refresh@example.com"
        password = "StrongPass123!"
        user = User.objects.create_user(
            email=email,
            password=password,
            role=User.Roles.DEVELOPER,
        )
        Developer.objects.create(user=user, company_name="Acme Inc")

        login = self.client.post(
            f"{BASE}/login/",
            data={"email": email, "password": password},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        refresh_token = login.data["refresh"]

        refresh = self.client.post(
            f"{BASE}/refresh/",
            data={"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh.data)

    def test_login_broker_success_returns_broker_rejection_reason(self):
        email = "broker_login@example.com"
        password = "StrongPass123!"

        user = User.objects.create_user(
            email=email,
            password=password,
            role=User.Roles.BROKER,
            inn_number=make_inn12("7721581040"),
        )
        Broker.objects.create(
            user=user,
            is_verified=False,
            verification_status=Broker.VerificationStatuses.REJECTED,
            rejection_reason="Passport scan is unreadable.",
        )

        resp = self.client.post(
            f"{BASE}/login/",
            data={"email": email, "password": password},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["user"]["role"], User.Roles.BROKER)
        self.assertIsNone(resp.data["user"]["developer"])
        self.assertIsNotNone(resp.data["user"]["broker"])
        self.assertEqual(
            resp.data["user"]["broker"]["verification_status"],
            Broker.VerificationStatuses.REJECTED,
        )
        self.assertEqual(
            resp.data["user"]["broker"]["rejection_reason"],
            "Passport scan is unreadable.",
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    },
)
class TestChangePassword(APITestCase):
    def setUp(self):
        cache.clear()
        self.old_password = "StrongPass123!"
        self.new_password = "NewStrongPass123!"

        self.user = User.objects.create_user(
            email="change-password@example.com",
            password=self.old_password,
            role=User.Roles.DEVELOPER,
        )
        Developer.objects.create(user=self.user, company_name="Acme Inc")
        self.url = f"{BASE}/change-password/"

    def test_change_password_success_updates_password(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            self.url,
            data={
                "old_password": self.old_password,
                "new_password": self.new_password,
                "new_password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Пароль успешно изменён.")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.old_password))

        self.client.force_authenticate(user=None)

        old_login = self.client.post(
            f"{BASE}/login/",
            data={
                "email": self.user.email,
                "password": self.old_password,
            },
            format="json",
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login = self.client.post(
            f"{BASE}/login/",
            data={
                "email": self.user.email,
                "password": self.new_password,
            },
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)
        self.assertIn("access", new_login.data)
        self.assertIn("refresh", new_login.data)

    def test_change_password_wrong_old_password_returns_400(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            self.url,
            data={
                "old_password": "WrongOldPass123!",
                "new_password": self.new_password,
                "new_password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", resp.data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_change_password_password_confirm_mismatch_returns_400(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            self.url,
            data={
                "old_password": self.old_password,
                "new_password": self.new_password,
                "new_password_confirm": "AnotherPass123!",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password_confirm", resp.data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_change_password_requires_authentication(self):
        resp = self.client.post(
            self.url,
            data={
                "old_password": self.old_password,
                "new_password": self.new_password,
                "new_password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertIn(
            resp.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )
