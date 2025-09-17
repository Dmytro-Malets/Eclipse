import os
from services.customerror import  MissingEnvVariableError

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not BOT_TOKEN:
    raise MissingEnvVariableError("BOT_TOKEN not set in .env file!")
