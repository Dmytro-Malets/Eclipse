import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.models import User
from services.space_weather_service import space_weather_service

logger = logging.getLogger(__name__)

async def cmd_spaceweather(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view space weather information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    await show_space_weather(message, user)

async def show_space_weather(message: Message, user: User):
    processing_msg = await message.answer("Loading space weather data...")

    try:
        weather_data = await space_weather_service.get_space_weather(user)

        if not weather_data:
            await processing_msg.edit_text(
                "❌ <b>Error loading space weather data</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        keyboard = create_spaceweather_keyboard(user.user_id)
        formatted_message = space_weather_service.format_space_weather_message(weather_data)

        await processing_msg.edit_text(formatted_message, reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error showing space weather for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def create_spaceweather_keyboard(user_id: int) -> InlineKeyboardMarkup:
    IMPACTS_URL = "https://www.swpc.noaa.gov/impacts"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"spaceweather_refresh:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="Technological and Health Impacts",
                url=IMPACTS_URL
            )
        ]
    ])
    return keyboard

async def spaceweather_refresh_callback(callback: CallbackQuery, user: User):
    try:
        callback_user_id = int(callback.data.split(':')[1])

        if callback_user_id != user.user_id:
            await callback.answer("This button is not for you", show_alert=True)
            return

        await callback.answer("Refreshing data...")

        weather_data = await space_weather_service.get_space_weather(user)

        if not weather_data:
            await callback.answer("Unable to refresh data", show_alert=True)
            return

        keyboard = create_spaceweather_keyboard(user.user_id)
        formatted_message = space_weather_service.format_space_weather_message(weather_data)

        try:
            await callback.message.edit_text(formatted_message, reply_markup=keyboard, disable_web_page_preview=True)
            await callback.answer()
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await callback.answer()
            else:
                logger.error(f"Error editing message: {edit_error}")
                await callback.answer("Error updating", show_alert=True)

    except Exception as e:
        logger.error(f"Error in space weather refresh callback: {e}")
        await callback.answer("Error occurred", show_alert=True)

def register_space_weather_handlers(dp: Dispatcher):
    dp.message.register(cmd_spaceweather, Command("spaceweather"))
    dp.callback_query.register(spaceweather_refresh_callback, F.data.startswith("spaceweather_refresh:"))