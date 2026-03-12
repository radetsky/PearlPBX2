import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Contact

_CALLERID_MAX = Contact._meta.get_field("callerid").max_length
_NAME_MAX = Contact._meta.get_field("name").max_length


class Command(BaseCommand):
    help = "Import contacts from a CSV file (columns: callerid, name)."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path", type=str, help="Path to the CSV file to import"
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update name for existing callerids instead of skipping them",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be imported without making changes",
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        update = kwargs["update"]
        dry_run = kwargs["dry_run"]

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        created = 0
        updated = 0
        skipped = 0
        errors = []

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            if not {"callerid", "name"}.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"CSV must have 'callerid' and 'name' columns. "
                    f"Found: {reader.fieldnames}"
                )

            rows = list(reader)

        for line_num, row in enumerate(rows, start=2):
            callerid = row.get("callerid", "").strip()
            name = row.get("name", "").strip()

            if not callerid:
                errors.append((line_num, "empty callerid"))
                continue
            if not name:
                errors.append((line_num, f"{callerid!r}: empty name"))
                continue
            if len(callerid) > _CALLERID_MAX:
                errors.append((line_num, f"{callerid!r}: callerid exceeds {_CALLERID_MAX} chars"))
                continue
            if len(name) > _NAME_MAX:
                errors.append((line_num, f"{callerid!r}: name exceeds {_NAME_MAX} chars"))
                continue

            if dry_run:
                exists = Contact.objects.filter(callerid=callerid).exists()
                if exists:
                    updated += 1 if update else 0
                    skipped += 0 if update else 1
                else:
                    created += 1
                continue

            with transaction.atomic():
                _, was_created = Contact.objects.update_or_create(
                    callerid=callerid,
                    defaults={"name": name} if update else {},
                )
            if was_created:
                created += 1
            elif update:
                updated += 1
            else:
                skipped += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN — no changes made ===\n"))

        if errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for line_num, reason in errors:
                self.stdout.write(f"  line {line_num}: {reason}")
            self.stdout.write("")

        summary = (
            f"Summary: created {created}, updated {updated}, "
            f"skipped {skipped}, errors {len(errors)}"
        )
        style = self.style.WARNING if dry_run else self.style.SUCCESS
        self.stdout.write(style(summary))
