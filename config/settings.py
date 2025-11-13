import os
from services.customerror import MissingEnvVariableError

IS_PROD = True

def get_env_var(key, default=None):
    if not IS_PROD:
        from os import getenv
        from dotenv import load_dotenv
        load_dotenv()
        return getenv(key, default)
    return os.environ.get(key, default)

BOT_TOKEN = get_env_var("BOT_TOKEN")
GOOGLE_API_KEY = get_env_var("GOOGLE_API_KEY")
NASA_API_KEY = get_env_var("NASA_API_KEY", "DEMO_KEY")
N2YO_API_KEY = get_env_var("N2YO_API_KEY")
WEATHER_API_KEY = get_env_var("WEATHER_API_KEY")
DATABASE_URL = get_env_var("DATABASE_URL") if IS_PROD else "sqlite+aiosqlite:///bot.db"
REDIS_URL = get_env_var("REDIS_URL") if IS_PROD else "redis://127.0.0.1:6379/0"

for env_key, value in {
    "BOT_TOKEN": BOT_TOKEN,
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "NASA_API_KEY": NASA_API_KEY,
    "N2YO_API_KEY": N2YO_API_KEY,
    "WEATHER_API_KEY": WEATHER_API_KEY
}.items():
    if not value:
        raise MissingEnvVariableError(f"{env_key} not set in environment file!")