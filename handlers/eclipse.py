import logging
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from database.models import User
from services.eclipse_service import eclipse_service

logger = logging.getLogger(__name__)

async def cmd_eclipse(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view eclipse information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    processing_msg = await message.answer("Calculating eclipse data...")

    try:
        eclipse_data = await eclipse_service.get_upcoming_eclipses(user, 5)

        if not eclipse_data:
            await processing_msg.edit_text(
                "❌ <b>Error calculating eclipse information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        formatted_message = eclipse_service.format_eclipse_message(eclipse_data)

        await processing_msg.edit_text(formatted_message)

    except Exception as e:
        logger.error(f"Error showing eclipse info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def register_eclipse_handlers(dp: Dispatcher):
    dp.message.register(cmd_eclipse, Command("eclipse"))