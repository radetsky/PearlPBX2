from django.core.management.base import BaseCommand

from apps.webhooks.sync import sync_webhooks_config


class Command(BaseCommand):
    help = "Push the active webhooks configuration to Redis (webhooks:config key)."

    def handle(self, *args, **options):
        sync_webhooks_config()
        self.stdout.write(self.style.SUCCESS("Webhooks config synced to Redis."))
