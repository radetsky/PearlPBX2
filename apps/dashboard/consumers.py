import asyncio
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AsteriskEventsConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer для реалтайм подій Asterisk"""

    async def connect(self):
        """Підключення клієнта"""
        # Перевірка аутентифікації (опціонально)
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        await self.accept()
        logger.info(f"WebSocket connected: {self.scope['user']}")

        # Підключаємось до Redis Pub/Sub
        try:
            self.redis = await redis.from_url(settings.REDIS_URL)
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe("asterisk:events")

            # Запускаємо прослуховування в окремому таску
            self.listen_task = asyncio.create_task(self.listen_redis())

            logger.info("Subscribed to Redis Pub/Sub")
        except Exception as e:
            logger.error(f"Error connecting to Redis: {e}")
            await self.close()

    async def listen_redis(self):
        """Слухаємо події з Redis Pub/Sub"""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    # ВАЖЛИВО: Перевіряємо тип даних
                    data = message["data"]

                    # Якщо data це bytes - декодуємо
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Відправляємо як TEXT, не bytes
                    await self.send(text_data=data)
                    # Перші 100 символів
                    logger.debug(f"Sent event: {data[:100]}...")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Error in Redis listener: {e}", exc_info=True)

    async def disconnect(self, close_code):
        """Відключення клієнта"""
        logger.info(
            f"WebSocket disconnected: {self.scope['user']} (code: {close_code})"
        )

        # Відписуємось і закриваємо з'єднання
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
