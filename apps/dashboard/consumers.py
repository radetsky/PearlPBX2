import asyncio
from urllib.parse import parse_qs

import redis.asyncio as redis
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@database_sync_to_async
def _user_for_token(key):
    from rest_framework.authtoken.models import Token

    try:
        return Token.objects.select_related("user").get(key=key).user
    except Token.DoesNotExist:
        return None


def _extract_token(scope):
    """Read an auth token from the ?token= query param or an
    Authorization: Token <key> header (browsers can't set custom WS headers,
    so the query param is the primary path)."""
    qs = parse_qs(scope.get("query_string", b"").decode())
    if qs.get("token"):
        return qs["token"][0]
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            parts = value.decode().split()
            if len(parts) == 2 and parts[0].lower() == "token":
                return parts[1]
    return None


class AsteriskEventsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time Asterisk events"""

    async def connect(self):
        """Client connection: Django session OR a valid auth token."""
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            token = _extract_token(self.scope)
            user = await _user_for_token(token) if token else None
            if user is None or not user.is_authenticated:
                await self.close()
                return
            self.scope["user"] = user

        await self.accept()
        logger.info(f"WebSocket connected: {self.scope['user']}")

        # Connect to Redis Pub/Sub
        try:
            self.redis = await redis.from_url(settings.REDIS_URL)
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe("asterisk:events")

            # Start listening in a separate task
            self.listen_task = asyncio.create_task(self.listen_redis())

            logger.info("Subscribed to Redis Pub/Sub")
        except Exception as e:
            logger.error(f"Error connecting to Redis: {e}")
            await self.close()

    async def listen_redis(self):
        """Listen for events from Redis Pub/Sub"""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    # Check data type
                    data = message["data"]

                    # If data is bytes - decode it
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Send as TEXT, not bytes
                    await self.send(text_data=data)
                    # First 100 characters
                    logger.debug(f"Sent event: {data[:100]}...")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Error in Redis listener: {e}", exc_info=True)

    async def disconnect(self, close_code):
        """Client disconnection"""
        logger.info(
            f"WebSocket disconnected: {self.scope['user']} (code: {close_code})"
        )

        # Unsubscribe and close connection
        if hasattr(self, "listen_task"):
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, "pubsub"):
            try:
                await self.pubsub.unsubscribe("asterisk:events")
                await self.pubsub.close()
            except Exception as e:
                logger.error(f"Error closing pubsub: {e}")

        if hasattr(self, "redis"):
            try:
                await self.redis.close()
            except Exception as e:
                logger.error(f"Error closing redis: {e}")
