import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import date, timedelta
from database.models import User
from services.night_sky_service import night_sky_service, get_user_today

logger = logging.getLogger(__name__)

async def cmd_night_sky(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view night sky information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_night_sky_info(message, user, user_today)

async def night_sky_button_handler(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view night sky information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_night_sky_info(message, user, user_today)

async def show_night_sky_info(message: Message, user: User, target_date: date):
    processing_msg = await message.answer("Calculating night sky data...")

    try:
        sky_data = await night_sky_service.get_night_sky_data(user, target_date)

        if not sky_data:
            await processing_msg.edit_text(
                "❌ <b>Error calculating night sky information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        keyboard = create_night_sky_navigation_keyboard(user.user_id, target_date, user)

        formatted_message = night_sky_service.format_night_sky_message(sky_data)

        await processing_msg.edit_text(formatted_message, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing night sky info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def create_night_sky_navigation_keyboard(user_id: int, current_date: date, user: User) -> InlineKeyboardMarkup:
    user_today = get_user_today(user)
    yesterday = current_date - timedelta(days=1)
    tomorrow = current_date + timedelta(days=1)

    if current_date == user_today:
        current_label = "today"
    elif current_date == user_today - timedelta(days=1):
        current_label = "yesterday"
    elif current_date == user_today + timedelta(days=1):
        current_label = "tomorrow"
    else:
        current_label = f"{current_date.strftime('%m/%d')}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="◀️ Prev",
                callback_data=f"nightsky_date:{user_id}:{yesterday.isoformat()}"
            ),
            InlineKeyboardButton(
                text=current_label,
                callback_data="nightsky_noop"
            ),
            InlineKeyboardButton(
                text="Next ▶️",
                callback_data=f"nightsky_date:{user_id}:{tomorrow.isoformat()}"
            )
        ],
        [
            InlineKeyboardButton(
                text="Today",
                callback_data=f"nightsky_date:{user_id}:{user_today.isoformat()}"
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"nightsky_date:{user_id}:{current_date.isoformat()}"
            )
        ]
    ])

    return keyboard

async def night_sky_date_callback(callback: CallbackQuery, user: User):
    try:
        parts = callback.data.split(':')
        if len(parts) != 3:
            await callback.answer("❌ Invalid callback data", show_alert=True)
            return

        callback_user_id = int(parts[1])
        target_date_str = parts[2]

        if callback_user_id != user.user_id:
            await callback.answer("❌ This button is not for you!", show_alert=True)
            return

        try:
            target_date = date.fromisoformat(target_date_str)
        except ValueError:
            await callback.answer("❌ Invalid date format", show_alert=True)
            return

        sky_data = await night_sky_service.get_night_sky_data(user, target_date)

        if not sky_data:
            await callback.answer("❌ Error calculating night sky information", show_alert=True)
            return

        keyboard = create_night_sky_navigation_keyboard(user.user_id, target_date, user)

        formatted_message = night_sky_service.format_night_sky_message(sky_data)

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
        logger.error(f"Error in night sky date callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

async def night_sky_noop_callback(callback: CallbackQuery):
    await callback.answer()

def register_night_sky_handlers(dp: Dispatcher):
    dp.message.register(cmd_night_sky, Command("sky"))
    dp.message.register(night_sky_button_handler, F.text == "🔭 Night Sky")
    dp.callback_query.register(night_sky_date_callback, F.data.startswith("nightsky_date:"))
    dp.callback_query.register(night_sky_noop_callback, F.data == "nightsky_noop")