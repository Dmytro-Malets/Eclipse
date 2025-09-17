from aiogram import Dispatcher
import logging
from .echo import register_echo_handlers

logger = logging.getLogger(__name__)

def register_all_handlers(dp: Dispatcher):
    register_echo_handlers(dp) # echo_handler is always last!
    logger.info("✅ All handlers are registered")