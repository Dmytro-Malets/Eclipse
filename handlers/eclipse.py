import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from database.models import User
from services.eclipse_service import eclipse_service

logger = logging.getLogger(__name__)

async def cmd_eclipse(message: Message, user: User):
    await show_eclipses(message, user)

async def btn_eclipse(message: Message, user: User):
    await show_eclipses(message, user)

async def show_eclipses(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view eclipses information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    processing_msg = await message.answer("Calculating eclipses data...")

    try:
        eclipse_data = await eclipse_service.get_upcoming_eclipses(user, 5)

        if not eclipse_data:
            await processing_msg.edit_text(
                "❌ <b>Error calculating eclipses information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        formatted_message = eclipse_service.format_eclipse_message(eclipse_data)

        await processing_msg.edit_text(formatted_message)

    except Exception as e:
        logger.error(f"Error showing eclipses info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def register_eclipse_handlers(dp: Dispatcher):
    dp.message.register(cmd_eclipse, Command("eclipses"))
    dp.message.register(btn_eclipse, F.text == "🌑 Eclipses")