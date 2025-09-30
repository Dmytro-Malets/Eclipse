from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Location"), KeyboardButton(text="🪐 Space Today")],
            [KeyboardButton(text="🌙 Moon"), KeyboardButton(text="☀️ Sun")],
            [KeyboardButton(text="/help"), KeyboardButton(text="📸 Mars Photos")],
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def remove_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], remove_keyboard=True)