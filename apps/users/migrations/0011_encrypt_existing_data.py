"""
Auto-encrypt pre-existing PII at deploy time.

Runs on `manage.py migrate`. Idempotent — looks for the encryption MAGIC
header (FE1: for fields, MTE1 for files) and skips already-encrypted rows /
files. Reverse migration is a no-op.

What it covers:
  1. Broker.phone_number   — rewritten through the encrypted field.
  2. Developer.phone_number — same.
  3. Files under MEDIA_ROOT — rewritten in-place via envelope encryption.

If FILE_ENCRYPTION_KEY isn't set anywhere, settings will auto-bootstrap
one into <BASE_DIR>/.file_encryption_key on first import. So this
migration "just works" on a fresh deploy with zero manual steps.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from django.conf import settings
from django.db import migrations


def _looks_field_encrypted(value: str | None) -> bool:
    if not value:
        return False
    try:
        from helpers.encrypted_fields import MAGIC

        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception:
        return False
    return raw.startswith(MAGIC)


def _encrypt_phones(apps, schema_editor):
    from django.db import connection

    from helpers.encrypted_fields import _encrypt_str

    for table in ("users_broker", "users_developer"):
        with connection.cursor() as c:
            c.execute(f"SELECT id, phone_number FROM {table}")
            rows = c.fetchall()

        for row_id, raw in rows:
            if _looks_field_encrypted(raw):
                continue
            encrypted = _encrypt_str(raw or "") or ""
            with connection.cursor() as c:
                c.execute(
                    f"UPDATE {table} SET phone_number = %s WHERE id = %s",
                    [encrypted, row_id],
                )


def _encrypt_files(apps, schema_editor):
    from helpers.encrypted_storage import encrypt_bytes, is_encrypted

    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if is_encrypted(data):
            continue
        try:
            ciphertext = encrypt_bytes(data)
            tmp = path.with_suffix(path.suffix + ".enc.tmp")
            with open(tmp, "wb") as f:
                f.write(ciphertext)
            os.replace(tmp, path)
        except Exception:
            # Don't block the migration on one bad file. Log via stderr.
            import sys

            print(f"  [encryption migration] skipped {path}", file=sys.stderr)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_alter_broker_phone_number_and_more"),
    ]

    operations = [
        migrations.RunPython(_encrypt_phones, migrations.RunPython.noop),
        migrations.RunPython(_encrypt_files, migrations.RunPython.noop),
    ]
