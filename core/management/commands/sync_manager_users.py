from django.core.management.base import BaseCommand

from core.models import ManagerUsers

# Must mirror the built-in service users defined in
# ansible/roles/pearlpbx2/templates/manager.conf.j2 so that regenerating
# manager.conf via the Django "Apply Changes" action does not drop AMI
# access for the callback, dashboard and fastagi services.
SERVICE_SCOPES = {
    "callback": {
        "read": "system,call,agent",
        "write": "system,call,originate",
    },
    "dashboard_listener": {
        "read": "system,call,log,agent,user,reporting,cdr,dialplan",
        "write": "system,call,agent,reporting",
    },
    "fastagi": {
        "read": "system,call,agent,reporting",
        "write": "reporting",
    },
}


class Command(BaseCommand):
    help = (
        "Create or update the AMI manager user records for PearlPBX2's "
        "built-in services (callback, dashboard, fastagi). Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--callback-secret", required=True)
        parser.add_argument("--dashboard-secret", required=True)
        parser.add_argument("--fastagi-secret", required=True)

    def handle(self, *args, **options):
        secrets = {
            "callback": options["callback_secret"],
            "dashboard_listener": options["dashboard_secret"],
            "fastagi": options["fastagi_secret"],
        }

        for username, scope in SERVICE_SCOPES.items():
            _, created = ManagerUsers.objects.update_or_create(
                username=username,
                defaults={
                    "secret": secrets[username],
                    "read": scope["read"],
                    "write": scope["write"],
                    "deny": "0.0.0.0/0.0.0.0",
                    "permit": "127.0.0.1/255.255.255.255",
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{verb} manager user '{username}'"))
