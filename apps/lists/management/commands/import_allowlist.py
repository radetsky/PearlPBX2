import csv

from django.core.management.base import BaseCommand, CommandError

from core.models import Whitelist


class Command(BaseCommand):
    help = "Import allowlist from CSV (columns: callerid, name). 'name' is stored as reason."

    def add_arguments(self, parser):
        parser.add_argument("csv_file", help="Path to the CSV file")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update reason for existing entries (default: skip duplicates)",
        )

    def handle(self, *args, **options):
        path = options["csv_file"]
        update = options["update"]
        created = updated = skipped = errors = 0

        try:
            f = open(path, newline="", encoding="utf-8")
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        with f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "callerid" not in reader.fieldnames:
                raise CommandError("CSV must have a 'callerid' column header.")

            for row_num, row in enumerate(reader, start=2):
                callerid = row.get("callerid", "").strip()
                name = row.get("name", "").strip()

                if not callerid:
                    self.stderr.write(f"Row {row_num}: empty callerid — skipped")
                    errors += 1
                    continue

                try:
                    obj, was_created = Whitelist.objects.get_or_create(
                        callerid=callerid,
                        defaults={"reason": name},
                    )
                    if was_created:
                        created += 1
                    elif update:
                        obj.reason = name
                        obj.save(update_fields=["reason"])
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    self.stderr.write(f"Row {row_num}: {callerid!r} — {e}")
                    errors += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Allowlist import done. "
                f"Created: {created}, updated: {updated}, skipped: {skipped}, errors: {errors}"
            )
        )
