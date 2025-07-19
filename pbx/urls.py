from django.contrib import admin
from django.urls import include, path
from .admin import ApplyChangesView

urlpatterns = [
    path("admin/apply", ApplyChangesView.as_view(), name="apply_changes"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
]
