import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import RoutingTable, SIPTransport, SIPUser


class Command(BaseCommand):
    help = (
        "Import SIP users from a PearlPBX1 migration CSV. "
        "Required columns: username, name, secret, nat (true/false)."
    )

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to the CSV file")
        parser.add_argument(
            "--transport",
            type=str,
            required=True,
            help="SIPTransport name to assign to all imported users (e.g. transport-udp)",
        )
        parser.add_argument(
            "--routing-table",
            type=str,
            default=settings.PEARLPBX_DEFAULT_ROUTING_TABLE,
            help=(
                "RoutingTable name to assign to all imported users. "
                "Defaults to PEARLPBX_DEFAULT_ROUTING_TABLE "
                f"(currently '{settings.PEARLPBX_DEFAULT_ROUTING_TABLE}')."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be imported without making changes",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing users instead of skipping them",
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        transport_name = kwargs["transport"]
        routing_table_name = kwargs["routing_table"]
        dry_run = kwargs["dry_run"]
        update = kwargs["update"]

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        try:
            transport = SIPTransport.objects.get(name=transport_name)
        except SIPTransport.DoesNotExist:
            available = list(SIPTransport.objects.values_list("name", flat=True))
            raise CommandError(
                f"SIPTransport '{transport_name}' not found. "
                f"Available: {available}"
            )

        try:
            routing_table = RoutingTable.objects.get(name=routing_table_name)
        except RoutingTable.DoesNotExist:
            available = list(RoutingTable.objects.values_list("name", flat=True))
            raise CommandError(
                f"RoutingTable '{routing_table_name}' not found. "
                f"Available: {available}"
            )

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = {"username", "name", "secret", "nat"}
            if not required.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"CSV must have columns: {required}. Found: {reader.fieldnames}"
                )
            rows = list(reader)

        created = updated = skipped = 0
        errors = []

        for line_num, row in enumerate(rows, start=2):
            username = row.get("username", "").strip()
            name = row.get("name", "").strip()
            secret = row.get("secret", "").strip()
            nat_raw = row.get("nat", "false").strip().lower()

            if not username:
                errors.append((line_num, "empty username"))
                continue
            if not secret:
                errors.append((line_num, f"{username!r}: empty secret"))
                continue

            nat = nat_raw in ("true", "1", "yes")

            defaults = {
                "name": name or username,
                "secret": secret,
                "transport": transport,
                "nat": nat,
                "extension": username,
                "routing_table": routing_table,
            }

            if dry_run:
                exists = SIPUser.objects.filter(username=username).exists()
                if exists:
                    if update:
                        updated += 1
                        self.stdout.write(f"  [UPDATE] {username} — {name}")
                    else:
                        skipped += 1
                        self.stdout.write(
                            self.style.WARNING(f"  [SKIP]   {username} — already exists")
                        )
                else:
                    created += 1
                    self.stdout.write(f"  [CREATE] {username} — {name}")
                continue

            with transaction.atomic():
                if update:
                    _, was_created = SIPUser.objects.update_or_create(
                        username=username,
                        defaults=defaults,
                    )
                else:
                    exists = SIPUser.objects.filter(username=username).exists()
                    if exists:
                        skipped += 1
                        continue
                    SIPUser.objects.create(username=username, **defaults)
                    was_created = True

            if was_created:
                created += 1
            else:
                updated += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN — no changes made ==="))

        if errors:
            self.stdout.write(self.style.ERROR("\nErrors:"))
            for line_num, reason in errors:
                self.stdout.write(f"  line {line_num}: {reason}")

        summary = (
            f"\nSummary: created {created}, updated {updated}, "
            f"skipped {skipped}, errors {len(errors)}"
        )
        self.stdout.write(
            self.style.WARNING(summary) if dry_run else self.style.SUCCESS(summary)
        )
