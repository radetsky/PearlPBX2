from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.i18n import set_language
from django.views.static import serve
from .admin import ApplyChangesView

urlpatterns = [
    path("i18n/set-language/", set_language, name="set_language"),
    path("admin/apply", ApplyChangesView.as_view(), name="apply_changes"),
    path("admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
    path("reports/", include("apps.reports.urls")),
    path("lists/", include("apps.lists.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Serve MOH files (authenticated users only — same tree is writable by admins)
MOH_ROOT = (
    "/var/lib/asterisk/moh/"
    if settings.DEVMODE != settings.DEVMODE_WITHOUT_ASTERISK
    else "moh/"
)
urlpatterns += [
    path("moh/<path:path>", login_required(serve), {"document_root": MOH_ROOT}),
]
