from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand
from keyboards.reply import main_menu_keyboard
from database.models import User

async def cmd_start(message: Message, user: User):
    user_name = html.bold(user.mention)
    text = f"""
👋 Hi, {user_name} !

📋 Use /help to see the commands

📅 You're with us since: {user.created_at.strftime('%d.%m.%Y')}
    """
    await message.answer(text.strip(), reply_markup=main_menu_keyboard())


async def cmd_help(message: Message):
    help_text = """
🆘 <b>Available commands:</b>

/start - Bot start
/help  - Show this menu
/location city - Register location

💬 You can also just write to me - I'll repeat everything!
    """
    await message.answer(help_text)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help"),
    ]
    await bot.set_my_commands(commands)

def register_start_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))