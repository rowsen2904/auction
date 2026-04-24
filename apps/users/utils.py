import logging
import random
import string
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    remaining_time: Optional[int] = None
    message: Optional[str] = None


class EmailRateLimiter:
    def __init__(self) -> None:
        self.limit_seconds = getattr(settings, "EMAIL_SEND_LIMIT", 60)
        self.cache_prefix = "email_rate_limit"

    def _get_ip_key(self, ip_address: str) -> str:
        return f"{self.cache_prefix}:ip:{ip_address}"

    def _get_email_key(self, email: str) -> str:
        return f"{self.cache_prefix}:email:{email.strip().lower()}"

    def _get_combined_key(self, ip_address: str, email: str) -> str:
        return f"{self.cache_prefix}:combined:{ip_address}:{email.strip().lower()}"

    def _get_timestamp(self) -> int:
        return int(timezone.now().timestamp())

    def _calculate_remaining_time(self, last_send_time: int) -> int:
        current_time = self._get_timestamp()
        elapsed = current_time - last_send_time
        return max(0, self.limit_seconds - elapsed)

    def check_rate_limit(self, ip_address: str, email: str) -> RateLimitResult:
        try:
            ip_key = self._get_ip_key(ip_address)
            email_key = self._get_email_key(email)
            combined_key = self._get_combined_key(ip_address, email)

            ip_last_send = cache.get(ip_key)
            if ip_last_send:
                remaining = self._calculate_remaining_time(ip_last_send)
                if remaining > 0:
                    return RateLimitResult(
                        allowed=False,
                        remaining_time=remaining,
                        message=f"Please wait {remaining} seconds before requesting another code.",
                    )

            email_last_send = cache.get(email_key)
            if email_last_send:
                remaining = self._calculate_remaining_time(email_last_send)
                if remaining > 0:
                    return RateLimitResult(
                        allowed=False,
                        remaining_time=remaining,
                        message=(
                            f"Please wait {remaining} seconds before requesting another code "
                            "for this email."
                        ),
                    )

            combined_last_send = cache.get(combined_key)
            if combined_last_send:
                remaining = self._calculate_remaining_time(combined_last_send)
                if remaining > 0:
                    return RateLimitResult(
                        allowed=False,
                        remaining_time=remaining,
                        message=f"Please wait {remaining} seconds before requesting another code.",
                    )

            return RateLimitResult(allowed=True)

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return RateLimitResult(allowed=True)

    def record_email_send(self, ip_address: str, email: str) -> None:
        try:
            now_ts = self._get_timestamp()
            ttl = self.limit_seconds + 60

            cache.set(self._get_ip_key(ip_address), now_ts, ttl)
            cache.set(self._get_email_key(email), now_ts, ttl)
            cache.set(self._get_combined_key(ip_address, email), now_ts, ttl)

        except Exception as e:
            logger.error(f"Rate limit record failed: {e}")


email_rate_limiter = EmailRateLimiter()


def norm_email(email: str) -> str:
    return email.strip().lower()


def get_verification_key(email: str) -> str:
    return f"email_verification:{norm_email(email)}"


def generate_code(length: int) -> str:
    return "".join(random.choices(string.digits, k=length))


def send_verification_email_to(email: str, ip_address: Optional[str] = None) -> str:
    email = norm_email(email)
    code_len = getattr(settings, "EMAIL_VERIFICATION_CODE_LENGTH", 6)
    expiry_seconds = getattr(settings, "EMAIL_VERIFICATION_CODE_EXPIRY", 15 * 60)
    code = generate_code(code_len)
    cache_key = get_verification_key(email)
    cache.set(cache_key, code, expiry_seconds)
    subject = "Email verification - MIG Tender"
    message = f"""
Hello!

Your verification code: {code}

The code is valid for 15 minutes.

If you did not request this, simply ignore this email.

With regards,
The MIG Tender team
""".strip()
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )
    if ip_address:
        email_rate_limiter.record_email_send(ip_address, email)
    return code


def verify_code(email: str, code: str) -> bool:
    email = norm_email(email)
    cache_key = get_verification_key(email)
    stored_code = cache.get(cache_key)
    if stored_code and stored_code == code.strip():
        cache.delete(cache_key)
        return True
    return False


send_verification_email = send_verification_email_to


# Registration utils


def get_registration_verified_key(email: str) -> str:
    return f"email_registration_verified:{norm_email(email)}"


def mark_email_verified_for_registration(
    email: str, ttl_seconds: Optional[int] = None
) -> None:
    """
    Marks an email as verified for registration for a limited time window.
    This is separate from the OTP code itself (OTP gets deleted on successful verification).
    """
    if ttl_seconds is None:
        ttl_seconds = getattr(
            settings, "EMAIL_REGISTRATION_VERIFIED_TTL", 30 * 60
        )  # 30 min default
    cache.set(get_registration_verified_key(email), True, ttl_seconds)


def is_email_verified_for_registration(email: str) -> bool:
    return bool(cache.get(get_registration_verified_key(email)))


def clear_email_verified_for_registration(email: str) -> None:
    cache.delete(get_registration_verified_key(email))


# Password reset utils


def get_password_reset_code_key(email: str) -> str:
    return f"password_reset_code:{norm_email(email)}"


def get_password_reset_verified_key(email: str) -> str:
    return f"password_reset_verified:{norm_email(email)}"


def send_password_reset_email_to(
    email: str, ip_address: Optional[str] = None
) -> str:
    email = norm_email(email)
    code_len = getattr(settings, "EMAIL_VERIFICATION_CODE_LENGTH", 6)
    expiry_seconds = getattr(settings, "EMAIL_VERIFICATION_CODE_EXPIRY", 15 * 60)
    code = generate_code(code_len)
    cache.set(get_password_reset_code_key(email), code, expiry_seconds)
    subject = "Password reset - MIG Tender"
    message = f"""
Hello!

Your password reset code: {code}

The code is valid for 15 minutes.

If you did not request a password reset, simply ignore this email —
your current password will remain unchanged.

With regards,
The MIG Tender team
""".strip()
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )
    if ip_address:
        email_rate_limiter.record_email_send(ip_address, email)
    return code


def verify_password_reset_code(email: str, code: str) -> bool:
    email = norm_email(email)
    cache_key = get_password_reset_code_key(email)
    stored_code = cache.get(cache_key)
    if stored_code and stored_code == code.strip():
        cache.delete(cache_key)
        return True
    return False


def mark_email_verified_for_password_reset(
    email: str, ttl_seconds: Optional[int] = None
) -> None:
    if ttl_seconds is None:
        ttl_seconds = getattr(
            settings, "EMAIL_PASSWORD_RESET_VERIFIED_TTL", 15 * 60
        )
    cache.set(get_password_reset_verified_key(email), True, ttl_seconds)


def is_email_verified_for_password_reset(email: str) -> bool:
    return bool(cache.get(get_password_reset_verified_key(email)))


def clear_email_verified_for_password_reset(email: str) -> None:
    cache.delete(get_password_reset_verified_key(email))
