import logging, re
from datetime import datetime
from typing import Optional
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, \
    InputMediaPhoto
from datetime import date, timedelta
from database.models import User
from services.moon_service import moon_service, get_user_today
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

async def cmd_moon(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view moon information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_moon_info(message, user, user_today)

async def moon_button_handler(message: Message, user: User):
    if not user.has_location:
        await message.answer(
            "❌ <b>Location not registered!</b>\n\n"
            "To view moon information, please register your location first.\n\n"
            "Use /location command or press the 📍Location button"
        )
        return

    user_today = get_user_today(user)
    await show_moon_info(message, user, user_today)

async def show_moon_info(message: Message, user: User, target_date: date):
    processing_msg = await message.answer("Calculating moon information...")

    try:
        # Clear any existing moon message records for this user/chat
        await redis_service.delete_moon_photo_message(user.user_id, message.chat.id)

        moon_data = await moon_service.get_moon_data(user, target_date)

        if not moon_data:
            await processing_msg.edit_text(
                "❌ <b>Error calculating moon information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        await processing_msg.delete()

        moon_image = moon_data.get('moon_image')
        photo_message = None

        if moon_image:
            try:
                photo = BufferedInputFile(
                    moon_image.getvalue(),
                    filename=f"moon_phase_{target_date.isoformat()}.png"
                )

                phase_info = moon_data['moon_phase']
                caption = f"<b>{phase_info['phase_name']}</b>"

                photo_message = await message.answer_photo(photo=photo, caption=caption)
                moon_image.close()

            except Exception as e:
                logger.error(f"Error sending moon image: {e}")
                # Continue with text message even if image fails

        keyboard = create_moon_navigation_keyboard(user.user_id, target_date, user)

        formatted_message = moon_service.format_moon_info_message(moon_data)

        text_message = await message.answer(formatted_message, reply_markup=keyboard)

        # Store message IDs in Redis
        if photo_message:
            await redis_service.set_moon_photo_message(
                user.user_id,
                message.chat.id,
                photo_message.message_id,
                text_message.message_id
            )

    except Exception as e:
        logger.error(f"Error showing moon info for user {user.user_id}: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Please try again later."
        )

def create_moon_navigation_keyboard(user_id: int, current_date: date, user: User) -> InlineKeyboardMarkup:
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
                callback_data=f"moon_date:{user_id}:{yesterday.isoformat()}"
            ),
            InlineKeyboardButton(
                text=current_label,
                callback_data="moon_noop"  # No operation
            ),
            InlineKeyboardButton(
                text="Next ▶️",
                callback_data=f"moon_date:{user_id}:{tomorrow.isoformat()}"
            )
        ],
        [
            InlineKeyboardButton(
                text="Today",
                callback_data=f"moon_date:{user_id}:{user_today.isoformat()}"
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=f"moon_refresh:{user_id}:{current_date.isoformat()}"
            )
        ]
    ])

    return keyboard

async def moon_date_callback(callback: CallbackQuery, user: User):
    try:
        # Parse callback data: moon_date:user_id:date
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

        current_date = _extract_current_date_from_message(callback.message.text)

        # If trying to navigate to the same date, treat as refresh
        if current_date and current_date == target_date:
            await _update_moon_info(callback, user, target_date, update_photo=False)
            await callback.answer("Already showing this date")
        else:
            await _update_moon_info(callback, user, target_date, update_photo=True)
            await callback.answer()

    except Exception as e:
        logger.error(f"Error in moon date callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

async def moon_refresh_callback(callback: CallbackQuery, user: User):
    try:
        # Parse callback data: moon_refresh:user_id:date
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

        await _update_moon_info(callback, user, target_date, update_photo=False)
        await callback.answer("🔄 Data refreshed")

    except Exception as e:
        logger.error(f"Error in moon refresh callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

async def _update_moon_info(callback: CallbackQuery, user: User, target_date: date, update_photo: bool = True):
    try:
        moon_data = await moon_service.get_moon_data(user, target_date)

        if not moon_data:
            await callback.answer("❌ Error calculating moon information", show_alert=True)
            return

        # Update photo if requested and if we have stored message IDs
        if update_photo:
            moon_image = moon_data.get('moon_image')
            if moon_image:
                try:
                    # Get stored message IDs
                    stored_messages = await redis_service.get_moon_photo_message(user.user_id, callback.message.chat.id)

                    if stored_messages:
                        photo = BufferedInputFile(
                            moon_image.getvalue(),
                            filename=f"moon_phase_{target_date.isoformat()}.png"
                        )

                        phase_info = moon_data['moon_phase']
                        caption = f"<b>{phase_info['phase_name']}</b>"

                        # Try to edit existing photo
                        await callback.bot.edit_message_media(
                            chat_id=callback.message.chat.id,
                            message_id=stored_messages['photo_message_id'],
                            media=InputMediaPhoto(media=photo, caption=caption)
                        )

                        moon_image.close()

                except Exception as e:
                    logger.error(f"Error updating moon image: {e}")

                    # If it's "message is not modified" error, don't send new photo
                    if "message is not modified" in str(e).lower():
                        logger.info("Photo is identical, skipping update")
                        if moon_image:
                            moon_image.close()
                    else:
                        # If editing fails for other reasons, send new photo and update Redis
                        try:
                            if moon_image:
                                photo = BufferedInputFile(
                                    moon_image.getvalue(),
                                    filename=f"moon_phase_{target_date.isoformat()}.png"
                                )

                                phase_info = moon_data['moon_phase']
                                caption = f"<b>{phase_info['phase_name']}</b>"

                                new_photo_message = await callback.message.answer_photo(photo=photo, caption=caption)

                                # Update Redis with new message ID
                                await redis_service.set_moon_photo_message(
                                    user.user_id,
                                    callback.message.chat.id,
                                    new_photo_message.message_id,
                                    callback.message.message_id
                                )

                                moon_image.close()
                        except Exception as send_error:
                            logger.error(f"Error sending new moon image: {send_error}")

        # Update the text message
        keyboard = create_moon_navigation_keyboard(user.user_id, target_date, user)
        formatted_message = moon_service.format_moon_info_message(moon_data)

        try:
            await callback.message.edit_text(formatted_message, reply_markup=keyboard)
            if not update_photo:  # Only answer callback if it's not a date change
                await callback.answer()
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await callback.answer()
            else:
                logger.error(f"Error editing message: {edit_error}")
                await callback.answer("❌ Error updating", show_alert=True)

    except Exception as e:
        logger.error(f"Error updating moon info: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

async def moon_noop_callback(callback: CallbackQuery):
    await callback.answer()

def _extract_current_date_from_message(message_text: str) -> Optional[date]:
    try:
        if not message_text:
            return None

        # Extract year, month, day
        date_pattern = r'(\w+day),\s+(\w+)\s+(\d{1,2}),\s+(\d{4})'
        match = re.search(date_pattern, message_text)

        if match:
            month_name = match.group(2)
            day = int(match.group(3))
            year = int(match.group(4))

            # Parse month name to number
            date_str = f"{month_name} {day}, {year}"
            parsed_date = datetime.strptime(date_str, "%B %d, %Y").date()
            return parsed_date

        return None

    except Exception as e:
        logger.error(f"Error extracting date from message: {e}")
        return None

def register_moon_handlers(dp: Dispatcher):
    dp.message.register(cmd_moon, Command("moon"))
    dp.message.register(moon_button_handler, F.text == "🌙 Moon")
    dp.callback_query.register(moon_date_callback, F.data.startswith("moon_date:"))
    dp.callback_query.register(moon_refresh_callback, F.data.startswith("moon_refresh:"))
    dp.callback_query.register(moon_noop_callback, F.data == "moon_noop")