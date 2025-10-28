import redis.asyncio as redis
import json, logging
from typing import Dict, Any
from config.settings import REDIS_URL

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self):
        self.redis_url = REDIS_URL
        self.redis = None

    async def connect(self) -> bool:
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            logger.info("✅ Redis connected successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            return False

    async def disconnect(self):
        try:
            if self.redis:
                await self.redis.close()
                logger.info("🔌 Redis disconnected")
        except Exception as e:
            logger.error(f"❌ Error disconnecting Redis: {e}")

    async def set_temp_location(self, user_id: int, location_data: Dict[str, Any], expire_seconds: int = 600):
        try:
            key = f"temp_location:{user_id}"
            value = json.dumps(location_data)
            await self.redis.setex(key, expire_seconds, value)
            logger.info(f"📦 Stored temp location for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error storing temp location: {e}")
            raise

    async def get_temp_location(self, user_id: int) -> Dict[str, Any] | None:
        try:
            key = f"temp_location:{user_id}"
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"❌ Error getting temp location: {e}")
            return None

    async def delete_temp_location(self, user_id: int):
        try:
            key = f"temp_location:{user_id}"
            await self.redis.delete(key)
            logger.info(f"🗑️ Deleted temp location for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting temp location: {e}")

    async def set_iss_messages(self, user_id: int, chat_id: int, location_message_id: int, text_message_id: int):
        try:
            key = f"iss_messages:{user_id}:{chat_id}"
            value = json.dumps({
                "location_message_id": location_message_id,
                "text_message_id": text_message_id
            })
            await self.redis.set(key, value)
            logger.info(f"📦 Stored ISS messages for user {user_id} in chat {chat_id}")
        except Exception as e:
            logger.error(f"❌ Error storing ISS messages: {e}")

    async def get_iss_messages(self, user_id: int, chat_id: int) -> Dict[str, int] | None:
        try:
            key = f"iss_messages:{user_id}:{chat_id}"
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"❌ Error getting ISS messages: {e}")
            return None


redis_service = RedisService()