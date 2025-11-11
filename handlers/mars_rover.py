import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from database.models import User
from services.mars_rover_service import mars_rover_service

logger = logging.getLogger(__name__)

async def cmd_rovers(message: Message, user: User = None):
    await show_rover_selection(message, user)

async def cmd_perseverance(message: Message, user: User = None):
    await show_specific_rover_photos(message, user, "perseverance")

async def cmd_curiosity(message: Message, user: User = None):
    await show_specific_rover_photos(message, user, "curiosity")

async def rovers_button_handler(message: Message, user: User = None):
    await show_rover_selection(message, user)

async def show_specific_rover_photos(message: Message, user: User, rover_name: str):
    try:
        await message.answer(f"Loading {rover_name.capitalize()} rover photos...")

        rover_data = await mars_rover_service.get_rover_latest_photos(rover_name, max_photos=10)

        if not rover_data or not rover_data.get('photos'):
            await message.answer(
                f"❌ <b>No photos available for {rover_name.title()}</b>\n\n"
                "The rover might not have taken photos recently.\n"
                "Please try again later."
            )
            return

        photos = rover_data['photos']
        user_tz = user.timezone if user and user.timezone else 'UTC'
        media_group = [
            InputMediaPhoto(
                media=photo['img_src'],
                caption=f"Date: {(date_tz := mars_rover_service.format_earth_date(photo['earth_date'], user_tz))[0]} {date_tz[1]}"
            )
            for photo in photos
        ]

        photos_sent = 0
        while photos_sent < len(media_group):
            batch = media_group[photos_sent:photos_sent + 10]
            await message.answer_media_group(batch)
            photos_sent += 10

        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Get New Photos",
                callback_data=f"mars_rover:{user.user_id if user else 0}:{rover_name}"
            )],
            [InlineKeyboardButton(
                text="⬅️ Choose Another Rover",
                callback_data=f"mars_back:{user.user_id if user else 0}"
            )]
        ])

        summary_message = mars_rover_service.format_rover_photos_message(rover_data)
        await message.answer(summary_message, reply_markup=back_keyboard)

    except Exception as e:
        logger.error(f"Error showing {rover_name} photos: {e}")
        await message.answer(
            f"❌ <b>Error loading {rover_name.title()} photos</b>\n\n"
            "Please try again later."
        )

async def show_rover_selection(message: Message, user: User = None):
    try:
        available_rovers = await mars_rover_service.get_available_rovers()

        if not available_rovers:
            await message.answer(
                "❌ <b>Mars rover data unavailable</b>\n\n"
                "NASA services may be temporarily unavailable.\n"
                "Please try again later."
            )
            return

        keyboard = create_rover_selection_keyboard(available_rovers, user)
        selection_message = mars_rover_service.format_rover_selection_message()

        await message.answer(selection_message, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing rover selection: {e}")
        await message.answer(
            "❌ <b>Error occurred</b>\n\n"
            "Failed to load Mars rover data.\n"
            "Please try again later."
        )

def create_rover_selection_keyboard(rovers: list, user: User = None) -> InlineKeyboardMarkup:
    buttons = []

    for rover in rovers:
        rover_name = rover['name'].lower()
        button_text = f"{rover['name']}"

        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"mars_rover:{user.user_id if user else 0}:{rover_name}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def mars_rover_callback(callback: CallbackQuery, user: User = None):
    try:
        parts = callback.data.split(':')
        if len(parts) != 3:
            await callback.answer("❌ Invalid callback data", show_alert=True)
            return

        callback_user_id = int(parts[1])
        rover_name = parts[2]

        if user and callback_user_id != user.user_id and callback_user_id != 0:
            await callback.answer("❌ This button is not for you!", show_alert=True)
            return

        await callback.answer(f"Loading {rover_name.capitalize()} rover photos...")

        rover_data = await mars_rover_service.get_rover_latest_photos(rover_name, max_photos=10)

        if not rover_data or not rover_data.get('photos'):
            await callback.message.answer(
                f"❌ <b>No photos available for {rover_name.title()}</b>\n\n"
                "The rover might not have taken photos recently.\n"
                "Please try again later or select another rover."
            )
            return

        photos = rover_data['photos']
        user_tz = user.timezone if user and user.timezone else 'UTC'
        media_group = [
            InputMediaPhoto(
                media=photo['img_src'],
                caption=f"Date: {(date_tz := mars_rover_service.format_earth_date(photo['earth_date'], user_tz))[0]} {date_tz[1]}"
            )
            for photo in photos
        ]

        photos_sent = 0
        while photos_sent < len(media_group):
            batch = media_group[photos_sent:photos_sent + 10]
            await callback.message.answer_media_group(batch)
            photos_sent += 10

        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Get New Photos",
                callback_data=f"mars_rover:{user.user_id if user else 0}:{rover_name}"
            )],
            [InlineKeyboardButton(
                text="⬅️ Back to Rover Selection",
                callback_data=f"mars_back:{user.user_id if user else 0}"
            )]
        ])

        summary_message = mars_rover_service.format_rover_photos_message(rover_data)

        await callback.message.answer(summary_message, reply_markup=back_keyboard)

    except Exception as e:
        logger.error(f"Error in mars rover callback: {e}")
        await callback.answer("❌ Error loading rover photos", show_alert=True)

async def mars_back_callback(callback: CallbackQuery, user: User = None):
    try:
        callback_user_id = int(callback.data.split(':')[1])

        if user and callback_user_id != user.user_id and callback_user_id != 0:
            await callback.answer("❌ This button is not for you!", show_alert=True)
            return

        available_rovers = await mars_rover_service.get_available_rovers()

        if not available_rovers:
            await callback.answer("❌ Unable to load rover data", show_alert=True)
            return

        keyboard = create_rover_selection_keyboard(available_rovers, user)
        selection_message = mars_rover_service.format_rover_selection_message()

        await callback.message.edit_text(selection_message, reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in mars back callback: {e}")
        await callback.answer("❌ Error occurred", show_alert=True)

def register_mars_handlers(dp: Dispatcher):
    dp.message.register(cmd_rovers, Command("rovers"))
    dp.message.register(cmd_perseverance, Command("perseverance"))
    dp.message.register(cmd_curiosity, Command("curiosity"))
    dp.message.register(rovers_button_handler, F.text == "📸 Mars Photos")
    dp.callback_query.register(mars_rover_callback, F.data.startswith("mars_rover:"))
    dp.callback_query.register(mars_back_callback, F.data.startswith("mars_back:"))