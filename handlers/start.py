from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand
from keyboards.reply import main_menu_keyboard
from database.models import User

async def cmd_start(message: Message, user: User):
    user_name = html.bold(user.mention)
    text = f"""
Welcome, {user_name}

<b>Eclipse</b> - your personal astronomy assistant

<b>Features:</b>
🌙 Moon phases & position
☀️ Sun times & UV index
🔭 Night sky objects
🪐 NASA space news
📸 Mars rover photos

<b>Quick Start:</b>
/help - Show available commands
/location <i>place</i> - Set your location
    """

    if not user.has_location:
        text += "\n<i>💡 Set your location to unlock most features</i>"

    await message.answer(text.strip(), reply_markup=main_menu_keyboard())

async def cmd_help(message: Message, user: User):
    help_text = """
<b>Eclipse - Available Commands</b>

/start - Start the bot
/help - Show this message
/location <i>place</i> - Set your location
/moon - Moon information
/sun - Sun information
/sky - Visible planets & stars
/space - NASA Picture of the Day & NEO
/eclipse - Upcoming lunar eclipses
/rovers - Mars rover photo gallery
/perseverance - Perseverance rover photos
/curiosity - Curiosity rover photos
    """

    if not user.has_location:
        help_text += "\n<i>💡 Set your location to unlock most features</i>"

    await message.answer(help_text)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show available commands"),
        BotCommand(command="location", description="Set your location")
    ]
    await bot.set_my_commands(commands)

def register_start_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))