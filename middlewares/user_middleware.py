from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from typing import Callable, Dict, Any, Awaitable
import logging
from services.user_service import get_or_create_user

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """
    Middleware for automatic user registration
    Triggered on every message/callback
    """
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:

        telegram_user = None

        if isinstance(event, Message):
            telegram_user = event.from_user
        elif isinstance(event, CallbackQuery):
            telegram_user = event.from_user

        if telegram_user and not telegram_user.is_bot:
            try:
                user = await get_or_create_user(telegram_user)

                if user.is_banned:
                    logger.warning(f"🚫 Banned user {user.user_id} tried to write")
                    return  # We do not process messages from banned people.

                # Adding a user to the context for handlers
                data["user"] = user

            except Exception as e:
                logger.error(f"❌ Error in UserMiddleware: {e}")

        return await handler(event, data)

def setup_middlewares(dp):
    """Configures middleware for the dispatcher"""
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())
    logger.info("✅ UserMiddleware configured")