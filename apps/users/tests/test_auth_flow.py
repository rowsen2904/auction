import tempfile
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model

from apps.users.models import Broker
from apps.users.utils import (
    get_verification_key,
    get_registration_verified_key,
)

User = get_user_model()

BASE = "/api/v1/auth"


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

        # OTP code stored in cache
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

        # Create code first via endpoint
        with patch("apps.users.views.get_client_ip", return_value="1.2.3.4"):
            r1 = self.client.post(f"{BASE}/get-code/", data={"email": email}, format="json")
            self.assertEqual(r1.status_code, status.HTTP_200_OK)

        otp = cache.get(get_verification_key(email))
        self.assertTrue(otp)

        r2 = self.client.post(
            f"{BASE}/verify-email/",
            data={"email": email, "code": otp},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        # OTP should be deleted after successful verification
        self.assertIsNone(cache.get(get_verification_key(email)))

        # Registration verified flag should be set
        self.assertTrue(cache.get(get_registration_verified_key(email)))

    def test_verify_email_invalid_code_returns_400(self):
        email = "badcode@example.com"

        # Put some OTP in cache via endpoint
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
        # request OTP
        with patch("apps.users.views.get_client_ip", return_value="1.2.3.4"):
            r1 = self.client.post(f"{BASE}/get-code/", data={"email": email}, format="json")
            self.assertEqual(r1.status_code, status.HTTP_200_OK)

        otp = cache.get(get_verification_key(email))
        self.assertTrue(otp)

        # verify OTP
        r2 = self.client.post(
            f"{BASE}/verify-email/",
            data={"email": email, "code": otp},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(cache.get(get_registration_verified_key(email)))

    def test_register_developer_requires_verified_email(self):
        email = "dev1@example.com"

        resp = self.client.post(
            f"{BASE}/register/developer/",
            data={
                "email": email,
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "first_name": "John",
                "last_name": "Doe",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)

    def test_register_developer_password_mismatch(self):
        email = "dev2@example.com"
        self._verify_email_for_registration(email)

        resp = self.client.post(
            f"{BASE}/register/developer/",
            data={
                "email": email,
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!!",
                "first_name": "John",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", resp.data)

    def test_register_developer_success_returns_tokens_and_user(self):
        email = "dev3@example.com"
        self._verify_email_for_registration(email)

        resp = self.client.post(
            f"{BASE}/register/developer/",
            data={
                "email": email,
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "first_name": "John",
                "last_name": "Doe",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertIn("refresh", resp.data)
        self.assertIn("access", resp.data)
        self.assertEqual(resp.data["message"], "Registration successful.")
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["email"], email)
        self.assertEqual(resp.data["user"]["role"], "developer")
        self.assertIsNone(resp.data["user"]["broker"])

        # Registration verified flag should be cleared after registration
        self.assertFalse(cache.get(get_registration_verified_key(email)))

        # User exists in DB
        self.assertTrue(User.objects.filter(email=email).exists())

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
        self.assertIn("verification_document", resp.data)

    def test_register_broker_success_creates_broker_profile(self):
        email = "broker2@example.com"
        self._verify_email_for_registration(email)

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(MEDIA_ROOT=tmp_media):
                file = SimpleUploadedFile(
                    name="doc.pdf",
                    content=b"dummy pdf",
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
                        "verification_document": file,
                    },
                    format="multipart",
                )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("refresh", resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["email"], email)
        self.assertEqual(resp.data["user"]["role"], "broker")

        # Broker info embedded in user
        self.assertIsNotNone(resp.data["user"]["broker"])
        self.assertEqual(resp.data["user"]["broker"]["is_verified"], False)
        self.assertEqual(resp.data["user"]["broker"]["verification_status"], "pending")

        # DB checks
        user = User.objects.get(email=email)
        broker = Broker.objects.get(user=user)
        self.assertFalse(broker.is_verified)
        self.assertEqual(broker.verification_status, Broker.VerificationStatuses.PENDING)
        self.assertTrue(broker.verification_document.name)

        # Registration verified flag should be cleared
        self.assertFalse(cache.get(get_registration_verified_key(email)))


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
        user = User.objects.create_user(email=email, password=password, role=User.Roles.DEVELOPER)

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

    def test_login_invalid_password(self):
        email = "login2@example.com"
        User.objects.create_user(email=email, password="StrongPass123!", role=User.Roles.DEVELOPER)

        resp = self.client.post(
            f"{BASE}/login/",
            data={"email": email, "password": "wrongpass"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_new_access(self):
        email = "refresh@example.com"
        password = "StrongPass123!"
        User.objects.create_user(email=email, password=password, role=User.Roles.DEVELOPER)

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
