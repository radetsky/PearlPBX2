from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.api.views import lists, calls, recordings

router = DefaultRouter()
router.register("blacklist", lists.BlacklistViewSet, basename="blacklist")
router.register("whitelist", lists.WhitelistViewSet, basename="whitelist")
router.register("contacts", lists.ContactViewSet, basename="contacts")
router.register("lists", lists.CustomListViewSet, basename="lists")

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path(
        "lists/<uuid:pk>/entries/<uuid:entry_pk>/",
        lists.CustomListEntryDetailView.as_view(),
        name="lists_entry_detail",
    ),
    path("calls/originate/", calls.OriginateView.as_view(), name="calls_originate"),
    path("calls/conference/", calls.ConferenceView.as_view(), name="calls_conference"),
    path(
        "recordings/<str:uniqueid>/",
        recordings.RecordingByUniqueidView.as_view(),
        name="recording_by_uniqueid",
    ),
    path("", include(router.urls)),
]
