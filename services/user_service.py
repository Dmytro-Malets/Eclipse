from typing import Optional, Dict, Any
from sqlalchemy import select, update
from aiogram.types import User as TelegramUser
import logging
from database.database import get_db
from database.models import User


logger = logging.getLogger(__name__)

async def get_user(user_id: int) -> Optional[User]:
    async with get_db() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

async def create_user(telegram_user: TelegramUser) -> User:
    async with get_db() as session:
        user = User(
            user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )

        session.add(user)
        await session.flush()  # To get ID

        logger.info(f"👤 New user: {user.full_name} (ID: {user.user_id})")
        return user

async def get_or_create_user(telegram_user: TelegramUser) -> User:
    user = await get_user(telegram_user.id)

    if not user:
        user = await create_user(telegram_user)
    else:
        # We update the data if it has changed
        await update_user_info(user, telegram_user)

    return user

async def update_user_info(user: User, telegram_user: TelegramUser) -> User:
    async with get_db() as session:
        # Checking if the data has changed
        if (user.username != telegram_user.username or
                user.first_name != telegram_user.first_name or
                user.last_name != telegram_user.last_name):
            await session.execute(
                update(User)
                .where(User.user_id == user.user_id)
                .values(
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name
                )
            )

            logger.info(f"📝 User data updated {user.user_id}")

    return user

async def update_user_location(user: User, location_data: Dict[str, Any]) -> User:
    async with get_db() as session:
        await session.execute(
            update(User)
            .where(User.user_id == user.user_id)
            .values(
                city=location_data['name'],
                latitude=location_data['latitude'],
                longitude=location_data['longitude'],
                timezone=location_data['timezone']
            )
        )

        logger.info(f"📍 Location updated for user {user.user_id}: {location_data['name']}")

        user.city = location_data['name']
        user.latitude = location_data['latitude']
        user.longitude = location_data['longitude']
        user.timezone = location_data['timezone']

        return user