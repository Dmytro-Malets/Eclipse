import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.models import User
from services.iss_service import iss_service

logger = logging.getLogger(__name__)

async def cmd_iss(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view ISS information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    await show_iss_info(message, user)

async def iss_button_handler(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view ISS information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    await show_iss_info(message, user)

async def show_iss_info(message: Message, user: User):
    processing_msg = await message.answer("Calculating ISS data...")

    try:
        iss_data = await iss_service.get_iss_data(user)

        if not iss_data:
            await processing_msg.edit_text(
                "❌ <b>Error loading ISS information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        keyboard = create_iss_keyboard(user.user_id)
        formatted_message = iss_service.format_iss_message(iss_data)

        await processing_msg.edit_text(formatted_message, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing ISS info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def create_iss_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"iss_refresh:{user_id}"
            )
        ]
    ])
    return keyboard

async def iss_refresh_callback(callback: CallbackQuery, user: User):
    try:
        callback_user_id = int(callback.data.split(':')[1])

        if callback_user_id != user.user_id:
            await callback.answer("❌ This button is not for you!", show_alert=True)
            return

        await callback.answer("🔄 Refreshing data...")

        iss_data = await iss_service.get_iss_data(user)

        if not iss_data:
            await callback.answer("❌ Unable to refresh data", show_alert=True)
            return

        keyboard = create_iss_keyboard(user.user_id)
        formatted_message = iss_service.format_iss_message(iss_data)

        try:
            await callback.message.edit_text(formatted_message, reply_markup=keyboard)
            await callback.answer()
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await callback.answer()
            else:
                logger.error(f"Error editing message: {edit_error}")
                await callback.answer("❌ Error updating", show_alert=True)

    except Exception as e:
        logger.error(f"Error in ISS refresh callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

def register_iss_handlers(dp: Dispatcher):
    dp.message.register(cmd_iss, Command("iss"))
    dp.message.register(iss_button_handler, F.text == "🛰 ISS")
    dp.callback_query.register(iss_refresh_callback, F.data.startswith("iss_refresh:"))