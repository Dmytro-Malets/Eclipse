import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from database.models import User
from services.space_service import space_service

logger = logging.getLogger(__name__)

async def cmd_space(message: Message, user: User = None):
    await show_space_data(message, user)

async def space_button_handler(message: Message, user: User = None):
    await show_space_data(message, user)

async def show_space_data(message: Message, user: User = None):
    processing_msg = await message.answer("🪐 Loading space data...")

    try:
        space_data = await space_service.get_space_data(user)

        if not space_data:
            await processing_msg.edit_text(
                "❌ <b>Unable to load space data</b>\n\n"
                "NASA services may be temporarily unavailable.\n"
                "Please try again later."
            )
            return

        # Delete processing message
        await processing_msg.delete()

        # Get APOD data for image preview
        apod_data = None
        for item in space_data:
            if item['type'] == 'apod':
                apod_data = item['data']
                break

        formatted_message = space_service.format_space_message(space_data, user)
        keyboard = create_space_keyboard(user)

        is_image = apod_data and apod_data.get('media_type') == 'image'
        is_video = apod_data and apod_data.get('media_type') == 'video'
        media_url = None

        if is_image:
            media_url = apod_data.get('url')
        elif is_video and apod_data.get('thumbnail_url'):
            media_url = apod_data.get('thumbnail_url')

        if media_url:
            try:
                await message.answer_photo(photo=media_url, caption=formatted_message, reply_markup=keyboard)
            except Exception as photo_error:
                logger.warning(f"Failed to send photo, sending text only: {photo_error}")
                await message.answer(formatted_message, reply_markup=keyboard, disable_web_page_preview=False)
        else:
            await message.answer(formatted_message, reply_markup=keyboard, disable_web_page_preview=False)

    except Exception as e:
        logger.error(f"Error showing space data: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error occurred</b>\n\n"
            "Failed to retrieve space data.\n"
            "Please try again later."
        )

def create_space_keyboard(user: User = None) -> InlineKeyboardMarkup:
    buttons = []

    buttons.append([
        InlineKeyboardButton(
            text="🔄 Refresh Data",
            callback_data=f"astro_refresh:{user.user_id if user else 0}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def space_refresh_callback(callback: CallbackQuery, user: User = None):
    try:
        callback_user_id = int(callback.data.split(':')[1])

        if user and callback_user_id != user.user_id and callback_user_id != 0:
            await callback.answer("❌ This button is not for you!", show_alert=True)
            return

        await callback.answer("🔄 Refreshing data...")

        space_data = await space_service.get_space_data(user)

        if not space_data:
            await callback.answer("❌ Unable to refresh data", show_alert=True)
            return

        # Get APOD data for image preview
        apod_data = None
        for item in space_data:
            if item['type'] == 'apod':
                apod_data = item['data']
                break

        formatted_message = space_service.format_space_message(space_data, user)
        keyboard = create_space_keyboard(user)

        try:
            is_new_image = apod_data and apod_data.get('media_type') == 'image'
            is_new_video = apod_data and apod_data.get('media_type') == 'video'
            new_media_url = None

            if is_new_image:
                new_media_url = apod_data['url']
            elif is_new_video and apod_data.get('thumbnail_url'):
                new_media_url = apod_data['thumbnail_url']

            has_old_photo = bool(callback.message.photo)

            if has_old_photo and new_media_url:
                await callback.message.edit_media(
                    media=InputMediaPhoto(media=new_media_url, caption=formatted_message),
                    reply_markup=keyboard
                )
            elif has_old_photo and not new_media_url:
                chat_id = callback.message.chat.id
                await callback.message.delete()
                await callback.bot.send_message(chat_id=chat_id, text=formatted_message, reply_markup=keyboard, disable_web_page_preview=False)
            elif not has_old_photo and new_media_url:
                chat_id = callback.message.chat.id
                await callback.message.delete()
                await callback.bot.send_photo(chat_id=chat_id, photo=new_media_url, caption=formatted_message, reply_markup=keyboard)
            else:
                await callback.message.edit_text(text=formatted_message, reply_markup=keyboard, disable_web_page_preview=False)

        except Exception as e:
            if "message is not modified" in str(e).lower():
                await callback.answer()
            else:
                logger.error(f"Error updating message: {e}")
                await callback.answer("❌ Error updating message", show_alert=True)

    except Exception as e:
        logger.error(f"Error in space refresh callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

def register_space_handlers(dp: Dispatcher):
    dp.message.register(cmd_space, Command("space"))
    dp.message.register(space_button_handler, F.text == "🪐 Space Today")
    dp.callback_query.register(space_refresh_callback, F.data.startswith("astro_refresh:"))