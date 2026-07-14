from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.api.views import lists

router = DefaultRouter()
router.register("blacklist", lists.BlacklistViewSet, basename="blacklist")
router.register("whitelist", lists.WhitelistViewSet, basename="whitelist")
router.register("contacts", lists.ContactViewSet, basename="contacts")
router.register("lists", lists.CustomListViewSet, basename="lists")

urlpatterns = [
    path(
        "lists/<uuid:pk>/entries/<uuid:entry_pk>/",
        lists.CustomListEntryDetailView.as_view(),
        name="lists_entry_detail",
    ),
    path("", include(router.urls)),
]
