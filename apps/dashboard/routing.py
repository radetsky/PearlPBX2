# apps/dashboard/routing.py

from django.urls import path
from apps.dashboard.consumers import AsteriskEventsConsumer

websocket_urlpatterns = [
    path("ws/asterisk/", AsteriskEventsConsumer.as_asgi(), name="asterisk_events"),
]
