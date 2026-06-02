import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import MusicOnHold, Queue, QueueMember, SIPUser


class Command(BaseCommand):
    help = (
        "Add SIP users to a queue from a CSV file. "
        "Required column: username. "
        "Creates the queue if it does not exist."
    )

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to the CSV file")
        parser.add_argument(
            "--queue",
            type=str,
            required=True,
            help="Queue name to add members to (e.g. Support)",
        )
        parser.add_argument(
            "--penalty",
            type=int,
            default=0,
            help="Penalty value for all added members (default: 0)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be done without making changes",
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        queue_name = kwargs["queue"]
        penalty = kwargs["penalty"]
        dry_run = kwargs["dry_run"]

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if "username" not in (reader.fieldnames or []):
                raise CommandError(
                    f"CSV must have a 'username' column. Found: {reader.fieldnames}"
                )
            rows = list(reader)

        queue = Queue.objects.filter(name=queue_name).first()

        if queue is None:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f"  [CREATE QUEUE] '{queue_name}' (dry-run)")
                )
            else:
                moh = MusicOnHold.objects.filter(name="default").first() or MusicOnHold.objects.first()
                if moh is None:
                    raise CommandError(
                        "No MusicOnHold entries found. "
                        "Create at least one Music on Hold class in the admin before running this command."
                    )
                queue = Queue.objects.create(
                    name=queue_name,
                    music_class=moh,
                    strategy="ringall",
                )
                self.stdout.write(self.style.SUCCESS(f"  Created queue '{queue_name}'"))
        else:
            self.stdout.write(f"  Using existing queue '{queue_name}'")

        created = skipped = 0
        errors = []

        for line_num, row in enumerate(rows, start=2):
            username = row.get("username", "").strip()
            if not username:
                errors.append((line_num, "empty username"))
                continue

            sip_user = SIPUser.objects.filter(username=username).first()
            if sip_user is None:
                errors.append((line_num, f"{username!r}: SIPUser not found"))
                continue

            interface = sip_user.standard_pjsip_user
            member_name = sip_user.name

            if dry_run:
                exists = queue is not None and QueueMember.objects.filter(
                    queue__name=queue_name, interface=interface
                ).exists()
                if exists:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(f"  [SKIP]   {username} — already a member")
                    )
                else:
                    created += 1
                    self.stdout.write(f"  [ADD]    {username} ({member_name})")
                continue

            with transaction.atomic():
                _, was_created = QueueMember.objects.get_or_create(
                    queue=queue,
                    interface=interface,
                    defaults={
                        "member_name": member_name,
                        "penalty": penalty,
                        "state_interface": interface,
                    },
                )

            if was_created:
                created += 1
            else:
                skipped += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN — no changes made ==="))

        if errors:
            self.stdout.write(self.style.ERROR("\nWarnings / Errors:"))
            for line_num, reason in errors:
                self.stdout.write(f"  line {line_num}: {reason}")

        summary = (
            f"\nSummary: added {created}, skipped {skipped}, errors {len(errors)}"
        )
        self.stdout.write(
            self.style.WARNING(summary) if dry_run else self.style.SUCCESS(summary)
        )
