import os
from services.customerror import  MissingEnvVariableError

MODE = os.environ.get("MODE", "dev")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
REDIS_URL = os.environ.get("REDIS_URL")

if not BOT_TOKEN:
    raise MissingEnvVariableError("BOT_TOKEN not set in .env file!")
if not GOOGLE_API_KEY:
    raise MissingEnvVariableError("GOOGLE_API_KEY not set in .env file!")
if not OPENWEATHER_API_KEY:
    raise MissingEnvVariableError("OPENWEATHER_API_KEY not set in .env file!")
if not REDIS_URL:
    raise MissingEnvVariableError("REDIS_URL not set in .env file!")