"""
Application-level file encryption with envelope encryption (AES-256-GCM).

Each file gets its own random 256-bit DEK (data encryption key). The DEK is
wrapped with the master key (`FILE_ENCRYPTION_KEY`, also AES-256-GCM) and
prepended to the ciphertext as a header. The full on-disk layout is:

    [4 bytes magic 'MTE1']
    [1 byte version (=1)]
    [12 bytes DEK-wrapping nonce]
    [16 bytes DEK-wrapping AES-GCM tag]
    [60 bytes wrapped DEK   = 32 plaintext + 16 tag + 12 nonce above]
    [12 bytes payload nonce]
    [N bytes payload ciphertext + 16 byte AES-GCM tag at the end]

Total overhead per file: 4 + 1 + 12 + 16 + 32 + 12 + 16 = 93 bytes header
plus 16-byte AES-GCM tag on the payload.

Properties:
- Compromise of one DEK leaks one file, not all of them.
- Master key can be rotated by re-wrapping DEKs only (no payload re-encryption).
- AES-256-GCM provides authenticated encryption (integrity + confidentiality).
"""

from __future__ import annotations

import io
import os
import struct
from typing import IO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

MAGIC = b"MTE1"  # MIG Tender Encryption v1
VERSION = 1
HEADER_FMT = "!4sB12s16s32s12s"  # magic, ver, wrap_nonce, wrap_tag, wrapped_dek, payload_nonce
HEADER_SIZE = struct.calcsize(HEADER_FMT)
DEK_SIZE = 32  # 256 bits
NONCE_SIZE = 12  # AES-GCM standard
TAG_SIZE = 16


def _master_key() -> bytes:
    """Returns master key as raw bytes. Settings stores it base64-encoded."""
    import base64

    raw = getattr(settings, "FILE_ENCRYPTION_KEY", None)
    if not raw:
        raise RuntimeError(
            "FILE_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"import secrets, base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
        )
    if isinstance(raw, str):
        raw = raw.encode()
    key = base64.urlsafe_b64decode(raw)
    if len(key) != 32:
        raise RuntimeError(
            f"FILE_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(key)}."
        )
    return key


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Wrap plaintext into the envelope-encrypted format described in the module docstring."""
    master = _master_key()
    dek = AESGCM.generate_key(bit_length=256)

    # Wrap the DEK
    wrap_nonce = os.urandom(NONCE_SIZE)
    wrapped_with_tag = AESGCM(master).encrypt(wrap_nonce, dek, None)
    # AESGCM.encrypt appends 16-byte tag at the end → split for clarity
    wrapped_dek = wrapped_with_tag[:-TAG_SIZE]
    wrap_tag = wrapped_with_tag[-TAG_SIZE:]

    # Encrypt payload
    payload_nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(dek).encrypt(payload_nonce, plaintext, None)

    header = struct.pack(
        HEADER_FMT,
        MAGIC,
        VERSION,
        wrap_nonce,
        wrap_tag,
        wrapped_dek,
        payload_nonce,
    )
    return header + ciphertext


def decrypt_bytes(blob: bytes) -> bytes:
    """Reverse of encrypt_bytes(). Raises ValueError on tampered/invalid data."""
    master = _master_key()
    if len(blob) < HEADER_SIZE:
        raise ValueError("Encrypted blob too short.")

    magic, version, wrap_nonce, wrap_tag, wrapped_dek, payload_nonce = struct.unpack(
        HEADER_FMT, blob[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError(f"Bad magic header: {magic!r} (expected {MAGIC!r}).")
    if version != VERSION:
        raise ValueError(f"Unsupported encryption version: {version}.")

    dek = AESGCM(master).decrypt(wrap_nonce, wrapped_dek + wrap_tag, None)
    return AESGCM(dek).decrypt(payload_nonce, blob[HEADER_SIZE:], None)


def is_encrypted(blob: bytes) -> bool:
    return len(blob) >= 4 and blob[:4] == MAGIC


class EncryptedFileSystemStorage(FileSystemStorage):
    """
    Drop-in replacement for FileSystemStorage that transparently
    encrypts files on write and decrypts on read.

    Files written through this storage are unreadable without the master key
    (FILE_ENCRYPTION_KEY). Direct serving of /media/* via nginx is therefore
    pointless — files MUST be served via Django views that go through this
    storage's open() method (auth-gated download endpoints).

    Backwards compatibility: open() falls back to plaintext if the file is
    not in the encrypted format (no MAGIC header). This lets us migrate old
    files gradually.
    """

    def _save(self, name: str, content) -> str:
        # Read all bytes, encrypt, then write via parent
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except Exception:
                pass
        plaintext = content.read()
        encrypted = encrypt_bytes(plaintext)
        return super()._save(name, ContentFile(encrypted))

    def _open(self, name: str, mode: str = "rb") -> IO[bytes]:
        # Read from disk, decrypt if encrypted, return BytesIO
        raw_file = super()._open(name, mode="rb")
        try:
            blob = raw_file.read()
        finally:
            raw_file.close()

        if is_encrypted(blob):
            data = decrypt_bytes(blob)
        else:
            # Legacy/plaintext file (pre-encryption migration). Pass through.
            data = blob

        return ContentFile(data, name=name)

    def size(self, name: str) -> int:
        # The on-disk size is encrypted-bytes count; for client-facing size we
        # could decrypt and measure, but that's expensive. We return the disk
        # size — it's an upper bound on plaintext size (within ~93 bytes).
        return super().size(name)
