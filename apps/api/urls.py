from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.api.views import (
    lists,
    calls,
    recordings,
    queues,
    sip_users,
    sip_transports,
    sip_peers,
    routing_tables,
    trunk_groups,
    config,
)

router = DefaultRouter()
router.register("blacklist", lists.BlacklistViewSet, basename="blacklist")
router.register("whitelist", lists.WhitelistViewSet, basename="whitelist")
router.register("contacts", lists.ContactViewSet, basename="contacts")
router.register("lists", lists.CustomListViewSet, basename="lists")
router.register("sip-users", sip_users.SIPUserViewSet, basename="sip-users")
router.register("sip-transports", sip_transports.SIPTransportViewSet, basename="sip-transports")
router.register("sip-peers", sip_peers.SIPPeerViewSet, basename="sip-peers")
router.register("routing-tables", routing_tables.RoutingTableViewSet, basename="routing-tables")
router.register("trunk-groups", trunk_groups.TrunkGroupViewSet, basename="trunk-groups")

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
    path("queues/members/", queues.QueueMemberListView.as_view(), name="queue_members"),
    path(
        "queues/members/pause/",
        queues.QueueMemberPauseView.as_view(),
        name="queue_member_pause",
    ),
    path(
        "recordings/<str:uniqueid>/",
        recordings.RecordingByUniqueidView.as_view(),
        name="recording_by_uniqueid",
    ),
    path("config/preview/", config.ConfigPreviewView.as_view(), name="config_preview"),
    path("config/apply/", config.ConfigApplyView.as_view(), name="config_apply"),
    path("", include(router.urls)),
]
