import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.models import User
from services.iss_service import iss_service
from services.redis_service import redis_service

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
        # Get old ISS messages if any
        old_messages = await redis_service.get_iss_messages(user.user_id, message.chat.id)

        # Delete old messages if they exist
        if old_messages:
            for msg_type, msg_id in [('location', old_messages['location_message_id']), ('text', old_messages['text_message_id'])]:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                    logger.info(f"🗑️ Deleted old ISS {msg_type} message {msg_id}")
                except Exception as e:
                    logger.warning(f"Could not delete old {msg_type} message: {e}")

        # Get fresh ISS data
        iss_data = await iss_service.get_iss_data(user)

        if not iss_data:
            await processing_msg.edit_text(
                "❌ <b>Error loading ISS information</b>\n\n"
                "Please try again later or check your location settings."
            )
            return

        await processing_msg.delete()

        # Create new location marker
        current_pos = iss_data.get('current_position')
        location_msg = None

        if current_pos:
            location_msg = await message.answer_location(
                latitude=current_pos['sat_latitude'],
                longitude=current_pos['sat_longitude'],
                live_period=600  # 10 minutes
            )

        # Create new text message
        keyboard = create_iss_keyboard(user.user_id)
        formatted_message = iss_service.format_iss_message(iss_data)
        text_msg = await message.answer(formatted_message, reply_markup=keyboard)

        # Store in Redis
        if location_msg:
            await redis_service.set_iss_messages(
                user_id=user.user_id,
                chat_id=message.chat.id,
                location_message_id=location_msg.message_id,
                text_message_id=text_msg.message_id
            )

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

        # Get stored messages from Redis
        stored_messages = await redis_service.get_iss_messages(user.user_id, callback.message.chat.id)

        if not stored_messages:
            await callback.answer("❌ Data not found. Please use /iss again", show_alert=True)
            return

        # Check if this is the correct text message
        if stored_messages['text_message_id'] != callback.message.message_id:
            await callback.answer("❌ This is an old message. Please use /iss for fresh data", show_alert=True)
            return

        # Get fresh ISS data
        iss_data = await iss_service.get_iss_data(user)

        if not iss_data:
            await callback.answer("❌ Unable to refresh data", show_alert=True)
            return

        current_pos = iss_data.get('current_position')
        location_msg_id = stored_messages['location_message_id']

        # Update or recreate live location
        if current_pos and location_msg_id:
            try:
                # Try to update existing live location
                await callback.message.bot.edit_message_live_location(
                    chat_id=callback.message.chat.id,
                    message_id=location_msg_id,
                    latitude=current_pos['sat_latitude'],
                    longitude=current_pos['sat_longitude']
                )

                # Update text message
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
                error_msg = str(e).lower()

                # If live period expired - recreate both messages
                if any(x in error_msg for x in ["message to edit not found", "message can't be edited", "live period", "bad request"]):
                    logger.warning(f"🗑️ Live location expired, recreating both messages")

                    # Delete both old messages
                    for msg_id in [location_msg_id, callback.message.message_id]:
                        try:
                            await callback.message.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
                        except Exception as del_error:
                            logger.warning(f"Could not delete message {msg_id}: {del_error}")

                    # Create new location marker
                    new_location_msg = await callback.message.bot.send_location(
                        chat_id=callback.message.chat.id,
                        latitude=current_pos['sat_latitude'],
                        longitude=current_pos['sat_longitude'],
                        live_period=600  # 10 minutes
                    )

                    # Create new text message
                    keyboard = create_iss_keyboard(user.user_id)
                    formatted_message = iss_service.format_iss_message(iss_data)

                    new_text_msg = await callback.message.bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=formatted_message,
                        reply_markup=keyboard
                    )

                    # Update Redis with new message IDs
                    await redis_service.set_iss_messages(
                        user_id=user.user_id,
                        chat_id=callback.message.chat.id,
                        location_message_id=new_location_msg.message_id,
                        text_message_id=new_text_msg.message_id
                    )

                else:
                    logger.error(f"❌ Unexpected error updating location: {e}")
                    await callback.answer("❌ Error updating location", show_alert=True)
                    return

    except Exception as e:
        logger.error(f"Error in ISS refresh callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

def register_iss_handlers(dp: Dispatcher):
    dp.message.register(cmd_iss, Command("iss"))
    dp.message.register(iss_button_handler, F.text == "🛰 ISS")
    dp.callback_query.register(iss_refresh_callback, F.data.startswith("iss_refresh:"))