import asyncio
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AsteriskEventsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time Asterisk events"""

    async def connect(self):
        """Client connection"""
        # Authentication check (optional)
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

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
