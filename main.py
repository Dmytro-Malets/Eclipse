import asyncio, logging, os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import BOT_TOKEN
from config.logging_config import configure_logging
from database.database import check_connection
from handlers import register_all_handlers
from middlewares.user_middleware import setup_middlewares


async def main():

    prod = os.environ.get("MODE", 'dev').lower() == 'prod'
    configure_logging(prod)

    logger = logging.getLogger(__name__)

    if not await check_connection(): return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    setup_middlewares(dp)
    register_all_handlers(dp)

    # Start polling
    try:
        logger.info("🚀 Bot is starting...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())