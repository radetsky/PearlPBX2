from django.conf import settings
from django.core.checks import Error, register

from core.models import DialplanContext


@register()
def check_conference_context_exists(app_configs, **kwargs):
    context_name = settings.PEARLPBX_CONFERENCE_CONTEXT
    try:
        exists = DialplanContext.objects.filter(name=context_name).exists()
    except Exception:
        # DB not reachable yet or migrations not applied (e.g. during initial
        # `migrate`/`makemigrations` on a fresh database) — nothing to check yet.
        return []

    if exists:
        return []

    return [
        Error(
            f'DialplanContext "{context_name}" (settings.PEARLPBX_CONFERENCE_CONTEXT) does not exist.',
            hint=(
                "POST /api/v1/calls/conference/ lands each leg into this context via "
                "ConfBridge. Run migrations (creates the default 'conference' context) "
                "or create a matching DialplanContext/DialplanExtension manually if "
                "PEARLPBX_CONFERENCE_CONTEXT was changed from its default."
            ),
            id="core.E001",
        )
    ]
