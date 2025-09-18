import asyncio, logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config.settings import BOT_TOKEN, MODE
from config.logging_config import configure_logging
from database.database import check_connection
from handlers import register_all_handlers, set_commands
from middlewares.user_middleware import setup_middlewares
from services.redis_service import redis_service

async def startup() -> bool:
    if not await check_connection(): return False
    if not await redis_service.connect(): return False
    return True

async def main():

    prod = MODE.lower() == 'prod'
    configure_logging(prod)

    logger = logging.getLogger(__name__)

    if not await startup():
        logger.error("❌ Failed to initialize services")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    setup_middlewares(dp)
    register_all_handlers(dp)
    await set_commands(bot)

    # Start polling
    try:
        logger.info("🚀 Bot is starting...")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    finally:
        logger.info("🔄 Shutting down...")
        await bot.session.close()
        await redis_service.disconnect()


if __name__ == "__main__":
    asyncio.run(main())