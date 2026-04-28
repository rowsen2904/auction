"""
Re-encrypt all existing on-disk media files in place.

Run once after deploying the encryption changes. Walks MEDIA_ROOT, reads each
file, and rewrites it through EncryptedFileSystemStorage.encrypt_bytes().
Files already encrypted (MAGIC header) are skipped.

Idempotent: safe to run multiple times.

Usage:
    python manage.py encrypt_existing_files            # encrypt
    python manage.py encrypt_existing_files --dry-run  # report only
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from helpers.encrypted_storage import encrypt_bytes, is_encrypted


class Command(BaseCommand):
    help = "Encrypt every plaintext file under MEDIA_ROOT in place."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be done without modifying files.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        root = Path(settings.MEDIA_ROOT)
        if not root.exists():
            self.stdout.write(self.style.WARNING(f"MEDIA_ROOT {root} doesn't exist."))
            return

        encrypted = 0
        skipped = 0
        errors = 0

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if is_encrypted(data):
                    skipped += 1
                    continue

                if dry:
                    self.stdout.write(f"  WOULD ENCRYPT  {path.relative_to(root)}")
                    encrypted += 1
                    continue

                ciphertext = encrypt_bytes(data)
                # write to temp file in same dir, then rename for atomicity
                tmp = path.with_suffix(path.suffix + ".enc.tmp")
                with open(tmp, "wb") as f:
                    f.write(ciphertext)
                os.replace(tmp, path)
                encrypted += 1
                self.stdout.write(f"  encrypted      {path.relative_to(root)}")
            except Exception as e:
                errors += 1
                self.stderr.write(self.style.ERROR(f"  FAILED {path}: {e}"))

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. encrypted={encrypted} skipped={skipped} errors={errors} "
                f"(dry-run={dry})"
            )
        )
