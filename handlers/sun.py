import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import date, timedelta
from database.models import User
from services.sun_service import sun_service, get_user_today

logger = logging.getLogger(__name__)

async def cmd_sun(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view sun information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_sun_info(message, user, user_today)

async def sun_button_handler(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view sun information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_sun_info(message, user, user_today)

async def show_sun_info(message: Message, user: User, target_date: date):
    processing_msg = await message.answer("Calculating sun information...")

    try:
        sun_data = await sun_service.get_sun_times(user, target_date)

        if not sun_data:
            await processing_msg.edit_text(
                "❌ <b>Error calculating sun information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        keyboard = create_sun_navigation_keyboard(user.user_id, target_date, user)

        formatted_message = sun_service.format_sun_info_message(sun_data)

        await processing_msg.edit_text(formatted_message, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing sun info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def create_sun_navigation_keyboard(user_id: int, current_date: date, user: User) -> InlineKeyboardMarkup:
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
                callback_data=f"sun_date:{user_id}:{yesterday.isoformat()}"
            ),
            InlineKeyboardButton(
                text=current_label,
                callback_data="sun_noop"  # No operation
            ),
            InlineKeyboardButton(
                text="Next ▶️",
                callback_data=f"sun_date:{user_id}:{tomorrow.isoformat()}"
            )
        ],
        [
            InlineKeyboardButton(
                text="Today",
                callback_data=f"sun_date:{user_id}:{user_today.isoformat()}"
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"sun_date:{user_id}:{current_date.isoformat()}"
            )
        ]
    ])

    return keyboard

async def sun_date_callback(callback: CallbackQuery, user: User):
    try:
        # Parse callback data: sun_date:user_id:date
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

        sun_data = await sun_service.get_sun_times(user, target_date)

        if not sun_data:
            await callback.answer("❌ Error calculating sun information", show_alert=True)
            return

        keyboard = create_sun_navigation_keyboard(user.user_id, target_date, user)

        formatted_message = sun_service.format_sun_info_message(sun_data)

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
        logger.error(f"Error in sun date callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

async def sun_noop_callback(callback: CallbackQuery):
    await callback.answer()

def register_sun_handlers(dp: Dispatcher):
    dp.message.register(cmd_sun, Command("sun"))
    dp.message.register(sun_button_handler, F.text == "☀️ Sun")
    dp.callback_query.register(sun_date_callback, F.data.startswith("sun_date:"))
    dp.callback_query.register(sun_noop_callback, F.data == "sun_noop")