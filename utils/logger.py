# 📁 utils/logger.py

from loguru import logger
import os
import sys
from datetime import datetime

# ✅ Setup log directory
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

# ✅ Main log file: logs/yts-2025-06-12.log
LOG_FILE = os.path.join(LOG_DIR, f"yts-{datetime.now().strftime('%Y-%m-%d')}.log")
ERROR_FILE = os.path.join(LOG_DIR, f"errors-{datetime.now().strftime('%Y-%m-%d')}.log")

# ✅ Remove existing handlers first
logger.remove()

# ✅ Console output (colorful, minimal)
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    colorize=True
)

# ✅ Rotating file log (full details)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="1 day",
    retention="7 days",
    backtrace=True,
    diagnose=True,
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
)

# ✅ Separate error log
logger.add(
    ERROR_FILE,
    level="ERROR",
    rotation="1 day",
    retention="14 days",
    backtrace=True,
    diagnose=True,
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
)

# ✅ Optional: Hook uncaught exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("💥 Uncaught Exception")

sys.excepthook = handle_exception

# ✅ Example of contextual logger usage:
# custom_logger = logger.bind(module="downloader")
# custom_logger.info("Download started")
