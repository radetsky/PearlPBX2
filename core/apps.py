from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Must stay a local import: apps.py is executed while Django is still
        # populating the app registry, and core.checks imports core.models at
        # module level (top-level import per project convention) — importing
        # it here, before that, raises AppRegistryNotReady.
        from core import checks  # noqa: F401
