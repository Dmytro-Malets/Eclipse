from aiogram import Dispatcher
import logging
from .start import register_start_handlers, set_commands
from .location import register_location_handlers
from .sun import register_sun_handlers
from .moon import register_moon_handlers
from .astronomy import register_astronomy_handlers
from .mars_rover import register_mars_handlers
from .echo import register_echo_handlers

logger = logging.getLogger(__name__)

def register_all_handlers(dp: Dispatcher):
    register_start_handlers(dp)
    register_location_handlers(dp)
    register_sun_handlers(dp)
    register_moon_handlers(dp)
    register_astronomy_handlers(dp)
    register_mars_handlers(dp)
    register_echo_handlers(dp) # echo_handler is always last!
    logger.info("✅ All handlers are registered")