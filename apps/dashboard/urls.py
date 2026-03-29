from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.new_dashboard, name="dashboard"),
    path("live/", views.new_dashboard, name="new_dashboard"),
    path("old/", views.operator_panel, name="operator_panel"),
    path("ulines/", views.uline_monitor, name="uline_monitor"),
    path("ulines/flush/", views.uline_flush, name="uline_flush"),
    # Queues
    path("api/queues/", views.get_all_queues, name="get_all_queues"),
    path("api/queues/<str:queue_name>/", views.get_queue_state, name="get_queue_state"),
    # Channels
    path("api/channels/", views.get_all_channels, name="get_all_channels"),
    path(
        "api/channels/type/<str:channel_type>/",
        views.get_channels_by_type,
        name="get_channels_by_type",
    ),
    path("api/channels/<path:channel_name>/", views.get_channel, name="get_channel"),
    path("api/calls/active/", views.get_active_calls, name="get_active_calls"),
    path("api/endpoints/", views.get_sip_endpoints, name="get_sip_endpoints"),
    path("api/channels/hangup/", views.hangup_channel, name="hangup_channel"),
]
