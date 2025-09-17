import os
from services.customerror import  MissingEnvVariableError

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "sqlite+aiosqlite:///bot.db"

if not BOT_TOKEN:
    raise MissingEnvVariableError("BOT_TOKEN not set in .env file!")
