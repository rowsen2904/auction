"""
Field-level encryption for sensitive PII columns.

Uses AES-256-GCM with the same master key as file storage. Stored on disk
as base64(MAGIC || nonce || ciphertext || tag). Plaintext shorter than 1KB.

Caveats:
- Encrypted columns are NOT searchable / filterable / orderable in SQL.
- Each call to encrypt() yields a different ciphertext (random nonce), so
  unique constraints on encrypted columns are pointless.
- Compatible with non-encrypted legacy values: decrypt() will pass through
  any string that doesn't start with the MAGIC marker.

Use sparingly — only for fields that are:
  (a) genuinely sensitive (PII, secrets), AND
  (b) only ever read back as-is, never used in WHERE/ORDER/JOIN.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import models

from .encrypted_storage import _master_key  # reuse master key loader

MAGIC = b"FE1:"  # Field Encryption v1
NONCE_SIZE = 12


def _encrypt_str(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    if plaintext == "":
        return ""
    nonce = os.urandom(NONCE_SIZE)
    blob = AESGCM(_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(MAGIC + nonce + blob).decode("ascii")


def _decrypt_str(stored: str | None) -> str | None:
    if stored is None:
        return None
    if stored == "":
        return ""
    try:
        raw = base64.urlsafe_b64decode(stored.encode("ascii"))
    except Exception:
        # Not base64 — must be legacy plaintext.
        return stored
    if not raw.startswith(MAGIC):
        # Legacy plaintext that happened to be valid base64.
        return stored
    body = raw[len(MAGIC):]
    if len(body) < NONCE_SIZE:
        return stored
    nonce, ct = body[:NONCE_SIZE], body[NONCE_SIZE:]
    try:
        return AESGCM(_master_key()).decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        # Corrupted or wrong key. Don't crash the whole queryset; surface raw.
        return stored


class EncryptedCharField(models.CharField):
    """
    Drop-in replacement for CharField. Plaintext on save → ciphertext in DB.
    Read returns plaintext.

    Note: max_length must accommodate the base64-encoded ciphertext, which
    is roughly ceil((4 + 12 + N + 16) / 3) * 4 bytes. For phone numbers
    (~20 chars plaintext), 128 chars max_length is plenty.
    """

    description = "AES-256-GCM-encrypted CharField"

    def from_db_value(self, value, expression, connection):
        return _decrypt_str(value)

    def to_python(self, value):
        # Called on form deserialization & full_clean. Don't double-decrypt.
        return value if value is None else value

    def get_prep_value(self, value):
        if value is None:
            return None
        # Already-encrypted blob? Pass through (rare; happens during raw SQL).
        if isinstance(value, str) and value.startswith(
            base64.urlsafe_b64encode(MAGIC).decode("ascii").rstrip("=")
        ):
            return value
        return _encrypt_str(value if isinstance(value, str) else str(value))
