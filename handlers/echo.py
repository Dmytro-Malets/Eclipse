from aiogram import Dispatcher
from aiogram.types import Message
from database.models import User

async def echo_handler(message: Message, user: User):
    help_text = """
<b>Eclipse - Available Commands</b>

/start - Start the bot
/help - Show this message
/location <i>place</i> - Set your location
/moon - Moon information
/sun - Sun information
/sky - Visible planets & stars
/space - NASA Picture of the Day & NEO
/eclipse - Upcoming lunar & solar eclipses
/iss - ISS tracking & passes
/spaceweather - Space weather report
/rovers - Mars rover photo gallery
/perseverance - Perseverance rover photos
/curiosity - Curiosity rover photos
    """

    if not user.has_location:
        help_text += "\n<i>💡 Set your location to unlock most features</i>"

    await message.answer(help_text)

def register_echo_handlers(dp: Dispatcher):
    dp.message.register(echo_handler)