import re

from django.core.management.base import BaseCommand

from core.models import QueueMember, SIPPeer, SIPUser

INTERFACE_RE = re.compile(r"^PJSIP/(.+)$")


class Command(BaseCommand):
    help = (
        "Remove QueueMember rows whose interface (PJSIP/<name>) matches "
        "neither an existing SIPUser nor an existing SIPPeer. Handles rows "
        "orphaned before core.signals.on_sipuser_post_delete existed, or "
        "typed by hand in the admin."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be removed without making changes",
        )

    def handle(self, *args, **kwargs):
        dry_run = kwargs["dry_run"]

        usernames = set(SIPUser.objects.values_list("username", flat=True))
        peer_names = set(SIPPeer.objects.values_list("name", flat=True))

        orphans = []
        for member in QueueMember.objects.all():
            match = INTERFACE_RE.match(member.interface)
            if not match:
                continue
            name = match.group(1)
            if name in usernames or name in peer_names:
                continue
            orphans.append(member)

        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphaned queue members found."))
            return

        for member in orphans:
            label = f"  {member.interface} (queue: {member.queue.name})"
            if dry_run:
                self.stdout.write(self.style.WARNING(f"[WOULD REMOVE] {label}"))
            else:
                self.stdout.write(f"[REMOVED] {label}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\n=== DRY RUN — {len(orphans)} row(s) would be removed ===")
            )
            return

        count = len(orphans)
        QueueMember.objects.filter(pk__in=[m.pk for m in orphans]).delete()
        self.stdout.write(self.style.SUCCESS(f"\nRemoved {count} orphaned queue member(s)."))
