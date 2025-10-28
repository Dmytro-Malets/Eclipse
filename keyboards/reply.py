from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Location"), KeyboardButton(text="🛰 ISS")],
            [KeyboardButton(text="🌙 Moon"), KeyboardButton(text="☀️ Sun")],
            [KeyboardButton(text="🔭 Night Sky"), KeyboardButton(text="📸 Mars Photos")],
            [KeyboardButton(text="⚡ Space Weather"), KeyboardButton(text="🌑 Eclipses")]
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def remove_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], remove_keyboard=True)