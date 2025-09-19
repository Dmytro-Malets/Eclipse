from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Location"), KeyboardButton(text="🔭 Astronomy")],
            [KeyboardButton(text="🌙 Moon Phase"), KeyboardButton(text="☀️ Sun")],
            [KeyboardButton(text="/help"), KeyboardButton(text="info")],
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def remove_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], remove_keyboard=True)