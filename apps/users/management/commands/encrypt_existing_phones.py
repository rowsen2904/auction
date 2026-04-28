"""
Re-encrypt phone_number values for existing Broker / Developer rows.

Field-level encryption (helpers/encrypted_fields.EncryptedCharField) only
encrypts on save. Pre-existing plaintext phones in the DB stay plaintext
until rewritten. This command rewrites them by saving each row, which goes
through get_prep_value() and produces a ciphertext blob.

Idempotent: a phone that already looks encrypted (FE1: prefix when decoded)
is left alone.

Usage:
    python manage.py encrypt_existing_phones
    python manage.py encrypt_existing_phones --dry-run
"""

from __future__ import annotations

import base64

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.models import Broker, Developer
from helpers.encrypted_fields import MAGIC


def _looks_encrypted(value: str | None) -> bool:
    if not value:
        return False
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception:
        return False
    return raw.startswith(MAGIC)


class Command(BaseCommand):
    help = "Encrypt plaintext phone_number values on Broker and Developer rows."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]

        for label, qs in (("Broker", Broker.objects.all()), ("Developer", Developer.objects.all())):
            updated = skipped = 0
            for obj in qs:
                # Read directly from DB column — bypass field's from_db_value decryption.
                from django.db import connection

                table = obj._meta.db_table
                with connection.cursor() as c:
                    c.execute(
                        f"SELECT phone_number FROM {table} WHERE id = %s", [obj.pk]
                    )
                    raw = c.fetchone()[0]
                if _looks_encrypted(raw):
                    skipped += 1
                    continue
                if dry:
                    self.stdout.write(
                        f"  WOULD ENCRYPT  {label}#{obj.pk} phone={raw!r}"
                    )
                    updated += 1
                    continue
                with transaction.atomic():
                    # Reload via ORM (model thinks raw is legacy plaintext, decrypt
                    # passes it through). Then save — get_prep_value encrypts.
                    obj.phone_number = raw or ""
                    obj.save(update_fields=["phone_number"])
                updated += 1
                self.stdout.write(f"  encrypted      {label}#{obj.pk}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"{label}: encrypted={updated} skipped={skipped} (dry-run={dry})"
                )
            )
