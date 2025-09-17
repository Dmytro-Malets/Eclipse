from aiogram import Dispatcher
from aiogram.types import Message

async def echo_handler(message: Message):
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer(
            "🤖 I received your message!\n"
            "💬 Type /help to see commands"
        )

def register_echo_handlers(dp: Dispatcher):
    dp.message.register(echo_handler)