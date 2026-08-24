from django.conf import settings
from django.core.management.base import BaseCommand

from core.ami import AsteriskManagementInterface
from core.conf import get_users_excluded_from_pjsip
from pbx.admin import ApplyChangesView


class Command(BaseCommand):
    help = (
        "Regenerate Asterisk configuration files from the database and reload "
        "Asterisk — the non-interactive equivalent of clicking Apply Changes "
        "in the admin. Hard-restarts Asterisk over AMI by default; pass --soft "
        "to reload individual modules instead."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--soft",
            action="store_true",
            help="Soft-reload individual modules instead of a hard 'core restart now'.",
        )

    def handle(self, *args, **options):
        view = ApplyChangesView()
        cfgfiles = view._build_cfgfiles()
        view.apply_changes(cfgfiles)
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(cfgfiles)} configuration file(s).")
        )

        skipped = get_users_excluded_from_pjsip()
        if skipped.exists():
            names = ", ".join(u.username for u in skipped)
            self.stdout.write(
                self.style.WARNING(
                    f"{skipped.count()} user(s) skipped in pjsip.conf "
                    f"(missing transport or routing table): {names}"
                )
            )

        if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
            self.stdout.write("DEVMODE_WITHOUT_ASTERISK — skipping AMI reload.")
            return

        with AsteriskManagementInterface() as ami:
            if options["soft"]:
                ami.soft_reload()
                self.stdout.write(self.style.SUCCESS("Asterisk soft-reloaded."))
            else:
                ami.restart()
                self.stdout.write(self.style.SUCCESS("Asterisk hard-restarted."))
