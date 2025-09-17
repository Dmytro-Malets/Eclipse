import logging
import sys
from logging.handlers import RotatingFileHandler

def configure_logging(prod: bool = False):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Common log format
    log_format = logging.Formatter(
        "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
    )

    if prod:
        # Production: File logging with rotation
        file_handler = RotatingFileHandler(
            filename="/var/log/bot/app.log",
            maxBytes=1024 * 1024 * 5,  # 5 MB
            backupCount=5
        )
        file_handler.setFormatter(log_format)
        file_handler.setLevel(logging.WARNING)  # Log only WARNING and above to file
        logger.addHandler(file_handler)

        # Also log to console for Docker
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
    else:
        # Local: Console logging only
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)