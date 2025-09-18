from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from typing import Dict, Any
import logging, random
from database.models import User
from services.location_service import location_service, decimal_to_dms, format_utc_offset
from services.user_service import update_user_location
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

def get_location_prompt() -> str:

    cities = [
        "London", "New York", "Kyiv", "Tokyo", "Paris",
        "Berlin", "Madrid", "Rome", "Melbourne", "Toronto",
        "Sydney", "Beijing", "Seoul", "Bangkok", "Dubai",
        "Singapore", "Amsterdam", "Lisbon", "Prague", "Vienna",
        "Warsaw", "Istanbul", "Los Angeles", "Chicago", "Mumbai",
        "Delhi", "Hong Kong", "Barcelona", "Budapest", "Copenhagen"
    ]

    example_city = random.choice(cities)
    return (
        "<b>Reply to this message with your location name:</b>\n\n"
        f"<b>Example:</b> <code>{example_city}</code>\n\n"
        "<i>Use English names for best results</i>"
    )

async def cmd_location(message: Message, user: User):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "❌ Please specify a location!\n\n"
            "<b>Example:</b> <code>/location Miami</code>\n\n"
            "<i>You can also use the \"📍Location button\"</i>"
        )
        return

    location_name = args[1]
    await process_location_registration(message, user, location_name)

async def location_button_handler(message: Message):
    await message.answer(get_location_prompt())

async def location_reply_handler(message: Message, user: User):
    if (message.reply_to_message and
            message.reply_to_message.from_user.is_bot and
            message.reply_to_message.text and
            "Reply to this message with your location name" in message.reply_to_message.text):
        location_name = message.text.strip()
        await process_location_registration(message, user, location_name)

async def process_location_registration(message: Message, user: User, location_name: str):
    processing_msg = await message.answer("Searching for location...")
    try:
        location_data = await location_service.process_location(location_name)

        if not location_data:
            error_and_prompt = (
                f"❌ <b>Location not found: '{location_name}'</b>\n\n"
                "Please check spelling and try again\n\n"
                "<b>Tips:</b>\n"
                "▫️ Use English names\n"
                "▫️ Check for typos\n\n"
                "💡 <i>Try searching for a larger nearby city</i>\n\n"
                "───────────────────────\n\n" +
                get_location_prompt()
            )
            await processing_msg.edit_text(error_and_prompt)
            return

        await message.answer_location(latitude=location_data['latitude'], longitude=location_data['longitude'])

        await processing_msg.delete()

        confirmation_text = format_location_confirmation(location_data)

        callback_data = f"loc_confirm:{user.user_id}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=callback_data),
                InlineKeyboardButton(text="❌ Enter Different Location", callback_data="loc_different")
            ]
        ])

        await message.answer(text=confirmation_text, reply_markup=keyboard)

        # Store in Redis for 5 minutes
        await redis_service.set_temp_location(user.user_id, location_data, expire_seconds=600)

    except Exception as e:
        logger.error(f"Error processing location registration: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error processing location</b>\n\n"
            "Please try again later or contact support\n\n"
            "───────────────────────\n\n" +
            get_location_prompt()
        )

def format_location_confirmation(location_data: Dict[str, Any]) -> str:
    time_info = location_data['current_time']

    # Convert coordinates to user-friendly format
    lat_dms = decimal_to_dms(location_data['latitude'], False)
    lng_dms = decimal_to_dms(location_data['longitude'], True)

    # Format GMT offset
    gmt_offset = format_utc_offset(time_info['utc_offset'])

    return f"""📍 <b>{location_data['name']}</b>
🌍 {location_data['full_name']}

<b>Coordinates:</b>
{lat_dms}, {lng_dms}
({location_data['latitude']:.4f}, {location_data['longitude']:.4f})

🌐 <b>Current Time:</b> {time_info['time']} on {time_info['date']} ({gmt_offset})

<i>Please confirm if this is your correct location:</i>""".strip()

async def location_confirm_callback(callback: CallbackQuery, user: User):
    try:
        callback_user_id = int(callback.data.split(':')[1])

        if callback_user_id != user.user_id:
            await callback.answer("❌ This confirmation is not for you!", show_alert=True)
            return

        # Get from Redis
        location_data = await redis_service.get_temp_location(user.user_id)

        if not location_data:
            await callback.message.edit_text(
                "⌛️ <b>Location data expired</b>\n\n" + get_location_prompt(),
                reply_markup=None
            )
            await callback.answer("Please enter your location again", show_alert=True)
            return

        # Save to database
        updated_user = await update_user_location(user, location_data)

        # Clean up Redis
        await redis_service.delete_temp_location(user.user_id)

        await callback.message.edit_text(
            f"✅ <b>Location Successfully Registered!</b>\n\n"
            f"<b>Location:</b> {updated_user.city}\n\n"
            f"🔄 <i>To change your location, use /location command again</i>"
        )

        await callback.answer("✅ Location confirmed and saved!")

    except Exception as e:
        logger.error(f"Error confirming location: {e}")
        await callback.message.edit_text("❌ <b>Error occurred</b>\n\n" + get_location_prompt(), reply_markup=None)
        await callback.answer("❌ Error occurred, please try again", show_alert=True)

async def location_different_callback(callback: CallbackQuery):
    await callback.message.edit_text(get_location_prompt())
    await callback.answer()

def register_location_handlers(dp: Dispatcher):
    dp.message.register(cmd_location, Command("location"))
    dp.message.register(location_button_handler, F.text == "📍 Location")
    dp.message.register(location_reply_handler, F.reply_to_message)
    dp.callback_query.register(location_confirm_callback, F.data.startswith("loc_confirm:"))
    dp.callback_query.register(location_different_callback, F.data == "loc_different")