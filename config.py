"""Bot configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "bot.db")
VIDEO_SIZE_LIMIT: int = int(os.getenv("VIDEO_SIZE_LIMIT", str(50 * 1024 * 1024)))
DOWNLOAD_WORKERS: int = int(os.getenv("DOWNLOAD_WORKERS", "8"))
CACHE_LIFETIME: int = int(os.getenv("CACHE_LIFETIME", "3600"))
THROTTLE_PER_MINUTE: int = int(os.getenv("THROTTLE_PER_MINUTE", "10"))
